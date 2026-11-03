"""Classical session-key establishment model.

Models the overhead and availability of classical authenticated key establishment
over an RF link.  This is a *protocol engineering* model, not a cryptographic
implementation: it accounts for handshake timing, authentication assumptions,
session lifetime, and AES-256-GCM encryption overhead, but performs no actual
cryptographic operations.

Protocol
--------
1. The satellite and ground station share a long-term authentication credential
   (pre-shared key or public-key certificate — configured via ``auth_method``).
2. An ephemeral key agreement (conceptual ECDH P-256 or X25519) is performed
   over the RF link at the start of each session.
3. The resulting session key is used for AES-256-GCM authenticated encryption
   for the rest of the contact window.
4. A new session is initiated if the previous one expires or the link drops.

Assumptions and limitations
----------------------------
- No forward secrecy model beyond per-session keys.
- Authentication relies on the long-term credential; compromise of that
  credential invalidates all sessions.
- Handshake round-trip uses one-way propagation delay at the satellite range.
- AES-256-GCM overhead is per-packet (nonce + tag).
- No modelling of key escrow, certificate revocation, or multi-party trust.
- Classical cryptography is a legitimate security baseline; this model does not
  fabricate weaknesses to favour a QKD comparison.

References
----------
NIST SP 800-56A Rev 3 — Recommendation for Pair-Wise Key-Establishment Schemes
  using Discrete Logarithm Cryptography.
NIST SP 800-38D — Recommendation for Block Cipher Modes of Operation: GCM and GMAC.
"""
from dataclasses import dataclass
import math


_SPEED_OF_LIGHT = 299_792_458.0  # m/s


@dataclass
class ClassicalSessionConfig:
    """Parameters for the classical session-key establishment model."""

    # Key material
    session_key_bits: int = 256            # AES-256
    ecdh_curve: str = 'P-256'              # conceptual key-agreement curve
    auth_method: str = 'psk'               # 'psk' | 'certificate'

    # AES-256-GCM overhead per packet
    nonce_bits: int = 96                   # 12 bytes; NIST recommended
    tag_bits: int = 128                    # 16 bytes; full authentication tag
    aad_bits: int = 128                    # additional authenticated data (header)
    packet_payload_bits: int = 8192        # 1 KiB nominal payload per packet

    # Session lifecycle
    session_lifetime_s: float = 3600.0     # re-key after this interval
    handshake_messages: int = 4            # 2-RTT (4 one-way messages)
    max_retries: int = 3                   # before declaring establishment failure

    # Link dependency
    min_snr_db_for_handshake: float = 3.0  # minimum RF SNR for handshake success

    def validate(self):
        if self.session_key_bits not in (128, 192, 256):
            raise ValueError("session_key_bits must be 128, 192, or 256")
        if self.session_lifetime_s <= 0:
            raise ValueError("session_lifetime_s must be positive")
        if self.max_retries < 1:
            raise ValueError("max_retries must be at least 1")
        if self.packet_payload_bits <= 0:
            raise ValueError("packet_payload_bits must be positive")
        return self


def _handshake_duration_s(range_m: float, cfg: ClassicalSessionConfig) -> float:
    """Total handshake duration including propagation delay for all messages."""
    one_way_delay_s = range_m / _SPEED_OF_LIGHT
    return cfg.handshake_messages * one_way_delay_s


def _overhead_fraction(cfg: ClassicalSessionConfig) -> float:
    """Fraction of bits in each packet consumed by encryption overhead (nonce + tag + AAD)."""
    overhead = cfg.nonce_bits + cfg.tag_bits + cfg.aad_bits
    total = cfg.packet_payload_bits + overhead
    return overhead / total


def classical_key_establishment(
    link_available: bool,
    snr_db: float,
    range_m: float,
    contact_duration_s: float,
    cfg: ClassicalSessionConfig,
) -> dict:
    """Compute classical session-key establishment outcome for one contact window.

    Parameters
    ----------
    link_available : bool
        Whether the RF link is above the SNR threshold for data transfer.
    snr_db : float
        Current RF signal-to-noise ratio, dB.
    range_m : float
        Slant range, metres.  Used to compute propagation delay.
    contact_duration_s : float
        Duration of the contact window, seconds.
    cfg : ClassicalSessionConfig
        Protocol and key parameters.

    Returns
    -------
    dict with keys:
        channel_id               : 'classical_session'
        key_established          : bool
        failure_reason           : str or None
        session_key_bits         : int  (0 if not established)
        auth_method              : str
        encryption_profile       : str  (e.g. 'AES-256-GCM')
        handshake_duration_s     : float
        sessions_possible        : int  (how many session lifetimes fit in window)
        overhead_fraction        : float  (encryption overhead per packet)
        usable_payload_fraction  : float  (1 - overhead_fraction)
        effective_lifetime_s     : float  (min of session_lifetime_s and contact_duration_s)
        model_id                 : 'classical_ecdh_aes256gcm'
        security_note            : str  (explicit assumption statement)
    """
    cfg.validate()
    if range_m <= 0:
        raise ValueError("range_m must be positive")
    if contact_duration_s < 0:
        raise ValueError("contact_duration_s must be nonnegative")

    handshake_s = _handshake_duration_s(range_m, cfg)
    overhead_frac = _overhead_fraction(cfg)
    usable_frac = 1.0 - overhead_frac
    effective_lifetime = min(cfg.session_lifetime_s, contact_duration_s)
    sessions_possible = math.floor(contact_duration_s / cfg.session_lifetime_s) if cfg.session_lifetime_s > 0 else 0

    if not link_available:
        return _failure(
            cfg, handshake_s, overhead_frac, usable_frac, effective_lifetime,
            sessions_possible,
            "RF link unavailable — SNR below reception threshold",
        )

    if snr_db < cfg.min_snr_db_for_handshake:
        return _failure(
            cfg, handshake_s, overhead_frac, usable_frac, effective_lifetime,
            sessions_possible,
            f"RF SNR {snr_db:.1f} dB below handshake minimum {cfg.min_snr_db_for_handshake:.1f} dB",
        )

    if contact_duration_s < handshake_s * cfg.max_retries:
        return _failure(
            cfg, handshake_s, overhead_frac, usable_frac, effective_lifetime,
            sessions_possible,
            f"Contact window {contact_duration_s:.1f} s too short for handshake "
            f"({handshake_s:.3f} s × {cfg.max_retries} retries)",
        )

    return {
        "channel_id": "classical_session",
        "key_established": True,
        "failure_reason": None,
        "session_key_bits": cfg.session_key_bits,
        "auth_method": cfg.auth_method,
        "encryption_profile": f"AES-{cfg.session_key_bits}-GCM",
        "handshake_duration_s": handshake_s,
        "sessions_possible": max(1, sessions_possible),
        "overhead_fraction": overhead_frac,
        "usable_payload_fraction": usable_frac,
        "effective_lifetime_s": effective_lifetime,
        "model_id": "classical_ecdh_aes256gcm",
        "security_note": (
            "Key establishment assumed secure under chosen-ciphertext hardness of "
            f"{cfg.ecdh_curve} and AES-256.  "
            f"Authentication via {cfg.auth_method}: "
            "session security depends on credential integrity. "
            "Classical cryptography is a legitimate security baseline."
        ),
    }


def _failure(cfg, handshake_s, overhead_frac, usable_frac, effective_lifetime,
             sessions_possible, reason):
    return {
        "channel_id": "classical_session",
        "key_established": False,
        "failure_reason": reason,
        "session_key_bits": 0,
        "auth_method": cfg.auth_method,
        "encryption_profile": f"AES-{cfg.session_key_bits}-GCM",
        "handshake_duration_s": handshake_s,
        "sessions_possible": sessions_possible,
        "overhead_fraction": overhead_frac,
        "usable_payload_fraction": usable_frac,
        "effective_lifetime_s": effective_lifetime,
        "model_id": "classical_ecdh_aes256gcm",
        "security_note": (
            "Session not established.  "
            "Classical key establishment is a legitimate security baseline when "
            "the link is available and credentials are uncompromised."
        ),
    }

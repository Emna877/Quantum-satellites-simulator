"""Classical session-key establishment model (pre-quantum and post-quantum).

Models the overhead and availability of classical authenticated key establishment
over an RF link.  This is a *protocol engineering* model, not a cryptographic
implementation: it accounts for handshake message sizes and timing, authentication
assumptions, session lifetime, and AES-256-GCM encryption overhead, but performs
no actual cryptographic operations.

Protocol
--------
1. The satellite and ground station share a long-term authentication credential
   (pre-shared key or public-key certificate — configured via ``auth_method``).
2. An ephemeral key exchange is performed over the RF link at the start of each
   session.  ``key_exchange`` selects one of:
     'ECDH-P256'           elliptic-curve Diffie–Hellman (NIST SP 800-56A)
     'ML-KEM-768'          module-lattice KEM (NIST FIPS 203, 2024)
     'X25519+ML-KEM-768'   hybrid: secure if either component is secure
3. The resulting session key is used for AES-256-GCM authenticated encryption
   for the rest of the contact window.
4. A new session is initiated if the previous one expires or the link drops.

Quantum resistance
------------------
ECDH and ECDSA rely on the elliptic-curve discrete logarithm problem, which
Shor's algorithm solves on a cryptographically relevant quantum computer.
Recorded ECDH handshakes are therefore exposed to "harvest now, decrypt later".
ML-KEM (FIPS 203) and ML-DSA (FIPS 204) rest on module-lattice problems with no
known efficient quantum attack.  Their security is computational, not
information-theoretic as claimed for QKD; pre-shared symmetric keys (PSK) with
256-bit strength are considered quantum-resistant.

Message sizes (bytes, from the standards)
------------------------------------------
  ECDH-P256            public key 65 (uncompressed) per side
  ML-KEM-768           encapsulation key 1184, ciphertext 1088
  X25519+ML-KEM-768    32 + 1184 and 32 + 1088
  ECDSA-P256           public key 65, signature 64
  ML-DSA-65            public key 1952, signature 3309
  PSK                  32-byte MAC per side

Assumptions and limitations
----------------------------
- No forward secrecy model beyond per-session keys.
- Authentication relies on the long-term credential; compromise of that
  credential invalidates all sessions.
- Handshake duration = propagation delay of all messages + serialization time
  at a fraction (link_coding_efficiency) of the RF Shannon capacity.
- Certificates are modelled as one public key + one signature per side; chains,
  revocation and multi-party trust are not modelled.
- AES-256-GCM overhead is per-packet (nonce + tag + AAD).
- Classical cryptography is a legitimate security baseline; this model does not
  fabricate weaknesses to favour a QKD comparison.

References
----------
NIST SP 800-56A Rev 3 — Pair-Wise Key-Establishment Schemes Using Discrete
  Logarithm Cryptography.
NIST FIPS 203 (2024) — Module-Lattice-Based Key-Encapsulation Mechanism Standard.
NIST FIPS 204 (2024) — Module-Lattice-Based Digital Signature Standard.
NIST SP 800-38D — Recommendation for Block Cipher Modes of Operation: GCM and GMAC.
"""
from dataclasses import dataclass
import math


_SPEED_OF_LIGHT = 299_792_458.0  # m/s

# key_exchange → (bytes sent by both sides, signature scheme, quantum resistant, security basis)
KEY_EXCHANGES = {
    'ECDH-P256': (65 + 65, 'ECDSA-P256', False,
                  'elliptic-curve discrete logarithm (broken by Shor\'s algorithm)'),
    'ML-KEM-768': (1184 + 1088, 'ML-DSA-65', True,
                   'module learning-with-errors (NIST FIPS 203)'),
    'X25519+ML-KEM-768': (32 + 1184 + 32 + 1088, 'ML-DSA-65', True,
                          'hybrid: X25519 and module learning-with-errors'),
}

# signature → (bytes per side: public key + signature, quantum resistant)
SIGNATURES = {
    'ECDSA-P256': (65 + 64, False),
    'ML-DSA-65': (1952 + 3309, True),
}

_PSK_MAC_BYTES = 32


@dataclass
class ClassicalSessionConfig:
    """Parameters for the classical session-key establishment model."""

    # Key material
    session_key_bits: int = 256            # AES-256
    key_exchange: str = 'ECDH-P256'        # see KEY_EXCHANGES
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
    link_coding_efficiency: float = 0.5    # achievable fraction of Shannon capacity

    def validate(self):
        if self.session_key_bits not in (128, 192, 256):
            raise ValueError("session_key_bits must be 128, 192, or 256")
        if self.key_exchange not in KEY_EXCHANGES:
            raise ValueError(f"key_exchange must be one of {sorted(KEY_EXCHANGES)}")
        if self.auth_method not in ('psk', 'certificate'):
            raise ValueError("auth_method must be 'psk' or 'certificate'")
        if self.session_lifetime_s <= 0:
            raise ValueError("session_lifetime_s must be positive")
        if self.max_retries < 1:
            raise ValueError("max_retries must be at least 1")
        if self.packet_payload_bits <= 0:
            raise ValueError("packet_payload_bits must be positive")
        if not (0.0 < self.link_coding_efficiency <= 1.0):
            raise ValueError("link_coding_efficiency must be in (0, 1]")
        return self


def handshake_profile(cfg: ClassicalSessionConfig) -> dict:
    """Bytes on the wire and quantum-resistance flags for the configured handshake."""
    kex_bytes, signature, kex_qr, basis = KEY_EXCHANGES[cfg.key_exchange]
    if cfg.auth_method == 'certificate':
        sig_bytes, auth_qr = SIGNATURES[signature]
        auth_bytes = 2 * sig_bytes
        auth_scheme = signature
    else:
        auth_bytes = 2 * _PSK_MAC_BYTES
        auth_qr = True
        auth_scheme = 'PSK-HMAC-SHA256'
    return {
        "key_exchange": cfg.key_exchange,
        "auth_scheme": auth_scheme,
        "handshake_bytes": kex_bytes + auth_bytes,
        "quantum_resistant": kex_qr and auth_qr,
        "harvest_now_decrypt_later_exposed": not kex_qr,
        "security_basis": basis,
    }


def _handshake_duration_s(range_m: float, cfg: ClassicalSessionConfig,
                          handshake_bytes: int = 0, capacity_bps: float = None) -> float:
    """Handshake duration: propagation delay of all messages plus serialization time."""
    one_way_delay_s = range_m / _SPEED_OF_LIGHT
    duration = cfg.handshake_messages * one_way_delay_s
    if capacity_bps and capacity_bps > 0:
        duration += handshake_bytes * 8 / (capacity_bps * cfg.link_coding_efficiency)
    return duration


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
    capacity_bps: float = None,
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
    capacity_bps : float or None
        RF Shannon capacity; when given, handshake serialization time is included.

    Returns
    -------
    dict with keys:
        channel_id               : 'classical_session'
        key_established          : bool
        failure_reason           : str or None
        session_key_bits         : int  (0 if not established)
        key_exchange             : str  (e.g. 'ECDH-P256', 'ML-KEM-768')
        auth_method, auth_scheme : str
        handshake_bytes          : int  (all handshake messages, both directions)
        quantum_resistant        : bool (key exchange and authentication)
        harvest_now_decrypt_later_exposed : bool
        security_basis           : str
        encryption_profile       : str  (e.g. 'AES-256-GCM')
        handshake_duration_s     : float
        sessions_possible        : int  (how many session lifetimes fit in window)
        overhead_fraction        : float  (encryption overhead per packet)
        usable_payload_fraction  : float  (1 - overhead_fraction)
        effective_lifetime_s     : float  (min of session_lifetime_s and contact_duration_s)
        model_id                 : e.g. 'classical_ecdh_aes256gcm', 'classical_mlkem768_aes256gcm'
        security_note            : str  (explicit assumption statement)
    """
    cfg.validate()
    if range_m <= 0:
        raise ValueError("range_m must be positive")
    if contact_duration_s < 0:
        raise ValueError("contact_duration_s must be nonnegative")

    profile = handshake_profile(cfg)
    handshake_s = _handshake_duration_s(range_m, cfg, profile["handshake_bytes"], capacity_bps)
    overhead_frac = _overhead_fraction(cfg)
    usable_frac = 1.0 - overhead_frac
    effective_lifetime = min(cfg.session_lifetime_s, contact_duration_s)
    sessions_possible = math.floor(contact_duration_s / cfg.session_lifetime_s) if cfg.session_lifetime_s > 0 else 0
    common = dict(cfg=cfg, profile=profile, handshake_s=handshake_s, overhead_frac=overhead_frac,
                  usable_frac=usable_frac, effective_lifetime=effective_lifetime)

    if not link_available:
        return _failure(sessions_possible=sessions_possible,
                        reason="RF link unavailable — SNR below reception threshold", **common)

    if snr_db < cfg.min_snr_db_for_handshake:
        return _failure(sessions_possible=sessions_possible,
                        reason=f"RF SNR {snr_db:.1f} dB below handshake minimum {cfg.min_snr_db_for_handshake:.1f} dB",
                        **common)

    if contact_duration_s < handshake_s * cfg.max_retries:
        return _failure(sessions_possible=sessions_possible,
                        reason=(f"Contact window {contact_duration_s:.1f} s too short for handshake "
                                f"({handshake_s:.3f} s × {cfg.max_retries} retries)"),
                        **common)

    note = (f"Key establishment assumed secure under the hardness of {profile['security_basis']} "
            f"and AES-256.  Authentication via {profile['auth_scheme']}: "
            "session security depends on credential integrity.  ")
    if profile["harvest_now_decrypt_later_exposed"]:
        note += ("Recorded handshakes can be decrypted later by a cryptographically "
                 "relevant quantum computer (harvest now, decrypt later).")
    else:
        note += "Believed quantum-resistant; security remains computational, not information-theoretic."
    note += "  Classical cryptography is a legitimate security baseline."
    return {
        "channel_id": "classical_session",
        "key_established": True,
        "failure_reason": None,
        "session_key_bits": cfg.session_key_bits,
        **_profile_fields(cfg, profile),
        "handshake_duration_s": handshake_s,
        "sessions_possible": max(1, sessions_possible),
        "overhead_fraction": overhead_frac,
        "usable_payload_fraction": usable_frac,
        "effective_lifetime_s": effective_lifetime,
        "model_id": _model_id(cfg),
        "security_note": note,
    }


def _model_id(cfg):
    slug = {'ECDH-P256': 'ecdh', 'ML-KEM-768': 'mlkem768', 'X25519+ML-KEM-768': 'x25519mlkem768'}
    return f"classical_{slug[cfg.key_exchange]}_aes256gcm"


def _profile_fields(cfg, profile):
    return {
        "key_exchange": profile["key_exchange"],
        "auth_method": cfg.auth_method,
        "auth_scheme": profile["auth_scheme"],
        "handshake_bytes": profile["handshake_bytes"],
        "quantum_resistant": profile["quantum_resistant"],
        "harvest_now_decrypt_later_exposed": profile["harvest_now_decrypt_later_exposed"],
        "security_basis": profile["security_basis"],
        "encryption_profile": f"AES-{cfg.session_key_bits}-GCM",
    }


def _failure(cfg, profile, handshake_s, overhead_frac, usable_frac, effective_lifetime,
             sessions_possible, reason):
    return {
        "channel_id": "classical_session",
        "key_established": False,
        "failure_reason": reason,
        "session_key_bits": 0,
        **_profile_fields(cfg, profile),
        "handshake_duration_s": handshake_s,
        "sessions_possible": sessions_possible,
        "overhead_fraction": overhead_frac,
        "usable_payload_fraction": usable_frac,
        "effective_lifetime_s": effective_lifetime,
        "model_id": _model_id(cfg),
        "security_note": (
            "Session not established.  "
            "Classical key establishment is a legitimate security baseline when "
            "the link is available and credentials are uncompromised."
        ),
    }

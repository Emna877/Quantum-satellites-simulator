"""Asymptotic BB84 secret-key rate model.

This is the qkd_classical_protocol channel's key-establishment calculation.
It consumes the optical link metrics (sifted count, QBER) and returns an
asymptotic key rate estimate with explicit limitations.

Channel ID: qkd_classical_protocol (key establishment result)

Protocol: Decoy-state BB84 (asymptotic limit, infinite key length assumed).

Secret-key rate formula (asymptotic, one-way error correction):
    R_key = R_sifted * max(0, 1 - f_ec * H2(QBER) - H2(QBER))
where:
    R_sifted  = sifted detection rate (Hz)
    f_ec      = error correction efficiency (1.0 = perfect; ~1.15–1.22 in practice)
    H2(p)     = binary entropy = -p log2(p) - (1-p) log2(1-p)

Security threshold: QBER must be below 11% for BB84 to produce positive key
rate in the asymptotic limit.  QBER above 25% implies eavesdropping or a
broken link by definition.

Limitations
-----------
- Finite-key effects are NOT included.  Asymptotic rates overestimate the key
  rate for short passes (< ~10^6 sifted bits).  Do not claim security from
  these numbers without finite-key analysis.
- Decoy-state tagging and multi-photon fraction are not modeled here; a weak
  coherent pulse source needs separate decoy-state counting.
- Privacy amplification overhead is accounted for in the formula above but
  authentication overhead (for the classical protocol channel) is not subtracted.
- One-way error correction is assumed; two-way protocols can do better.
- Key storage, buffer accounting, and consumption rates are not tracked here.

References
----------
Shor, P. W. & Preskill, J. (2000) "Simple proof of security of the BB84
  quantum key distribution protocol", PRL 85, 441.
Lo, H.-K., Chau, H. F. & Ardehali, M. (2005) "Efficient quantum key distribution
  scheme and a proof of its unconditional security", J. Cryptology 18, 133.
"""
from dataclasses import dataclass
import math


@dataclass
class QKDModelConfig:
    """BB84 asymptotic key-rate model parameters."""
    ec_efficiency: float = 1.16     # error correction inefficiency factor (f_ec ≥ 1.0)
    qber_threshold: float = 0.11    # above this QBER the formula gives 0 key rate

    def validate(self):
        if self.ec_efficiency < 1.0:
            raise ValueError("ec_efficiency must be ≥ 1.0 (perfect is exactly 1.0)")
        if not (0.0 < self.qber_threshold < 0.5):
            raise ValueError("qber_threshold must be in (0, 0.5)")
        return self


def _h2(p: float) -> float:
    """Binary entropy function H2(p) = -p log2(p) - (1-p) log2(1-p)."""
    if p <= 0.0 or p >= 1.0:
        return 0.0
    return -(p * math.log2(p) + (1.0 - p) * math.log2(1.0 - p))


def qkd_key_metrics(sifted_count_hz: float, qber: float, cfg: QKDModelConfig) -> dict:
    """Compute asymptotic BB84 secret-key metrics.

    Parameters
    ----------
    sifted_count_hz : float
        Sifted detection rate from the optical link model, photons/s.
    qber : float
        Quantum bit error rate from the optical link model, [0, 0.5].
    cfg : QKDModelConfig
        Protocol parameters.

    Returns
    -------
    dict with keys:
        channel_id            : 'qkd_classical_protocol'
        key_establishment     : dict — key_status, secret_key_rate_bit_s, reason
        sifted_count_hz       : sifted rate used as input
        qber                  : QBER used as input
        h2_qber               : binary entropy of QBER
        ec_leak_fraction      : error-correction information leakage fraction
        secure_fraction       : fraction of sifted bits that become secret key
        secret_key_rate_bit_s : secret key generation rate, bit/s (asymptotic)
        model_id              : 'bb84_asymptotic'
        finite_key_valid      : always False — finite-key effects not included
    """
    cfg.validate()
    if sifted_count_hz < 0:
        raise ValueError("sifted_count_hz must be nonnegative")
    if not (0.0 <= qber <= 0.5):
        raise ValueError("qber must be in [0, 0.5]")

    h2_q = _h2(qber)
    ec_leak = cfg.ec_efficiency * h2_q
    secure_fraction = max(0.0, 1.0 - ec_leak - h2_q)
    key_rate = sifted_count_hz * secure_fraction

    if sifted_count_hz == 0.0:
        status = "aborted"
        reason = "No sifted photons (link unavailable or blocked)"
        key_rate = 0.0
    elif qber >= cfg.qber_threshold and secure_fraction == 0.0:
        status = "aborted"
        reason = f"QBER {qber:.4f} exceeds asymptotic security threshold {cfg.qber_threshold:.2f}"
        key_rate = 0.0
    else:
        status = "succeeded"
        reason = "Asymptotic estimate; finite-key effects not included"

    return {
        "channel_id": "qkd_classical_protocol",
        "key_establishment": {
            "key_status": status,
            "secret_key_rate_bit_s": key_rate,
            "reason": reason,
        },
        "sifted_count_hz": sifted_count_hz,
        "qber": qber,
        "h2_qber": h2_q,
        "ec_leak_fraction": ec_leak,
        "secure_fraction": secure_fraction,
        "secret_key_rate_bit_s": key_rate,
        "model_id": "bb84_asymptotic",
        "finite_key_valid": False,
    }

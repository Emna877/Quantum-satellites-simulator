"""Asymptotic BB84 secret-key rate model.

This is the qkd_classical_protocol channel's key-establishment calculation.
It consumes the optical link metrics (sifted count, QBER, and the decoy-state
single-photon quantities) and returns an asymptotic key rate estimate with
explicit limitations.

Channel ID: qkd_classical_protocol (key establishment result)

Secret-key rate (GLLP form, one-way error correction, infinite key length):
    R_key = R_sifted * max(0, Δ1 (1 − H2(e1)) − f_ec H2(E))
where:
    R_sifted  = sifted detection rate (Hz)
    E         = observed QBER of all sifted detections
    Δ1        = fraction of detections that come from single-photon pulses
    e1        = error rate of those single-photon detections
    f_ec      = error correction inefficiency (1.0 = Shannon limit; ~1.1–1.2 in practice)
    H2(p)     = binary entropy = −p log2(p) − (1−p) log2(1−p)

For an ideal single-photon source Δ1 = 1 and e1 = E, which reduces to the
Shor–Preskill rate 1 − H2(E) − f_ec H2(E).  For weak coherent pulses the optical
model supplies Δ1 and e1 in the infinite-decoy-state limit (Lo, Ma & Chen 2005).

Security threshold: with f_ec = 1 the Shor–Preskill rate is positive only for
QBER below ≈ 11 %.

Limitations
-----------
- Finite-key effects are NOT included.  Use security/qkd_finite_key.py for
  per-pass key lengths.  Do not claim security from these numbers.
- Decoy-state bounds are the infinite-decoy limit, not a finite decoy analysis.
- Authentication overhead for the classical protocol channel is not subtracted.
- One-way error correction is assumed; two-way protocols can do better.

References
----------
Shor, P. W. & Preskill, J. (2000) "Simple proof of security of the BB84
  quantum key distribution protocol", PRL 85, 441.
Gottesman, Lo, Lütkenhaus & Preskill (2004) "Security of quantum key
  distribution with imperfect devices", Quant. Inf. Comput. 4, 325.
Lo, H.-K., Ma, X. & Chen, K. (2005) "Decoy state quantum key distribution",
  PRL 94, 230504.
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


def qkd_key_metrics(sifted_count_hz: float, qber: float, cfg: QKDModelConfig,
                    single_photon_fraction: float = 1.0,
                    single_photon_qber: float = None) -> dict:
    """Compute asymptotic BB84 secret-key metrics.

    Parameters
    ----------
    sifted_count_hz : float
        Sifted detection rate from the optical link model, photons/s.
    qber : float
        Quantum bit error rate from the optical link model, [0, 0.5].
    cfg : QKDModelConfig
        Protocol parameters.
    single_photon_fraction : float
        Δ1, fraction of detections from single-photon pulses (1 = ideal source).
    single_photon_qber : float or None
        e1, single-photon error rate; defaults to ``qber``.

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
        single_photon_fraction: Δ1 used
        single_photon_qber    : e1 used
        model_id              : 'bb84_asymptotic' (ideal source) or 'bb84_asymptotic_gllp_decoy'
        finite_key_valid      : always False — finite-key effects not included
    """
    cfg.validate()
    if sifted_count_hz < 0:
        raise ValueError("sifted_count_hz must be nonnegative")
    if not (0.0 <= qber <= 0.5):
        raise ValueError("qber must be in [0, 0.5]")

    if not (0.0 <= single_photon_fraction <= 1.0):
        raise ValueError("single_photon_fraction must be in [0, 1]")
    e1 = qber if single_photon_qber is None else single_photon_qber

    h2_q = _h2(qber)
    ec_leak = cfg.ec_efficiency * h2_q
    secure_fraction = max(0.0, single_photon_fraction * (1.0 - _h2(e1)) - ec_leak)
    key_rate = sifted_count_hz * secure_fraction

    if sifted_count_hz == 0.0:
        status = "aborted"
        reason = "No sifted photons (link unavailable or blocked)"
        key_rate = 0.0
    elif qber >= cfg.qber_threshold and secure_fraction == 0.0:
        status = "aborted"
        reason = f"QBER {qber:.4f} exceeds asymptotic security threshold {cfg.qber_threshold:.2f}"
        key_rate = 0.0
    elif secure_fraction == 0.0:
        status = "aborted"
        reason = "Single-photon contribution too small for positive key"
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
        "single_photon_fraction": single_photon_fraction,
        "single_photon_qber": e1,
        "model_id": "bb84_asymptotic" if single_photon_fraction == 1.0 else "bb84_asymptotic_gllp_decoy",
        "finite_key_valid": False,
    }

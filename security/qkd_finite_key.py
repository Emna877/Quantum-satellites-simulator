"""BB84 secret-key rate with finite-key corrections.

The asymptotic formula in communication/qkd_model.py overestimates the key
rate for short contact passes because it assumes an infinite number of sifted
bits.  This module applies finite-key corrections that reduce or eliminate the
key rate for passes with fewer sifted bits than the security parameters require.

Finite-key model (Tomamichel et al. 2012)
------------------------------------------
The secure key length (bits) for n_sifted sifted bits is:

    l = n_sifted * r_asym - xi * sqrt(n_sifted) - log2(2 / eps_PA)

where:
    r_asym  = max(0, 1 - f_ec * H2(q) - H2(q))   [asymptotic rate per sifted bit]
    xi      = sqrt(2) * k_sigma * sqrt(log2(8 / eps_sec))
    k_sigma = constant accounting for statistical estimation uncertainty (~7 for
              standard parameters; derived from Chernoff / Azuma bounds)
    eps_sec = desired security parameter (total failure probability)
    eps_PA  = privacy amplification failure probability (≤ eps_sec / 2)

The correction term ``xi * sqrt(n_sifted)`` captures statistical fluctuations
in the error rate estimate and the privacy amplification hash length.

Key behaviour
-------------
- For very short passes (n_sifted < ~10^4), l ≤ 0 and no key is produced.
- The crossover n_min (where l first becomes positive) depends on eps_sec:
    eps_sec = 1e-9 (research): n_min ≈ 10^5 sifted bits
    eps_sec = 1e-6 (demo):     n_min ≈ 10^4 sifted bits
- Well above n_min the finite-key rate approaches the asymptotic rate.

Limitations
-----------
- Simplified Chernoff-bound treatment; a rigorous composable security proof
  (e.g. Pirandola et al. 2020 review) requires more involved calculations.
- Decoy-state phase-error estimation is not included.  With a WCP source, the
  single-photon yield must be bounded separately (see decoy-state literature).
- Authentication cost for the classical protocol channel is not subtracted.
- Two-way error correction and advantage distillation are not modelled.
- ``finite_key_valid`` is True only when n_sifted ≥ n_min; below that threshold
  this formula returns l = 0 (abort), which is conservative but correct.

References
----------
Tomamichel, M., Lim, C. C. W., Gisin, N. & Renner, R. (2012) "Tight finite-key
  analysis for quantum cryptography", Nature Communications 3, 634.
Ma, X., Fung, C.-H. F. & Razavi, M. (2012) "Statistical fluctuation analysis
  for measurement-device-independent quantum key distribution",
  Physical Review A 86, 052305.
"""
from dataclasses import dataclass
import math


@dataclass
class BB84FiniteKeyConfig:
    """Finite-key BB84 parameters."""

    # Error correction
    ec_efficiency: float = 1.16           # f_ec ≥ 1.0 (1.0 = perfect)
    qber_threshold: float = 0.11          # abort if QBER ≥ this value

    # Security parameters
    eps_sec: float = 1e-9                 # desired security parameter (failure prob)
    k_sigma: float = 7.0                  # statistical estimation constant (Chernoff)

    # Minimum sifted-bit count to attempt finite-key analysis
    # (Below this the correction term always dominates → l ≤ 0.)
    n_min_sifted: int = 1000              # hard floor; 0 below this

    def validate(self):
        if self.ec_efficiency < 1.0:
            raise ValueError("ec_efficiency must be ≥ 1.0")
        if not (0.0 < self.qber_threshold < 0.5):
            raise ValueError("qber_threshold must be in (0, 0.5)")
        if not (0.0 < self.eps_sec < 1.0):
            raise ValueError("eps_sec must be in (0, 1)")
        if self.k_sigma <= 0:
            raise ValueError("k_sigma must be positive")
        if self.n_min_sifted < 0:
            raise ValueError("n_min_sifted must be nonnegative")
        return self


def _h2(p: float) -> float:
    """Binary entropy H2(p)."""
    if p <= 0.0 or p >= 1.0:
        return 0.0
    return -(p * math.log2(p) + (1.0 - p) * math.log2(1.0 - p))


def _finite_key_correction(n_sifted: float, cfg: BB84FiniteKeyConfig) -> float:
    """Compute the finite-key correction term in bits.

    correction = xi * sqrt(n_sifted) + log2(2 / eps_PA)
    where eps_PA = eps_sec / 2, xi = sqrt(2) * k_sigma * sqrt(log2(8 / eps_sec))
    """
    eps_PA = cfg.eps_sec / 2.0
    xi = math.sqrt(2.0) * cfg.k_sigma * math.sqrt(math.log2(8.0 / cfg.eps_sec))
    correction = xi * math.sqrt(n_sifted) + math.log2(2.0 / eps_PA)
    return correction


def bb84_finite_key_metrics(
    sifted_count_hz: float,
    qber: float,
    pass_duration_s: float,
    cfg: BB84FiniteKeyConfig,
) -> dict:
    """Compute finite-key BB84 secret-key metrics for a single contact pass.

    Parameters
    ----------
    sifted_count_hz : float
        Sifted detection rate from the optical link model, photons/s.
    qber : float
        Quantum bit error rate, [0, 0.5].
    pass_duration_s : float
        Duration of the contact window used for key accumulation, seconds.
        The total sifted bits are ``sifted_count_hz * pass_duration_s``.
    cfg : BB84FiniteKeyConfig
        Protocol and security parameters.

    Returns
    -------
    dict with keys:
        channel_id              : 'qkd_finite_key'
        key_status              : 'succeeded' | 'aborted'
        abort_reason            : str or None
        n_sifted_bits           : total sifted bits in the pass
        r_asymptotic            : asymptotic rate per sifted bit (no finite-key correction)
        correction_bits         : finite-key correction term, bits
        secure_key_bits         : bits of secure key from this pass (≥ 0)
        secure_key_rate_bit_s   : average rate over the pass, bit/s
        finite_key_valid        : True when n_sifted ≥ n_min_sifted
        model_id                : 'bb84_finite_tomamichel2012'
        eps_sec                 : security parameter used
    """
    cfg.validate()
    if sifted_count_hz < 0:
        raise ValueError("sifted_count_hz must be nonneg")
    if not (0.0 <= qber <= 0.5):
        raise ValueError("qber must be in [0, 0.5]")
    if pass_duration_s < 0:
        raise ValueError("pass_duration_s must be nonneg")

    n_sifted = sifted_count_hz * pass_duration_s
    h2_q = _h2(qber)
    ec_leak = cfg.ec_efficiency * h2_q
    r_asym = max(0.0, 1.0 - ec_leak - h2_q)

    # Abort conditions
    if sifted_count_hz == 0.0 or n_sifted == 0.0:
        return _abort(cfg, n_sifted, r_asym, 0.0, "No sifted photons (link unavailable)", pass_duration_s)

    if qber >= cfg.qber_threshold:
        return _abort(cfg, n_sifted, r_asym, 0.0,
                      f"QBER {qber:.4f} ≥ threshold {cfg.qber_threshold:.2f}", pass_duration_s)

    if r_asym == 0.0:
        return _abort(cfg, n_sifted, r_asym, 0.0,
                      "Asymptotic rate is zero (QBER too high for positive key)", pass_duration_s)

    if n_sifted < cfg.n_min_sifted:
        return _abort(cfg, n_sifted, r_asym, 0.0,
                      f"Insufficient sifted bits: {n_sifted:.0f} < n_min {cfg.n_min_sifted}",
                      pass_duration_s)

    correction = _finite_key_correction(n_sifted, cfg)
    secure_bits = max(0.0, n_sifted * r_asym - correction)
    finite_key_valid = n_sifted >= cfg.n_min_sifted

    if secure_bits == 0.0:
        return _abort(cfg, n_sifted, r_asym, correction,
                      "Finite-key correction exceeds asymptotic key length", pass_duration_s)

    rate = secure_bits / pass_duration_s if pass_duration_s > 0 else 0.0
    return {
        "channel_id": "qkd_finite_key",
        "key_status": "succeeded",
        "abort_reason": None,
        "n_sifted_bits": n_sifted,
        "r_asymptotic": r_asym,
        "correction_bits": correction,
        "secure_key_bits": secure_bits,
        "secure_key_rate_bit_s": rate,
        "finite_key_valid": finite_key_valid,
        "model_id": "bb84_finite_tomamichel2012",
        "eps_sec": cfg.eps_sec,
    }


def _abort(cfg, n_sifted, r_asym, correction, reason, pass_duration_s):
    return {
        "channel_id": "qkd_finite_key",
        "key_status": "aborted",
        "abort_reason": reason,
        "n_sifted_bits": n_sifted,
        "r_asymptotic": r_asym,
        "correction_bits": correction,
        "secure_key_bits": 0.0,
        "secure_key_rate_bit_s": 0.0,
        "finite_key_valid": False,
        "model_id": "bb84_finite_tomamichel2012",
        "eps_sec": cfg.eps_sec,
    }

"""BB84 secret-key length with finite-key corrections.

The asymptotic formula in communication/qkd_model.py overestimates the key
length for short contact passes because it assumes infinitely many sifted
bits.  This module applies the finite-key bound of Tomamichel et al. (2012),
combined with decoy-state single-photon bounds (GLLP form) for weak coherent
pulse sources.

Finite-key bound (Tomamichel, Lim, Gisin & Renner 2012, Nat. Commun. 3, 634)
-----------------------------------------------------------------------------
Of the N sifted bits, k = pe_fraction · N are disclosed to estimate the error
rate and n = N − k form the raw key.  The protocol is ε_cor-correct and
ε_sec-secret if the extracted key length satisfies

    ℓ ≤ n (1 − H2(Q + μ)) − leak_EC − log2(2 / (ε_sec² ε_cor))

    μ = sqrt( (n + k)/(n k) · (k + 1)/k · ln(2 / ε_sec) )
    leak_EC = f_ec · n · H2(Q)

where Q is the observed error rate and μ the statistical deviation allowed
between the error rate of the test bits and that of the key bits.

Decoy-state extension (heuristic combination)
---------------------------------------------
For weak coherent pulses only single-photon detections contribute to the
secret key (GLLP).  With Δ1 the single-photon fraction of detections and e1
their error rate, this module uses

    ℓ = n1 (1 − H2(e1 + μ1)) − f_ec · n · H2(Q) − log2(2 / (ε_sec² ε_cor))

with n1 = Δ1 n, k1 = Δ1 k and μ1 evaluated on (n1, k1).  Δ1 and e1 come from
the optical model (infinite-decoy limit) when supplied; otherwise, for a WCP
source with decoy states, Δ1 = e^−μ (low-loss limit of Q1/Qμ) and the
worst-case bound e1 ≤ Q / Δ1 is used.  Without decoy states, multi-photon
pulses cannot be bounded at satellite losses (photon-number splitting), so
Δ1 = 0 and no key is produced.

This combination is NOT a composable finite-size decoy-state proof.  A rigorous
treatment (e.g. Lim, Curty, Walenta, Xu & Zbinden 2014) also bounds the decoy
yields with finite statistics, which lowers the key further.

Limitations
-----------
- Decoy-state yields use infinite statistics; only the error-rate estimate is finite.
- Authentication cost for the classical protocol channel is not subtracted.
- Two-way error correction and advantage distillation are not modelled.
- ``finite_key_valid`` is True only when a positive key is produced and
  N ≥ n_min_sifted.  n_min_sifted is a hard floor, not the crossover length.

References
----------
Tomamichel, M., Lim, C. C. W., Gisin, N. & Renner, R. (2012) "Tight finite-key
  analysis for quantum cryptography", Nature Communications 3, 634.
Gottesman, Lo, Lütkenhaus & Preskill (2004) "Security of quantum key
  distribution with imperfect devices", Quant. Inf. Comput. 4, 325.
Lo, H.-K., Ma, X. & Chen, K. (2005) "Decoy state quantum key distribution",
  Physical Review Letters 94, 230504.
Lim, C. C. W., Curty, M., Walenta, N., Xu, F. & Zbinden, H. (2014) "Concise
  security bounds for practical decoy-state quantum key distribution",
  Physical Review A 89, 022307.
"""
from dataclasses import dataclass
import math


@dataclass
class BB84FiniteKeyConfig:
    """Finite-key BB84 parameters, with optional WCP / decoy-state correction."""

    # Error correction
    ec_efficiency: float = 1.16           # f_ec ≥ 1.0 (1.0 = Shannon limit)
    qber_threshold: float = 0.11          # abort if observed QBER ≥ this value

    # Security parameters (Tomamichel et al. 2012)
    eps_sec: float = 1e-9                 # secrecy parameter
    eps_cor: float = 1e-12                # correctness parameter
    pe_fraction: float = 0.1              # fraction of sifted bits disclosed for error estimation

    # Hard floor on sifted bits before any key is attempted
    n_min_sifted: int = 1000

    # Weak coherent pulse / decoy-state parameters, used only when the optical
    # model does not supply single-photon quantities.
    wcp_mean_photon_number: float = 0.0   # μ; 0 = ideal single-photon source
    use_decoy_state: bool = True          # False = multi-photon pulses unbounded (PNS)

    def validate(self):
        if self.ec_efficiency < 1.0:
            raise ValueError("ec_efficiency must be ≥ 1.0")
        if not (0.0 < self.qber_threshold < 0.5):
            raise ValueError("qber_threshold must be in (0, 0.5)")
        if not (0.0 < self.eps_sec < 1.0):
            raise ValueError("eps_sec must be in (0, 1)")
        if not (0.0 < self.eps_cor < 1.0):
            raise ValueError("eps_cor must be in (0, 1)")
        if not (0.0 < self.pe_fraction < 1.0):
            raise ValueError("pe_fraction must be in (0, 1)")
        if self.n_min_sifted < 0:
            raise ValueError("n_min_sifted must be nonnegative")
        if self.wcp_mean_photon_number < 0:
            raise ValueError("wcp_mean_photon_number must be nonneg (0 = ideal SPS)")
        return self


def _h2(p: float) -> float:
    """Binary entropy H2(p)."""
    if p <= 0.0 or p >= 1.0:
        return 0.0
    return -(p * math.log2(p) + (1.0 - p) * math.log2(1.0 - p))


def _single_photon_bounds(qber, cfg, single_photon_fraction, single_photon_qber):
    """Return (Δ1, e1, info) for the key-rate formula."""
    if single_photon_fraction is not None:
        e1 = qber if single_photon_qber is None else single_photon_qber
        return single_photon_fraction, e1, {
            "wcp_applied": single_photon_fraction < 1.0,
            "mu": cfg.wcp_mean_photon_number,
            "single_photon_fraction": single_photon_fraction,
            "e1_upper_bound": e1,
            "model": "decoy_state_infinite_limit_from_link",
        }

    mu = cfg.wcp_mean_photon_number
    if mu <= 0.0:
        return 1.0, qber, {
            "wcp_applied": False,
            "mu": 0.0,
            "single_photon_fraction": 1.0,
            "model": "ideal_single_photon",
        }

    p1 = mu * math.exp(-mu)
    p_multi = max(0.0, 1.0 - math.exp(-mu) - p1)
    if cfg.use_decoy_state:
        delta1 = math.exp(-mu)            # Q1/Qμ when μη ≪ 1 and background is negligible
        e1 = min(0.5, qber / delta1)      # all errors attributed to single photons
        model = "decoy_state_infinite_limit"
    else:
        delta1 = 0.0                      # P_multi ≫ Qμ at satellite losses: PNS breaks all
        e1 = 0.5
        model = "no_decoy_single_photon_only"
    return delta1, e1, {
        "wcp_applied": True,
        "mu": mu,
        "P1": p1,
        "P_multi": p_multi,
        "single_photon_fraction": delta1,
        "e1_upper_bound": e1,
        "model": model,
    }


def _statistical_deviation(n: float, k: float, eps_sec: float) -> float:
    """Tomamichel et al. (2012) deviation μ between test and key error rates."""
    if n <= 0 or k <= 0:
        return 0.5
    return math.sqrt((n + k) / (n * k) * (k + 1) / k * math.log(2.0 / eps_sec))


def bb84_finite_key_metrics(
    sifted_count_hz: float,
    qber: float,
    pass_duration_s: float,
    cfg: BB84FiniteKeyConfig,
    single_photon_fraction: float = None,
    single_photon_qber: float = None,
) -> dict:
    """Compute finite-key BB84 secret-key metrics for a single contact pass.

    Parameters
    ----------
    sifted_count_hz : float
        Sifted detection rate from the optical link model, clicks/s.
    qber : float
        Observed quantum bit error rate, [0, 0.5].
    pass_duration_s : float
        Duration used for key accumulation, seconds.
        The total sifted bits are ``sifted_count_hz * pass_duration_s``.
    cfg : BB84FiniteKeyConfig
        Protocol and security parameters.
    single_photon_fraction, single_photon_qber : float or None
        Decoy-state Δ1 and e1 from the optical model.  When omitted, they are
        derived from ``cfg.wcp_mean_photon_number``.

    Returns
    -------
    dict with keys:
        channel_id              : 'qkd_finite_key'
        key_status              : 'succeeded' | 'aborted'
        abort_reason            : str or None
        n_sifted_bits           : total sifted bits in the pass (N)
        n_key_bits              : raw key bits after parameter estimation (n)
        n_pe_bits               : bits disclosed for parameter estimation (k)
        qber                    : observed QBER used
        statistical_deviation   : μ, finite-size deviation added to e1
        r_asymptotic            : asymptotic secret fraction per raw key bit
        correction_bits         : finite-size penalty relative to the asymptotic length, bits
        secure_key_bits         : bits of secure key from this pass (≥ 0)
        secure_key_rate_bit_s   : average rate over the pass, bit/s
        finite_key_valid        : True when a positive key is produced and N ≥ n_min_sifted
        model_id                : 'bb84_finite_tomamichel2012' or '..._gllp_decoy'
        eps_sec, eps_cor        : security parameters used
        wcp                     : single-photon bound details
    """
    cfg.validate()
    if sifted_count_hz < 0:
        raise ValueError("sifted_count_hz must be nonneg")
    if not (0.0 <= qber <= 0.5):
        raise ValueError("qber must be in [0, 0.5]")
    if pass_duration_s < 0:
        raise ValueError("pass_duration_s must be nonneg")

    delta1, e1, wcp_info = _single_photon_bounds(qber, cfg, single_photon_fraction, single_photon_qber)
    model_id = "bb84_finite_tomamichel2012" if delta1 == 1.0 else "bb84_finite_tomamichel2012_gllp_decoy"

    n_total = sifted_count_hz * pass_duration_s
    k = cfg.pe_fraction * n_total
    n = n_total - k
    n1, k1 = delta1 * n, delta1 * k

    leak_ec = cfg.ec_efficiency * n * _h2(qber)
    r_asym = max(0.0, delta1 * (1.0 - _h2(e1)) - cfg.ec_efficiency * _h2(qber))
    mu = _statistical_deviation(n1, k1, cfg.eps_sec)
    hash_cost = math.log2(2.0 / (cfg.eps_sec ** 2 * cfg.eps_cor))

    base = dict(cfg=cfg, n_total=n_total, n=n, k=k, qber=qber, mu=mu, r_asym=r_asym,
                pass_duration_s=pass_duration_s, wcp_info=wcp_info, model_id=model_id)

    if sifted_count_hz == 0.0 or n_total == 0.0:
        return _abort(reason="No sifted photons (link unavailable)", correction=0.0, **base)
    if qber >= cfg.qber_threshold:
        return _abort(reason=f"QBER {qber:.4f} ≥ threshold {cfg.qber_threshold:.2f}", correction=0.0, **base)
    if r_asym == 0.0:
        return _abort(reason="Asymptotic rate is zero (single-photon phase error too high for positive key)",
                      correction=0.0, **base)
    if n_total < cfg.n_min_sifted:
        return _abort(reason=f"Insufficient sifted bits: {n_total:.0f} < n_min {cfg.n_min_sifted}",
                      correction=0.0, **base)

    e1_eff = min(0.5, e1 + mu)
    secure_bits = max(0.0, n1 * (1.0 - _h2(e1_eff)) - leak_ec - hash_cost)
    correction = n * r_asym - secure_bits

    if secure_bits == 0.0:
        return _abort(reason="Finite-key correction exceeds asymptotic key length", correction=correction, **base)

    rate = secure_bits / pass_duration_s if pass_duration_s > 0 else 0.0
    return {
        "channel_id": "qkd_finite_key",
        "key_status": "succeeded",
        "abort_reason": None,
        "n_sifted_bits": n_total,
        "n_key_bits": n,
        "n_pe_bits": k,
        "qber": qber,
        "statistical_deviation": mu,
        "r_asymptotic": r_asym,
        "correction_bits": correction,
        "secure_key_bits": secure_bits,
        "secure_key_rate_bit_s": rate,
        "finite_key_valid": True,
        "model_id": model_id,
        "eps_sec": cfg.eps_sec,
        "eps_cor": cfg.eps_cor,
        "wcp": wcp_info,
    }


def _abort(cfg, n_total, n, k, qber, mu, r_asym, correction, reason, pass_duration_s, wcp_info, model_id):
    return {
        "channel_id": "qkd_finite_key",
        "key_status": "aborted",
        "abort_reason": reason,
        "n_sifted_bits": n_total,
        "n_key_bits": n,
        "n_pe_bits": k,
        "qber": qber,
        "statistical_deviation": mu,
        "r_asymptotic": r_asym,
        "correction_bits": correction,
        "secure_key_bits": 0.0,
        "secure_key_rate_bit_s": 0.0,
        "finite_key_valid": False,
        "model_id": model_id,
        "eps_sec": cfg.eps_sec,
        "eps_cor": cfg.eps_cor,
        "wcp": wcp_info,
    }

"""Model card for the console: formulas, parameters and validation, all from Python.

The browser only renders this record; it never re-derives a formula or a value.
"""
from experiments.validation import REFERENCE, micius_comparison

FORMULAS = [
    dict(group='RF link', quantity='Free-space path loss',
         formula='FSPL = 20 log₁₀(4πR / λ)',
         source='Friis transmission equation; Pratt, Bostian & Allnutt (2003), ch. 3'),
    dict(group='RF link', quantity='Noise floor and SNR',
         formula='N = −174 dBm/Hz + 10 log₁₀ B + NF;  SNR = P_rx − N',
         source='Thermal (kTB) noise at 290 K'),
    dict(group='RF link', quantity='Capacity (upper bound)',
         formula='C = B log₂(1 + SNR)',
         source='Shannon (1948)'),
    dict(group='Optical link', quantity='Beam collection',
         formula='η_geo = 1 − exp(−2a² / w²),  w = θ·R,  a = D_rx / 2',
         source='Gaussian beam; Bourgoin et al. (2013) New J. Phys. 15, 023006'),
    dict(group='Optical link', quantity='Atmospheric loss',
         formula='L_atm = L_zenith / sin(elevation)  (airmass ≤ 10)',
         source='Plane-parallel atmosphere approximation'),
    dict(group='Optical link', quantity='Detections',
         formula='S = rate · (1 − e^(−μ η_sys));  B = (dark + sky) · min(1, τ_gate · rate)',
         source='Poisson weak coherent pulses; gated detection'),
    dict(group='Optical link', quantity='QBER',
         formula='E = (e_sig · S + ½ B) / (S + B)',
         source='Background clicks are random: wrong half the time'),
    dict(group='Optical link', quantity='Intercept-resend error',
         formula='e_sig = (1 − f) e_d + f (¼ + e_d / 2)',
         source='Bennett & Brassard (1984); full interception gives E ≈ 25 %'),
    dict(group='QKD security', quantity='Decoy-state single photons',
         formula='Y₁ = Y₀ + η_sys;  e₁ = (½ Y₀ + e_sig η_sys) / Y₁;  Δ₁ = Y₁ μ e^(−μ) / Q_μ',
         source='Lo, Ma & Chen (2005) PRL 94, 230504 (infinite-decoy limit)'),
    dict(group='QKD security', quantity='Asymptotic key rate',
         formula='R = R_sift · [Δ₁ (1 − H₂(e₁)) − f_EC H₂(E)]',
         source='Gottesman, Lo, Lütkenhaus & Preskill (2004)'),
    dict(group='QKD security', quantity='Finite key length',
         formula=('ℓ = n₁ (1 − H₂(e₁ + μ)) − f_EC n H₂(E) − log₂(2 / (ε_sec² ε_cor)),  '
                  'μ = √[(n + k)/(nk) · (k + 1)/k · ln(2/ε_sec)]'),
         source='Tomamichel, Lim, Gisin & Renner (2012) Nat. Commun. 3, 634'),
    dict(group='QKD security', quantity='Dependency on RF',
         formula='Key credited only if RF available ≥ 10 s and RF bits ≥ 2·detections + f_EC n H₂(E)',
         source='Post-processing over the authenticated classical channel'),
    dict(group='Classical sessions', quantity='Handshake time',
         formula='t = 4R / c + 8 · bytes / (η_code · C)',
         source='Message sizes: NIST SP 800-56A (ECDH), FIPS 203 (ML-KEM), FIPS 204 (ML-DSA)'),
]


def _parameter_rows(cfg):
    rf, opt, fin, ecdh, pqc = cfg.rf, cfg.optical, cfg.qkd_finite, cfg.classical_session, cfg.pqc_session
    return [
        ('RF link', 'Transmit power', f'{rf.tx_power_dbm:g}', 'dBm'),
        ('RF link', 'Satellite antenna gain', f'{rf.tx_antenna_gain_dbi:g}', 'dBi'),
        ('RF link', 'Ground antenna gain', f'{rf.rx_antenna_gain_dbi:g}', 'dBi (≈3 m dish at X-band)'),
        ('RF link', 'Frequency', f'{rf.frequency_hz / 1e9:g}', 'GHz'),
        ('RF link', 'Bandwidth', f'{rf.bandwidth_hz / 1e6:g}', 'MHz'),
        ('RF link', 'Noise figure', f'{rf.system_noise_figure_db:g}', 'dB'),
        ('RF link', 'Pointing loss (tx + rx)', f'{rf.tx_pointing_loss_db + rf.rx_pointing_loss_db:g}', 'dB'),
        ('Optical link', 'Pulse rate', f'{opt.source_rate_hz:.3g}', 'pulses/s'),
        ('Optical link', 'Mean photon number μ', f'{opt.mean_photon_number:g}', '0 = ideal single-photon source'),
        ('Optical link', 'Wavelength', f'{opt.wavelength_m * 1e9:g}', 'nm'),
        ('Optical link', 'Beam divergence (1/e² half-angle)', f'{opt.beam_divergence_half_angle_rad * 1e6:g}', 'µrad'),
        ('Optical link', 'Receiver aperture', f'{opt.rx_aperture_m:g}', 'm'),
        ('Optical link', 'Detector efficiency', f'{opt.detector_efficiency:g}', ''),
        ('Optical link', 'Dark counts', f'{opt.dark_counts_hz:g}', 'counts/s'),
        ('Optical link', 'Sky background (before gating)', f'{opt.sky_background_hz:g}', 'counts/s, night-time'),
        ('Optical link', 'Detection window', f'{opt.timing_resolution_s * 1e9:g}', 'ns'),
        ('Optical link', 'Zenith atmospheric loss', f'{opt.zenith_atmospheric_loss_db:g}', 'dB'),
        ('Optical link', 'Pointing loss', f'{opt.pointing_loss_db:g}', 'dB'),
        ('Optical link', 'Optics and coupling loss', f'{opt.optical_efficiency_loss_db:g}', 'dB'),
        ('Optical link', 'Misalignment error e_d', f'{opt.misalignment_error:g}', ''),
        ('QKD security', 'Error-correction inefficiency f_EC', f'{fin.ec_efficiency:g}', ''),
        ('QKD security', 'QBER abort threshold', f'{fin.qber_threshold:g}', ''),
        ('QKD security', 'Secrecy parameter ε_sec', f'{fin.eps_sec:g}', ''),
        ('QKD security', 'Correctness parameter ε_cor', f'{fin.eps_cor:g}', ''),
        ('QKD security', 'Parameter-estimation fraction', f'{fin.pe_fraction:g}', 'of sifted bits'),
        ('QKD security', 'Minimum RF time for post-processing', f'{cfg.min_post_processing_link_s:g}', 's'),
        ('Classical sessions', 'Key exchanges compared', f'{ecdh.key_exchange} vs {pqc.key_exchange}', ''),
        ('Classical sessions', 'Authentication', ecdh.auth_method.upper(), ''),
        ('Classical sessions', 'Minimum SNR for handshake', f'{ecdh.min_snr_db_for_handshake:g}', 'dB'),
        ('Classical sessions', 'Achievable fraction of capacity', f'{ecdh.link_coding_efficiency:g}', ''),
        ('Geometry', 'Minimum elevation', f'{cfg.min_elevation_deg:g}', '°'),
    ]


def model_card(runner_config):
    return dict(
        format='model_card.v1',
        formulas=FORMULAS,
        parameters=[dict(group=g, name=n, value=v, unit=u) for g, n, v, u in _parameter_rows(runner_config)],
        validation=dict(reference=REFERENCE, rows=micius_comparison(),
                        assumption='Night-time sky background of 500 counts/s before gating is assumed; '
                                   'the paper does not report it.'),
    )

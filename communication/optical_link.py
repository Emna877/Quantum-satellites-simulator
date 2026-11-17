"""Optical quantum channel model for the quantum_optical channel.

Models free-space optical (FSO) beam propagation and single-photon detector response
for a downward-looking satellite QKD transmitter.  All loss terms are additive in dB.

Channel ID: quantum_optical

Physical model
--------------
Total channel loss (dB) = geometric + atmospheric + pointing + optical_efficiency_loss

  geometric: Gaussian beam (1/e² radius w = θ_div R) collected by a circular
    aperture of radius a = D_rx / 2:
        η_geo = 1 − exp(−2 a² / w²)           (≈ 2 a² / w² when a ≪ w)

  atmospheric: zenith loss scaled by airmass ≈ 1/sin(elevation), clipped to
    max_airmass to avoid divergence at very low elevation.

  pointing: fixed jitter/bias loss from telescope mount and ACS residuals.

  optical_efficiency_loss: transmission of telescope optics, filters, and fibers.

Detection model (per pulse slot; source_rate_hz is the pulse repetition rate)
------------------------------------------------------------------------------
  η_sys   = channel transmittance × detector efficiency
  signal  : ideal single-photon source (mean_photon_number = 0):
                S = rate · η_sys
            weak coherent pulses with mean photon number μ > 0:
                S = rate · (1 − exp(−μ η_sys))
  gating  : detectors only accept clicks inside a window of timing_resolution_s
            around each expected pulse, so the accepted background is
                B = (dark_counts_hz + sky_background_hz) · min(1, window · rate)
  QBER    : background clicks are random, so they are wrong half the time:
                QBER = (e_sig · S + 0.5 · B) / (S + B)
            with e_sig the error rate on genuine signal photons (misalignment,
            plus intercept-resend errors when an eavesdropper is active).
  sifting : all accepted clicks (signal and background) go through basis
            reconciliation: sifted = (S + B) · sifting_fraction.

Intercept-resend eavesdropping
------------------------------
On an intercepted photon Eve guesses the wrong basis half the time; Bob's result
is then random.  The error rate on intercepted sifted bits is 1/4 + e_d/2, so
    e_sig = (1 − f) e_d + f (1/4 + e_d/2)
for an intercepted fraction f.  Full interception (f = 1) gives QBER ≈ 25 %.
Eve is assumed to resend through a lossless channel, so count rates are unchanged.

Single-photon quantities (decoy-state, infinite-decoy limit; Lo, Ma & Chen 2005)
--------------------------------------------------------------------------------
  Y0 = B / rate                            background yield per pulse
  Y1 = Y0 + η_sys                          single-photon yield
  e1 = (0.5 Y0 + e_sig η_sys) / Y1         single-photon error rate
  Q1 = Y1 μ e^−μ                           single-photon gain
  Qμ = (S + B) / rate                      total gain
  single_photon_fraction = Q1 / Qμ         (1 for an ideal single-photon source)

Limitations
-----------
- Far-field Gaussian beam only; near-field, truncation, M² > 1 and wavefront-error
  losses are folded into pointing/optical efficiency terms.
- Partial cloud cover, seeing conditions, and wavelength-dependent atmosphere not modeled.
- Sky background is a configurable scalar, not a sky-radiance or solar-angle model.
- Detector dead time, afterpulsing, and saturation are not modeled.
- Decoy-state values are the infinite-decoy (exact Y1, e1) limit; finite decoy
  statistics are not included.
- Only the signal intensity is modeled; the pulse slots spent on decoy and vacuum
  states are not subtracted from the rate.

References
----------
Liao et al. (2017) "Satellite-to-ground quantum key distribution",
  Nature 549, 43–47; arXiv:1707.00542. (Micius link budget)
Bourgoin et al. (2013) "A comprehensive design and performance analysis of LEO
  satellite quantum communication", New J. Phys. 15, 023006.
Lo, Ma & Chen (2005) "Decoy state quantum key distribution", PRL 94, 230504.
"""
from dataclasses import dataclass
import math


@dataclass
class OpticalLinkConfig:
    """All configurable optical quantum channel parameters with explicit units."""

    # Source
    source_rate_hz: float = 1e8          # pulse repetition rate, pulses/s
    mean_photon_number: float = 0.0      # μ of the signal state; 0 = ideal single-photon source
    wavelength_m: float = 785e-9         # m  (free-space QKD ~780-850 nm or 1550 nm)

    # Transmitter optics (satellite)
    tx_aperture_m: float = 0.10          # m  transmit telescope diameter
    beam_divergence_half_angle_rad: float = 10e-6  # rad  1/e² half-angle divergence

    # Receiver optics (ground)
    rx_aperture_m: float = 1.0           # m  receive telescope diameter (1 m class)

    # Detector
    detector_efficiency: float = 0.30   # single-photon detector efficiency (0–1)
    dark_counts_hz: float = 100.0        # dark counts per second (all detectors)
    sky_background_hz: float = 1000.0   # ungated sky/stray-light counts per second (night-time)
    timing_resolution_s: float = 1e-9   # detection window around each expected pulse, s

    # Loss contributions
    zenith_atmospheric_loss_db: float = 1.0  # dB  clear-sky zenith loss
    pointing_loss_db: float = 3.0        # dB  ACS + fine-steering residual
    optical_efficiency_loss_db: float = 3.0  # dB  telescope, filter and fiber-coupling loss

    # Protocol
    sifting_fraction: float = 0.5        # BB84 basis-match fraction
    misalignment_error: float = 0.01     # fractional contribution to QBER from polarization/phase errors

    # Atmospheric clipping
    max_airmass: float = 10.0

    # Environmental blocking
    cloud_blocked: bool = False   # True = cloud/obstruction blocks optical path entirely

    # Eavesdropping
    intercept_resend_fraction: float = 0.0  # fraction of signal photons intercepted and resent

    def validate(self):
        for name, val in [('source_rate_hz', self.source_rate_hz),
                          ('wavelength_m', self.wavelength_m),
                          ('tx_aperture_m', self.tx_aperture_m),
                          ('rx_aperture_m', self.rx_aperture_m),
                          ('timing_resolution_s', self.timing_resolution_s)]:
            if val <= 0 or not math.isfinite(val):
                raise ValueError(f"{name} must be positive and finite")
        for name, val in [('detector_efficiency', self.detector_efficiency),
                          ('sifting_fraction', self.sifting_fraction)]:
            if not (0.0 < val <= 1.0):
                raise ValueError(f"{name} must be in (0, 1]")
        if self.misalignment_error < 0 or self.misalignment_error >= 0.5:
            raise ValueError("misalignment_error must be in [0, 0.5)")
        if self.dark_counts_hz < 0 or self.sky_background_hz < 0:
            raise ValueError("dark and sky background counts must be nonnegative")
        if self.beam_divergence_half_angle_rad <= 0:
            raise ValueError("beam divergence must be positive")
        if self.mean_photon_number < 0 or not math.isfinite(self.mean_photon_number):
            raise ValueError("mean_photon_number must be nonnegative (0 = ideal single-photon source)")
        if not (0.0 <= self.intercept_resend_fraction <= 1.0):
            raise ValueError("intercept_resend_fraction must be in [0, 1]")
        return self


_SPEED_OF_LIGHT = 299_792_458.0


def geometric_loss_db(range_m: float, cfg: OpticalLinkConfig) -> float:
    """Gaussian-beam geometric loss in dB.

    η_geo = 1 − exp(−2 a² / w²),  a = D_rx / 2,  w = θ_div R
    loss_db = −10 log10(η_geo)  [positive, increasing with range]
    """
    beam_radius_at_rx = cfg.beam_divergence_half_angle_rad * range_m
    rx_radius = cfg.rx_aperture_m / 2.0
    if beam_radius_at_rx <= 0:
        return 0.0
    eta = -math.expm1(-2.0 * (rx_radius / beam_radius_at_rx) ** 2)
    return -10.0 * math.log10(eta)


def atmospheric_loss_db(elevation_deg: float, cfg: OpticalLinkConfig) -> float:
    """Slant-path atmospheric loss from zenith loss scaled by airmass.

    airmass ≈ 1 / sin(elevation), clipped to max_airmass.
    """
    elev_rad = math.radians(max(elevation_deg, 0.1))
    airmass = min(1.0 / math.sin(elev_rad), cfg.max_airmass)
    return cfg.zenith_atmospheric_loss_db * airmass


def gate_duty_cycle(cfg: OpticalLinkConfig) -> float:
    """Fraction of time the detectors accept clicks (window × pulse rate, ≤ 1)."""
    return min(1.0, cfg.timing_resolution_s * cfg.source_rate_hz)


def signal_error_rate(cfg: OpticalLinkConfig) -> float:
    """Error rate on genuine signal photons, including intercept-resend errors."""
    e_d = cfg.misalignment_error
    f = cfg.intercept_resend_fraction
    return (1.0 - f) * e_d + f * (0.25 + 0.5 * e_d)


def optical_link_metrics(range_m: float, elevation_deg: float, cfg: OpticalLinkConfig) -> dict:
    """Return optical quantum channel metrics for a given slant range and elevation.

    Parameters
    ----------
    range_m : float
        Slant range from satellite to ground, meters.
    elevation_deg : float
        Ground-station elevation angle to satellite, degrees.
    cfg : OpticalLinkConfig
        Optical channel parameters.

    Returns
    -------
    dict with keys:
        channel_id             : 'quantum_optical'
        available              : bool — True when signal count is positive
        total_loss_db          : total channel loss, dB (positive means loss)
        geometric_loss_db      : free-space geometric/diffraction loss, dB
        atmospheric_loss_db    : slant-path atmospheric attenuation, dB
        pointing_loss_db       : telescope pointing residual loss, dB
        optical_efficiency_loss_db : optics/filter insertion loss, dB
        channel_transmittance  : fraction (linear) of photons received per emitted photon
        signal_count_hz        : detected signal clicks per second
        background_count_hz    : accepted (gated) background + dark clicks per second
        total_count_hz         : signal + background per second
        gate_duty_cycle        : fraction of time detectors accept clicks
        signal_error_rate      : error rate on signal photons (misalignment + interception)
        qber                   : quantum bit error rate (0–0.5); 0.5 = unusable
        sifted_count_hz        : sifted detection rate after basis reconciliation, Hz
        single_photon_fraction : fraction of detections from single-photon pulses (decoy-state bound)
        single_photon_qber     : error rate of single-photon detections (decoy-state bound)
        intercept_resend_fraction : intercepted fraction used for this sample
        link_usable            : bool — True when QBER < 0.11 (BB84 positive-key threshold)
    """
    cfg.validate()
    if range_m <= 0:
        raise ValueError("range_m must be positive")

    duty = gate_duty_cycle(cfg)
    background_count_hz = (cfg.dark_counts_hz + cfg.sky_background_hz) * duty
    e_sig = signal_error_rate(cfg)

    if cfg.cloud_blocked:
        return {
            "channel_id": "quantum_optical",
            "available": False,
            "total_loss_db": float('inf'),
            "geometric_loss_db": float('inf'),
            "atmospheric_loss_db": float('inf'),
            "pointing_loss_db": cfg.pointing_loss_db,
            "optical_efficiency_loss_db": cfg.optical_efficiency_loss_db,
            "channel_transmittance": 0.0,
            "signal_count_hz": 0.0,
            "background_count_hz": background_count_hz,
            "total_count_hz": background_count_hz,
            "gate_duty_cycle": duty,
            "signal_error_rate": e_sig,
            "qber": 0.5,
            "sifted_count_hz": 0.0,
            "single_photon_fraction": 0.0,
            "single_photon_qber": 0.5,
            "intercept_resend_fraction": cfg.intercept_resend_fraction,
            "link_usable": False,
            "blocked_reason": "cloud_blocked",
        }

    geo_loss = geometric_loss_db(range_m, cfg)
    atm_loss = atmospheric_loss_db(elevation_deg, cfg)
    total_loss_db = geo_loss + atm_loss + cfg.pointing_loss_db + cfg.optical_efficiency_loss_db

    # Linear channel transmittance (photons received per photon emitted)
    channel_transmittance = min(10.0 ** (-total_loss_db / 10.0), 1.0)
    eta_sys = channel_transmittance * cfg.detector_efficiency

    mu = cfg.mean_photon_number
    if mu > 0:
        signal_count_hz = cfg.source_rate_hz * -math.expm1(-mu * eta_sys)
    else:
        signal_count_hz = cfg.source_rate_hz * eta_sys

    total_count = signal_count_hz + background_count_hz
    if total_count > 0:
        qber = (e_sig * signal_count_hz + 0.5 * background_count_hz) / total_count
    else:
        qber = 0.5
    qber = min(qber, 0.5)

    sifted_count_hz = total_count * cfg.sifting_fraction

    # Single-photon contribution (infinite-decoy limit)
    y0 = background_count_hz / cfg.source_rate_hz
    y1 = y0 + eta_sys
    e1 = min(0.5, (0.5 * y0 + e_sig * eta_sys) / y1) if y1 > 0 else 0.5
    if mu > 0:
        q_mu = total_count / cfg.source_rate_hz
        single_photon_fraction = min(1.0, y1 * mu * math.exp(-mu) / q_mu) if q_mu > 0 else 0.0
    else:
        # Ideal single-photon source: every click comes from a ≤1-photon pulse.
        single_photon_fraction = 1.0
        e1 = qber

    return {
        "channel_id": "quantum_optical",
        "available": signal_count_hz > 0,
        "total_loss_db": total_loss_db,
        "geometric_loss_db": geo_loss,
        "atmospheric_loss_db": atm_loss,
        "pointing_loss_db": cfg.pointing_loss_db,
        "optical_efficiency_loss_db": cfg.optical_efficiency_loss_db,
        "channel_transmittance": channel_transmittance,
        "signal_count_hz": signal_count_hz,
        "background_count_hz": background_count_hz,
        "total_count_hz": total_count,
        "gate_duty_cycle": duty,
        "signal_error_rate": e_sig,
        "qber": qber,
        "sifted_count_hz": sifted_count_hz,
        "single_photon_fraction": single_photon_fraction,
        "single_photon_qber": e1,
        "intercept_resend_fraction": cfg.intercept_resend_fraction,
        "link_usable": qber < 0.11,
    }

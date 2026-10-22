"""Optical quantum channel model for the quantum_optical channel.

Models free-space optical (FSO) beam propagation and single-photon detector response
for a downward-looking satellite QKD transmitter.  All loss terms are additive in dB.

Channel ID: quantum_optical

Physical model
--------------
Total channel loss (dB) = FSPL_optical + atmospheric_loss + pointing_loss + optical_efficiency_loss

  FSPL_optical: Gaussian beam diffraction loss to a finite-aperture receiver.
    η_geo = (π D_rx² / 4) / (π (θ_div R)²) where D_rx is receiver diameter,
    θ_div is half-angle beam divergence, R is slant range.
    Written in dB: FSPL_optical = 20 log10(θ_div R / (D_rx/2))   [approx; far-field]

  atmospheric_loss: zenith loss scaled by secant(zenith angle) ≈ 1/sin(elevation).
    Clipped to a maximum airmass of 10 to avoid divergence at very low elevation.

  pointing_loss: fixed jitter/bias loss from telescope mount and ACS residuals.

  optical_efficiency_loss: transmission of telescope optics, filters, and fibers.

Detection model
---------------
  signal_count_hz = source_rate_hz * η_channel * detector_efficiency
  background_count_hz = dark_counts_hz + sky_background_hz
  QBER ≈ misalignment_error + background_count_hz / (signal_count_hz + background_count_hz)
         capped at 0.5 (link is useless above 0.25 for BB84)

  "Raw" sifted count = signal_count_hz * sifting_fraction (0.5 for BB84 basis reconciliation)

Limitations
-----------
- Far-field Gaussian beam only; near-field or truncated-beam effects are not modeled.
- Partial cloud cover, seeing conditions, and wavelength-dependent atmosphere not modeled.
- Sky background uses a configurable scalar, not a sky-radiance or solar-angle model.
- Detector dead time, afterpulsing, and photon-number statistics are not modeled.
- Full umbra eclipse does not change atmospheric loss (conservative).
- Polarization, mode-matching, and wavefront-error losses are folded into optical_efficiency_loss.

References
----------
Liao et al. (2017) "Satellite-to-ground quantum key distribution",
  Nature 549, 43–47. (Micius link budget)
Bourgoin et al. (2015) "A comprehensive design and performance analysis of LEO
  satellite quantum communication", New J. Phys. 17, 023003.
"""
from dataclasses import dataclass
import math


@dataclass
class OpticalLinkConfig:
    """All configurable optical quantum channel parameters with explicit units."""

    # Source
    source_rate_hz: float = 1e8          # photons/s (mean, per pulse slot for WCP)
    wavelength_m: float = 785e-9         # m  (free-space QKD ~780-850 nm or 1550 nm)

    # Transmitter optics (satellite)
    tx_aperture_m: float = 0.10          # m  transmit telescope diameter
    beam_divergence_half_angle_rad: float = 10e-6  # rad  half-angle; 10 µrad for 10 cm aperture

    # Receiver optics (ground)
    rx_aperture_m: float = 1.0           # m  receive telescope diameter (1 m class)
    optical_efficiency: float = 0.50     # fraction of photons through optics/filters (0–1)

    # Detector
    detector_efficiency: float = 0.30   # single-photon detector efficiency (0–1)
    dark_counts_hz: float = 100.0        # dark counts per second
    sky_background_hz: float = 1000.0   # sky background counts per second (daytime high estimate)
    timing_resolution_s: float = 1e-9   # coincidence window width, s

    # Loss contributions
    zenith_atmospheric_loss_db: float = 1.0  # dB  clear-sky zenith loss
    pointing_loss_db: float = 3.0        # dB  ACS + fine-steering residual
    optical_efficiency_loss_db: float = 3.0  # dB  10*log10(1/optical_efficiency) override

    # Protocol
    sifting_fraction: float = 0.5        # BB84 basis-match fraction
    misalignment_error: float = 0.01     # fractional contribution to QBER from polarization/phase errors

    # Atmospheric clipping
    max_airmass: float = 10.0

    def validate(self):
        for name, val in [('source_rate_hz', self.source_rate_hz),
                          ('wavelength_m', self.wavelength_m),
                          ('tx_aperture_m', self.tx_aperture_m),
                          ('rx_aperture_m', self.rx_aperture_m)]:
            if val <= 0 or not math.isfinite(val):
                raise ValueError(f"{name} must be positive and finite")
        for name, val in [('detector_efficiency', self.detector_efficiency),
                          ('optical_efficiency', self.optical_efficiency),
                          ('sifting_fraction', self.sifting_fraction)]:
            if not (0.0 < val <= 1.0):
                raise ValueError(f"{name} must be in (0, 1]")
        if self.misalignment_error < 0 or self.misalignment_error >= 0.5:
            raise ValueError("misalignment_error must be in [0, 0.5)")
        if self.dark_counts_hz < 0 or self.sky_background_hz < 0:
            raise ValueError("dark and sky background counts must be nonnegative")
        if self.beam_divergence_half_angle_rad <= 0:
            raise ValueError("beam divergence must be positive")
        return self


_SPEED_OF_LIGHT = 299_792_458.0


def geometric_loss_db(range_m: float, cfg: OpticalLinkConfig) -> float:
    """Far-field Gaussian beam geometric loss in dB.

    η_geo = (D_rx / 2)² / (θ_div * R)²
    loss_db = -10 log10(η_geo)  [positive, increasing with range]
    """
    beam_radius_at_rx = cfg.beam_divergence_half_angle_rad * range_m
    rx_radius = cfg.rx_aperture_m / 2.0
    if beam_radius_at_rx <= 0:
        return 0.0
    eta = (rx_radius / beam_radius_at_rx) ** 2
    eta = min(eta, 1.0)  # aperture cannot collect more than the full beam
    return -10.0 * math.log10(eta)


def atmospheric_loss_db(elevation_deg: float, cfg: OpticalLinkConfig) -> float:
    """Slant-path atmospheric loss from zenith loss scaled by airmass.

    airmass ≈ 1 / sin(elevation), clipped to max_airmass.
    """
    elev_rad = math.radians(max(elevation_deg, 0.1))
    airmass = min(1.0 / math.sin(elev_rad), cfg.max_airmass)
    return cfg.zenith_atmospheric_loss_db * airmass


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
        available              : bool — True when signal count exceeds minimum threshold
        total_loss_db          : total channel loss, dB (positive means loss)
        geometric_loss_db      : free-space geometric/diffraction loss, dB
        atmospheric_loss_db    : slant-path atmospheric attenuation, dB
        pointing_loss_db       : telescope pointing residual loss, dB
        optical_efficiency_loss_db : optics/filter insertion loss, dB
        channel_transmittance  : fraction (linear) of photons received per emitted photon
        signal_count_hz        : detected signal photons per second
        background_count_hz    : total background + dark counts per second
        total_count_hz         : signal + background per second
        qber                   : quantum bit error rate (0–0.5); 0.5 = unusable
        sifted_count_hz        : raw sifted detection rate after basis reconciliation, Hz
        link_usable            : bool — True when QBER < 0.25 (BB84 security threshold)
    """
    cfg.validate()
    if range_m <= 0:
        raise ValueError("range_m must be positive")

    geo_loss = geometric_loss_db(range_m, cfg)
    atm_loss = atmospheric_loss_db(elevation_deg, cfg)
    total_loss_db = geo_loss + atm_loss + cfg.pointing_loss_db + cfg.optical_efficiency_loss_db

    # Linear channel transmittance (photons received per photon emitted)
    channel_transmittance = 10.0 ** (-total_loss_db / 10.0)
    channel_transmittance = min(channel_transmittance, 1.0)  # clamp numerical noise

    # Detected signal rate (photons/s)
    signal_count_hz = cfg.source_rate_hz * channel_transmittance * cfg.detector_efficiency
    signal_count_hz = max(signal_count_hz, 0.0)

    # Background counts
    background_count_hz = cfg.dark_counts_hz + cfg.sky_background_hz

    # QBER: misalignment + background fraction
    total_count = signal_count_hz + background_count_hz
    if total_count > 0:
        qber = cfg.misalignment_error + background_count_hz / total_count
    else:
        qber = 0.5
    qber = min(qber, 0.5)

    # Sifted rate (basis reconciliation; 0.5 for BB84)
    sifted_count_hz = signal_count_hz * cfg.sifting_fraction

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
        "qber": qber,
        "sifted_count_hz": sifted_count_hz,
        "link_usable": qber < 0.25,
    }

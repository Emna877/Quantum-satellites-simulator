"""Validation of the optical/QKD models against the Micius satellite experiment.

Reference: Liao, S.-K. et al. (2017) "Satellite-to-ground quantum key
distribution", Nature 549, 43–47; arXiv:1707.00542.

Published inputs used below (paper section in brackets):
  - 848.6 nm, 100 MHz pulses; μs = 0.8, μ1 = 0.1, μ2 = 0 sent with
    probabilities 50 / 25 / 25 %                     [Experimental procedure]
  - 300 mm transmitter, ~10 µrad far-field divergence; 1 m receiver;
    diffraction loss "estimated to be 22 dB at 1200 km"   [Challenges]
  - atmospheric absorption + turbulence 3–8 dB at 1200 km; pointing < 3 dB
  - overall receive optical efficiency ~16 %; detector efficiency 50 %,
    dark counts < 25 Hz (four detectors); 2 ns timing window
  - polarization contrast 280:1 after compensation (misalignment ≈ 1/281)
  - satellite altitude ~500 km

Published results compared against:
  - sifted key rate ~12 kbit/s at 645 km and ~1 kbit/s at 1200 km
  - QBER average 1.1 %, 1–3 % over 23 days
  - 1,671,072 sifted bits and 300,939 final bits in a 273 s pass at failure
    probability 1e-9

Assumption not stated in the paper: night-time sky/stray-light rate before
gating, set to 500 counts/s.  Tolerances are deliberately wide (factor 2 on
rates, ±50 % on final key): the paper gives loss ranges, not exact values.
"""
import math
import unittest

from communication.optical_link import OpticalLinkConfig, optical_link_metrics, geometric_loss_db
from security.qkd_finite_key import BB84FiniteKeyConfig, bb84_finite_key_metrics

EARTH_RADIUS_M = 6371e3
MICIUS_ALTITUDE_M = 500e3


def elevation_for_range(range_m, altitude_m=MICIUS_ALTITUDE_M):
    """Elevation (deg) at which a satellite at altitude_m is seen at slant range_m."""
    r_sat = EARTH_RADIUS_M + altitude_m
    sin_e = (r_sat ** 2 - EARTH_RADIUS_M ** 2 - range_m ** 2) / (2 * EARTH_RADIUS_M * range_m)
    return math.degrees(math.asin(sin_e))


def micius_config(divergence_half_angle_rad):
    elev_1200 = elevation_for_range(1200e3)
    return OpticalLinkConfig(
        source_rate_hz=1e8,
        mean_photon_number=0.5 * 0.8 + 0.25 * 0.1,   # average over signal/decoy/vacuum slots
        wavelength_m=848.6e-9,
        tx_aperture_m=0.30,
        beam_divergence_half_angle_rad=divergence_half_angle_rad,
        rx_aperture_m=1.0,
        detector_efficiency=0.50,
        dark_counts_hz=4 * 25.0,
        sky_background_hz=500.0,
        timing_resolution_s=2e-9,
        # midpoint of the stated 3–8 dB atmospheric loss at 1200 km
        zenith_atmospheric_loss_db=5.5 * math.sin(math.radians(elev_1200)),
        pointing_loss_db=3.0,
        optical_efficiency_loss_db=-10 * math.log10(0.16),
        misalignment_error=1 / 281,
    )


# Half-angle that reproduces the paper's own 22 dB diffraction estimate at 1200 km
PAPER_BUDGET_DIVERGENCE = 7.41e-6
# Half-angle from the quoted ~10 µrad (full-angle) far-field divergence
QUOTED_DIVERGENCE = 5e-6


class MiciusLinkBudgetTests(unittest.TestCase):

    def test_ideal_gaussian_diffraction_is_within_4_db_of_paper_estimate(self):
        # An ideal Gaussian beam is optimistic compared with a real telescope
        # (M² > 1, obscuration, wavefront error), so the model gives less loss.
        loss = geometric_loss_db(1200e3, micius_config(QUOTED_DIVERGENCE))
        self.assertLess(loss, 22.0)
        self.assertGreater(loss, 22.0 - 4.0)

    def test_paper_budget_reproduces_22_db_diffraction(self):
        loss = geometric_loss_db(1200e3, micius_config(PAPER_BUDGET_DIVERGENCE))
        self.assertAlmostEqual(loss, 22.0, delta=0.1)

    def test_sifted_rates_within_factor_two(self):
        cfg = micius_config(PAPER_BUDGET_DIVERGENCE)
        for range_m, measured in ((645e3, 12e3), (1200e3, 1e3)):
            with self.subTest(range_km=range_m / 1e3):
                m = optical_link_metrics(range_m, elevation_for_range(range_m), cfg)
                ratio = m['sifted_count_hz'] / measured
                self.assertGreater(ratio, 0.5)
                self.assertLess(ratio, 2.0)

    def test_qber_in_measured_range(self):
        cfg = micius_config(PAPER_BUDGET_DIVERGENCE)
        for range_m in (645e3, 900e3, 1200e3):
            with self.subTest(range_km=range_m / 1e3):
                m = optical_link_metrics(range_m, elevation_for_range(range_m), cfg)
                self.assertGreater(m['qber'], 0.003)
                self.assertLess(m['qber'], 0.03)


class MiciusFiniteKeyTests(unittest.TestCase):

    def test_final_key_for_reported_pass_within_50_percent(self):
        # 1,671,072 sifted bits, QBER 1.1 %, 273 s, failure probability 1e-9
        cfg = BB84FiniteKeyConfig(wcp_mean_photon_number=0.8, eps_sec=1e-9)
        r = bb84_finite_key_metrics(1671072 / 273, 0.011, 273.0, cfg)
        self.assertEqual(r['key_status'], 'succeeded')
        ratio = r['secure_key_bits'] / 300939
        self.assertGreater(ratio, 0.5)
        self.assertLess(ratio, 1.5)


if __name__ == '__main__':
    unittest.main()

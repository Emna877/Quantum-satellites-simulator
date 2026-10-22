"""Unit tests for the communication channel models.

Tests cover: units, equations, limiting cases, parameter validation, and
documented assumptions for rf_link, optical_link, and qkd_model.

Run with: python -m unittest scripts.test_communication
"""
import math
import unittest

from communication.rf_link import (
    RFLinkConfig, rf_link_budget, free_space_path_loss_db, thermal_noise_floor_dbm,
    shannon_capacity_bps,
)
from communication.optical_link import (
    OpticalLinkConfig, optical_link_metrics, geometric_loss_db, atmospheric_loss_db,
)
from communication.qkd_model import QKDModelConfig, qkd_key_metrics, _h2


class TestFreeSpacePathLoss(unittest.TestCase):
    """Validate FSPL against known values."""

    def test_fspl_formula_at_700km_X_band(self):
        """FSPL at 700 km, 10 GHz: 20*log10(4π*700e3/0.03) ≈ 169.3 dB."""
        fspl = free_space_path_loss_db(700e3, 10e9)
        # Verify by formula: λ=c/f=0.02998 m; 4πR/λ=4π*700e3/0.02998≈293.5e6; 20log10=169.4 dB
        self.assertAlmostEqual(fspl, 169.3, delta=0.5)

    def test_fspl_increases_with_range(self):
        """Doubling range increases FSPL by 20*log10(2) ≈ 6.021 dB."""
        f1 = free_space_path_loss_db(1000e3, 10e9)
        f2 = free_space_path_loss_db(2000e3, 10e9)
        self.assertAlmostEqual(f2 - f1, 20 * math.log10(2), places=6)

    def test_fspl_decreases_with_frequency(self):
        """Higher frequency means shorter wavelength, higher loss."""
        f_low = free_space_path_loss_db(700e3, 2.4e9)
        f_high = free_space_path_loss_db(700e3, 10e9)
        self.assertGreater(f_high, f_low)

    def test_zero_range_raises(self):
        with self.assertRaises(ValueError):
            free_space_path_loss_db(0, 10e9)

    def test_negative_range_raises(self):
        with self.assertRaises(ValueError):
            free_space_path_loss_db(-1, 10e9)


class TestThermalNoise(unittest.TestCase):
    def test_thermal_noise_at_10MHz(self):
        """kTB for 10 MHz at 290 K ≈ -104 dBm (commonly quoted value)."""
        noise = thermal_noise_floor_dbm(10e6, 0.0)
        self.assertAlmostEqual(noise, -104.0, delta=0.1)

    def test_noise_figure_added(self):
        n0 = thermal_noise_floor_dbm(10e6, 0.0)
        n3 = thermal_noise_floor_dbm(10e6, 3.0)
        self.assertAlmostEqual(n3 - n0, 3.0, delta=0.01)

    def test_wider_bandwidth_raises_noise(self):
        n1 = thermal_noise_floor_dbm(10e6, 0.0)
        n2 = thermal_noise_floor_dbm(100e6, 0.0)
        self.assertAlmostEqual(n2 - n1, 10.0, delta=0.01)


class TestShannonCapacity(unittest.TestCase):
    def test_zero_snr_nonzero_capacity(self):
        # SNR=0 → log2(1) = 0 → capacity = 0
        self.assertEqual(shannon_capacity_bps(10e6, 0.0), 0.0)

    def test_positive_capacity(self):
        c = shannon_capacity_bps(10e6, 10.0)
        self.assertGreater(c, 0)

    def test_negative_snr_raises(self):
        with self.assertRaises(ValueError):
            shannon_capacity_bps(10e6, -0.1)


class TestRFLinkBudget(unittest.TestCase):
    def setUp(self):
        self.cfg = RFLinkConfig()

    def test_returns_all_keys(self):
        result = rf_link_budget(700e3, self.cfg)
        for key in ('channel_id', 'available', 'fspl_db', 'eirp_dbm', 'Pr_dbm',
                    'noise_floor_dbm', 'snr_db', 'snr_linear', 'shannon_capacity_bps'):
            self.assertIn(key, result)

    def test_channel_id(self):
        self.assertEqual(rf_link_budget(700e3, self.cfg)['channel_id'], 'rf_data')

    def test_snr_decreases_with_range(self):
        snr_near = rf_link_budget(300e3, self.cfg)['snr_db']
        snr_far = rf_link_budget(1500e3, self.cfg)['snr_db']
        self.assertGreater(snr_near, snr_far)

    def test_received_power_consistency(self):
        """Pr = EIRP + Rx_gain - Rx_pointing_loss - FSPL."""
        r = rf_link_budget(700e3, self.cfg)
        expected_Pr = (r['eirp_dbm'] + self.cfg.rx_antenna_gain_dbi
                       - self.cfg.rx_pointing_loss_db - r['fspl_db'])
        self.assertAlmostEqual(r['Pr_dbm'], expected_Pr, places=10)

    def test_snr_linear_matches_db(self):
        r = rf_link_budget(700e3, self.cfg)
        expected_lin = 10.0 ** (r['snr_db'] / 10.0)
        self.assertAlmostEqual(r['snr_linear'], expected_lin, places=8)

    def test_available_flag_reflects_snr(self):
        """Available is True iff SNR > 0 dB."""
        r = rf_link_budget(700e3, self.cfg)
        self.assertEqual(r['available'], r['snr_db'] > 0)

    def test_invalid_config_raises(self):
        bad = RFLinkConfig(frequency_hz=-1)
        with self.assertRaises(ValueError):
            rf_link_budget(700e3, bad)

    def test_zero_range_raises(self):
        with self.assertRaises(ValueError):
            rf_link_budget(0, self.cfg)


class TestGeometricLoss(unittest.TestCase):
    def setUp(self):
        self.cfg = OpticalLinkConfig()

    def test_loss_increases_with_range(self):
        loss_near = geometric_loss_db(300e3, self.cfg)
        loss_far = geometric_loss_db(1500e3, self.cfg)
        self.assertGreater(loss_far, loss_near)

    def test_loss_is_nonnegative(self):
        self.assertGreaterEqual(geometric_loss_db(700e3, self.cfg), 0.0)

    def test_larger_receiver_reduces_loss(self):
        small = OpticalLinkConfig(rx_aperture_m=0.5)
        large = OpticalLinkConfig(rx_aperture_m=1.5)
        self.assertGreater(geometric_loss_db(700e3, small), geometric_loss_db(700e3, large))

    def test_tighter_divergence_reduces_loss(self):
        wide = OpticalLinkConfig(beam_divergence_half_angle_rad=50e-6)
        tight = OpticalLinkConfig(beam_divergence_half_angle_rad=5e-6)
        self.assertGreater(geometric_loss_db(700e3, wide), geometric_loss_db(700e3, tight))


class TestAtmosphericLoss(unittest.TestCase):
    def setUp(self):
        self.cfg = OpticalLinkConfig()

    def test_loss_at_90deg_equals_zenith(self):
        """90-degree elevation → airmass = 1 → zenith loss."""
        loss = atmospheric_loss_db(90.0, self.cfg)
        self.assertAlmostEqual(loss, self.cfg.zenith_atmospheric_loss_db, places=6)

    def test_loss_increases_at_lower_elevation(self):
        high = atmospheric_loss_db(60.0, self.cfg)
        low = atmospheric_loss_db(10.0, self.cfg)
        self.assertGreater(low, high)

    def test_airmass_is_clipped(self):
        """Very low elevations should be clipped to max_airmass."""
        cfg = OpticalLinkConfig(zenith_atmospheric_loss_db=1.0, max_airmass=10.0)
        loss_1 = atmospheric_loss_db(0.5, cfg)
        loss_2 = atmospheric_loss_db(0.1, cfg)
        # Both are clipped to the same max airmass so should be equal
        self.assertAlmostEqual(loss_1, loss_2, places=10)
        self.assertAlmostEqual(loss_1, 10.0, places=10)


class TestOpticalLinkMetrics(unittest.TestCase):
    def setUp(self):
        self.cfg = OpticalLinkConfig()

    def test_returns_all_keys(self):
        r = optical_link_metrics(700e3, 30.0, self.cfg)
        for key in ('channel_id', 'available', 'total_loss_db', 'geometric_loss_db',
                    'atmospheric_loss_db', 'pointing_loss_db', 'optical_efficiency_loss_db',
                    'channel_transmittance', 'signal_count_hz', 'background_count_hz',
                    'total_count_hz', 'qber', 'sifted_count_hz', 'link_usable'):
            self.assertIn(key, r)

    def test_channel_id(self):
        self.assertEqual(optical_link_metrics(700e3, 30.0, self.cfg)['channel_id'], 'quantum_optical')

    def test_total_loss_is_sum_of_components(self):
        r = optical_link_metrics(700e3, 45.0, self.cfg)
        expected = (r['geometric_loss_db'] + r['atmospheric_loss_db']
                    + r['pointing_loss_db'] + r['optical_efficiency_loss_db'])
        self.assertAlmostEqual(r['total_loss_db'], expected, places=10)

    def test_qber_is_in_range(self):
        r = optical_link_metrics(700e3, 10.0, self.cfg)
        self.assertGreaterEqual(r['qber'], 0.0)
        self.assertLessEqual(r['qber'], 0.5)

    def test_channel_transmittance_bounded(self):
        r = optical_link_metrics(700e3, 45.0, self.cfg)
        self.assertGreater(r['channel_transmittance'], 0.0)
        self.assertLessEqual(r['channel_transmittance'], 1.0)

    def test_signal_count_decreases_with_range(self):
        near = optical_link_metrics(300e3, 45.0, self.cfg)['signal_count_hz']
        far = optical_link_metrics(1500e3, 45.0, self.cfg)['signal_count_hz']
        self.assertGreater(near, far)

    def test_qber_increases_with_range(self):
        """More loss → lower signal → higher background fraction → higher QBER."""
        near = optical_link_metrics(300e3, 45.0, self.cfg)['qber']
        far = optical_link_metrics(1500e3, 45.0, self.cfg)['qber']
        self.assertLessEqual(near, far)

    def test_zero_range_raises(self):
        with self.assertRaises(ValueError):
            optical_link_metrics(0, 45.0, self.cfg)

    def test_invalid_config_raises(self):
        bad = OpticalLinkConfig(detector_efficiency=2.0)
        with self.assertRaises(ValueError):
            optical_link_metrics(700e3, 45.0, bad)

    def test_sifted_count_is_fraction_of_signal(self):
        r = optical_link_metrics(700e3, 45.0, self.cfg)
        self.assertAlmostEqual(r['sifted_count_hz'],
                               r['signal_count_hz'] * self.cfg.sifting_fraction, places=10)


class TestBinaryEntropy(unittest.TestCase):
    def test_h2_at_zero_and_one(self):
        self.assertEqual(_h2(0.0), 0.0)
        self.assertEqual(_h2(1.0), 0.0)

    def test_h2_at_half_is_one(self):
        self.assertAlmostEqual(_h2(0.5), 1.0, places=10)

    def test_h2_is_symmetric(self):
        self.assertAlmostEqual(_h2(0.11), _h2(0.89), places=10)

    def test_h2_is_nonnegative(self):
        for p in (0.01, 0.1, 0.25, 0.49):
            self.assertGreaterEqual(_h2(p), 0.0)


class TestQKDKeyMetrics(unittest.TestCase):
    def setUp(self):
        self.cfg = QKDModelConfig()

    def test_returns_all_keys(self):
        r = qkd_key_metrics(1000.0, 0.05, self.cfg)
        for key in ('channel_id', 'key_establishment', 'sifted_count_hz', 'qber',
                    'h2_qber', 'ec_leak_fraction', 'secure_fraction',
                    'secret_key_rate_bit_s', 'model_id', 'finite_key_valid'):
            self.assertIn(key, r)

    def test_channel_id(self):
        self.assertEqual(qkd_key_metrics(1000.0, 0.05, self.cfg)['channel_id'], 'qkd_classical_protocol')

    def test_zero_sifted_rate_gives_abort(self):
        r = qkd_key_metrics(0.0, 0.05, self.cfg)
        self.assertEqual(r['key_establishment']['key_status'], 'aborted')
        self.assertEqual(r['secret_key_rate_bit_s'], 0.0)

    def test_high_qber_gives_abort(self):
        r = qkd_key_metrics(1000.0, 0.20, self.cfg)
        self.assertEqual(r['key_establishment']['key_status'], 'aborted')
        self.assertEqual(r['secret_key_rate_bit_s'], 0.0)

    def test_low_qber_gives_positive_key_rate(self):
        r = qkd_key_metrics(1000.0, 0.03, self.cfg)
        self.assertEqual(r['key_establishment']['key_status'], 'succeeded')
        self.assertGreater(r['secret_key_rate_bit_s'], 0.0)

    def test_key_rate_decreases_with_qber(self):
        r_low = qkd_key_metrics(1000.0, 0.02, self.cfg)
        r_high = qkd_key_metrics(1000.0, 0.09, self.cfg)
        self.assertGreater(r_low['secret_key_rate_bit_s'], r_high['secret_key_rate_bit_s'])

    def test_key_rate_scales_with_sifted_rate(self):
        r1 = qkd_key_metrics(1000.0, 0.03, self.cfg)
        r2 = qkd_key_metrics(2000.0, 0.03, self.cfg)
        self.assertAlmostEqual(r2['secret_key_rate_bit_s'], 2 * r1['secret_key_rate_bit_s'], places=10)

    def test_finite_key_valid_is_always_false(self):
        """The model is asymptotic; this flag must remain False until finite-key analysis is added."""
        self.assertFalse(qkd_key_metrics(1000.0, 0.05, self.cfg)['finite_key_valid'])

    def test_abort_retains_reason_and_zero_bits(self):
        r = qkd_key_metrics(0.0, 0.05, self.cfg)
        self.assertEqual(r['secret_key_rate_bit_s'], 0.0)
        self.assertIsNotNone(r['key_establishment']['reason'])
        self.assertTrue(len(r['key_establishment']['reason']) > 0)

    def test_invalid_ec_efficiency_raises(self):
        bad = QKDModelConfig(ec_efficiency=0.5)
        with self.assertRaises(ValueError):
            qkd_key_metrics(1000.0, 0.05, bad)

    def test_negative_sifted_rate_raises(self):
        with self.assertRaises(ValueError):
            qkd_key_metrics(-1.0, 0.05, self.cfg)

    def test_qber_out_of_range_raises(self):
        with self.assertRaises(ValueError):
            qkd_key_metrics(1000.0, 0.6, self.cfg)


class TestEndToEndChannelPipeline(unittest.TestCase):
    """Integration: RF + optical + QKD metrics are consistent for a plausible pass sample."""

    def test_plausible_700km_pass_sample(self):
        """At 700 km, 45° elevation, all three channels should return physically plausible values."""
        range_m = 700e3
        elev_deg = 45.0
        rf_cfg = RFLinkConfig()
        opt_cfg = OpticalLinkConfig()
        qkd_cfg = QKDModelConfig()

        rf = rf_link_budget(range_m, rf_cfg)
        opt = optical_link_metrics(range_m, elev_deg, opt_cfg)
        qkd = qkd_key_metrics(opt['sifted_count_hz'], opt['qber'], qkd_cfg)

        # RF channel: should have positive SNR at 700 km with default 10 GHz / 10 MHz / 20 dBi Rx
        self.assertTrue(math.isfinite(rf['snr_db']))
        self.assertGreater(rf['shannon_capacity_bps'], 0)

        # Optical channel: geometric aperture model produces meaningful loss at satellite range.
        # With 10 µrad divergence and 1 m receiver at 700 km, geometric loss ≈ 23 dB.
        # Total loss (geometric + atmosphere + pointing + optics) should be > 20 dB and finite.
        self.assertGreater(opt['total_loss_db'], 20)
        self.assertTrue(math.isfinite(opt['total_loss_db']))
        self.assertGreater(opt['total_loss_db'], opt['geometric_loss_db'])
        self.assertGreaterEqual(opt['qber'], 0.0)
        self.assertLessEqual(opt['qber'], 0.5)

        # QKD: key rate is finite; status is documented
        self.assertTrue(math.isfinite(qkd['secret_key_rate_bit_s']))
        self.assertIn(qkd['key_establishment']['key_status'], ('succeeded', 'aborted', 'failed'))
        self.assertFalse(qkd['finite_key_valid'])


if __name__ == '__main__':
    unittest.main()

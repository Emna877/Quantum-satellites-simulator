"""Regression tests for the security/ package.

Covers:
  - ClassicalSessionConfig and classical_key_establishment
  - BB84FiniteKeyConfig and bb84_finite_key_metrics
  - KeyStore and KeyStoreConfig
  - channel_effects: rf_config_with_jamming, optical_config_with_background_increase
  - optical_link: cloud_blocked behaviour

Run:
    python -m unittest scripts.test_security
"""
import math
import unittest

from communication.rf_link import RFLinkConfig, rf_link_budget
from communication.optical_link import OpticalLinkConfig, optical_link_metrics
from communication.channel_effects import (
    rf_config_with_jamming,
    optical_config_with_background_increase,
    optical_config_with_extra_loss,
)
from security.classical_session import ClassicalSessionConfig, classical_key_establishment
from security.qkd_finite_key import BB84FiniteKeyConfig, bb84_finite_key_metrics
from security.key_store import KeyStore, KeyStoreConfig


# ---------------------------------------------------------------------------
# channel_effects tests
# ---------------------------------------------------------------------------

class TestRFConfigWithJamming(unittest.TestCase):

    def test_zero_jamming_is_identity(self):
        base = RFLinkConfig()
        result = rf_config_with_jamming(base, 0.0)
        self.assertEqual(result.rx_pointing_loss_db, base.rx_pointing_loss_db)

    def test_jamming_increases_loss(self):
        base = RFLinkConfig(rx_pointing_loss_db=2.0)
        result = rf_config_with_jamming(base, 10.0)
        self.assertAlmostEqual(result.rx_pointing_loss_db, 12.0)

    def test_negative_jamming_clamped_to_zero(self):
        base = RFLinkConfig(rx_pointing_loss_db=2.0)
        result = rf_config_with_jamming(base, -5.0)
        self.assertEqual(result.rx_pointing_loss_db, base.rx_pointing_loss_db)

    def test_base_config_not_mutated(self):
        base = RFLinkConfig(rx_pointing_loss_db=2.0)
        _ = rf_config_with_jamming(base, 20.0)
        self.assertEqual(base.rx_pointing_loss_db, 2.0)

    def test_jamming_degrades_snr(self):
        base = RFLinkConfig()
        jammed = rf_config_with_jamming(base, 30.0)
        r = 700e3
        snr_base = rf_link_budget(r, base)['snr_db']
        snr_jammed = rf_link_budget(r, jammed)['snr_db']
        self.assertLess(snr_jammed, snr_base)
        self.assertAlmostEqual(snr_base - snr_jammed, 30.0, places=6)

    def test_severe_jamming_makes_link_unavailable(self):
        base = RFLinkConfig()
        jammed = rf_config_with_jamming(base, 100.0)
        result = rf_link_budget(700e3, jammed)
        self.assertFalse(result['available'])


class TestOpticalCloudBlocked(unittest.TestCase):

    def test_cloud_blocked_returns_zero_signal(self):
        cfg = OpticalLinkConfig(cloud_blocked=True)
        result = optical_link_metrics(700e3, 45.0, cfg)
        self.assertFalse(result['available'])
        self.assertFalse(result['link_usable'])
        self.assertEqual(result['signal_count_hz'], 0.0)
        self.assertEqual(result['sifted_count_hz'], 0.0)
        self.assertEqual(result['qber'], 0.5)
        self.assertEqual(result['channel_transmittance'], 0.0)
        self.assertEqual(result['blocked_reason'], 'cloud_blocked')

    def test_clear_sky_allows_signal(self):
        cfg = OpticalLinkConfig(cloud_blocked=False)
        result = optical_link_metrics(700e3, 45.0, cfg)
        self.assertTrue(result['available'])
        self.assertGreater(result['signal_count_hz'], 0.0)

    def test_background_increase_raises_qber(self):
        base = OpticalLinkConfig()
        high_bg = optical_config_with_background_increase(base, 100.0)
        r1 = optical_link_metrics(700e3, 45.0, base)
        r2 = optical_link_metrics(700e3, 45.0, high_bg)
        self.assertGreater(r2['qber'], r1['qber'])

    def test_background_scale_below_one_clamped(self):
        base = OpticalLinkConfig()
        result = optical_config_with_background_increase(base, 0.5)
        self.assertEqual(result.sky_background_hz, base.sky_background_hz)

    def test_extra_loss_reduces_signal(self):
        base = OpticalLinkConfig()
        lossy = optical_config_with_extra_loss(base, 10.0)
        r1 = optical_link_metrics(700e3, 45.0, base)
        r2 = optical_link_metrics(700e3, 45.0, lossy)
        self.assertLess(r2['signal_count_hz'], r1['signal_count_hz'])


# ---------------------------------------------------------------------------
# ClassicalSession tests
# ---------------------------------------------------------------------------

class TestClassicalSessionConfig(unittest.TestCase):

    def test_invalid_key_bits(self):
        with self.assertRaises(ValueError):
            ClassicalSessionConfig(session_key_bits=64).validate()

    def test_invalid_session_lifetime(self):
        with self.assertRaises(ValueError):
            ClassicalSessionConfig(session_lifetime_s=0).validate()

    def test_valid_config(self):
        ClassicalSessionConfig().validate()


class TestClassicalKeyEstablishment(unittest.TestCase):

    def _call(self, link=True, snr=20.0, range_m=700e3, duration=600.0, cfg=None):
        return classical_key_establishment(
            link_available=link,
            snr_db=snr,
            range_m=range_m,
            contact_duration_s=duration,
            cfg=cfg or ClassicalSessionConfig(),
        )

    def test_normal_conditions_succeed(self):
        r = self._call()
        self.assertTrue(r['key_established'])
        self.assertIsNone(r['failure_reason'])
        self.assertEqual(r['session_key_bits'], 256)
        self.assertEqual(r['encryption_profile'], 'AES-256-GCM')

    def test_link_unavailable_fails(self):
        r = self._call(link=False)
        self.assertFalse(r['key_established'])
        self.assertIn('unavailable', r['failure_reason'].lower())

    def test_low_snr_fails(self):
        r = self._call(snr=0.0)
        self.assertFalse(r['key_established'])
        self.assertIn('SNR', r['failure_reason'])

    def test_overhead_fraction_in_range(self):
        r = self._call()
        self.assertGreater(r['overhead_fraction'], 0.0)
        self.assertLess(r['overhead_fraction'], 1.0)
        self.assertAlmostEqual(r['overhead_fraction'] + r['usable_payload_fraction'], 1.0, places=10)

    def test_channel_id_correct(self):
        r = self._call()
        self.assertEqual(r['channel_id'], 'classical_session')

    def test_handshake_duration_positive(self):
        r = self._call()
        self.assertGreater(r['handshake_duration_s'], 0.0)

    def test_very_short_contact_fails(self):
        # 0.001 s contact — handshake cannot complete
        r = self._call(duration=0.001)
        self.assertFalse(r['key_established'])

    def test_security_note_present(self):
        r = self._call()
        self.assertIn('legitimate security baseline', r['security_note'])


# ---------------------------------------------------------------------------
# BB84 finite-key tests
# ---------------------------------------------------------------------------

class TestBB84FiniteKeyConfig(unittest.TestCase):

    def test_invalid_ec_efficiency(self):
        with self.assertRaises(ValueError):
            BB84FiniteKeyConfig(ec_efficiency=0.5).validate()

    def test_invalid_eps_sec(self):
        with self.assertRaises(ValueError):
            BB84FiniteKeyConfig(eps_sec=0).validate()

    def test_valid_config(self):
        BB84FiniteKeyConfig().validate()


class TestBB84FiniteKeyMetrics(unittest.TestCase):

    def _call(self, sifted=1e6, qber=0.05, duration=600.0, cfg=None):
        return bb84_finite_key_metrics(
            sifted_count_hz=sifted,
            qber=qber,
            pass_duration_s=duration,
            cfg=cfg or BB84FiniteKeyConfig(),
        )

    def test_zero_sifted_aborts(self):
        r = self._call(sifted=0.0)
        self.assertEqual(r['key_status'], 'aborted')
        self.assertEqual(r['secure_key_bits'], 0.0)
        self.assertFalse(r['finite_key_valid'])

    def test_qber_above_threshold_aborts(self):
        r = self._call(qber=0.12)
        self.assertEqual(r['key_status'], 'aborted')
        self.assertIn('QBER', r['abort_reason'])

    def test_very_few_sifted_bits_aborts(self):
        cfg = BB84FiniteKeyConfig(n_min_sifted=1000)
        r = self._call(sifted=1.0, duration=10.0, cfg=cfg)  # only 10 sifted bits
        self.assertEqual(r['key_status'], 'aborted')

    def test_large_pass_produces_positive_key(self):
        # 10^6 sifted photons/s × 600 s = 6×10^8 sifted bits; well above finite-key crossover
        r = self._call(sifted=1e6, qber=0.05, duration=600.0)
        self.assertEqual(r['key_status'], 'succeeded')
        self.assertGreater(r['secure_key_bits'], 0.0)
        self.assertGreater(r['secure_key_rate_bit_s'], 0.0)
        self.assertTrue(r['finite_key_valid'])

    def test_finite_key_rate_less_than_asymptotic(self):
        # Finite rate should be <= asymptotic rate × n_sifted
        r = self._call(sifted=1e6, qber=0.05, duration=600.0)
        n_sifted = 1e6 * 600.0
        max_asym_bits = n_sifted * r['r_asymptotic']
        self.assertLessEqual(r['secure_key_bits'], max_asym_bits + 1e-6)

    def test_correction_increases_with_security_parameter(self):
        # Tighter security (smaller eps) → larger correction → fewer bits
        cfg_loose = BB84FiniteKeyConfig(eps_sec=1e-3)
        cfg_tight = BB84FiniteKeyConfig(eps_sec=1e-12)
        r_loose = self._call(sifted=1e5, qber=0.05, duration=100.0, cfg=cfg_loose)
        r_tight = self._call(sifted=1e5, qber=0.05, duration=100.0, cfg=cfg_tight)
        self.assertGreaterEqual(r_tight['correction_bits'], r_loose['correction_bits'])

    def test_channel_id_correct(self):
        r = self._call()
        self.assertEqual(r['channel_id'], 'qkd_finite_key')

    def test_finite_key_valid_flag_false_for_small_n(self):
        cfg = BB84FiniteKeyConfig(n_min_sifted=int(1e6))
        # Only 1000 sifted bits total
        r = bb84_finite_key_metrics(10.0, 0.05, 100.0, cfg)
        self.assertFalse(r['finite_key_valid'])

    def test_model_id_present(self):
        r = self._call()
        self.assertEqual(r['model_id'], 'bb84_finite_tomamichel2012')


# ---------------------------------------------------------------------------
# KeyStore tests
# ---------------------------------------------------------------------------

class TestKeyStore(unittest.TestCase):

    def _store(self, capacity=1e6, consumption=1000.0):
        return KeyStore(config=KeyStoreConfig(capacity_bits=capacity,
                                             consumption_rate_bit_s=consumption))

    def test_initial_state_empty(self):
        s = self._store()
        self.assertEqual(s.current_bits, 0.0)
        self.assertEqual(s.fill_fraction, 0.0)

    def test_replenish_adds_bits(self):
        s = self._store()
        added = s.replenish(1000.0, 10.0)
        self.assertEqual(added, 10000.0)
        self.assertEqual(s.current_bits, 10000.0)

    def test_replenish_capped_at_capacity(self):
        s = self._store(capacity=100.0)
        added = s.replenish(1000.0, 10.0)  # would add 10000, but cap is 100
        self.assertEqual(s.current_bits, 100.0)
        self.assertAlmostEqual(added, 100.0)

    def test_consume_reduces_bits(self):
        s = self._store()
        s.replenish(1000.0, 10.0)  # 10000 bits
        result = s.consume(5.0, transmitting=True)  # consume 5000
        self.assertAlmostEqual(s.current_bits, 5000.0)
        self.assertFalse(result['exhausted'])

    def test_exhaustion_recorded(self):
        s = self._store(capacity=1e6, consumption=1000.0)
        s.replenish(1.0, 1.0)  # only 1 bit
        result = s.consume(10.0, transmitting=True)  # demand 10000
        self.assertTrue(result['exhausted'])
        self.assertEqual(s.exhaustion_count, 1)

    def test_no_consumption_when_not_transmitting(self):
        s = self._store()
        s.replenish(1000.0, 10.0)
        before = s.current_bits
        result = s.consume(100.0, transmitting=False)
        self.assertEqual(s.current_bits, before)
        self.assertFalse(result['exhausted'])

    def test_update_replenish_then_consume(self):
        s = self._store(consumption=100.0)
        result = s.update(dt_s=10.0, replenishment_rate_bit_s=500.0, transmitting=True)
        # added = 5000, consumed = 1000, net = 4000
        self.assertAlmostEqual(s.current_bits, 4000.0)
        self.assertEqual(result['added_bits'], 5000.0)
        self.assertAlmostEqual(result['consumed_bits'], 1000.0)

    def test_snapshot_is_serialisable(self):
        import json
        s = self._store()
        s.replenish(500.0, 2.0)
        snap = s.snapshot()
        json.dumps(snap)  # must not raise

    def test_fill_fraction_bounds(self):
        s = self._store(capacity=100.0)
        s.replenish(100.0, 10.0)
        self.assertAlmostEqual(s.fill_fraction, 1.0)
        s.consume(1000.0)
        self.assertAlmostEqual(s.fill_fraction, 0.0)


# ---------------------------------------------------------------------------
# Scenario catalogue smoke test
# ---------------------------------------------------------------------------

class TestScenarioCatalogue(unittest.TestCase):

    def test_all_scenarios_importable(self):
        from experiments.scenarios import SCENARIOS
        self.assertIn('baseline', SCENARIOS)
        self.assertIn('rf_jamming_moderate', SCENARIOS)
        self.assertIn('optical_cloud_blocked', SCENARIOS)
        self.assertIn('combined_rf_and_optical', SCENARIOS)

    def test_baseline_has_no_disturbances(self):
        from experiments.scenarios import SCENARIOS
        s = SCENARIOS['baseline']
        self.assertEqual(s.rf_signal_loss_db, 0.0)
        self.assertEqual(s.optical_background_scale, 1.0)
        self.assertFalse(s.optical_cloud_blocked)

    def test_rf_jamming_scenario_has_positive_loss(self):
        from experiments.scenarios import SCENARIOS
        s = SCENARIOS['rf_jamming_moderate']
        self.assertGreater(s.rf_signal_loss_db, 0.0)
        self.assertEqual(s.optical_background_scale, 1.0)  # optical unaffected

    def test_optical_block_has_no_rf_loss(self):
        from experiments.scenarios import SCENARIOS
        s = SCENARIOS['optical_cloud_blocked']
        self.assertTrue(s.optical_cloud_blocked)
        self.assertEqual(s.rf_signal_loss_db, 0.0)

    def test_build_events_returns_list(self):
        from datetime import datetime, timezone, timedelta
        from experiments.scenarios import SCENARIOS
        s = SCENARIOS['rf_jamming_moderate']
        start = datetime(2025, 11, 9, 12, 0, 0, tzinfo=timezone.utc)
        end = start + timedelta(minutes=10)
        events = s.build_events(start, end)
        self.assertIsInstance(events, list)


if __name__ == '__main__':
    unittest.main()

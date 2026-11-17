"""Scenario study: results table, uncertainty sweep, detection column, model card."""
from datetime import datetime, timedelta, timezone
import unittest

from experiments.model_card import model_card
from experiments.runner import RunnerConfig
from experiments.scenarios import SCENARIOS
from experiments.study import CachedGeometry, run_study


class _FakePropagator:
    """One 300 s overhead pass at fixed geometry; counts Orekit-style queries."""

    def __init__(self, start):
        self.window = {'start': start, 'end': start + timedelta(seconds=300)}
        self.geometry_calls = 0

    def contact_windows(self, start, end, station, min_elevation_deg):
        return [self.window]

    def station_geometry(self, t, station):
        self.geometry_calls += 1
        return {'range_m': 600e3, 'elev_deg': 60.0, 'azimuth_deg': 0.0}


class ScenarioStudyTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        start = datetime(2025, 11, 9, 12, 0, 0, tzinfo=timezone.utc)
        cls.propagator = _FakePropagator(start)
        cls.study = run_study(cls.propagator, {'name': 'test'}, RunnerConfig(),
                              start, start + timedelta(minutes=10), 30.0)
        cls.rows = {row['scenario_id']: row for row in cls.study['rows']}

    def test_one_row_per_scenario_baseline_first(self):
        self.assertEqual(list(self.rows), list(SCENARIOS))
        self.assertEqual(self.study['rows'][0]['scenario_id'], 'baseline')

    def test_geometry_is_computed_once_for_all_variants(self):
        # 11 samples + 1 mid-pass query, regardless of 13 scenarios × 9 variants
        self.assertLessEqual(self.propagator.geometry_calls, 12)
        self.assertEqual(self.study['sweep']['variants'], 9)

    def test_key_range_brackets_nominal(self):
        for row in self.study['rows']:
            with self.subTest(row=row['scenario_id']):
                self.assertLessEqual(row['qkd_key_bits_min'], row['nominal']['qkd_key_bits'])
                self.assertGreaterEqual(row['qkd_key_bits_max'], row['nominal']['qkd_key_bits'])

    def test_baseline_has_key_and_sessions(self):
        nominal = self.rows['baseline']['nominal']
        self.assertEqual(nominal['ecdh_passes'], 1)
        self.assertEqual(nominal['mlkem_passes'], 1)
        self.assertGreater(nominal['qkd_key_bits'], 0)
        self.assertGreater(self.rows['baseline']['qkd_key_bits_max'], self.rows['baseline']['qkd_key_bits_min'])
        self.assertEqual(self.rows['baseline']['detection']['verdict'], 'baseline')

    def test_full_intercept_is_detected_and_aborted(self):
        row = self.rows['qkd_intercept_resend']
        self.assertEqual(row['detection']['verdict'], 'detected')
        self.assertIn('detected, QKD aborted', row['detection']['text'])
        self.assertEqual(row['qkd_key_bits_max'], 0)
        self.assertEqual(row['nominal']['main_abort_reason'], 'QBER ≥ 11 %')

    def test_partial_intercept_is_noticed(self):
        row = self.rows['qkd_intercept_resend_partial']
        self.assertEqual(row['detection']['verdict'], 'noticed')
        self.assertLess(row['nominal']['qkd_key_bits'], self.rows['baseline']['nominal']['qkd_key_bits'])

    def test_rf_jamming_is_denial_and_blocks_qkd(self):
        row = self.rows['classical_auth_dependency']
        self.assertEqual(row['detection']['verdict'], 'denial')
        self.assertIn('QKD post-processing blocked', row['detection']['text'])
        self.assertEqual(row['nominal']['main_abort_reason'], 'No RF for post-processing')

    def test_cloud_is_availability_not_secrecy(self):
        row = self.rows['optical_cloud_blocked']
        self.assertEqual(row['detection']['verdict'], 'denial')
        self.assertIn('not a secrecy breach', row['detection']['text'])

    def test_spoofing_has_no_modelled_effect(self):
        self.assertEqual(self.rows['gnss_spoofing']['detection']['verdict'], 'none')

    def test_method_lines_are_fair(self):
        lines = {m['id']: m['summary'] for m in self.study['methods']}
        self.assertEqual(lines['ecdh'], 'Breakable by a future quantum computer')
        self.assertEqual(lines['mlkem'], 'Computational, NIST FIPS 203')
        self.assertIn('needs PSK authentication', lines['qkd'])


class CachedGeometryTests(unittest.TestCase):

    def test_repeated_queries_hit_cache(self):
        start = datetime(2025, 11, 9, 12, 0, 0, tzinfo=timezone.utc)
        fake = _FakePropagator(start)
        cached = CachedGeometry(fake)
        for _ in range(3):
            cached.station_geometry(start, {})
        self.assertEqual(fake.geometry_calls, 1)


class ModelCardTests(unittest.TestCase):

    def test_model_card_has_formulas_parameters_and_passing_validation(self):
        card = model_card(RunnerConfig())
        self.assertGreaterEqual(len(card['formulas']), 10)
        self.assertTrue(all(f['source'] for f in card['formulas']))
        names = {p['name'] for p in card['parameters']}
        self.assertIn('Ground antenna gain', names)
        self.assertIn('Secrecy parameter ε_sec', names)
        self.assertTrue(all(row['passed'] for row in card['validation']['rows']))


if __name__ == '__main__':
    unittest.main()

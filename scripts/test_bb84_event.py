"""Event-level BB84 against the formulas, plus each protocol step on its own."""
from datetime import datetime, timedelta, timezone
from dataclasses import replace
import math
import unittest

import numpy as np

from communication.optical_link import OpticalLinkConfig, optical_link_metrics
from security.bb84_protocol import (
    BB84EventConfig, QKDKeyPool, correct_errors, simulate_detections, simulate_pass, toeplitz_hash, _h2,
)
from security.qkd_finite_key import BB84FiniteKeyConfig, bb84_finite_key_metrics

FINITE = BB84FiniteKeyConfig()
DURATION_S = 300.0


def _pass(intercept=0.0, seed=7, range_m=900e3, elevation=45.0):
    cfg = OpticalLinkConfig(intercept_resend_fraction=intercept)
    optical = optical_link_metrics(range_m, elevation, cfg)
    formula = bb84_finite_key_metrics(optical['sifted_count_hz'], optical['qber'], DURATION_S, FINITE)
    event = simulate_pass(optical['signal_count_hz'] * DURATION_S, optical['background_count_hz'] * DURATION_S,
                          cfg.misalignment_error, intercept, FINITE, seed=seed)
    return optical, formula, event


class AgreementWithFormulaTests(unittest.TestCase):
    """The simulation must reproduce the formulas within statistical noise."""

    @classmethod
    def setUpClass(cls):
        cls.optical, cls.formula, cls.event = _pass()

    def test_sifted_count_within_five_sigma(self):
        expected = self.formula['n_sifted_bits']
        self.assertLess(abs(self.event['sifted_bits'] - expected), 5 * math.sqrt(expected))

    def test_measured_qber_within_four_sigma(self):
        q, k = self.optical['qber'], self.event['pe_bits']
        self.assertLess(abs(self.event['qber_measured'] - q), 4 * math.sqrt(q * (1 - q) / k))

    def test_key_produced_and_identical(self):
        self.assertEqual(self.event['key_status'], 'succeeded')
        self.assertTrue(self.event['keys_identical'])
        self.assertEqual(len(self.event['_key_bits']), self.event['secure_key_bits'])

    def test_key_close_to_formula(self):
        # The simulated error correction leaks more than the formula's 1.16 × Shannon,
        # so the simulated key is somewhat shorter, never longer.
        ratio = self.event['secure_key_bits'] / self.formula['secure_key_bits']
        self.assertGreater(ratio, 0.75)
        self.assertLess(ratio, 1.02)

    def test_error_correction_respects_shannon_limit(self):
        efficiency = self.event['error_correction']['efficiency_vs_shannon']
        self.assertGreater(efficiency, 1.0)
        self.assertLess(efficiency, 2.0)


class EavesdroppingTests(unittest.TestCase):

    def test_full_intercept_resend_gives_quarter_errors_and_aborts(self):
        optical, _, event = _pass(intercept=1.0)
        self.assertAlmostEqual(event['qber_measured'], optical['qber'], delta=0.01)
        self.assertGreater(event['qber_measured'], 0.24)
        self.assertEqual(event['key_status'], 'aborted')
        self.assertEqual(len(event['_key_bits']), 0)

    def test_eve_actually_intercepts_the_configured_fraction(self):
        _, _, event = _pass(intercept=0.2)
        fraction = event['intercepted_photons'] / event['signal_detections']
        self.assertAlmostEqual(fraction, 0.2, delta=0.005)

    def test_partial_intercept_shrinks_the_key(self):
        _, _, clean = _pass()
        _, _, attacked = _pass(intercept=0.2)
        self.assertEqual(attacked['key_status'], 'succeeded')
        self.assertLess(attacked['secure_key_bits'], 0.6 * clean['secure_key_bits'])


class ReproducibilityTests(unittest.TestCase):

    def test_same_seed_same_key(self):
        a, b = _pass(seed=3)[2], _pass(seed=3)[2]
        self.assertTrue(np.array_equal(a['_key_bits'], b['_key_bits']))

    def test_different_seed_different_key(self):
        a, b = _pass(seed=3)[2], _pass(seed=4)[2]
        self.assertFalse(np.array_equal(a['_key_bits'][:1000], b['_key_bits'][:1000]))


class ProtocolStepTests(unittest.TestCase):

    def test_sifting_keeps_half(self):
        events = simulate_detections(200_000, 0, 0.0, 0.0, np.random.default_rng(1))
        self.assertAlmostEqual(len(events['alice']) / 200_000, 0.5, delta=0.01)
        self.assertTrue(np.array_equal(events['alice'], events['bob']))   # no noise, no errors

    def test_background_clicks_are_wrong_half_the_time(self):
        events = simulate_detections(0, 200_000, 0.0, 0.0, np.random.default_rng(2))
        self.assertAlmostEqual(float(np.mean(events['alice'] != events['bob'])), 0.5, delta=0.01)

    def test_error_correction_removes_all_errors(self):
        rng = np.random.default_rng(5)
        for q in (0.01, 0.05, 0.09):
            with self.subTest(qber=q):
                alice = rng.integers(0, 2, 200_000, dtype=np.uint8)
                bob = alice ^ (rng.random(200_000) < q).astype(np.uint8)
                result = correct_errors(alice, bob, q, rng, BB84EventConfig())
                self.assertTrue(result['verified'])
                self.assertTrue(np.array_equal(result['bob'], alice))
                # Disclosed parities cannot be fewer than the Shannon limit n·H2(q)
                self.assertGreater(result['leaked_bits'], 200_000 * _h2(float(np.mean(alice != bob))))

    def test_toeplitz_hash_equals_matrix_product(self):
        bits = np.random.default_rng(1).integers(0, 2, 300).astype(np.uint8)
        hashed = toeplitz_hash(bits, 120, np.random.default_rng(9))
        seed = np.random.default_rng(9).integers(0, 2, 300 + 120 - 1)
        matrix = np.array([[seed[i - j + 299] for j in range(300)] for i in range(120)])
        self.assertTrue(np.array_equal(hashed, (matrix @ bits) % 2))

    def test_key_pool_hands_out_256_bit_keys(self):
        pool = QKDKeyPool()
        pool.add(np.ones(600, dtype=np.uint8))
        self.assertEqual(pool.take_key(), b'\xff' * 32)
        self.assertEqual(pool.available_bits, 344)
        with self.assertRaises(ValueError):
            pool.take_key(512)


class _FakePropagator:
    def __init__(self, start):
        self.window = {'start': start, 'end': start + timedelta(seconds=240)}

    def contact_windows(self, start, end, station, min_elevation_deg):
        return [self.window]

    def station_geometry(self, t, station):
        return {'range_m': 700e3, 'elev_deg': 60.0, 'azimuth_deg': 0.0}


class RunnerEventModeTests(unittest.TestCase):

    def _run(self, scenario_key):
        from experiments.runner import ExperimentRunner, RunnerConfig
        from experiments.scenarios import SCENARIOS
        start = datetime(2025, 11, 9, 12, 0, 0, tzinfo=timezone.utc)
        cfg = RunnerConfig(event_mode=True, execute_crypto=True)
        result = ExperimentRunner(_FakePropagator(start), {'name': 'test'}, SCENARIOS[scenario_key], cfg).run(
            start, start + timedelta(minutes=10), dt_s=30.0)
        return result.passes[0]

    def test_photons_to_key_to_encrypted_message(self):
        p = self._run('baseline')
        self.assertEqual(p['qkd_event']['key_status'], 'succeeded')
        self.assertNotIn('_key_bits', p['qkd_event'])                    # bits stay out of the record
        self.assertTrue(p['qkd_exec']['all_attacks_rejected'])
        self.assertEqual(p['qkd_key_pool']['consumed_bits'], 256)
        for name in ('classical_exec', 'pqc_exec'):
            self.assertTrue(p[name]['executed'])
            self.assertTrue(p[name]['all_attacks_rejected'])

    def test_jamming_blocks_execution_and_qkd_key(self):
        p = self._run('classical_auth_dependency')
        self.assertFalse(p['classical_exec']['executed'])
        self.assertFalse(p['pqc_exec']['executed'])
        self.assertEqual(p['qkd_event']['key_status'], 'aborted')
        self.assertIn('Authenticated classical channel', p['qkd_event']['abort_reason'])
        self.assertFalse(p['qkd_exec']['executed'])

    def test_cloud_gives_no_photons(self):
        p = self._run('optical_cloud_blocked')
        self.assertEqual(p['qkd_event']['sifted_bits'], 0)
        self.assertTrue(p['classical_exec']['executed'])


if __name__ == '__main__':
    unittest.main()

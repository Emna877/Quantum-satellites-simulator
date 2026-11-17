"""Validation of the optical/QKD models against the Micius satellite experiment.

The published inputs, results and the one unpublished assumption are listed in
experiments/validation.py, which the console's model card also uses.
"""
import unittest

from communication.optical_link import optical_link_metrics, geometric_loss_db
from experiments.validation import (
    PAPER_BUDGET_DIVERGENCE, QUOTED_DIVERGENCE, elevation_for_range, micius_comparison,
    micius_config, micius_final_key,
)


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
        r = micius_final_key()
        self.assertEqual(r['key_status'], 'succeeded')
        ratio = r['secure_key_bits'] / 300939
        self.assertGreater(ratio, 0.5)
        self.assertLess(ratio, 1.5)


class MiciusComparisonTableTests(unittest.TestCase):

    def test_every_console_row_passes(self):
        rows = micius_comparison()
        self.assertEqual(len(rows), 5)
        for row in rows:
            with self.subTest(quantity=row['quantity']):
                self.assertTrue(row['passed'], row)


if __name__ == '__main__':
    unittest.main()

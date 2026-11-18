"""Scientific regression checks: python -m unittest scripts.test_orbit."""
from datetime import timedelta, timezone
import math
import unittest

import jpype
import numpy as np
from config import get_simulation_config
from simulation.propagator import OrekitPropagator, iso, sample_offsets, utc, update_state_from_propagator

# Module-level propagator: JPype cannot restart a JVM, so all test classes share one instance.
_shared_runtime = None
_shared_config = None


def setUpModule():
    global _shared_runtime, _shared_config
    _shared_config = get_simulation_config()
    _shared_config['start_time'] = '2025-11-09T12:00:00.123456Z'
    _shared_config['orbit'].update(eccentricity=0.0, inclination_deg=98.0)
    _shared_runtime = OrekitPropagator.from_config(_shared_config)


def tearDownModule():
    if _shared_runtime is not None:
        _shared_runtime.shutdown()


class OrbitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = _shared_config
        cls.runtime = _shared_runtime
        cls.start = cls.runtime.start_time
        cls.station = dict(name='Tunis_GS', lat_deg=36.8, lon_deg=10.18, alt_m=20.0)

    def test_circular_period_radius_speed_and_energy(self):
        p = self.runtime
        radius = self.config['orbit']['semi_major_axis']
        period = 2 * math.pi * math.sqrt(radius**3 / p.mu)
        self.assertAlmostEqual(period, p.period_seconds, places=7)
        energies = []
        for t in np.linspace(0, period, 17):
            pv = p.pv_at(self.start + timedelta(seconds=float(t)), p.gcrf)
            position, velocity = p.array(pv.getPosition()), p.array(pv.getVelocity())
            self.assertAlmostEqual(np.linalg.norm(position), radius, delta=1e-6)
            self.assertAlmostEqual(np.linalg.norm(velocity), math.sqrt(p.mu/radius), delta=1e-6)
            energies.append(np.dot(velocity, velocity)/2-p.mu/np.linalg.norm(position))
        self.assertLess(np.ptp(energies), 1e-6)
        first = p.array(p.pv_at(self.start, p.gcrf).getPosition())
        last = p.array(p.pv_at(self.start+timedelta(seconds=period), p.gcrf).getPosition())
        self.assertLess(np.linalg.norm(last-first), 0.01)

    def test_ecef_velocity_matches_position_derivative(self):
        p = self.runtime
        time = self.start+timedelta(seconds=1234)
        before, _ = p.propagate_at(time-timedelta(seconds=0.1))
        after, _ = p.propagate_at(time+timedelta(seconds=0.1))
        _, velocity = p.propagate_at(time)
        np.testing.assert_allclose((after-before)/0.2, velocity, atol=0.002, rtol=0)

    def test_utc_subseconds_and_nonmutating_queries(self):
        p = self.runtime
        offset_time = self.start.astimezone(timezone(timedelta(hours=1)))
        self.assertEqual(utc(offset_time), self.start)
        date = p.absolute_date(self.start)
        self.assertAlmostEqual(float(date.durationFrom(p.absolute_date(self.start.replace(microsecond=0)))), 0.123456, places=8)
        cursor = p.current_time
        p.state_at(self.start+timedelta(hours=3))
        self.assertEqual(p.current_time, cursor)
        self.assertIn('.123456Z', iso(self.start))

    def test_incremental_state_time_alignment(self):
        p = self.runtime
        state = p.state_at(p.current_time)
        previous = state.timestamp
        state = update_state_from_propagator(state, p, 7)
        self.assertEqual(state.timestamp, previous+timedelta(seconds=7))
        self.assertEqual(state.timestamp, p.current_time)
        np.testing.assert_allclose(state.position, p.propagate_at(state.timestamp)[0], atol=1e-8)

    def test_eclipse_has_light_shadow_and_geometric_consistency(self):
        p = self.runtime
        states = p.sample_states(p.period_seconds*2, 30)
        self.assertEqual({s.in_eclipse for s in states}, {False, True})
        sun = jpype.JClass('org.orekit.bodies.CelestialBodyFactory').getSun()
        for state in states:
            if state.in_eclipse:
                solar = p.array(sun.getPosition(p.absolute_date(state.timestamp), p.itrf))
                self.assertLess(np.dot(state.position, solar), 0)

    def test_contact_roots_and_clipped_windows(self):
        p = self.runtime
        windows = p.contact_windows(self.start, self.start+timedelta(days=1), self.station, 5)
        self.assertTrue(windows, 'Expected at least one Tunis pass during a day')
        for window in windows:
            self.assertLess(window['start'], window['end'])
            for boundary in (window['start'], window['end']):
                self.assertAlmostEqual(p.station_geometry(boundary, self.station)['elev_deg'], 5, delta=1e-4)
        window = windows[0]
        middle = window['start']+(window['end']-window['start'])/2
        geometry = p.station_geometry(middle, self.station)
        self.assertGreater(geometry['elev_deg'], 5)
        station_position = p.station_frame(self.station).getPVCoordinates(p.absolute_date(middle), p.itrf).getPosition()
        self.assertAlmostEqual(geometry['range_m'], np.linalg.norm(p.propagate_at(middle)[0]-p.array(station_position)), delta=1e-6)
        clipped = p.contact_windows(middle, window['end']+timedelta(seconds=30), self.station, 5)
        self.assertEqual(clipped[0]['start'], middle)
        clipped = p.contact_windows(window['start']-timedelta(seconds=30), middle, self.station, 5)
        self.assertEqual(clipped[0]['end'], middle)

    def test_samples_include_exact_endpoint(self):
        self.assertEqual(sample_offsets(65,30), [0,30,60,65])
        states = self.runtime.sample_states(65,30)
        self.assertEqual((states[-1].timestamp-states[0].timestamp).total_seconds(),65)

    def test_simultaneous_geometry_and_attack_events(self):
        from events.manager import EventManager, EventConfig
        from events.environmental import EclipseExit
        from events.attacks import JammingAttack
        manager = EventManager(EventConfig(enable_environmental=False, enable_attacks=False))
        manager.schedule_event(EclipseExit(timestamp=self.start))
        manager.schedule_event(JammingAttack(timestamp=self.start))
        self.assertEqual(len(manager.update(self.start, self.runtime.state_at(self.start))), 2)


class TunisPassEndToEndTest(unittest.TestCase):
    """End-to-end test: Orekit finds a Tunis pass and communication models run consistently."""

    @classmethod
    def setUpClass(cls):
        cls.config = _shared_config
        cls.runtime = _shared_runtime
        cls.station = {'name': 'Tunis_GS', 'lat_deg': 36.8, 'lon_deg': 10.18, 'alt_m': 20.0}
        start = cls.runtime.start_time
        end = start + timedelta(days=1)
        cls.windows = cls.runtime.contact_windows(start, end, cls.station, 5.0)

    def test_at_least_one_tunis_pass_in_24h(self):
        self.assertGreater(len(self.windows), 0,
                           'Expected at least one Tunis contact above 5° in a 24-hour run.')

    def test_pass_has_positive_duration_and_bounded_elevation(self):
        for w in self.windows:
            dur = (w['end'] - w['start']).total_seconds()
            self.assertGreater(dur, 0)
            mid = w['start'] + (w['end'] - w['start']) / 2
            geom = self.runtime.station_geometry(mid, self.station)
            self.assertGreater(geom['elev_deg'], 5.0)
            self.assertLess(geom['elev_deg'], 90.0)
            self.assertGreater(geom['range_m'], 0)

    def test_communication_models_run_at_pass_geometry(self):
        """RF, optical, and QKD metrics are consistent with Orekit pass geometry."""
        from communication.rf_link import RFLinkConfig, rf_link_budget
        from communication.optical_link import OpticalLinkConfig, optical_link_metrics
        from communication.qkd_model import QKDModelConfig, qkd_key_metrics
        import math

        rf_cfg = RFLinkConfig()
        opt_cfg = OpticalLinkConfig()
        qkd_cfg = QKDModelConfig()

        w = self.windows[0]
        mid = w['start'] + (w['end'] - w['start']) / 2
        geom = self.runtime.station_geometry(mid, self.station)
        range_m = geom['range_m']
        elev_deg = geom['elev_deg']

        rf = rf_link_budget(range_m, rf_cfg)
        opt = optical_link_metrics(range_m, elev_deg, opt_cfg)
        qkd = qkd_key_metrics(opt['sifted_count_hz'], opt['qber'], qkd_cfg)

        # RF: SNR and capacity must be finite
        self.assertTrue(math.isfinite(rf['snr_db']))
        self.assertGreater(rf['shannon_capacity_bps'], 0)

        # Optical: QBER must be in [0, 0.5], total loss finite
        self.assertGreaterEqual(opt['qber'], 0.0)
        self.assertLessEqual(opt['qber'], 0.5)
        self.assertTrue(math.isfinite(opt['total_loss_db']))
        self.assertTrue(math.isfinite(opt['signal_count_hz']))

        # QKD: key rate is finite; finite-key_valid is False (asymptotic model)
        self.assertTrue(math.isfinite(qkd['secret_key_rate_bit_s']))
        self.assertFalse(qkd['finite_key_valid'])

        # Channels are distinct: same geometry produces different metrics per channel
        self.assertNotEqual(rf['channel_id'], opt['channel_id'])
        self.assertNotEqual(opt['channel_id'], qkd['channel_id'])

    def test_communication_metrics_consistent_across_pass_samples(self):
        """SNR improves toward mid-pass (geometry drives both RF and optical)."""
        from communication.rf_link import RFLinkConfig, rf_link_budget
        from communication.optical_link import OpticalLinkConfig, optical_link_metrics

        rf_cfg = RFLinkConfig()
        opt_cfg = OpticalLinkConfig()
        w = self.windows[0]
        start_t = w['start']
        end_t = w['end']
        mid_t = start_t + (end_t - start_t) / 2

        g_start = self.runtime.station_geometry(start_t, self.station)
        g_mid = self.runtime.station_geometry(mid_t, self.station)

        rf_start = rf_link_budget(g_start['range_m'], rf_cfg)
        rf_mid = rf_link_budget(g_mid['range_m'], rf_cfg)

        opt_start = optical_link_metrics(g_start['range_m'], g_start['elev_deg'], opt_cfg)
        opt_mid = optical_link_metrics(g_mid['range_m'], g_mid['elev_deg'], opt_cfg)

        # Mid-pass: lower range → higher SNR and more signal counts
        self.assertGreater(rf_mid['snr_db'], rf_start['snr_db'])
        self.assertGreater(opt_mid['signal_count_hz'], opt_start['signal_count_hz'])


if __name__ == '__main__':
    unittest.main()

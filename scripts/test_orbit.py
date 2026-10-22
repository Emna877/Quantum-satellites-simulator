"""Scientific regression checks: python -m unittest scripts.test_orbit."""
import asyncio
from datetime import timedelta, timezone
import math
import unittest
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import jpype
import numpy as np
from config import get_simulation_config
from simulation.propagator import OrekitPropagator, iso, sample_offsets, utc, update_state_from_propagator


class OrbitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = get_simulation_config()
        cls.config['start_time'] = '2025-11-09T12:00:00.123456Z'
        cls.config['orbit'].update(eccentricity=0.0, inclination_deg=98.0)
        cls.runtime = OrekitPropagator.from_config(cls.config)
        cls.start = cls.runtime.start_time
        cls.station = dict(name='Tunis_GS', lat_deg=36.8, lon_deg=10.18, alt_m=20.0)

    @classmethod
    def tearDownClass(cls):
        cls.runtime.shutdown()

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

    def test_engine_clock_and_state_agree(self):
        from simulation.engine import SimulationEngine
        config = dict(self.config, time_step=7.0)
        config['event_config'] = dict(enable_environmental=False, enable_attacks=False)
        engine = SimulationEngine(config)
        engine.setup()
        async def stop(dt=None):
            engine.running = False
        engine.clock.sleep_until_next_tick = stop
        asyncio.run(engine.run())
        self.assertEqual(engine.clock.current_time, engine.state.timestamp)
        self.assertEqual(engine.state.timestamp, engine.propagator.current_time)

    def test_exporters_produce_identical_orekit_positions(self):
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as directory:
            simple = Path(directory) / 'orbit.czml'
            enhanced = Path(directory) / 'events.czml'
            environment = dict(os.environ, CZML_DEFAULT_DURATION_SECONDS='65', CZML_STEP_SECONDS='30',
                SIM_START_TIME='2025-11-09T12:00:00.123456Z',
                ORBIT_CZML_FILE=str(simple), CZML_OUTPUT_FILE=str(enhanced),
                ORBIT_CSV_FILE=str(Path(directory)/'orbit.csv'))
            environment.pop('CZML_DURATION_HOURS', None)
            environment.pop('ORBIT_PERIOD_MINUTES', None)
            for script in ('export_czml.py', 'export_czml_with_events.py'):
                result = subprocess.run([sys.executable, script], cwd=root, env=environment,
                                        capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            a, b = json.loads(simple.read_text()), json.loads(enhanced.read_text())
            self.assertEqual(a[1]['position'], b[1]['position'])
            self.assertEqual(a[1]['position']['cartesian'][-4], 65)
            self.assertTrue(a[0]['clock']['interval'].endswith('12:01:05.123456Z'))

    def test_simultaneous_geometry_and_attack_events(self):
        from events.manager import EventManager, EventConfig
        from events.environmental import EclipseExit
        from events.attacks import JammingAttack
        manager = EventManager(EventConfig(enable_environmental=False, enable_attacks=False))
        manager.schedule_event(EclipseExit(timestamp=self.start))
        manager.schedule_event(JammingAttack(timestamp=self.start))
        self.assertEqual(len(manager.update(self.start, self.runtime.state_at(self.start))), 2)


if __name__ == '__main__':
    unittest.main()

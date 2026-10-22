"""Engine/event regression suite: python -m unittest scripts.test_engine_events."""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import math
import unittest
from unittest.mock import patch
import numpy as np
from config import get_simulation_config
from events.base import Event
from events.manager import EventManager, EventConfig, EventApplicationError
from events.attacks import GPSSpoofing, CommandInjection, JammingAttack, LaserDazzle, PowerDrain, ThermalSabotage
from events.environmental import SolarFlare, EclipseEntry, EclipseExit, MicrometeoroidImpact, AtmosphericDragSpike, GeomagneticStorm
from simulation.clock import SimulationClock
from simulation.state import SatelliteState
from simulation.engine import SimulationEngine

START = datetime(2025,11,9,12,tzinfo=timezone.utc)
CLASSES = [SolarFlare,EclipseEntry,EclipseExit,MicrometeoroidImpact,AtmosphericDragSpike,
           GeomagneticStorm,GPSSpoofing,CommandInjection,JammingAttack,LaserDazzle,PowerDrain,ThermalSabotage]


def manager():
    return EventManager(EventConfig(enable_environmental=False,enable_attacks=False))


def state():
    return SatelliteState(timestamp=START,altitude=700000,solar_current=2.0,uplink_rate=1000,downlink_rate=2000)


class FailingEvent(Event):
    fail = True
    def impulse(self,state):
        state.battery_percent = 0
        if self.fail:
            raise RuntimeError('intentional test failure')


class EventTests(unittest.TestCase):
    def test_all_types_apply_and_expire(self):
        for cls in CLASSES:
            with self.subTest(event=cls.__name__):
                s,m=state(),manager()
                event=cls(timestamp=START)
                m.schedule_event(event)
                m.update(START,s)
                m.update(START+timedelta(seconds=event.duration_seconds+1),s)
                self.assertEqual(len(m.event_history),1)
                self.assertFalse(m.active_events)
                self.assertTrue(math.isfinite(s.internal_temp))
                self.assertTrue(math.isfinite(s.external_temp_c))

    def test_instantaneous_events_once_and_same_timestamp(self):
        s,m=state(),manager()
        impact=MicrometeoroidImpact(timestamp=START)
        m.schedule_event(impact)
        m.schedule_event(EclipseEntry(timestamp=START))
        self.assertEqual(len(m.update(START,s)),2)
        health=s.health_percent
        self.assertLess(health,100)
        self.assertTrue(s.in_eclipse)
        self.assertEqual(s.solar_current,0)
        for second in (0,1,30):
            m.update(START+timedelta(seconds=second),s)
        self.assertEqual(s.health_percent,health)
        with self.assertRaisesRegex(ValueError,'already'):
            m.schedule_event(impact)
        m.schedule_event(EclipseExit(timestamp=START+timedelta(seconds=31)))
        m.update(START+timedelta(seconds=31),s)
        self.assertFalse(s.in_eclipse)
        self.assertEqual(s.solar_current,2)

    def test_whole_event_inside_large_step(self):
        s,m=state(),manager()
        event=ThermalSabotage(timestamp=START+timedelta(seconds=10))
        m.schedule_event(event)
        m.update(START,s)
        m.update(START+timedelta(seconds=1000),s)
        self.assertAlmostEqual(s.internal_temp,30)
        self.assertAlmostEqual(s.external_temp,40)
        self.assertFalse(m.active_events)

    def test_integrals_independent_of_timestep(self):
        outputs=[]
        for dt in (1,7,60,1000):
            s,m=state(),manager()
            m.schedule_event(PowerDrain(timestamp=START+timedelta(seconds=10)))
            m.schedule_event(ThermalSabotage(timestamp=START+timedelta(seconds=13)))
            m.schedule_event(CommandInjection(timestamp=START+timedelta(seconds=17)))
            m.update(START,s)
            elapsed=0
            while elapsed < 1000:
                elapsed=min(1000,elapsed+dt)
                m.update(START+timedelta(seconds=elapsed),s)
            outputs.append([s.battery_percent,s.internal_temp,s.external_temp,s.health_percent,s.injected_command_count,s.angular_velocity_z])
        for actual in outputs[1:]:
            np.testing.assert_allclose(actual,outputs[0],rtol=0,atol=1e-9)

    def test_temporary_overlap_restores_baseline_and_keeps_damage(self):
        s,m=state(),manager()
        m.schedule_event(JammingAttack(timestamp=START))
        m.schedule_event(JammingAttack(timestamp=START))
        m.schedule_event(LaserDazzle(timestamp=START))
        m.update(START,s)
        self.assertAlmostEqual(s.signal_strength,-120)
        self.assertAlmostEqual(s.uplink_rate,490)
        m.update(START+timedelta(seconds=200),s)
        self.assertEqual(s.signal_strength,-100)
        self.assertEqual(s.uplink_rate,1000)
        self.assertEqual(s.downlink_rate,2000)
        self.assertEqual(s.packet_loss,0)
        self.assertEqual(s.sensor_noise_rad_s,0)
        self.assertLess(s.health_percent,100)

    def test_explicit_subsystem_baseline_update_is_preserved(self):
        s,m=state(),manager()
        m.schedule_event(JammingAttack(timestamp=START))
        m.update(START,s)
        m.clear_modifiers(s)
        s.signal_strength=-80
        m.update(START+timedelta(seconds=200),s)
        self.assertEqual(s.signal_strength,-80)

    def test_navigation_does_not_move_true_orbit(self):
        s,m=state(),manager()
        s.position=np.array([7078137.,0,0])
        original=s.position.copy()
        m.schedule_event(GPSSpoofing(timestamp=START))
        m.update(START,s)
        self.assertEqual(s.navigation_error_m,50)
        self.assertEqual(s.navigation_time_offset_ms,10)
        np.testing.assert_array_equal(original,s.position)
        m.update(START+timedelta(seconds=1200),s)
        self.assertEqual(s.navigation_error_m,0)

    def test_radiation_rate_and_dose_are_separate(self):
        s,m=state(),manager()
        event=SolarFlare(timestamp=START)
        m.schedule_event(event)
        m.update(START,s)
        self.assertGreater(s.radiation_dose_rate,0)
        self.assertEqual(s.radiation_dose,0)
        m.update(START+timedelta(seconds=event.duration_seconds),s)
        self.assertEqual(s.radiation_dose_rate,0)
        self.assertAlmostEqual(s.radiation_dose,event.parameters['radiation_rate_mgy_s']*event.duration_seconds/2)

    def test_transaction_rollback_and_visible_failure(self):
        s,m=state(),manager()
        m.schedule_event(FailingEvent(timestamp=START))
        with self.assertRaisesRegex(EventApplicationError,'intentional test failure'):
            m.update(START,s)
        self.assertEqual(s.battery_percent,100)
        self.assertEqual(len(m.event_history),0)
        self.assertEqual(len(m.event_queue),1)
        self.assertEqual(len(m.failures),1)
        m.event_queue[0][2].fail=False
        m.update(START,s)
        self.assertEqual(s.battery_percent,0)

    def test_modifier_failure_rolls_back(self):
        class BrokenJamming(JammingAttack):
            def temporary_effects(self,time):
                raise RuntimeError('broken sensor modifier')
        s,m=state(),manager()
        event=BrokenJamming(timestamp=START)
        m.schedule_event(event)
        before=s.to_dict()
        with self.assertRaisesRegex(EventApplicationError,event.event_id):
            m.update(START,s)
        self.assertEqual(s.to_dict(),before)
        self.assertEqual(len(m.event_queue),1)

    def test_same_timestamp_does_not_reintegrate(self):
        s,m=state(),manager()
        m.schedule_event(PowerDrain(timestamp=START))
        m.update(START,s)
        m.update(START+timedelta(seconds=30),s)
        before=s.to_dict()
        m.update(START+timedelta(seconds=30),s)
        self.assertEqual(before,s.to_dict())
        with self.assertRaisesRegex(ValueError,'backwards'):
            m.update(START,s)

    def test_poisson_arrivals_identical_across_step_sizes(self):
        logs=[]
        for dt in (1,10,100):
            config=EventConfig(enable_attacks=False,solar_flare_rate=8640,
                               micrometeoroid_rate=0,drag_spike_rate=0,geomagnetic_storm_rate=0,random_seed=11)
            s,m=state(),EventManager(config)
            m.update(START,s)
            for t in range(dt,101,dt):
                m.update(START+timedelta(seconds=t),s)
            logs.append(m.export_event_log())
        self.assertGreater(len(logs[0]),1)
        self.assertEqual(logs[0],logs[1])
        self.assertEqual(logs[0],logs[2])

    def test_poisson_probability_uses_elapsed_seconds(self):
        m=EventManager(EventConfig(enable_attacks=False,solar_flare_rate=86400,
             micrometeoroid_rate=0,drag_spike_rate=0,geomagnetic_storm_rate=0))
        with patch.object(m.rng,'random',return_value=0.5):
            self.assertIsNone(m.generate_random_event(START,0.1))
        with patch.object(m.rng,'random',return_value=0.5):
            self.assertIsNotNone(m.generate_random_event(START,1))

    def test_parameter_validation(self):
        with self.assertRaises(ValueError):
            GPSSpoofing(parameters=dict(unused=10))
        with self.assertRaises(ValueError):
            PowerDrain(parameters=dict(extra_power_w=float('nan')))
        with self.assertRaises(ValueError):
            JammingAttack(parameters=dict(throughput_loss_fraction=2))
        with self.assertRaises(ValueError):
            EventConfig(solar_flare_rate=-1)

    def test_snapshot_independence(self):
        s=state()
        s.navigation_error_m=20
        s.radiation_dose=0.2
        s.radiation_rate_mgy_s=0.1
        s.health_percent=99.8
        snapshot=s.copy()
        s.health_percent=50
        s.position[0]=1
        self.assertEqual(snapshot.health_percent,99.8)
        self.assertEqual(snapshot.position[0],0)
        self.assertEqual(snapshot.to_dict()['navigation_error_m'],20)


class ClockTests(unittest.TestCase):
    def test_speed_change_is_continuous_and_pause_freezes_expected_time(self):
        now=[0.]
        with patch('simulation.clock.time.monotonic',side_effect=lambda:now[0]):
            clock=SimulationClock(START)
            now[0]=10
            self.assertEqual(clock.expected_simulation_seconds,10)
            clock.set_speed(2)
            self.assertEqual(clock.expected_simulation_seconds,10)
            now[0]=15
            self.assertEqual(clock.expected_simulation_seconds,20)
            clock.pause()
            now[0]=100
            clock.set_speed(3)
            self.assertEqual(clock.expected_simulation_seconds,20)
            clock.resume()
            now[0]=102
            self.assertEqual(clock.expected_simulation_seconds,26)
            self.assertEqual(clock.elapsed_wall_seconds,17)

    def test_pacing_recalculates_after_speed_change(self):
        now=[0.]
        with patch('simulation.clock.time.monotonic',side_effect=lambda:now[0]):
            clock=SimulationClock(START,time_step=1)
            calls=[]
            async def sleep(seconds):
                calls.append(seconds)
                now[0]+=seconds
                if len(calls)==1:
                    clock.set_speed(2)
            with patch('simulation.clock.asyncio.sleep',side_effect=sleep):
                asyncio.run(clock.sleep_until_next_tick())
            self.assertAlmostEqual(now[0],0.525,places=6)
            self.assertEqual(clock.elapsed_simulation_seconds,0)

    def test_invalid_timing(self):
        for value in (0,-1,float('inf'),float('nan')):
            with self.subTest(value=value),self.assertRaises(ValueError):
                SimulationClock(START,speed_multiplier=value)


class FakePropagator:
    def __init__(self):
        self.start_time=self.current_time=START
        self.epoch=START
        self.calls=0
    def state_at(self,time,state=None):
        self.calls+=1
        state=state if state is not None else SatelliteState(timestamp=time)
        state.timestamp=time
        state.altitude=700000
        state.position=np.array([7078137.,(time-START).total_seconds(),0])
        return state
    def absolute_date(self,time):
        return time
    def shutdown(self):
        pass


def engine():
    config=get_simulation_config()
    config['event_config']=EventConfig(enable_environmental=False,enable_attacks=False)
    config['time_step']=7
    result=SimulationEngine(config)
    result.setup(FakePropagator())
    return result


class EngineTests(unittest.TestCase):
    def test_submicrosecond_step_is_rejected(self):
        e=engine()
        with self.assertRaisesRegex(ValueError,'microsecond'):
            e.step(1e-10)
        with self.assertRaisesRegex(ValueError,'microsecond'):
            e.run_offline(1e-10)

    def test_pause_is_a_complete_noop(self):
        e=engine()
        e.event_manager.schedule_event(MicrometeoroidImpact(timestamp=START))
        e.clock.pause()
        before=e.state.to_dict()
        calls=e.propagator.calls
        e.step(10)
        self.assertEqual(e.state.to_dict(),before)
        self.assertEqual(e.propagator.calls,calls)
        self.assertEqual(e.clock.tick_count,0)
        self.assertEqual(len(e.event_manager.event_history),0)
        e.clock.resume()
        e.step(10)
        self.assertEqual(e.clock.tick_count,1)
        self.assertLess(e.state.health_percent,100)

    def test_offline_paced_and_unpaced_use_same_steps(self):
        a,b,c=engine(),engine(),engine()
        for e in (a,b,c):
            e.event_manager.schedule_event(PowerDrain(timestamp=START+timedelta(seconds=5)))
        snapshots=a.run_offline(65)
        waits=[]
        async def sleep(dt):
            waits.append(dt)
        b.clock.sleep_until_next_tick=sleep
        asyncio.run(b.run(65,paced=True))
        asyncio.run(c.run(65,paced=False))
        self.assertEqual(a.state.to_dict(),b.state.to_dict())
        self.assertEqual(a.state.to_dict(),c.state.to_dict())
        self.assertEqual(waits[-1],2)
        self.assertEqual((snapshots[-1].timestamp-START).total_seconds(),65)
        self.assertEqual(snapshots[0].battery_percent,100)
        self.assertLess(snapshots[-1].battery_percent,100)
        self.assertEqual(a.clock.current_time,a.propagator.current_time)
        self.assertEqual(a.state.timestamp,a.clock.current_time)

    def test_failed_step_does_not_advance_state_clock_or_queue(self):
        e=engine()
        e.event_manager.schedule_event(FailingEvent(timestamp=START+timedelta(seconds=2)))
        before=e.state.to_dict()
        with self.assertRaises(EventApplicationError):
            e.step(10)
        self.assertEqual(e.state.to_dict(),before)
        self.assertEqual(e.clock.current_time,START)
        self.assertEqual(e.propagator.current_time,START)
        self.assertEqual(len(e.event_manager.event_queue),1)
        self.assertEqual(len(e.event_manager.failures),1)

    def test_paced_run_propagates_errors(self):
        e=engine()
        e.event_manager.schedule_event(FailingEvent(timestamp=START))
        with self.assertRaises(EventApplicationError):
            asyncio.run(e.run(10,paced=False))
        self.assertFalse(e.running)

    def test_run_waits_while_paused_without_updating_state(self):
        e=engine()
        e.clock.pause()
        original=e.state.to_dict()
        async def sleep(dt):
            self.assertEqual(e.state.to_dict(),original)
            e.running=False
        with patch('simulation.engine.asyncio.sleep',side_effect=sleep):
            asyncio.run(e.run(10))
        self.assertEqual(e.clock.tick_count,0)


if __name__ == '__main__':
    unittest.main()

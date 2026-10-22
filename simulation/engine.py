"""One transactional simulation step shared by offline and wall-clock paced runs."""
import asyncio
from copy import deepcopy
from datetime import timedelta
import math
from config import get_simulation_config, validate_runtime_config
from .propagator import OrekitPropagator
from .clock import SimulationClock
from events.manager import EventManager, EventConfig
from events.environmental import EclipseEntry, EclipseExit


class SimulationEngine:
    def __init__(self, config):
        self.config = validate_runtime_config(deepcopy(config))
        self.clock = self.propagator = self.state = self.event_manager = None
        self.logger = self.streamer = self.subsystem_models = None
        self.running = self.setup_complete = False
        self.last_events = []

    def setup(self,propagator=None):
        self.propagator = propagator or OrekitPropagator.from_config(self.config)
        self.clock = SimulationClock(self.propagator.start_time,
                                     self.config.get('speed_multiplier',1), self.config.get('time_step',1))
        self.state = self.propagator.state_at(self.propagator.start_time)
        event_config = self.config.get('event_config',EventConfig())
        if isinstance(event_config,dict):
            event_config = EventConfig(**event_config)
        self.event_manager = EventManager(event_config)
        self.event_manager.update(self.clock.current_time,self.state,0)
        self.setup_complete = True

    def step(self,dt=None):
        """Advance physical state and events together; pause makes this a no-op.

        Duration-event envelopes are integrated over the full interval; eclipses
        are observed at step endpoints. Only a successful step advances the clock.
        """
        if not self.setup_complete:
            raise RuntimeError('Call setup() before stepping')
        dt = self.clock.time_step if dt is None else dt
        if not math.isfinite(dt) or dt <= 0:
            raise ValueError('Step dt must be finite and positive')
        if self.clock.paused:
            return self.state
        previous = deepcopy(self.state.__dict__)
        previous_events = self.last_events
        manager_state = self.event_manager.checkpoint()
        target = self.clock.current_time+timedelta(seconds=dt)
        if target <= self.clock.current_time:
            raise ValueError('Step dt must advance time by at least one microsecond')
        try:
            self.event_manager.clear_modifiers(self.state)
            previous_eclipse = self.state.in_eclipse
            self.propagator.state_at(target,self.state)
            if previous_eclipse != self.state.in_eclipse:
                cls = EclipseEntry if self.state.in_eclipse else EclipseExit
                self.event_manager.schedule_event(cls(timestamp=target))
            self.last_events = self.event_manager.update(target,self.state,dt)
            self.state.validate()
        except Exception:
            self.state.__dict__.clear()
            self.state.__dict__.update(previous)
            self.event_manager.restore(manager_state)
            self.last_events = previous_events
            raise
        self.clock.tick(dt)
        self.propagator.current_time = target
        self.propagator.epoch = self.propagator.absolute_date(target)
        return self.state

    @staticmethod
    def _duration(duration):
        if not math.isfinite(duration) or duration < 1e-6:
            raise ValueError('Run duration must be finite and at least one microsecond')

    def run_offline(self,duration,time_step=None):
        """Return independent snapshots, including start and exact final endpoint."""
        self._duration(duration)
        if not self.setup_complete:
            raise RuntimeError('Call setup() before running')
        if self.clock.paused:
            raise RuntimeError('Resume the clock before an offline run')
        dt = self.clock.time_step if time_step is None else time_step
        if not math.isfinite(dt) or dt <= 0:
            raise ValueError('Offline timestep must be finite and positive')
        stop = self.clock.current_time+timedelta(seconds=duration)
        snapshots = [self.state.copy()]
        while self.clock.current_time < stop:
            self.step(min(dt,(stop-self.clock.current_time).total_seconds()))
            snapshots.append(self.state.copy())
        self.clock.rebase()
        return snapshots

    async def run(self,duration=None,paced=True):
        """Run until stopped or duration is reached; both modes call step()."""
        if not self.setup_complete:
            raise RuntimeError('Call setup() before running')
        if duration is not None:
            self._duration(duration)
        stop = self.clock.current_time+timedelta(seconds=duration) if duration is not None else None
        self.clock.rebase()
        self.running = True
        try:
            while self.running and (stop is None or self.clock.current_time < stop):
                if self.clock.paused:
                    await asyncio.sleep(0.05)
                    continue
                dt = self.clock.time_step
                if stop is not None:
                    dt = min(dt,(stop-self.clock.current_time).total_seconds())
                if paced:
                    await self.clock.sleep_until_next_tick(dt)
                if not self.running or self.clock.paused:
                    continue
                self.step(dt)
                if paced:
                    self.clock.calculate_lag()
                if self.logger:
                    self.logger.log(self.state)
                if self.streamer:
                    await self.streamer.send(self.state)
                await asyncio.sleep(0)
        finally:
            self.running = False
            await self.shutdown()

    def _print_status(self):
        print(self.clock, 'altitude_km=',self.state.altitude/1000,
              'battery_pct=',self.state.battery_percent, self.event_manager.get_statistics())

    async def shutdown(self):
        if self.propagator:
            self.propagator.shutdown()


async def main():
    import argparse
    parser = argparse.ArgumentParser(description='Orekit simulation engine')
    parser.add_argument('--seconds',type=float,help='Bounded simulation duration')
    parser.add_argument('--offline',action='store_true',help='Run without wall-clock pacing')
    args = parser.parse_args()
    engine = SimulationEngine(get_simulation_config())
    engine.setup()
    await engine.run(args.seconds,paced=not args.offline)
    engine._print_status()


if __name__ == '__main__':
    asyncio.run(main())

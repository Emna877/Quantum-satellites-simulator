"""Monotonic, piecewise-linear mapping between wall time and simulation time."""
import asyncio
import math
import time
from datetime import timedelta
from config import simulation_start


class SimulationClock:
    def __init__(self, start_time, speed_multiplier=1.0, time_step=1.0):
        for value in (speed_multiplier, time_step):
            if not math.isfinite(value) or value <= 0:
                raise ValueError('Speed and timestep must be finite and positive')
        self.sim_start_time = simulation_start(start_time.isoformat())
        self.sim_current_time = self.sim_start_time
        self.speed_multiplier = speed_multiplier
        self.time_step = time_step
        self.wall_start_time = time.monotonic()
        self._anchor_wall = self.wall_start_time
        self._anchor_sim = 0.0
        self.wall_pause_time = None
        self.total_pause_duration = 0.0
        self.paused = False
        self.running = False
        self.tick_count = 0
        self.total_lag_seconds = 0.0
        self.max_lag_seconds = 0.0
        self.lag_samples = []

    @property
    def current_time(self):
        return self.sim_current_time

    @property
    def elapsed_simulation_seconds(self):
        return (self.current_time-self.sim_start_time).total_seconds()

    @property
    def elapsed_wall_seconds(self):
        now = self.wall_pause_time if self.paused else time.monotonic()
        return now-self.wall_start_time-self.total_pause_duration

    @property
    def expected_simulation_seconds(self):
        return self._anchor_sim if self.paused else self._anchor_sim+(time.monotonic()-self._anchor_wall)*self.speed_multiplier

    def rebase(self):
        """Start pacing at the current simulated instant (e.g. after offline work)."""
        self._anchor_sim = self.elapsed_simulation_seconds
        self._anchor_wall = time.monotonic()

    def tick(self, dt=None):
        dt = self.time_step if dt is None else dt
        if not math.isfinite(dt) or dt <= 0:
            raise ValueError('Timestep must be finite and positive')
        if not self.paused:
            self.sim_current_time += timedelta(seconds=dt)
            self.tick_count += 1
        return self.current_time

    def pause(self):
        if not self.paused:
            self._anchor_sim = self.expected_simulation_seconds
            self.wall_pause_time = time.monotonic()
            self.paused = True

    def resume(self):
        if self.paused:
            now = time.monotonic()
            self.total_pause_duration += now-self.wall_pause_time
            self._anchor_wall = now
            self.wall_pause_time = None
            self.paused = False

    def set_speed(self, multiplier):
        if not math.isfinite(multiplier) or multiplier <= 0:
            raise ValueError('Speed multiplier must be finite and positive')
        self._anchor_sim = self.expected_simulation_seconds
        self._anchor_wall = time.monotonic()
        self.speed_multiplier = multiplier

    async def sleep_until_next_tick(self, dt=None):
        """Wait before advancing; reevaluate pause/speed changes during the wait."""
        target = self.elapsed_simulation_seconds+(self.time_step if dt is None else dt)
        while True:
            if self.paused:
                return
            remaining = (target-self.expected_simulation_seconds)/self.speed_multiplier
            if remaining <= 1e-9:
                return
            await asyncio.sleep(min(remaining, 0.05))

    def calculate_lag(self):
        lag = 0.0 if self.paused else self.expected_simulation_seconds-self.elapsed_simulation_seconds
        self.total_lag_seconds += lag
        self.max_lag_seconds = max(self.max_lag_seconds, abs(lag))
        self.lag_samples.append(lag)
        self.lag_samples = self.lag_samples[-1000:]
        return lag

    def get_statistics(self):
        return dict(sim_time=self.current_time.isoformat(), elapsed_sim_seconds=self.elapsed_simulation_seconds,
                    elapsed_wall_seconds=self.elapsed_wall_seconds, tick_count=self.tick_count,
                    speed_multiplier=self.speed_multiplier, paused=self.paused,
                    current_lag_seconds=0.0 if self.paused else self.expected_simulation_seconds-self.elapsed_simulation_seconds,
                    average_lag_seconds=sum(self.lag_samples)/len(self.lag_samples) if self.lag_samples else 0,
                    max_lag_seconds=self.max_lag_seconds, total_pause_duration=self.total_pause_duration)

    def __str__(self):
        return f'SimClock({self.current_time.isoformat()}, speed={self.speed_multiplier}, paused={self.paused})'

"""
Simulation Clock Manager - Synchronize simulated time with wall-clock time.

This module provides precise timing control for real-time simulation,
including pause/resume, speed control, and lag monitoring.
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Optional
from config import simulation_start


class SimulationClock:
    """
    Manages simulation time and synchronization with wall-clock time.
    """
    
    def __init__(self, start_time: datetime, speed_multiplier: float = 1.0, time_step: float = 1.0):
        """
        Initialize simulation clock.
        
        Args:
            start_time: Simulation starting time
            speed_multiplier: Simulation speed (1.0 = real-time, 2.0 = 2x speed)
            time_step: Time step in seconds for each tick
        """
        start_time = simulation_start(start_time.isoformat())
        self.sim_start_time = start_time
        self.sim_current_time = start_time
        self.wall_start_time = time.time()
        self.wall_pause_time: Optional[float] = None
        self.total_pause_duration = 0.0
        
        self.speed_multiplier = speed_multiplier
        self.time_step = time_step
        self.tick_count = 0
        
        self.paused = False
        self.running = False
        
        # Statistics
        self.total_lag_seconds = 0.0
        self.max_lag_seconds = 0.0
        self.lag_samples = []
    
    @property
    def current_time(self) -> datetime:
        """Get current simulation time."""
        return self.sim_current_time
    
    @property
    def elapsed_simulation_seconds(self) -> float:
        """Get total simulation time elapsed since start."""
        return (self.sim_current_time - self.sim_start_time).total_seconds()
    
    @property
    def elapsed_wall_seconds(self) -> float:
        """Get total wall-clock time elapsed (excluding pauses)."""
        if self.paused and self.wall_pause_time is not None:
            return self.wall_pause_time - self.wall_start_time - self.total_pause_duration
        return time.time() - self.wall_start_time - self.total_pause_duration
    
    def tick(self) -> datetime:
        """
        Advance simulation by one time step.
        
        Returns:
            New simulation time after tick
        """
        if self.paused:
            return self.sim_current_time
        
        self.sim_current_time += timedelta(seconds=self.time_step)
        self.tick_count += 1
        
        return self.sim_current_time
    
    def calculate_lag(self) -> float:
        """
        Calculate lag between where simulation should be vs where it is.
        
        Returns:
            Lag in seconds (positive = simulation behind, negative = ahead)
        """
        if self.paused:
            return 0.0
        
        # Where simulation should be based on wall clock and speed
        expected_sim_seconds = self.elapsed_wall_seconds * self.speed_multiplier
        
        # Where simulation actually is
        actual_sim_seconds = self.elapsed_simulation_seconds
        
        # Lag = expected - actual (positive means we're behind)
        lag = expected_sim_seconds - actual_sim_seconds
        
        # Update statistics
        self.total_lag_seconds += lag
        self.max_lag_seconds = max(self.max_lag_seconds, abs(lag))
        self.lag_samples.append(lag)
        
        # Keep only last 1000 samples
        if len(self.lag_samples) > 1000:
            self.lag_samples.pop(0)
        
        return lag
    
    async def sleep_until_next_tick(self):
        """
        Sleep until it's time for the next simulation tick.
        
        This maintains precise timing by calculating how long to sleep
        based on current lag and speed multiplier.
        """
        if self.paused:
            # Just sleep a bit while paused
            await asyncio.sleep(0.1)
            return
        
        # Calculate when next tick should occur (wall time)
        ticks_elapsed = self.tick_count
        next_tick_sim_seconds = ticks_elapsed * self.time_step
        next_tick_wall_seconds = next_tick_sim_seconds / self.speed_multiplier
        next_tick_wall_time = self.wall_start_time + next_tick_wall_seconds + self.total_pause_duration
        
        # How long until next tick?
        current_wall_time = time.time()
        sleep_duration = next_tick_wall_time - current_wall_time
        
        if sleep_duration > 0:
            await asyncio.sleep(sleep_duration)
        # If sleep_duration <= 0, we're behind schedule, so don't sleep
    
    def pause(self):
        """Pause the simulation clock."""
        if not self.paused:
            self.paused = True
            self.wall_pause_time = time.time()
            print(f"[Clock] Paused at sim_time={self.sim_current_time.isoformat()}")
    
    def resume(self):
        """Resume the simulation clock."""
        if self.paused and self.wall_pause_time is not None:
            pause_duration = time.time() - self.wall_pause_time
            self.total_pause_duration += pause_duration
            self.paused = False
            self.wall_pause_time = None
            print(f"[Clock] Resumed from sim_time={self.sim_current_time.isoformat()}")
    
    def set_speed(self, multiplier: float):
        """
        Change simulation speed multiplier.
        
        Args:
            multiplier: New speed multiplier (1.0 = real-time)
        """
        if multiplier <= 0:
            raise ValueError("Speed multiplier must be positive")
        
        old_speed = self.speed_multiplier
        self.speed_multiplier = multiplier
        print(f"[Clock] Speed changed from {old_speed:.2f}x to {multiplier:.2f}x")
    
    def get_statistics(self) -> dict:
        """
        Get clock performance statistics.
        
        Returns:
            Dictionary with timing statistics
        """
        avg_lag = sum(self.lag_samples) / len(self.lag_samples) if self.lag_samples else 0.0
        
        return {
            "sim_time": self.sim_current_time.isoformat(),
            "elapsed_sim_seconds": self.elapsed_simulation_seconds,
            "elapsed_wall_seconds": self.elapsed_wall_seconds,
            "tick_count": self.tick_count,
            "speed_multiplier": self.speed_multiplier,
            "paused": self.paused,
            "current_lag_seconds": self.calculate_lag(),
            "average_lag_seconds": avg_lag,
            "max_lag_seconds": self.max_lag_seconds,
            "total_pause_duration": self.total_pause_duration,
        }
    
    def __str__(self) -> str:
        """String representation of clock state."""
        stats = self.get_statistics()
        return (
            f"SimClock(sim_time={stats['sim_time']}, "
            f"ticks={stats['tick_count']}, "
            f"speed={stats['speed_multiplier']:.2f}x, "
            f"lag={stats['current_lag_seconds']:.3f}s, "
            f"paused={stats['paused']})"
        )

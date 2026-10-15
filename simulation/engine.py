"""
Simulation Engine - Main orchestration loop for real-time satellite simulation.

This module coordinates all simulation components:
- Time management via SimulationClock
- Orbital propagation via OrekitPropagator  
- Event generation and application
- Subsystem updates
- Data logging
- Real-time streaming
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional
import sys

from .state import SatelliteState
from .propagator import OrekitPropagator, initialize_state_from_propagator, update_state_from_propagator
from .clock import SimulationClock
from config import simulation_start
from events.manager import EventManager, EventConfig


class SimulationEngine:
    """
    Main simulation engine that orchestrates all components.
    """
    
    def __init__(self, config: dict):
        """
        Initialize simulation engine.
        
        Args:
            config: Configuration dictionary with simulation parameters
        """
        from config import validate_runtime_config
        self.config = validate_runtime_config(config)
        
        # Core components (will be initialized in setup())
        self.clock: Optional[SimulationClock] = None
        self.propagator: Optional[OrekitPropagator] = None
        self.state: Optional[SatelliteState] = None
        
        # Placeholder for future components
        self.event_manager = None
        self.subsystem_models = None
        self.logger = None
        self.streamer = None
        
        self.running = False
        self.setup_complete = False
    
    def setup(self):
        """
        Initialize all simulation components.
        """
        print("=" * 60)
        print("SIMULATION ENGINE SETUP")
        print("=" * 60)
        
        # 1. Initialize Orekit propagator
        print("\n[1/4] Initializing Orekit propagator...")
        jvm_path = self.config.get("jvm_path")
        orekit_data_path = Path(self.config.get("orekit_data_path"))
        
        if not jvm_path:
            raise ValueError("jvm_path not specified in config")
        if not orekit_data_path.exists():
            raise ValueError(f"orekit_data_path does not exist: {orekit_data_path}")
        
        self.propagator = OrekitPropagator.from_config(self.config)
        start_time = self.propagator.start_time

        # 2. Initialize simulation clock
        print("\n[2/4] Initializing simulation clock...")
        time_step = self.config.get("time_step", 1.0)
        speed_multiplier = self.config.get("speed_multiplier", 1.0)
        
        self.clock = SimulationClock(
            start_time=start_time,
            speed_multiplier=speed_multiplier,
            time_step=time_step
        )
        print(f"  Clock: time_step={time_step}s, speed={speed_multiplier}x")
        
        # 3. Initialize satellite state
        print("\n[3/4] Initializing satellite state...")
        self.state = initialize_state_from_propagator(self.propagator, start_time)
        print(f"  Initial altitude: {self.state.altitude/1e3:.1f} km")
        print(f"  Initial position: [{self.state.position[0]/1e3:.1f}, {self.state.position[1]/1e3:.1f}, {self.state.position[2]/1e3:.1f}] km")
        
        # 4. Initialize other components
        print("\n[4/4] Initializing subsystems...")
        
        # Initialize event manager with default or custom config
        event_config = self.config.get("event_config", EventConfig())
        if isinstance(event_config, dict):
            # Convert dict to EventConfig if needed
            event_config = EventConfig(**event_config)
        self.event_manager = EventManager(config=event_config)
        
        orbit_period = self.propagator.period_seconds / 60.0
        print(f"  Event manager initialized (Orekit period: {orbit_period:.3f} min)")

        print("  [TODO] Subsystem models")
        print("  [TODO] Telemetry logger")
        print("  [TODO] CZML streamer")
        
        self.setup_complete = True
        print("\n" + "=" * 60)
        print("SETUP COMPLETE - Ready to run simulation")
        print("=" * 60 + "\n")
    
    async def run(self):
        """
        Main simulation loop - runs continuously until stopped.
        """
        if not self.setup_complete:
            raise RuntimeError("Must call setup() before run()")
        
        self.running = True

        print(f"[Engine] Starting simulation at {self.clock.current_time.isoformat()}")
        print(f"[Engine] Press Ctrl+C to stop\n")
        
        try:
            while self.running:
                if self.clock.paused:
                    await asyncio.sleep(0.1)
                    continue
                # Advance clock and dynamics to the same instant before event evaluation.
                previous_eclipse = self.state.in_eclipse
                self.clock.tick()
                self.state = update_state_from_propagator(self.state, self.propagator, self.clock.time_step)
                if previous_eclipse != self.state.in_eclipse:
                    from events.environmental import EclipseEntry, EclipseExit
                    event_class = EclipseEntry if self.state.in_eclipse else EclipseExit
                    self.event_manager.schedule_event(event_class(timestamp=self.state.timestamp))
                # Phase 1: Generate and apply events
                if self.event_manager:
                    events_occurred = self.event_manager.update(self.clock.current_time, self.state)
                    
                    # Log any new events that occurred
                    for event in events_occurred:
                        print(f"[Event] {event.event_type.value.upper()} "
                              f"(Severity: {event.severity.name}, "
                              f"Type: {'ATTACK' if event.is_attack else 'ENVIRONMENTAL'})")
                
                # Phase 3: Update subsystems (placeholder)
                # if self.subsystem_models:
                #     self.state = self.subsystem_models.update(self.state, self.clock.time_step)
                
                # Phase 4: Validate state
                try:
                    self.state.validate()
                except ValueError as e:
                    print(f"[Engine] WARNING: State validation failed: {e}")
                
                # Phase 5: Log telemetry (placeholder)
                # if self.logger:
                #     self.logger.log(self.state)
                
                # Phase 6: Stream data (placeholder)
                # if self.streamer:
                #     await self.streamer.send(self.state)
                
                # Print periodic status
                if self.clock.tick_count % 60 == 0:  # Every 60 seconds
                    self._print_status()
                
                # Phase 7: Advance clock and sleep
                lag = self.clock.calculate_lag()
                
                if abs(lag) > 5.0:  # Warning if lag exceeds 5 seconds
                    print(f"[Engine] WARNING: High lag detected: {lag:.2f}s")
                
                await self.clock.sleep_until_next_tick()
        
        except KeyboardInterrupt:
            print("\n[Engine] Simulation interrupted by user")
        except Exception as e:
            print(f"\n[Engine] ERROR: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.running = False
            await self.shutdown()
    
    def _print_status(self):
        """Print current simulation status."""
        stats = self.clock.get_statistics()
        event_stats = self.event_manager.get_statistics() if self.event_manager else {}
        
        print(f"\n[Status] Sim Time: {self.clock.current_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Ticks: {stats['tick_count']} | "
              f"Altitude: {self.state.altitude/1e3:.1f} km | "
              f"Battery: {self.state.battery_percent:.1f}% | "
              f"Temp: {self.state.internal_temp:.1f}°C")
        print(f"  Speed: {stats['speed_multiplier']:.2f}x | "
              f"Lag: {stats['current_lag_seconds']:.3f}s | "
              f"Avg Lag: {stats['average_lag_seconds']:.3f}s")
        
        if event_stats:
            print(f"  Events: {event_stats['total_events']} total "
                  f"({event_stats['environmental_events']} environmental, "
                  f"{event_stats['attack_events']} attacks) | "
                  f"Active: {event_stats['active_events_count']}")
    
    async def shutdown(self):
        """Clean shutdown of all components."""
        print("\n[Engine] Shutting down...")
        
        if self.propagator:
            self.propagator.shutdown()
        
        if self.clock:
            final_stats = self.clock.get_statistics()
            print(f"\n[Engine] Final Statistics:")
            print(f"  Total simulation time: {final_stats['elapsed_sim_seconds']:.1f}s")
            print(f"  Total wall time: {final_stats['elapsed_wall_seconds']:.1f}s")
            print(f"  Total ticks: {final_stats['tick_count']}")
            print(f"  Max lag: {final_stats['max_lag_seconds']:.3f}s")
        
        if self.event_manager:
            event_stats = self.event_manager.get_statistics()
            print(f"\n[Event System] Statistics:")
            print(f"  Total events: {event_stats['total_events']}")
            print(f"  Environmental: {event_stats['environmental_events']}")
            print(f"  Attacks: {event_stats['attack_events']}")
            print(f"  By Severity: {dict(event_stats['by_severity'])}")
        
        print("[Engine] Shutdown complete")


async def main():
    """
    Example main function to run simulation.
    """
    from config import get_simulation_config
    config = get_simulation_config()
    
    engine = SimulationEngine(config)
    engine.setup()
    await engine.run()


if __name__ == "__main__":
    asyncio.run(main())

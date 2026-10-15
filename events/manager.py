"""
Event Manager - Phase 2

Manages event generation, scheduling, and application to satellite state.
Implements random event generation with configurable probabilities.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Type
import random
import heapq
from itertools import count
from config import simulation_start

from events.base import Event, EventType, EventSeverity
from events.environmental import (
    SolarFlare, EclipseEntry, EclipseExit, MicrometeoroidImpact,
    AtmosphericDragSpike, GeomagneticStorm
)
from events.attacks import (
    GPSSpoofing, CommandInjection, JammingAttack,
    LaserDazzle, PowerDrain, ThermalSabotage
)


@dataclass
class EventConfig:
    """Configuration for event generation probabilities."""
    # Environmental event probabilities (events per day)
    solar_flare_rate: float = 0.5        # ~1 every 2 days
    eclipse_entry_rate: float = 14.0     # ~14 orbits per day
    eclipse_exit_rate: float = 14.0      # Matches entries
    micrometeoroid_rate: float = 2.0     # ~2 per day
    drag_spike_rate: float = 1.0         # ~1 per day
    geomagnetic_storm_rate: float = 0.3  # ~1 every 3 days
    
    # Attack event probabilities (events per day)
    gps_spoofing_rate: float = 0.1       # Rare
    command_injection_rate: float = 0.05 # Very rare
    jamming_attack_rate: float = 0.2     # Occasional
    laser_dazzle_rate: float = 0.1       # Rare
    power_drain_rate: float = 0.05       # Very rare
    thermal_sabotage_rate: float = 0.05  # Very rare
    
    # Severity distribution (probabilities sum to 1.0)
    severity_distribution: Dict[EventSeverity, float] = field(default_factory=lambda: {
        EventSeverity.LOW: 0.5,
        EventSeverity.MEDIUM: 0.3,
        EventSeverity.HIGH: 0.15,
        EventSeverity.CRITICAL: 0.05
    })
    
    # Enable/disable event types
    enable_environmental: bool = True
    enable_attacks: bool = True


class EventManager:
    """
    Manages event generation and application for the simulation.
    
    The EventManager generates random events based on configured probabilities,
    maintains a priority queue of scheduled events, and applies their effects
    to the satellite state.
    """
    
    def __init__(self, config: Optional[EventConfig] = None):
        """
        Initialize the EventManager.
        
        Args:
            config: Event generation configuration (uses defaults if None)
        """
        self.config = config or EventConfig()
        self.event_queue: List[Event] = []  # Priority queue (heapq)
        self._event_sequence = count()
        self.active_events: List[Event] = []  # Currently active events
        self.event_history: List[Event] = []  # All past events for logging
        
        # Event class registry
        self.environmental_events: Dict[str, Type[Event]] = {
            'solar_flare': SolarFlare,
            'eclipse_entry': EclipseEntry,
            'eclipse_exit': EclipseExit,
            'micrometeoroid': MicrometeoroidImpact,
            'drag_spike': AtmosphericDragSpike,
            'geomagnetic_storm': GeomagneticStorm,
        }
        
        self.attack_events: Dict[str, Type[Event]] = {
            'gps_spoofing': GPSSpoofing,
            'command_injection': CommandInjection,
            'jamming': JammingAttack,
            'laser_dazzle': LaserDazzle,
            'power_drain': PowerDrain,
            'thermal_sabotage': ThermalSabotage,
        }
        
        # Statistics
        self.stats = {
            'total_events': 0,
            'environmental_events': 0,
            'attack_events': 0,
            'by_severity': {sev: 0 for sev in EventSeverity},
            'by_type': {et: 0 for et in EventType}
        }
    
    def generate_random_event(self, current_time: datetime) -> Optional[Event]:
        """
        Generate a random event based on configured probabilities.
        
        Args:
            current_time: Current simulation time
            
        Returns:
            Newly created Event or None if no event generated
        """
        # Determine if we should generate an event this tick
        # Convert rates from events/day to probability/second
        dt = 1.0  # 1 second timestep
        
        # Environmental events
        if self.config.enable_environmental:
            env_rate = (
                self.config.solar_flare_rate +
                self.config.micrometeoroid_rate +
                self.config.drag_spike_rate +
                self.config.geomagnetic_storm_rate
            ) / 86400.0  # Convert to per-second
            
            if random.random() < env_rate * dt:
                return self._create_environmental_event(current_time)
        
        # Attack events
        if self.config.enable_attacks:
            attack_rate = (
                self.config.gps_spoofing_rate +
                self.config.command_injection_rate +
                self.config.jamming_attack_rate +
                self.config.laser_dazzle_rate +
                self.config.power_drain_rate +
                self.config.thermal_sabotage_rate
            ) / 86400.0
            
            if random.random() < attack_rate * dt:
                return self._create_attack_event(current_time)
        
        return None
    
    def _create_environmental_event(self, timestamp: datetime) -> Event:
        """Create a random environmental event."""
        # Choose event type based on relative rates
        rates = {
            'solar_flare': self.config.solar_flare_rate,
            'micrometeoroid': self.config.micrometeoroid_rate,
            'drag_spike': self.config.drag_spike_rate,
            'geomagnetic_storm': self.config.geomagnetic_storm_rate,
        }
        
        total = sum(rates.values())
        choice = random.uniform(0, total)
        cumulative = 0
        
        for event_name, rate in rates.items():
            cumulative += rate
            if choice <= cumulative:
                event_class = self.environmental_events[event_name]
                severity = self._choose_severity()
                return event_class(timestamp=timestamp, severity=severity)
        
        # Fallback
        return SolarFlare(timestamp=timestamp, severity=EventSeverity.LOW)
    
    def _create_attack_event(self, timestamp: datetime) -> Event:
        """Create a random attack event."""
        rates = {
            'gps_spoofing': self.config.gps_spoofing_rate,
            'command_injection': self.config.command_injection_rate,
            'jamming': self.config.jamming_attack_rate,
            'laser_dazzle': self.config.laser_dazzle_rate,
            'power_drain': self.config.power_drain_rate,
            'thermal_sabotage': self.config.thermal_sabotage_rate,
        }
        
        total = sum(rates.values())
        choice = random.uniform(0, total)
        cumulative = 0
        
        for event_name, rate in rates.items():
            cumulative += rate
            if choice <= cumulative:
                event_class = self.attack_events[event_name]
                severity = self._choose_severity()
                return event_class(timestamp=timestamp, severity=severity)
        
        # Fallback
        return GPSSpoofing(timestamp=timestamp, severity=EventSeverity.LOW)
    
    def _choose_severity(self) -> EventSeverity:
        """Choose event severity based on configured distribution."""
        choice = random.random()
        cumulative = 0
        
        for severity, probability in self.config.severity_distribution.items():
            cumulative += probability
            if choice <= cumulative:
                return severity
        
        return EventSeverity.LOW  # Fallback
    
    def schedule_event(self, event: Event) -> None:
        """
        Add an event to the priority queue.
        
        Args:
            event: Event to schedule
        """
        # Use heapq for priority queue (events sorted by timestamp)
        heapq.heappush(self.event_queue, (event.timestamp, next(self._event_sequence), event))
        self._update_stats(event)
    
    def schedule_eclipse_events(self, 
                                current_time: datetime,
                                orbit_period_minutes: float = 90.0) -> None:
        """
        Schedule eclipse entry/exit events for the next orbit.
        
        Args:
            current_time: Current simulation time
            orbit_period_minutes: Satellite orbital period in minutes
        """
        # Simplified eclipse model: assume 35% of orbit is in shadow
        eclipse_duration = orbit_period_minutes * 0.35
        
        # Next eclipse entry (assume happens midway through orbit)
        next_entry = current_time + timedelta(minutes=orbit_period_minutes / 2)
        entry_event = EclipseEntry(timestamp=next_entry)
        self.schedule_event(entry_event)
        
        # Eclipse exit
        next_exit = next_entry + timedelta(minutes=eclipse_duration)
        exit_event = EclipseExit(timestamp=next_exit)
        self.schedule_event(exit_event)
    
    def update(self, current_time: datetime, state: Any) -> List[Event]:
        """
        Update event system and apply active events to state.
        
        Args:
            current_time: Current simulation time
            state: SatelliteState to apply events to
            
        Returns:
            List of events that occurred this timestep
        """
        current_time = simulation_start(current_time.isoformat())
        events_occurred = []
        
        # Process events from queue that are due
        while self.event_queue and self.event_queue[0][0] <= current_time:
            _, _, event = heapq.heappop(self.event_queue)
            self.active_events.append(event)
            self.event_history.append(event)
            events_occurred.append(event)
        
        # Apply all active events to state
        for event in self.active_events[:]:  # Copy list since we may modify it
            if event.is_active(current_time):
                try:
                    event.apply_to_state(state)
                except Exception as e:
                    print(f"Warning: Event {event.event_id} failed to apply: {e}")
            else:
                # Event no longer active, remove from active list
                self.active_events.remove(event)
        
        # Try to generate random events
        new_event = self.generate_random_event(current_time)
        if new_event:
            self.schedule_event(new_event)
        
        return events_occurred
    
    def _update_stats(self, event: Event) -> None:
        """Update event statistics."""
        self.stats['total_events'] += 1
        
        if event.is_attack:
            self.stats['attack_events'] += 1
        else:
            self.stats['environmental_events'] += 1
        
        self.stats['by_severity'][event.severity] += 1
        self.stats['by_type'][event.event_type] += 1
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get event statistics.
        
        Returns:
            Dictionary with event counts and distributions
        """
        stats = self.stats.copy()
        stats['active_events_count'] = len(self.active_events)
        stats['queued_events_count'] = len(self.event_queue)
        stats['history_length'] = len(self.event_history)
        return stats
    
    def get_active_events(self) -> List[Event]:
        """Get list of currently active events."""
        return self.active_events.copy()
    
    def get_event_history(self, 
                         since: Optional[datetime] = None,
                         event_type: Optional[EventType] = None,
                         is_attack: Optional[bool] = None) -> List[Event]:
        """
        Get event history with optional filtering.
        
        Args:
            since: Only return events after this time
            event_type: Filter by event type
            is_attack: Filter by attack/environmental (None = no filter)
            
        Returns:
            Filtered list of historical events
        """
        history = self.event_history
        
        if since:
            since = simulation_start(since.isoformat())
            history = [e for e in history if e.timestamp >= since]
        
        if event_type:
            history = [e for e in history if e.event_type == event_type]
        
        if is_attack is not None:
            history = [e for e in history if e.is_attack == is_attack]
        
        return history
    
    def export_event_log(self) -> List[Dict[str, Any]]:
        """
        Export complete event history for ML training.
        
        Returns:
            List of event dictionaries with all details
        """
        return [event.to_dict() for event in self.event_history]
    
    def clear_history(self) -> None:
        """Clear event history (useful for long simulations)."""
        self.event_history.clear()
    
    def reset(self) -> None:
        """Reset event manager to initial state."""
        self.event_queue.clear()
        self.active_events.clear()
        self.event_history.clear()
        self.stats = {
            'total_events': 0,
            'environmental_events': 0,
            'attack_events': 0,
            'by_severity': {sev: 0 for sev in EventSeverity},
            'by_type': {et: 0 for et in EventType}
        }

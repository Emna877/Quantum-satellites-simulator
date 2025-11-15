"""
Base Event Classes - Phase 2

Defines the fundamental event structure and enumerations for the simulation.
All events (environmental and attacks) inherit from the Event base class.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional
import uuid


class EventType(Enum):
    """Categories of events that can occur in the simulation."""
    # Environmental events
    SOLAR_FLARE = "solar_flare"
    ECLIPSE_ENTRY = "eclipse_entry"
    ECLIPSE_EXIT = "eclipse_exit"
    MICROMETEOROID_IMPACT = "micrometeoroid_impact"
    ATMOSPHERIC_DRAG_SPIKE = "atmospheric_drag_spike"
    GEOMAGNETIC_STORM = "geomagnetic_storm"
    
    # Attack events
    GPS_SPOOFING = "gps_spoofing"
    COMMAND_INJECTION = "command_injection"
    JAMMING_ATTACK = "jamming_attack"
    LASER_DAZZLE = "laser_dazzle"
    POWER_DRAIN = "power_drain"
    THERMAL_SABOTAGE = "thermal_sabotage"


class EventSeverity(Enum):
    """Severity levels for events, affecting impact magnitude."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class Event:
    """
    Base class for all simulation events.
    
    Events can be environmental (natural) or attacks (malicious).
    Each event has a timestamp, type, severity, and parameters that
    define how it affects the satellite state.
    
    Attributes:
        event_id: Unique identifier for this event instance
        timestamp: When the event occurs in simulation time
        event_type: Category of event (from EventType enum)
        severity: Impact level (from EventSeverity enum)
        is_attack: True if malicious attack, False if environmental
        duration_seconds: How long the event effects last (0 = instant)
        parameters: Event-specific parameters (e.g., radiation flux, frequency)
        description: Human-readable description
        ground_truth_label: True label for ML training (attack=1, natural=0)
    """
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.now)
    event_type: EventType = EventType.SOLAR_FLARE
    severity: EventSeverity = EventSeverity.LOW
    is_attack: bool = False
    duration_seconds: float = 0.0
    parameters: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    ground_truth_label: int = 0  # 0 = natural, 1 = attack
    
    def __post_init__(self):
        """Validate event data after initialization."""
        # Auto-set ground truth label based on is_attack flag
        self.ground_truth_label = 1 if self.is_attack else 0
        
        # Ensure duration is non-negative
        if self.duration_seconds < 0:
            self.duration_seconds = 0.0
        
        # Generate description if not provided
        if not self.description:
            self.description = self._generate_description()
    
    def _generate_description(self) -> str:
        """Generate a human-readable description of the event."""
        event_name = self.event_type.value.replace('_', ' ').title()
        severity_name = self.severity.name.title()
        attack_str = "Attack" if self.is_attack else "Event"
        
        return f"{severity_name} {event_name} {attack_str}"
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert event to dictionary for logging.
        
        Returns:
            Dictionary with all event attributes
        """
        return {
            'event_id': self.event_id,
            'timestamp': self.timestamp.isoformat(),
            'event_type': self.event_type.value,
            'severity': self.severity.name,
            'is_attack': self.is_attack,
            'duration_seconds': self.duration_seconds,
            'parameters': self.parameters,
            'description': self.description,
            'ground_truth_label': self.ground_truth_label
        }
    
    def apply_to_state(self, state: Any) -> None:
        """
        Apply event effects to satellite state.
        
        Override this method in subclasses to implement specific effects.
        
        Args:
            state: SatelliteState object to modify
        """
        raise NotImplementedError("Subclasses must implement apply_to_state()")
    
    def is_active(self, current_time: datetime) -> bool:
        """
        Check if event is currently active.
        
        Args:
            current_time: Current simulation time
            
        Returns:
            True if event is still affecting the satellite
        """
        if self.duration_seconds == 0:
            # Instantaneous event
            return False
        
        elapsed = (current_time - self.timestamp).total_seconds()
        return 0 <= elapsed <= self.duration_seconds
    
    def get_effect_multiplier(self, current_time: datetime) -> float:
        """
        Get current effect strength based on time since event start.
        
        For events with duration, effects may ramp up/down over time.
        
        Args:
            current_time: Current simulation time
            
        Returns:
            Multiplier from 0.0 to 1.0
        """
        if not self.is_active(current_time):
            return 0.0
        
        if self.duration_seconds == 0:
            return 1.0
        
        # Simple linear ramp: peak at start, decay to zero at end
        elapsed = (current_time - self.timestamp).total_seconds()
        return 1.0 - (elapsed / self.duration_seconds)
    
    def __str__(self) -> str:
        """String representation for logging."""
        return (f"Event({self.event_id[:8]}... @ {self.timestamp.isoformat()}: "
                f"{self.description})")
    
    def __repr__(self) -> str:
        """Detailed representation for debugging."""
        return (f"Event(id={self.event_id}, type={self.event_type.value}, "
                f"severity={self.severity.name}, is_attack={self.is_attack}, "
                f"duration={self.duration_seconds}s)")

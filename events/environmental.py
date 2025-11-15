"""
Environmental Events - Phase 2

Natural space environment events that affect satellite operations.
These events simulate realistic space weather and orbital conditions.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any
import random

from events.base import Event, EventType, EventSeverity


@dataclass
class SolarFlare(Event):
    """
    Solar flare event causing increased radiation and communication disruption.
    
    Effects:
    - Increases radiation dose rate
    - Reduces communication signal strength
    - May cause temporary power fluctuations
    - Duration: 30 minutes to 2 hours
    """
    
    def __post_init__(self):
        self.event_type = EventType.SOLAR_FLARE
        self.is_attack = False
        
        # Set duration based on severity (30 min to 2 hours)
        duration_map = {
            EventSeverity.LOW: 1800,      # 30 minutes
            EventSeverity.MEDIUM: 3600,   # 1 hour
            EventSeverity.HIGH: 5400,     # 1.5 hours
            EventSeverity.CRITICAL: 7200  # 2 hours
        }
        self.duration_seconds = duration_map.get(self.severity, 1800)
        
        # Set radiation flux (krad/s increase)
        flux_map = {
            EventSeverity.LOW: 0.001,
            EventSeverity.MEDIUM: 0.003,
            EventSeverity.HIGH: 0.008,
            EventSeverity.CRITICAL: 0.015
        }
        self.parameters['radiation_flux_increase'] = flux_map.get(self.severity, 0.001)
        self.parameters['comm_degradation_db'] = self.severity.value * 2.0
        
        super().__post_init__()
    
    def apply_to_state(self, state: Any) -> None:
        """Apply solar flare effects to satellite state."""
        multiplier = self.get_effect_multiplier(state.timestamp)
        
        if multiplier > 0:
            # Increase radiation dose rate
            radiation_increase = self.parameters['radiation_flux_increase'] * multiplier
            state.radiation_dose_rate += radiation_increase
            
            # Degrade communication signal
            comm_loss = self.parameters['comm_degradation_db'] * multiplier
            state.signal_strength_db = max(-120, state.signal_strength_db - comm_loss)
            
            # Minor power fluctuation
            power_variation = random.uniform(-5, 0) * multiplier
            state.battery_charge_pct = max(0, min(100, 
                state.battery_charge_pct + power_variation))


@dataclass
class EclipseEntry(Event):
    """
    Satellite enters Earth's shadow, cutting off solar power.
    
    Effects:
    - Solar power drops to zero
    - Battery begins discharging
    - Temperature starts decreasing
    - Duration: Instantaneous transition
    """
    
    def __post_init__(self):
        self.event_type = EventType.ECLIPSE_ENTRY
        self.is_attack = False
        self.duration_seconds = 0  # Instantaneous
        self.severity = EventSeverity.MEDIUM  # Always medium impact
        super().__post_init__()
    
    def apply_to_state(self, state: Any) -> None:
        """Mark satellite as entering eclipse."""
        state.in_sunlight = False
        state.solar_panel_power_w = 0.0


@dataclass
class EclipseExit(Event):
    """
    Satellite exits Earth's shadow, restoring solar power.
    
    Effects:
    - Solar power restored
    - Battery begins charging
    - Temperature starts increasing
    - Duration: Instantaneous transition
    """
    
    def __post_init__(self):
        self.event_type = EventType.ECLIPSE_EXIT
        self.is_attack = False
        self.duration_seconds = 0  # Instantaneous
        self.severity = EventSeverity.LOW  # Positive event
        super().__post_init__()
    
    def apply_to_state(self, state: Any) -> None:
        """Mark satellite as exiting eclipse."""
        state.in_sunlight = True
        # Solar power will be recalculated by subsystems


@dataclass
class MicrometeoroidImpact(Event):
    """
    Micrometeoroid collision causing minor structural damage.
    
    Effects:
    - Slight attitude disturbance
    - Minor temperature anomaly
    - Possible sensor degradation
    - Component health decrease
    - Duration: Instantaneous with lasting effects
    """
    
    def __post_init__(self):
        self.event_type = EventType.MICROMETEOROID_IMPACT
        self.is_attack = False
        self.duration_seconds = 0  # Instantaneous damage
        
        # Set impact energy based on severity
        energy_map = {
            EventSeverity.LOW: 0.01,      # Minor scratch
            EventSeverity.MEDIUM: 0.05,   # Small dent
            EventSeverity.HIGH: 0.15,     # Moderate damage
            EventSeverity.CRITICAL: 0.40  # Significant damage
        }
        self.parameters['impact_energy_j'] = energy_map.get(self.severity, 0.01)
        self.parameters['health_decrease'] = self.severity.value * 5.0
        
        super().__post_init__()
    
    def apply_to_state(self, state: Any) -> None:
        """Apply micrometeoroid impact effects."""
        # Attitude disturbance (angular velocity spike)
        disturbance = self.parameters['impact_energy_j'] * 0.1
        state.angular_velocity_rad_s[0] += random.uniform(-disturbance, disturbance)
        state.angular_velocity_rad_s[1] += random.uniform(-disturbance, disturbance)
        state.angular_velocity_rad_s[2] += random.uniform(-disturbance, disturbance)
        
        # Component health decrease
        health_loss = self.parameters['health_decrease']
        state.component_health_pct = max(0, state.component_health_pct - health_loss)
        
        # Temperature spike from impact
        state.internal_temp_c += random.uniform(0, 5)


@dataclass
class AtmosphericDragSpike(Event):
    """
    Temporary increase in atmospheric drag due to density variations.
    
    Effects:
    - Increased orbital decay rate
    - Altitude decreases faster
    - Attitude control required
    - Duration: 10-30 minutes
    """
    
    def __post_init__(self):
        self.event_type = EventType.ATMOSPHERIC_DRAG_SPIKE
        self.is_attack = False
        
        # Duration: 10-30 minutes depending on severity
        duration_map = {
            EventSeverity.LOW: 600,       # 10 minutes
            EventSeverity.MEDIUM: 1200,   # 20 minutes
            EventSeverity.HIGH: 1800,     # 30 minutes
            EventSeverity.CRITICAL: 2400  # 40 minutes
        }
        self.duration_seconds = duration_map.get(self.severity, 600)
        
        # Drag coefficient increase (multiplier)
        self.parameters['drag_multiplier'] = 1.0 + (self.severity.value * 0.5)
        
        super().__post_init__()
    
    def apply_to_state(self, state: Any) -> None:
        """Apply increased drag effects."""
        multiplier = self.get_effect_multiplier(state.timestamp)
        
        if multiplier > 0:
            # Drag effects handled by propagator, but we can mark it
            drag_factor = self.parameters['drag_multiplier']
            # In real implementation, this would affect orbit propagation
            # For now, we just note it in parameters
            state.parameters = getattr(state, 'parameters', {})
            state.parameters['drag_multiplier'] = drag_factor * multiplier


@dataclass
class GeomagneticStorm(Event):
    """
    Geomagnetic storm affecting communication and navigation.
    
    Effects:
    - GPS accuracy degradation
    - Communication link disruption
    - Increased radiation exposure
    - Torque from Earth's magnetic field
    - Duration: 2-8 hours
    """
    
    def __post_init__(self):
        self.event_type = EventType.GEOMAGNETIC_STORM
        self.is_attack = False
        
        # Duration: 2-8 hours based on severity
        duration_map = {
            EventSeverity.LOW: 7200,      # 2 hours
            EventSeverity.MEDIUM: 14400,  # 4 hours
            EventSeverity.HIGH: 21600,    # 6 hours
            EventSeverity.CRITICAL: 28800 # 8 hours
        }
        self.duration_seconds = duration_map.get(self.severity, 7200)
        
        # Kp index (geomagnetic activity, 1-9 scale)
        kp_map = {
            EventSeverity.LOW: 5,
            EventSeverity.MEDIUM: 7,
            EventSeverity.HIGH: 8,
            EventSeverity.CRITICAL: 9
        }
        self.parameters['kp_index'] = kp_map.get(self.severity, 5)
        self.parameters['gps_error_m'] = self.severity.value * 10.0
        
        super().__post_init__()
    
    def apply_to_state(self, state: Any) -> None:
        """Apply geomagnetic storm effects."""
        multiplier = self.get_effect_multiplier(state.timestamp)
        
        if multiplier > 0:
            # Degrade GPS accuracy
            gps_error = self.parameters['gps_error_m'] * multiplier
            # Add position uncertainty (would be used by navigation filter)
            
            # Communication degradation
            comm_loss = self.parameters['kp_index'] * multiplier
            state.signal_strength_db = max(-120, state.signal_strength_db - comm_loss)
            
            # Increased radiation
            radiation_increase = 0.0005 * self.parameters['kp_index'] * multiplier
            state.radiation_dose_rate += radiation_increase
            
            # Magnetic torque (affects attitude)
            torque = 0.001 * self.parameters['kp_index'] * multiplier
            state.angular_velocity_rad_s[2] += random.uniform(-torque, torque)

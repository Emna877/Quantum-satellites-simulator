"""
Attack Events - Phase 2

Simulated cyber and physical attack scenarios on satellite systems.
These events represent malicious actions with ground truth labels for ML training.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any
import random

from events.base import Event, EventType, EventSeverity


@dataclass
class GPSSpoofing(Event):
    """
    GPS spoofing attack providing false position/time data.
    
    Effects:
    - Position error increases gradually
    - Navigation accuracy degrades
    - Attitude determination affected
    - Time synchronization drift
    - Duration: 5-20 minutes until detection
    """
    
    def __post_init__(self):
        self.event_type = EventType.GPS_SPOOFING
        self.is_attack = True
        
        # Duration depends on detection time (faster for higher severity)
        duration_map = {
            EventSeverity.LOW: 1200,      # 20 minutes (subtle, hard to detect)
            EventSeverity.MEDIUM: 900,    # 15 minutes
            EventSeverity.HIGH: 600,      # 10 minutes
            EventSeverity.CRITICAL: 300   # 5 minutes (obvious, quick detection)
        }
        self.duration_seconds = duration_map.get(self.severity, 900)
        
        # Position error magnitude (meters)
        error_map = {
            EventSeverity.LOW: 50,
            EventSeverity.MEDIUM: 200,
            EventSeverity.HIGH: 500,
            EventSeverity.CRITICAL: 1000
        }
        self.parameters['position_error_m'] = error_map.get(self.severity, 100)
        self.parameters['time_drift_ms'] = self.severity.value * 10.0
        
        super().__post_init__()
    
    def apply_to_state(self, state: Any) -> None:
        """Apply GPS spoofing effects."""
        multiplier = self.get_effect_multiplier(state.timestamp)
        
        if multiplier > 0:
            # Position error accumulates over time
            position_error = self.parameters['position_error_m'] * (1.0 - multiplier)
            # Would affect navigation filter in real system
            
            # Mark anomaly in component health
            health_impact = self.severity.value * 2.0 * multiplier
            state.component_health_pct = max(0, state.component_health_pct - health_impact)


@dataclass
class CommandInjection(Event):
    """
    Unauthorized command injection attack.
    
    Effects:
    - Erratic system behavior
    - Unintended actuator commands
    - Attitude control disruption
    - Power system interference
    - Duration: Instantaneous or until countermeasures
    """
    
    def __post_init__(self):
        self.event_type = EventType.COMMAND_INJECTION
        self.is_attack = True
        
        # Duration: immediate to 5 minutes
        duration_map = {
            EventSeverity.LOW: 60,        # 1 minute
            EventSeverity.MEDIUM: 180,    # 3 minutes
            EventSeverity.HIGH: 300,      # 5 minutes
            EventSeverity.CRITICAL: 600   # 10 minutes
        }
        self.duration_seconds = duration_map.get(self.severity, 180)
        
        self.parameters['command_rate_hz'] = self.severity.value * 2.0
        self.parameters['actuator_error_deg'] = self.severity.value * 5.0
        
        super().__post_init__()
    
    def apply_to_state(self, state: Any) -> None:
        """Apply command injection effects."""
        multiplier = self.get_effect_multiplier(state.timestamp)
        
        if multiplier > 0:
            # Attitude disturbance from erratic commands
            disturbance = self.parameters['actuator_error_deg'] * multiplier * 0.01
            state.angular_velocity_rad_s[0] += random.uniform(-disturbance, disturbance)
            state.angular_velocity_rad_s[1] += random.uniform(-disturbance, disturbance)
            state.angular_velocity_rad_s[2] += random.uniform(-disturbance, disturbance)
            
            # Power fluctuation from unauthorized commands
            power_impact = random.uniform(-10, -5) * multiplier
            state.battery_charge_pct = max(0, min(100, 
                state.battery_charge_pct + power_impact))
            
            # System health degradation
            health_loss = self.severity.value * 3.0 * multiplier
            state.component_health_pct = max(0, state.component_health_pct - health_loss)


@dataclass
class JammingAttack(Event):
    """
    RF jamming attack disrupting communication links.
    
    Effects:
    - Communication link loss
    - Signal strength drops dramatically
    - Data throughput reduced to zero
    - Ground contact lost
    - Duration: 2-15 minutes
    """
    
    def __post_init__(self):
        self.event_type = EventType.JAMMING_ATTACK
        self.is_attack = True
        
        # Duration based on attack sophistication
        duration_map = {
            EventSeverity.LOW: 120,       # 2 minutes
            EventSeverity.MEDIUM: 300,    # 5 minutes
            EventSeverity.HIGH: 600,      # 10 minutes
            EventSeverity.CRITICAL: 900   # 15 minutes
        }
        self.duration_seconds = duration_map.get(self.severity, 300)
        
        # Jamming power (dBm)
        power_map = {
            EventSeverity.LOW: 30,
            EventSeverity.MEDIUM: 50,
            EventSeverity.HIGH: 70,
            EventSeverity.CRITICAL: 90
        }
        self.parameters['jamming_power_dbm'] = power_map.get(self.severity, 50)
        
        super().__post_init__()
    
    def apply_to_state(self, state: Any) -> None:
        """Apply jamming attack effects."""
        multiplier = self.get_effect_multiplier(state.timestamp)
        
        if multiplier > 0:
            # Severe signal degradation
            jamming_impact = self.parameters['jamming_power_dbm'] * multiplier * 0.5
            state.signal_strength_db = max(-120, state.signal_strength_db - jamming_impact)
            
            # Communication throughput drops
            throughput_loss = min(1.0, multiplier * 1.5)  # Can go to zero
            state.data_rate_mbps = max(0, state.data_rate_mbps * (1.0 - throughput_loss))
            
            # Packet loss increases
            state.packet_loss_pct = min(100, state.packet_loss_pct + 50 * multiplier)


@dataclass
class LaserDazzle(Event):
    """
    the 
    """
    
    def __post_init__(self):
        self.event_type = EventType.LASER_DAZZLE
        self.is_attack = True
        
        # Duration: brief bursts
        duration_map = {
            EventSeverity.LOW: 30,        # 30 seconds
            EventSeverity.MEDIUM: 60,     # 1 minute
            EventSeverity.HIGH: 180,      # 3 minutes
            EventSeverity.CRITICAL: 300   # 5 minutes
        }
        self.duration_seconds = duration_map.get(self.severity, 60)
        
        # Laser power (watts)
        self.parameters['laser_power_w'] = self.severity.value * 5.0
        self.parameters['sensor_degradation_pct'] = self.severity.value * 20.0
        
        super().__post_init__()
    
    def apply_to_state(self, state: Any) -> None:
        """Apply laser dazzle effects."""
        multiplier = self.get_effect_multiplier(state.timestamp)
        
        if multiplier > 0:
            # Attitude determination error increases
            # (would affect attitude quaternion accuracy in real system)
            
            # Component health impact (sensor damage)
            sensor_damage = self.parameters['sensor_degradation_pct'] * multiplier * 0.1
            state.component_health_pct = max(0, state.component_health_pct - sensor_damage)
            
            # Angular velocity uncertainty increases (gyros less reliable)
            noise = self.severity.value * 0.001 * multiplier
            state.angular_velocity_rad_s[0] += random.uniform(-noise, noise)
            state.angular_velocity_rad_s[1] += random.uniform(-noise, noise)
            state.angular_velocity_rad_s[2] += random.uniform(-noise, noise)


@dataclass
class PowerDrain(Event):
    """
    Malicious power drain attack via software exploit.
    
    Effects:
    - Battery discharge rate increases
    - System power consumption spikes
    - Thermal load increases
    - Component health degrades
    - Duration: 5-30 minutes until detection
    """
    
    def __post_init__(self):
        self.event_type = EventType.POWER_DRAIN
        self.is_attack = True
        
        # Duration until security systems detect anomaly
        duration_map = {
            EventSeverity.LOW: 1800,      # 30 minutes (subtle drain)
            EventSeverity.MEDIUM: 900,    # 15 minutes
            EventSeverity.HIGH: 600,      # 10 minutes
            EventSeverity.CRITICAL: 300   # 5 minutes (obvious spike)
        }
        self.duration_seconds = duration_map.get(self.severity, 900)
        
        # Additional power consumption (watts)
        power_map = {
            EventSeverity.LOW: 10,
            EventSeverity.MEDIUM: 30,
            EventSeverity.HIGH: 60,
            EventSeverity.CRITICAL: 100
        }
        self.parameters['extra_power_w'] = power_map.get(self.severity, 30)
        
        super().__post_init__()
    
    def apply_to_state(self, state: Any) -> None:
        """Apply power drain attack effects."""
        multiplier = self.get_effect_multiplier(state.timestamp)
        
        if multiplier > 0:
            # Accelerated battery discharge
            drain_rate = self.parameters['extra_power_w'] * multiplier * 0.01  # %/second
            state.battery_charge_pct = max(0, state.battery_charge_pct - drain_rate)
            
            # Temperature increase from extra power dissipation
            temp_increase = self.parameters['extra_power_w'] * multiplier * 0.01
            state.internal_temp_c += temp_increase
            
            # System health degradation from overuse
            health_loss = self.severity.value * 0.5 * multiplier
            state.component_health_pct = max(0, state.component_health_pct - health_loss)


@dataclass
class ThermalSabotage(Event):
    """
    Thermal management system sabotage causing temperature extremes.
    
    Effects:
    - Temperature control failure
    - Rapid temperature changes
    - Component stress and damage
    - System instability
    - Duration: 10-60 minutes
    """
    
    def __post_init__(self):
        self.event_type = EventType.THERMAL_SABOTAGE
        self.is_attack = True
        
        # Duration depends on thermal control system response
        duration_map = {
            EventSeverity.LOW: 600,       # 10 minutes
            EventSeverity.MEDIUM: 1800,   # 30 minutes
            EventSeverity.HIGH: 2700,     # 45 minutes
            EventSeverity.CRITICAL: 3600  # 60 minutes
        }
        self.duration_seconds = duration_map.get(self.severity, 1800)
        
        # Temperature excursion (degrees C)
        temp_map = {
            EventSeverity.LOW: 10,
            EventSeverity.MEDIUM: 20,
            EventSeverity.HIGH: 35,
            EventSeverity.CRITICAL: 50
        }
        self.parameters['temp_excursion_c'] = temp_map.get(self.severity, 20)
        
        super().__post_init__()
    
    def apply_to_state(self, state: Any) -> None:
        """Apply thermal sabotage effects."""
        multiplier = self.get_effect_multiplier(state.timestamp)
        
        if multiplier > 0:
            # Temperature oscillation (heating or cooling)
            temp_change = self.parameters['temp_excursion_c'] * multiplier
            # Randomly heat or cool
            direction = random.choice([-1, 1])
            state.internal_temp_c += direction * temp_change * 0.01
            
            # External temperature also affected
            state.external_temp_c += direction * temp_change * 0.02
            
            # Component health degrades from thermal stress
            thermal_damage = self.severity.value * 1.5 * multiplier
            state.component_health_pct = max(0, state.component_health_pct - thermal_damage)
            
            # Power system affected by temperature extremes
            if abs(state.internal_temp_c) > 40:  # Outside normal range
                power_impact = random.uniform(-5, 0) * multiplier
                state.battery_charge_pct = max(0, min(100, 
                    state.battery_charge_pct + power_impact))

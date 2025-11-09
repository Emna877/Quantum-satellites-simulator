"""
Satellite State Model - Comprehensive representation of satellite physical and operational state.

This module defines the SatelliteState dataclass that captures all parameters needed
for physics simulation, anomaly detection, and telemetry logging.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional
import numpy as np


@dataclass
class SatelliteState:
    """
    Complete satellite state representation.
    
    All units are SI unless otherwise specified:
    - Distances in meters
    - Velocities in meters/second
    - Angles in radians
    - Temperatures in Celsius
    - Power in Watts
    - Current in Amperes
    - Battery in percentage (0-100)
    """
    
    # Timestamp
    timestamp: datetime
    
    # Orbital state (ECEF - Earth-Centered Earth-Fixed frame)
    position: np.ndarray = field(default_factory=lambda: np.zeros(3))  # [x, y, z] meters
    velocity: np.ndarray = field(default_factory=lambda: np.zeros(3))  # [vx, vy, vz] m/s
    altitude: float = 0.0  # meters above reference ellipsoid
    
    # Attitude state
    quaternion: np.ndarray = field(default_factory=lambda: np.array([1.0, 0.0, 0.0, 0.0]))  # [qw, qx, qy, qz]
    angular_velocity: np.ndarray = field(default_factory=lambda: np.zeros(3))  # [ωx, ωy, ωz] rad/s
    
    # Power subsystem
    battery_percent: float = 100.0  # 0-100%
    solar_current: float = 0.0  # Amperes
    power_consumption: float = 0.0  # Watts
    charging_rate: float = 0.0  # Watts
    
    # Thermal subsystem
    internal_temp: float = 20.0  # Celsius
    external_temp: float = 20.0  # Celsius
    heat_dissipation_rate: float = 0.0  # Watts
    
    # Communication subsystem
    signal_strength: float = -100.0  # dBm
    packet_loss: float = 0.0  # percentage 0-100
    uplink_rate: float = 0.0  # kbps
    downlink_rate: float = 0.0  # kbps
    
    # Environmental exposure
    radiation_dose: float = 0.0  # mGy/h (milliGray per hour)
    drag_coefficient: float = 2.2  # dimensionless
    in_eclipse: bool = False
    
    # Component health
    component_health: Dict[str, str] = field(default_factory=lambda: {
        "solar_panel_1": "OPERATIONAL",
        "solar_panel_2": "OPERATIONAL",
        "battery": "OPERATIONAL",
        "radio": "OPERATIONAL",
        "computer": "OPERATIONAL",
        "star_tracker": "OPERATIONAL",
        "magnetometer": "OPERATIONAL",
        "gyroscope": "OPERATIONAL",
        "reaction_wheel": "OPERATIONAL",
    })
    
    # Error counters and diagnostics
    error_counters: Dict[str, int] = field(default_factory=lambda: {
        "communication_errors": 0,
        "single_event_upsets": 0,
        "attitude_control_errors": 0,
        "power_anomalies": 0,
    })
    
    # Last commanded action
    last_command_time: Optional[datetime] = None
    last_command_type: str = "NONE"
    
    def to_dict(self) -> dict:
        """Convert state to dictionary for logging."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "pos_x": float(self.position[0]),
            "pos_y": float(self.position[1]),
            "pos_z": float(self.position[2]),
            "vel_x": float(self.velocity[0]),
            "vel_y": float(self.velocity[1]),
            "vel_z": float(self.velocity[2]),
            "altitude": float(self.altitude),
            "quat_w": float(self.quaternion[0]),
            "quat_x": float(self.quaternion[1]),
            "quat_y": float(self.quaternion[2]),
            "quat_z": float(self.quaternion[3]),
            "omega_x": float(self.angular_velocity[0]),
            "omega_y": float(self.angular_velocity[1]),
            "omega_z": float(self.angular_velocity[2]),
            "battery_pct": float(self.battery_percent),
            "solar_current": float(self.solar_current),
            "power_consumption": float(self.power_consumption),
            "charging_rate": float(self.charging_rate),
            "internal_temp": float(self.internal_temp),
            "external_temp": float(self.external_temp),
            "signal_strength": float(self.signal_strength),
            "packet_loss": float(self.packet_loss),
            "uplink_rate": float(self.uplink_rate),
            "downlink_rate": float(self.downlink_rate),
            "radiation_dose": float(self.radiation_dose),
            "drag_coefficient": float(self.drag_coefficient),
            "in_eclipse": int(self.in_eclipse),
        }
    
    def validate(self) -> bool:
        """
        Validate that state is physically plausible.
        Returns True if valid, raises ValueError with details if invalid.
        """
        # Battery constraints
        if not (0.0 <= self.battery_percent <= 100.0):
            raise ValueError(f"Battery percent {self.battery_percent} outside valid range [0, 100]")
        
        # Temperature constraints (reasonable for CubeSat)
        if not (-50.0 <= self.internal_temp <= 85.0):
            raise ValueError(f"Internal temperature {self.internal_temp}°C outside survival range [-50, 85]")
        
        if not (-150.0 <= self.external_temp <= 150.0):
            raise ValueError(f"External temperature {self.external_temp}°C outside plausible range [-150, 150]")
        
        # Quaternion normalization check
        quat_norm = np.linalg.norm(self.quaternion)
        if not (0.99 <= quat_norm <= 1.01):
            raise ValueError(f"Quaternion norm {quat_norm} not normalized (should be ~1.0)")
        
        # Altitude check (LEO satellites typically 200-2000 km)
        if not (150e3 <= self.altitude <= 2500e3):
            raise ValueError(f"Altitude {self.altitude/1e3:.1f} km outside typical LEO range [150, 2500] km")
        
        # Signal strength check
        if not (-140.0 <= self.signal_strength <= 0.0):
            raise ValueError(f"Signal strength {self.signal_strength} dBm outside plausible range [-140, 0]")
        
        # Packet loss check
        if not (0.0 <= self.packet_loss <= 100.0):
            raise ValueError(f"Packet loss {self.packet_loss}% outside valid range [0, 100]")
        
        return True
    
    def copy(self) -> 'SatelliteState':
        """Create a deep copy of the state."""
        return SatelliteState(
            timestamp=self.timestamp,
            position=self.position.copy(),
            velocity=self.velocity.copy(),
            altitude=self.altitude,
            quaternion=self.quaternion.copy(),
            angular_velocity=self.angular_velocity.copy(),
            battery_percent=self.battery_percent,
            solar_current=self.solar_current,
            power_consumption=self.power_consumption,
            charging_rate=self.charging_rate,
            internal_temp=self.internal_temp,
            external_temp=self.external_temp,
            heat_dissipation_rate=self.heat_dissipation_rate,
            signal_strength=self.signal_strength,
            packet_loss=self.packet_loss,
            uplink_rate=self.uplink_rate,
            downlink_rate=self.downlink_rate,
            radiation_dose=self.radiation_dose,
            drag_coefficient=self.drag_coefficient,
            in_eclipse=self.in_eclipse,
            component_health=self.component_health.copy(),
            error_counters=self.error_counters.copy(),
            last_command_time=self.last_command_time,
            last_command_type=self.last_command_type,
        )

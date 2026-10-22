"""
Satellite State Model - Comprehensive representation of satellite physical and operational state.

This module defines the SatelliteState dataclass that captures all parameters needed
for physics simulation, anomaly detection, and telemetry logging.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional
import numpy as np
from copy import deepcopy
from config import simulation_start


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
    battery_capacity_wh: float = 20.0  # Event-energy accounting preset, not a subsystem model
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
    radiation_dose: float = 0.0  # Accumulated mGy
    radiation_rate_mgy_s: float = 0.0
    health_percent: float = 100.0
    navigation_error_m: float = 0.0
    navigation_time_offset_ms: float = 0.0
    attitude_error_deg: float = 0.0
    sensor_noise_rad_s: float = 0.0
    injected_command_count: float = 0.0  # Integrated expected count, not a random integer
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
    
    def __post_init__(self):
        self.timestamp = simulation_start(self.timestamp.isoformat())

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
            "radiation_rate_mgy_s": self.radiation_rate_mgy_s,
            "health_percent": self.health_percent,
            "navigation_error_m": self.navigation_error_m,
            "navigation_time_offset_ms": self.navigation_time_offset_ms,
            "attitude_error_deg": self.attitude_error_deg,
            "sensor_noise_rad_s": self.sensor_noise_rad_s,
            "injected_command_count": self.injected_command_count,
            "battery_capacity_wh": self.battery_capacity_wh,
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
        return deepcopy(self)

    # Compatibility properties for event system (aliased attributes)
    @property
    def radiation_dose_rate(self) -> float:
        """Compatibility name for dose rate in mGy/s (not accumulated dose)."""
        return self.radiation_rate_mgy_s
    
    @radiation_dose_rate.setter
    def radiation_dose_rate(self, value: float):
        self.radiation_rate_mgy_s = value
    
    @property
    def signal_strength_db(self) -> float:
        """Alias for signal_strength (dBm)."""
        return self.signal_strength
    
    @signal_strength_db.setter
    def signal_strength_db(self, value: float):
        self.signal_strength = value
    
    @property
    def signal_strength_dbm(self) -> float:
        """Alias for signal_strength (dBm)."""
        return self.signal_strength
    
    @signal_strength_dbm.setter
    def signal_strength_dbm(self, value: float):
        self.signal_strength = value
    
    @property
    def battery_charge_pct(self) -> float:
        """Alias for battery_percent."""
        return self.battery_percent
    
    @battery_charge_pct.setter
    def battery_charge_pct(self, value: float):
        self.battery_percent = value
    
    @property
    def solar_panel_power_w(self) -> float:
        """Solar power in watts (derived from current * voltage)."""
        return self.solar_current * 14.0  # Assume 14V nominal
    
    @solar_panel_power_w.setter
    def solar_panel_power_w(self, value: float):
        self.solar_current = value / 14.0
    
    @property
    def solar_panel_current(self) -> float:
        """Alias for solar_current."""
        return self.solar_current
    
    @solar_panel_current.setter
    def solar_panel_current(self, value: float):
        self.solar_current = value
    
    @property
    def in_sunlight(self) -> bool:
        """Inverse of in_eclipse."""
        return not self.in_eclipse
    
    @in_sunlight.setter
    def in_sunlight(self, value: bool):
        self.in_eclipse = not value
    
    @property
    def angular_velocity_rad_s(self) -> np.ndarray:
        """Alias for angular_velocity."""
        return self.angular_velocity
    
    @angular_velocity_rad_s.setter
    def angular_velocity_rad_s(self, value: np.ndarray):
        self.angular_velocity = value
    
    @property
    def component_health_pct(self) -> float:
        """Continuous aggregate damage budget; component failure modeling is deferred."""
        return self.health_percent
    
    @component_health_pct.setter
    def component_health_pct(self, value: float):
        """Store fractional damage without randomly changing component statuses."""
        self.health_percent = max(0.0, min(100.0, value))

    @property
    def component_health_percent(self) -> float:
        """Alias for component_health_pct."""
        return self.component_health_pct
    
    @component_health_percent.setter
    def component_health_percent(self, value: float):
        self.component_health_pct = value
    
    @property
    def internal_temp_c(self) -> float:
        """Alias for internal_temp."""
        return self.internal_temp
    
    @internal_temp_c.setter
    def internal_temp_c(self, value: float):
        self.internal_temp = value
    
    @property
    def navigation_accuracy_meters(self) -> float:
        """Nominal 10-m uncertainty plus the active navigation disturbance."""
        return 10.0 + self.navigation_error_m
    
    @navigation_accuracy_meters.setter
    def navigation_accuracy_meters(self, value: float):
        """Compatibility setter; does not modify true orbital position."""
        self.navigation_error_m = max(0.0, value-10.0)

    @property
    def external_temp_c(self):
        return self.external_temp

    @external_temp_c.setter
    def external_temp_c(self, value):
        self.external_temp = value

    @property
    def angular_velocity_z(self):
        return float(self.angular_velocity[2])

    @angular_velocity_z.setter
    def angular_velocity_z(self, value):
        self.angular_velocity[2] = value
    
    @property
    def data_rate_kbps(self) -> float:
        """Average of uplink and downlink rates."""
        return (self.uplink_rate + self.downlink_rate) / 2.0
    
    @data_rate_kbps.setter
    def data_rate_kbps(self, value: float):
        """Set both uplink and downlink to the same rate."""
        self.uplink_rate = value
        self.downlink_rate = value
    
    @property
    def data_rate_mbps(self) -> float:
        """Data rate in Mbps (converted from kbps)."""
        return self.data_rate_kbps / 1000.0
    
    @data_rate_mbps.setter
    def data_rate_mbps(self, value: float):
        """Set data rate in Mbps."""
        self.data_rate_kbps = value * 1000.0
    
    @property
    def packet_loss_pct(self) -> float:
        """Alias for packet_loss."""
        return self.packet_loss
    
    @packet_loss_pct.setter
    def packet_loss_pct(self, value: float):
        """Set packet loss percentage."""
        self.packet_loss = value

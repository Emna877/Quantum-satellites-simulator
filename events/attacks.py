"""Deterministic event surrogates, with explicit SI rates and reversible modifiers.

These presets exercise the engine; they are not calibrated spacecraft physics.
"""
from dataclasses import dataclass
import math
from events.base import Event, EventType


@dataclass
class GPSSpoofing(Event):
    def __post_init__(self):
        self.event_type, self.is_attack = EventType.GPS_SPOOFING, True
        self.duration_seconds = [1200, 900, 600, 300][self.severity.value-1]
        defaults = dict(position_error_m=[50,200,500,1000][self.severity.value-1],
                        time_drift_ms=self.severity.value*10.0)
        self.parameters = self.configure(defaults)
        super().__post_init__()

    def temporary_effects(self, timestamp):
        m = self.get_effect_multiplier(timestamp)
        return dict(navigation_error_m=(self.parameters['position_error_m']*m, 1),
                    navigation_time_offset_ms=(self.parameters['time_drift_ms']*m, 1))


@dataclass
class CommandInjection(Event):
    def __post_init__(self):
        self.event_type, self.is_attack = EventType.COMMAND_INJECTION, True
        self.duration_seconds = [60,180,300,600][self.severity.value-1]
        self.parameters = self.configure(dict(command_rate_hz=self.severity.value*2.0,
                                 actuator_error_deg=self.severity.value*5.0))
        super().__post_init__()

    def rates(self, state):
        rate = self.parameters['command_rate_hz']
        return dict(injected_command_count=rate, battery_percent=-rate*0.001,
                    component_health_pct=-rate*0.001,
                    angular_velocity_z=math.radians(self.parameters['actuator_error_deg'])*rate*0.0001)

    def temporary_effects(self, timestamp):
        return dict(attitude_error_deg=(self.parameters['actuator_error_deg']*self.get_effect_multiplier(timestamp), 1))


@dataclass
class JammingAttack(Event):
    def __post_init__(self):
        self.event_type, self.is_attack = EventType.JAMMING_ATTACK, True
        self.duration_seconds = [120,300,600,900][self.severity.value-1]
        self.parameters = self.configure(dict(signal_loss_db=self.severity.value*10.0,
                                 throughput_loss_fraction=min(1.0,self.severity.value*0.3),
                                 packet_loss_pct=self.severity.value*20.0))
        super().__post_init__()

    def temporary_effects(self, timestamp):
        m = self.get_effect_multiplier(timestamp)
        factor = 1-self.parameters['throughput_loss_fraction']*m
        return dict(signal_strength=(-self.parameters['signal_loss_db']*m, 1),
                    uplink_rate=(0,factor), downlink_rate=(0,factor),
                    packet_loss=(self.parameters['packet_loss_pct']*m,1))


@dataclass
class LaserDazzle(Event):
    def __post_init__(self):
        self.event_type, self.is_attack = EventType.LASER_DAZZLE, True
        self.duration_seconds = [30,60,180,300][self.severity.value-1]
        self.parameters = self.configure(dict(laser_power_w=self.severity.value*5.0,
                                 sensor_noise_rad_s=self.severity.value*0.001))
        super().__post_init__()

    def rates(self, state):
        return dict(component_health_pct=-self.parameters['laser_power_w']*0.0001,
                    internal_temp=self.parameters['laser_power_w']*0.001)

    def temporary_effects(self, timestamp):
        return dict(sensor_noise_rad_s=(self.parameters['sensor_noise_rad_s']*self.get_effect_multiplier(timestamp),1))


@dataclass
class PowerDrain(Event):
    def __post_init__(self):
        self.event_type, self.is_attack = EventType.POWER_DRAIN, True
        self.duration_seconds = [1800,900,600,300][self.severity.value-1]
        self.parameters = self.configure(dict(extra_power_w=[10,30,60,100][self.severity.value-1]))
        super().__post_init__()

    def rates(self, state):
        power = self.parameters['extra_power_w']
        if state.battery_capacity_wh <= 0:
            raise ValueError('battery_capacity_wh must be positive')
        return dict(battery_percent=-100*power/(3600*state.battery_capacity_wh),
                    internal_temp=power*0.0001, component_health_pct=-power*0.00001)

    def temporary_effects(self, timestamp):
        return dict(power_consumption=(self.parameters['extra_power_w']*self.get_effect_multiplier(timestamp),1))


@dataclass
class ThermalSabotage(Event):
    def __post_init__(self):
        self.event_type, self.is_attack = EventType.THERMAL_SABOTAGE, True
        self.duration_seconds = [600,1800,2700,3600][self.severity.value-1]
        self.parameters = self.configure(dict(temp_excursion_c=[10,20,35,50][self.severity.value-1], direction=1))
        if self.parameters['direction'] not in (-1,1):
            raise ValueError('Thermal direction must be -1 or 1')
        super().__post_init__()

    def rates(self, state):
        # Normalization makes the full-event internal excursion equal the parameter.
        rate = 2*self.parameters['temp_excursion_c']*self.parameters['direction']/self.duration_seconds
        return dict(internal_temp=rate, external_temp=rate*2,
                    component_health_pct=-2*self.severity.value/self.duration_seconds)

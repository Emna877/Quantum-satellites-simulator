"""Environmental event surrogates; orbital forces remain owned by Orekit."""
from dataclasses import dataclass
from events.base import Event, EventType, EventSeverity


@dataclass
class SolarFlare(Event):
    def __post_init__(self):
        self.event_type, self.is_attack = EventType.SOLAR_FLARE, False
        self.duration_seconds = [1800,3600,5400,7200][self.severity.value-1]
        self.parameters = self.configure(dict(radiation_rate_mgy_s=self.severity.value*0.000001,
                                 comm_degradation_db=self.severity.value*2.0,
                                 battery_drain_pct_s=self.severity.value*0.0005))
        super().__post_init__()

    def rates(self, state):
        return dict(radiation_dose=self.parameters['radiation_rate_mgy_s'],
                    battery_percent=-self.parameters['battery_drain_pct_s'])

    def temporary_effects(self, timestamp):
        m = self.get_effect_multiplier(timestamp)
        return dict(radiation_rate_mgy_s=(self.parameters['radiation_rate_mgy_s']*m,1),
                    signal_strength=(-self.parameters['comm_degradation_db']*m,1))


@dataclass
class EclipseEntry(Event):
    def __post_init__(self):
        self.event_type, self.is_attack = EventType.ECLIPSE_ENTRY, False
        self.duration_seconds, self.severity = 0, EventSeverity.MEDIUM
        super().__post_init__()

    def impulse(self, state):
        state.in_eclipse = True


@dataclass
class EclipseExit(Event):
    def __post_init__(self):
        self.event_type, self.is_attack = EventType.ECLIPSE_EXIT, False
        self.duration_seconds, self.severity = 0, EventSeverity.LOW
        super().__post_init__()

    def impulse(self, state):
        state.in_eclipse = False


@dataclass
class MicrometeoroidImpact(Event):
    def __post_init__(self):
        self.event_type, self.is_attack = EventType.MICROMETEOROID_IMPACT, False
        self.duration_seconds = 0
        self.parameters = self.configure(dict(impact_energy_j=[0.01,0.05,0.15,0.4][self.severity.value-1],
                                 health_decrease=self.severity.value*5.0))
        super().__post_init__()

    def impulse(self, state):
        energy = self.parameters['impact_energy_j']
        state.angular_velocity += energy*0.1
        state.component_health_pct = max(0,state.component_health_pct-self.parameters['health_decrease'])
        state.internal_temp += energy*5


@dataclass
class AtmosphericDragSpike(Event):
    """Temporary drag-coefficient disturbance; no decay in the two-body model."""
    def __post_init__(self):
        self.event_type, self.is_attack = EventType.ATMOSPHERIC_DRAG_SPIKE, False
        self.duration_seconds = [600,1200,1800,2400][self.severity.value-1]
        self.parameters = self.configure(dict(drag_multiplier=1+self.severity.value*0.5))
        super().__post_init__()

    def temporary_effects(self, timestamp):
        return dict(drag_coefficient=(0,1+(self.parameters['drag_multiplier']-1)*self.get_effect_multiplier(timestamp)))


@dataclass
class GeomagneticStorm(Event):
    def __post_init__(self):
        self.event_type, self.is_attack = EventType.GEOMAGNETIC_STORM, False
        self.duration_seconds = [7200,14400,21600,28800][self.severity.value-1]
        self.parameters = self.configure(dict(kp_index=[5,7,8,9][self.severity.value-1],
                                 gps_error_m=self.severity.value*10.0))
        super().__post_init__()

    def rates(self, state):
        return dict(radiation_dose=self.parameters['kp_index']*0.0000005)

    def temporary_effects(self, timestamp):
        m = self.get_effect_multiplier(timestamp)
        return dict(signal_strength=(-self.parameters['kp_index']*m,1),
                    navigation_error_m=(self.parameters['gps_error_m']*m,1),
                    radiation_rate_mgy_s=(self.parameters['kp_index']*0.0000005*m,1))

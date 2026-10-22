"""Transactional event lifecycle with exact envelope integration and Poisson arrivals."""
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import timedelta
import heapq
import math
import random
import uuid
from config import simulation_start
from events.base import Event, EventType, EventSeverity
from events.environmental import SolarFlare, EclipseEntry, EclipseExit, MicrometeoroidImpact, AtmosphericDragSpike, GeomagneticStorm
from events.attacks import GPSSpoofing, CommandInjection, JammingAttack, LaserDazzle, PowerDrain, ThermalSabotage


class EventApplicationError(RuntimeError):
    pass


@dataclass
class EventConfig:
    solar_flare_rate: float = 0.5
    micrometeoroid_rate: float = 2.0
    drag_spike_rate: float = 1.0
    geomagnetic_storm_rate: float = 0.3
    gps_spoofing_rate: float = 0.1
    command_injection_rate: float = 0.05
    jamming_attack_rate: float = 0.2
    laser_dazzle_rate: float = 0.1
    power_drain_rate: float = 0.05
    thermal_sabotage_rate: float = 0.05
    severity_distribution: dict = field(default_factory=lambda: {
        EventSeverity.LOW:0.5, EventSeverity.MEDIUM:0.3, EventSeverity.HIGH:0.15, EventSeverity.CRITICAL:0.05})
    enable_environmental: bool = True
    enable_attacks: bool = True
    random_seed: int = 0

    def __post_init__(self):
        for key,value in vars(self).items():
            if key.endswith('_rate') and (not math.isfinite(value) or value < 0):
                raise ValueError(f'{key} must be finite and nonnegative')
        distribution = self.severity_distribution
        if not distribution or any(not isinstance(k,EventSeverity) or not math.isfinite(v) or v < 0 for k,v in distribution.items()) or not math.isclose(sum(distribution.values()),1.0):
            raise ValueError('Severity probabilities must use EventSeverity keys and sum to 1')


class EventManager:
    environmental_events = dict(solar_flare=SolarFlare, micrometeoroid=MicrometeoroidImpact,
                                drag_spike=AtmosphericDragSpike, geomagnetic_storm=GeomagneticStorm)
    attack_events = dict(gps_spoofing=GPSSpoofing, command_injection=CommandInjection,
                         jamming_attack=JammingAttack, laser_dazzle=LaserDazzle,
                         power_drain=PowerDrain, thermal_sabotage=ThermalSabotage)

    def __init__(self, config=None):
        self.config = deepcopy(config or EventConfig())
        self.rng = random.Random(self.config.random_seed)
        self.event_queue = []
        self._event_sequence = 0
        self._seen = set()
        self.active_events = []
        self.event_history = []
        self._last_time = None
        self._next_random = None
        self._modifiers = {}
        self._modified_state = None
        self.failures = []
        self.stats = dict(total_events=0,environmental_events=0,attack_events=0,
                          by_severity={s:0 for s in EventSeverity},by_type={t:0 for t in EventType})

    def _rates(self, environmental=None):
        result = {}
        if environmental is not False and self.config.enable_environmental:
            result.update({cls:getattr(self.config,name+'_rate') for name,cls in self.environmental_events.items()})
        if environmental is not True and self.config.enable_attacks:
            result.update({cls:getattr(self.config,name+'_rate') for name,cls in self.attack_events.items()})
        return {cls:rate for cls,rate in result.items() if rate > 0}

    def _choose_severity(self):
        values = list(self.config.severity_distribution)
        return self.rng.choices(values, weights=[self.config.severity_distribution[v] for v in values])[0]

    def _create_event(self, timestamp, rates):
        if not rates:
            raise ValueError('No enabled event types with a positive rate')
        cls = self.rng.choices(list(rates),weights=list(rates.values()))[0]
        return cls(timestamp=timestamp,severity=self._choose_severity(),event_id=str(uuid.UUID(int=self.rng.getrandbits(128))))

    def _create_environmental_event(self,timestamp):
        return self._create_event(timestamp,self._rates(True))

    def _create_attack_event(self,timestamp):
        return self._create_event(timestamp,self._rates(False))

    def generate_random_event(self,current_time,dt_seconds=1.0):
        """Single Poisson trial for callers; update() uses exact arrival times instead."""
        if not math.isfinite(dt_seconds) or dt_seconds < 0:
            raise ValueError('Random event dt must be finite and nonnegative')
        rates = self._rates()
        probability = -math.expm1(-sum(rates.values())*dt_seconds/86400)
        return self._create_event(current_time,rates) if self.rng.random() < probability else None

    def _generate_arrivals(self,start,end):
        rates = self._rates()
        total = sum(rates.values())/86400
        if not total:
            return
        if self._next_random is None:
            self._next_random = start+timedelta(seconds=self.rng.expovariate(total))
        while self._next_random <= end:
            self.schedule_event(self._create_event(self._next_random,rates))
            self._next_random += timedelta(seconds=max(1e-6,self.rng.expovariate(total)))

    def schedule_event(self,event):
        if event.event_id in self._seen:
            raise ValueError(f'Event {event.event_id} is already scheduled or processed')
        if self._last_time is not None and event.timestamp < self._last_time:
            raise ValueError('Cannot schedule an event before the last processed time')
        self._seen.add(event.event_id)
        heapq.heappush(self.event_queue,(event.timestamp,self._event_sequence,event))
        self._event_sequence += 1
        self.stats['total_events'] += 1
        self.stats['attack_events' if event.is_attack else 'environmental_events'] += 1
        self.stats['by_severity'][event.severity] += 1
        self.stats['by_type'][event.event_type] += 1

    def schedule_eclipse_events(self,*args,**kwargs):
        raise ValueError('Synthetic periodic eclipses are removed; schedule transitions from Orekit eclipse states')

    def clear_modifiers(self,state):
        """Remove previous endpoint modifiers before a new subsystem baseline is computed.

        Explicit external assignments replace a baseline; unchanged modified values
        restore their saved baseline. Pass one persistent state per manager.
        """
        if self._modified_state is not None and self._modified_state is not state:
            raise ValueError('EventManager must update the same persistent state object')
        for name,(baseline,displayed) in self._modifiers.items():
            if getattr(state,name) == displayed:
                setattr(state,name,baseline)
        self._modifiers = {}
        self._modified_state = None

    def _apply_modifiers(self,state,time):
        combined = {}
        for event in self.active_events:
            try:
                effects = event.temporary_effects(time)
            except Exception as exc:
                raise EventApplicationError(f'{event.event_type.value} ({event.event_id}) modifier failed: {exc}') from exc
            for name,(offset,factor) in effects.items():
                old_offset,old_factor = combined.get(name,(0.0,1.0))
                combined[name] = (old_offset+offset, old_factor*factor)
        if state.in_eclipse:
            combined['solar_current'] = (0,0)
        for name,(offset,factor) in combined.items():
            base = getattr(state,name)
            value = base*factor+offset
            if not math.isfinite(value):
                raise ValueError(f'Non-finite temporary modifier for {name}')
            if name == 'signal_strength':
                value = max(-140,min(0,value))
            if name == 'packet_loss':
                value = max(0,min(100,value))
            setattr(state,name,value)
            self._modifiers[name] = (base,value)
        self._modified_state = state

    def update(self,current_time,state,dt_seconds=None):
        """Advance [previous, current], including events completely inside a large step.

        First call without dt establishes a zero-length initial observation. Repeated
        calls at the same time do not integrate twice. Failures restore state and queue.
        """
        current_time = simulation_start(current_time.isoformat())
        if dt_seconds is not None and (not math.isfinite(dt_seconds) or dt_seconds < 0):
            raise ValueError('Event dt must be finite and nonnegative')
        start = self._last_time if self._last_time is not None else current_time-timedelta(seconds=dt_seconds or 0)
        if current_time < start:
            raise ValueError('Event time cannot move backwards')
        if dt_seconds is not None and not math.isclose((current_time-start).total_seconds(),dt_seconds,abs_tol=1e-6):
            raise ValueError('Event dt does not match the elapsed timestamp interval')
        before = deepcopy(state.__dict__)
        bookkeeping = deepcopy({k:v for k,v in self.__dict__.items() if k not in ('_modified_state','failures')})
        modified_state = self._modified_state
        current_event = None
        try:
            self.clear_modifiers(state)
            state.timestamp = current_time
            self._generate_arrivals(start,current_time)
            occurred = []
            while self.event_queue and self.event_queue[0][0] <= current_time:
                _,_,event = heapq.heappop(self.event_queue)
                self.event_history.append(event)
                self.active_events.append(event)
                occurred.append(event)
            # Integrate at chronological impulse boundaries to preserve ordering.
            boundaries = sorted({start,current_time} | {e.timestamp for e in self.active_events if start < e.timestamp < current_time and e.duration_seconds == 0})
            impulses = sorted([e for e in occurred if e.duration_seconds == 0],key=lambda e:e.timestamp)
            for left,right in zip(boundaries,boundaries[1:]):
                for event in impulses[:]:
                    if event.timestamp <= left:
                        current_event=event
                        event.impulse(state)
                        impulses.remove(event)
                for event in self.active_events:
                    if event.duration_seconds:
                        current_event=event
                        event.integrate(state,left,right)
            for event in impulses:
                current_event=event
                event.impulse(state)
            self.active_events = [e for e in self.active_events if e.is_active(current_time)]
            self._apply_modifiers(state,current_time)
            self._last_time = current_time
            return occurred
        except Exception as exc:
            state.__dict__.clear()
            state.__dict__.update(before)
            self.__dict__.update(bookkeeping)
            self._modified_state = modified_state
            identity = f'{current_event.event_type.value} ({current_event.event_id})' if current_event else 'event modifiers/generation'
            self.failures.append(dict(timestamp=current_time.isoformat(),event=identity,error=str(exc)))
            raise EventApplicationError(f'Failed to apply {identity}: {exc}') from exc

    def checkpoint(self):
        return (deepcopy({k:v for k,v in self.__dict__.items() if k not in ('_modified_state','failures')}), self._modified_state)

    def restore(self,checkpoint):
        values,state = checkpoint
        self.__dict__.update(values)
        self._modified_state = state

    def get_statistics(self):
        return dict(deepcopy(self.stats),active_events_count=len(self.active_events),
                    queued_events_count=len(self.event_queue),history_length=len(self.event_history),
                    failed_updates=len(self.failures))

    def get_active_events(self):
        return self.active_events.copy()

    def get_event_history(self,since=None,event_type=None,is_attack=None):
        since = simulation_start(since.isoformat()) if since else None
        return [e for e in self.event_history if (since is None or e.timestamp >= since)
                and (event_type is None or e.event_type == event_type)
                and (is_attack is None or e.is_attack == is_attack)]

    def export_event_log(self):
        return [event.to_dict() for event in self.event_history]

    def clear_history(self):
        self.event_history.clear()

    def reset(self):
        if self._modified_state is not None:
            self.clear_modifiers(self._modified_state)
        self.__init__(self.config)

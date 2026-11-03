"""Named, reproducible attack and baseline scenario definitions.

Each scenario is a dataclass that specifies:
  - A human-readable name and description.
  - A list of event factory functions (called at runner setup time to create
    fresh event instances with specific timestamps).
  - Channel-specific disturbance parameters (separate from the event engine,
    for direct channel-config overrides when the event->state->channel path
    is not used).
  - A random seed for any stochastic elements.

Usage
-----
    from experiments.scenarios import SCENARIOS, build_events
    scenario = SCENARIOS['rf_jamming_moderate']
    events = scenario.build_events(contact_start, contact_end)

Determinism
-----------
All scenarios use a fixed default seed.  The runner passes this seed to the
EventManager so that repeated runs produce identical event schedules and
parameter draws.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional


@dataclass
class ScenarioDefinition:
    """A named, self-describing experiment scenario."""
    name: str
    description: str
    random_seed: int = 0
    # Each factory receives (contact_start, contact_end) and returns a list of events.
    event_factories: List[Callable] = field(default_factory=list)
    # Direct channel-disturbance overrides (applied in runner regardless of state)
    rf_signal_loss_db: float = 0.0          # extra RF loss (jamming)
    optical_background_scale: float = 1.0   # multiplier on sky background
    optical_cloud_blocked: bool = False     # hard optical block
    optical_extra_loss_db: float = 0.0      # additional optical path loss

    def build_events(self, contact_start: datetime, contact_end: datetime) -> list:
        events = []
        for factory in self.event_factories:
            events.extend(factory(contact_start, contact_end))
        return events


def _jamming_factory(severity: int, fraction_of_pass: float = 0.5,
                     offset_fraction: float = 0.2):
    """Return an event-factory that schedules a JammingAttack during the contact."""
    def factory(start: datetime, end: datetime):
        from events.attacks import JammingAttack
        from events.base import EventSeverity
        duration = (end - start).total_seconds()
        jam_start = start + timedelta(seconds=duration * offset_fraction)
        sev = [EventSeverity.LOW, EventSeverity.MEDIUM, EventSeverity.HIGH, EventSeverity.CRITICAL][severity - 1]
        return [JammingAttack(timestamp=jam_start, severity=sev)]
    return factory


def _spoofing_factory(severity: int, offset_fraction: float = 0.1):
    """Return an event-factory that schedules a GPSSpoofing event early in the pass."""
    def factory(start: datetime, end: datetime):
        from events.attacks import GPSSpoofing
        from events.base import EventSeverity
        duration = (end - start).total_seconds()
        spoof_start = start + timedelta(seconds=duration * offset_fraction)
        sev = [EventSeverity.LOW, EventSeverity.MEDIUM, EventSeverity.HIGH, EventSeverity.CRITICAL][severity - 1]
        return [GPSSpoofing(timestamp=spoof_start, severity=sev)]
    return factory


def _laser_dazzle_factory(severity: int, offset_fraction: float = 0.3):
    """Return an event-factory for a LaserDazzle event (elevates optical background)."""
    def factory(start: datetime, end: datetime):
        from events.attacks import LaserDazzle
        from events.base import EventSeverity
        duration = (end - start).total_seconds()
        dazzle_start = start + timedelta(seconds=duration * offset_fraction)
        sev = [EventSeverity.LOW, EventSeverity.MEDIUM, EventSeverity.HIGH, EventSeverity.CRITICAL][severity - 1]
        return [LaserDazzle(timestamp=dazzle_start, severity=sev)]
    return factory


# ---------------------------------------------------------------------------
# Named scenario catalogue
# ---------------------------------------------------------------------------

SCENARIOS: Dict[str, ScenarioDefinition] = {

    'baseline': ScenarioDefinition(
        name='Baseline',
        description=(
            'No disturbances.  Both classical and quantum-assisted links operate '
            'under clear-sky, nominal signal conditions.  Establishes the reference '
            'performance for all other scenarios.'
        ),
    ),

    'rf_jamming_low': ScenarioDefinition(
        name='RF Jamming (Low)',
        description=(
            'Moderate RF jamming targeting the classical data channel.  '
            'The optical QKD channel is on a separate physical link and is '
            'not directly affected by this attack.'
        ),
        rf_signal_loss_db=10.0,
        event_factories=[_jamming_factory(severity=1)],
    ),

    'rf_jamming_moderate': ScenarioDefinition(
        name='RF Jamming (Moderate)',
        description=(
            'Moderate-to-severe RF jamming.  Expected to degrade or break the '
            'classical RF link.  Classical key establishment may fail. '
            'Optical QKD channel is unaffected (separate physical channel).'
        ),
        rf_signal_loss_db=20.0,
        event_factories=[_jamming_factory(severity=2)],
    ),

    'rf_jamming_severe': ScenarioDefinition(
        name='RF Jamming (Severe)',
        description=(
            'Full-pass RF jamming at maximum severity.  Classical link expected '
            'to be unavailable for most or all of the contact window. '
            'QKD key rate may be unaffected if the optical link is clear.'
        ),
        rf_signal_loss_db=40.0,
        event_factories=[_jamming_factory(severity=4)],
    ),

    'gnss_spoofing': ScenarioDefinition(
        name='GNSS Spoofing',
        description=(
            'Navigation position estimate is corrupted.  The true Orekit orbital '
            'trajectory is unaffected; only the reported navigation measurement '
            'diverges.  Both RF and optical channels use true geometry; pointing '
            'errors from spoofed navigation are a future model extension.'
        ),
        event_factories=[_spoofing_factory(severity=2)],
    ),

    'optical_interference': ScenarioDefinition(
        name='Optical Interference (LaserDazzle)',
        description=(
            'Background-count elevation on the optical/QKD channel from laser '
            'interference or stray light.  QBER increases; the QKD protocol may '
            'abort if QBER exceeds the security threshold.  The RF channel is '
            'unaffected by this optical disturbance.'
        ),
        optical_background_scale=50.0,
        event_factories=[_laser_dazzle_factory(severity=2)],
    ),

    'optical_cloud_blocked': ScenarioDefinition(
        name='Optical Path Blocked (Cloud)',
        description=(
            'The optical path is fully blocked (cloud, obstruction).  The QKD '
            'optical channel produces zero sifted photons; key generation aborts. '
            'The RF channel is unaffected.'
        ),
        optical_cloud_blocked=True,
    ),

    'combined_rf_and_optical': ScenarioDefinition(
        name='Combined RF Jamming + Optical Interference',
        description=(
            'Simultaneous RF jamming and elevated optical background.  '
            'Classical key establishment is expected to fail; QKD key rate '
            'is degraded by elevated QBER.  Worst-case availability scenario.'
        ),
        rf_signal_loss_db=20.0,
        optical_background_scale=20.0,
        event_factories=[_jamming_factory(severity=2), _laser_dazzle_factory(severity=2)],
    ),

    'classical_auth_dependency': ScenarioDefinition(
        name='Classical Authentication Dependency',
        description=(
            'Baseline scenario demonstrating that QKD requires an authenticated '
            'classical channel for its own protocol messages.  If the classical '
            'channel is unavailable, QKD cannot complete its post-processing '
            'even if photons are received.  This scenario applies full RF jamming '
            'to show that QKD availability depends on classical availability.'
        ),
        rf_signal_loss_db=40.0,
        event_factories=[_jamming_factory(severity=4)],
    ),
}

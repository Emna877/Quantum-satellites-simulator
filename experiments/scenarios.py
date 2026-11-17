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
    rf_signal_loss_db: float = 0.0          # extra RF loss (jamming / power reduction)
    optical_background_scale: float = 1.0   # multiplier on sky background
    optical_cloud_blocked: bool = False     # hard optical block
    optical_extra_loss_db: float = 0.0      # additional optical path loss (pointing error, etc.)
    qkd_intercept_resend_fraction: float = 0.0  # fraction of signal photons intercepted and resent

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


def _power_drain_factory(severity: int, offset_fraction: float = 0.1):
    """Return an event-factory for a PowerDrain event."""
    def factory(start: datetime, end: datetime):
        from events.attacks import PowerDrain
        from events.base import EventSeverity
        duration = (end - start).total_seconds()
        drain_start = start + timedelta(seconds=duration * offset_fraction)
        sev = [EventSeverity.LOW, EventSeverity.MEDIUM, EventSeverity.HIGH, EventSeverity.CRITICAL][severity - 1]
        return [PowerDrain(timestamp=drain_start, severity=sev)]
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

    'qkd_intercept_resend': ScenarioDefinition(
        name='QKD Intercept-Resend (Full)',
        description=(
            'An eavesdropper intercepts every signal photon, measures it in a '
            'randomly chosen basis and resends her result.  Half of her basis '
            'guesses are wrong, so a quarter of the sifted bits disagree: QBER '
            'rises to about 25 % and the QKD protocol must abort.  This is the '
            'textbook demonstration that eavesdropping on the quantum channel is '
            'detectable.  The RF channel is unaffected.'
        ),
        qkd_intercept_resend_fraction=1.0,
    ),

    'qkd_intercept_resend_partial': ScenarioDefinition(
        name='QKD Intercept-Resend (20 %)',
        description=(
            'An eavesdropper intercepts 20 % of the signal photons.  QBER rises by '
            'about 5 percentage points.  Privacy amplification removes the leaked '
            'information, so the secure key shrinks but may remain positive.'
        ),
        qkd_intercept_resend_fraction=0.2,
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
            'Demonstrates that QKD requires an authenticated classical channel '
            'for its own protocol messages.  Full RF jamming blocks the RF link; '
            'photons are still detected on the clear optical link, but the runner '
            'aborts every pass because sifting, error correction and privacy '
            'amplification cannot be carried out.'
        ),
        rf_signal_loss_db=40.0,
        event_factories=[_jamming_factory(severity=4)],
    ),

    'pointing_error': ScenarioDefinition(
        name='Optical Pointing Error',
        description=(
            'Telescope pointing error adds extra optical path loss, reducing '
            'signal count and degrading QBER.  Models ACS residuals or satellite '
            'attitude disturbances that exceed the fine-steering mirror range.  '
            'The RF channel is unaffected; pointing loss is optical-only.  '
            'Extra loss of 6 dB corresponds to roughly doubling the effective '
            'beam divergence.'
        ),
        optical_extra_loss_db=6.0,
        event_factories=[],
    ),

    'power_shortage': ScenarioDefinition(
        name='Power Shortage',
        description=(
            'A PowerDrain attack or anomaly reduces available satellite power.  '
            'The direct channel-level effect modelled here is transmitter power '
            'reduction: the satellite reduces its RF transmit power by 6 dB to '
            'conserve energy, degrading link margin.  The optical transmitter '
            'may also reduce pulse rate; this is not yet modelled separately.  '
            'Expected result: lower RF SNR and potentially reduced optical '
            'source rate in future model extensions.'
        ),
        rf_signal_loss_db=6.0,
        event_factories=[_power_drain_factory(severity=2)],
    ),
}

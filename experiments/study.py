"""Scenario study: every scenario × an optical-uncertainty sweep on one shared geometry.

The study answers the paper-level question "what happens to each key-establishment
method under each scenario?" and reports the QKD key as a range instead of a
single number, because two optical inputs are poorly known:

  - sky/stray-light background: × 0.5, × 1, × 2 of the configured value
  - zenith atmospheric loss:    × 0.5, × 1, × 2 of the configured value
    (1 dB zenith ≈ 2.9 dB at 20° elevation; the sweep spans ≈ 1.5–6 dB there,
    comparable with the 3–8 dB Micius reported at 1200 km)

All 9 combinations are run for every scenario.  The nominal row uses the
configured values; the range is the minimum and maximum over the 9 variants.
Orekit geometry is computed once and reused, so variants differ only in the
channel parameters.

Detection column
----------------
For each scenario the study compares channel observables with the baseline and
states what the legitimate parties would notice:
  - QKD: the pass QBER.  If more passes abort at QBER ≥ 11 % than in the
    baseline, the disturbance was "detected"; a smaller, count-weighted rise
    shrinks the key through privacy amplification ("noticed").  QBER cannot tell an eavesdropper from noise, so optical
    interference is reported the same way: the protocol does not need to know
    the cause to stay secure.
  - RF: a session that succeeded in the baseline and fails in the scenario is
    a loss of availability (denial of service), not a loss of secrecy.
"""
from collections import Counter
from dataclasses import replace

from experiments.runner import ExperimentRunner
from experiments.scenarios import SCENARIOS

SWEEP_FACTORS = (0.5, 1.0, 2.0)
QBER_THRESHOLD = 0.11

METHODS = [
    dict(id='ecdh', name='ECDH P-256', channel='RF',
         summary='Breakable by a future quantum computer',
         detail=("Security rests on the elliptic-curve discrete logarithm, which Shor's algorithm "
                 'solves. Recorded traffic is exposed to "harvest now, decrypt later".')),
    dict(id='mlkem', name='ML-KEM-768', channel='RF',
         summary='Computational, NIST FIPS 203',
         detail=('Module-lattice key encapsulation standardised in 2024. No known quantum attack; '
                 'runs on existing radios and processors. Security is a hardness assumption.')),
    dict(id='qkd', name='Decoy-state BB84 QKD', channel='Optical + authenticated RF',
         summary=('Information-theoretic, but needs PSK authentication, special hardware and '
                  'clear skies, and only works at night'),
         detail=('Secrecy follows from quantum physics once post-processing is authenticated '
                 '(with a pre-shared key). Needs a single-photon transmitter, a telescope and '
                 'photon detectors; clouds block it and daylight is not modelled.')),
]


class CachedGeometry:
    """Propagator facade that computes each Orekit query once per study."""

    def __init__(self, propagator):
        self._propagator = propagator
        self._geometry = {}
        self._windows = {}

    def contact_windows(self, start, end, station, min_elevation_deg=5.0):
        key = (start, end, min_elevation_deg)
        if key not in self._windows:
            self._windows[key] = self._propagator.contact_windows(start, end, station, min_elevation_deg)
        return self._windows[key]

    def station_geometry(self, timestamp, station):
        if timestamp not in self._geometry:
            self._geometry[timestamp] = self._propagator.station_geometry(timestamp, station)
        return self._geometry[timestamp]


def _abort_category(reason):
    if not reason:
        return None
    if reason.startswith('QBER'):
        return 'QBER ≥ 11 %'
    if reason.startswith('Authenticated classical channel'):
        return 'No RF for post-processing'
    if reason.startswith('No sifted photons'):
        return 'No photons (optical link blocked)'
    if reason.startswith('Asymptotic rate is zero'):
        return 'Single-photon error too high'
    return 'Too few bits for finite-key bound'


def summarize(result):
    """Reduce one ExperimentResult.to_dict() to per-method pass counts and key bits."""
    passes = result['passes']
    finite = [p['qkd_finite_pass'] for p in passes]
    sifted = sum(f['n_sifted_bits'] for f in finite)
    qber = sum(f['qber'] * f['n_sifted_bits'] for f in finite) / sifted if sifted > 0 else None
    reasons = Counter(_abort_category(f['abort_reason']) for f in finite if f['key_status'] != 'succeeded')
    lit = [f['qber'] for f in finite if f['n_sifted_bits'] > 0]
    return {
        'passes': len(passes),
        'ecdh_passes': sum(bool(p['classical_session_summary']['key_established']) for p in passes),
        'mlkem_passes': sum(bool(p['pqc_session_summary']['key_established']) for p in passes),
        'qkd_passes': sum(f['key_status'] == 'succeeded' for f in finite),
        'qkd_key_bits': sum(f['secure_key_bits'] for f in finite),
        'qkd_qber': qber,
        'qkd_qber_max': max(lit) if lit else None,
        'abort_reasons': dict(reasons),
        'main_abort_reason': reasons.most_common(1)[0][0] if reasons else None,
    }


def detection(scenario_id, nominal, baseline):
    """State what the legitimate parties observe in this scenario, compared with the baseline."""
    if scenario_id == 'baseline':
        return dict(verdict='baseline', text='— (no attack)')
    parts, verdicts = [], []

    q, q0 = nominal['qkd_qber'], baseline['qkd_qber']
    if q is None and q0 is not None:
        parts.append('Optical link blocked → no QKD key (availability loss, not a secrecy breach)')
        verdicts.append('denial')
    elif q is not None and q0 is not None:
        qber_aborts = nominal['abort_reasons'].get('QBER ≥ 11 %', 0)
        if qber_aborts > baseline['abort_reasons'].get('QBER ≥ 11 %', 0):
            parts.append(f'QBER up to {nominal["qkd_qber_max"]:.1%} ≥ 11 % → detected, QKD aborted '
                         f'in {qber_aborts}/{nominal["passes"]} passes')
            verdicts.append('detected')
        if q - q0 > 0.005 and nominal['qkd_passes'] > 0:
            prefix = 'Other passes: ' if verdicts else ''
            parts.append(f'{prefix}QBER {q:.1%} (baseline {q0:.1%}) → noticed, key shrunk by privacy amplification')
            verdicts.append('noticed')

    lost_sessions = (baseline['ecdh_passes'] - nominal['ecdh_passes'],
                     baseline['mlkem_passes'] - nominal['mlkem_passes'])
    if max(lost_sessions) > 0:
        text = (f'RF SNR drop → {nominal["ecdh_passes"]}/{nominal["passes"]} ECDH and '
                f'{nominal["mlkem_passes"]}/{nominal["passes"]} ML-KEM sessions (availability loss)')
        if nominal['abort_reasons'].get('No RF for post-processing'):
            text += '; QKD post-processing blocked'
        parts.append(text)
        verdicts.append('denial')

    if not parts:
        return dict(verdict='none', text='No observable effect on the modelled channels')
    verdict = next(v for v in ('detected', 'noticed', 'denial') if v in verdicts)
    return dict(verdict=verdict, text=' · '.join(parts))


def _variant_configs(runner_config):
    optical = runner_config.optical
    for sky in SWEEP_FACTORS:
        for atmosphere in SWEEP_FACTORS:
            yield (sky, atmosphere), replace(runner_config, optical=replace(
                optical,
                sky_background_hz=optical.sky_background_hz * sky,
                zenith_atmospheric_loss_db=optical.zenith_atmospheric_loss_db * atmosphere,
            ))


def run_study(propagator, station, runner_config, start, end, dt_s):
    """Run every scenario under every sweep variant and return the results table."""
    geometry = CachedGeometry(propagator)
    variants = list(_variant_configs(runner_config))
    summaries = {}
    for scenario_id, scenario in SCENARIOS.items():
        summaries[scenario_id] = {
            key: summarize(ExperimentRunner(geometry, station, scenario, cfg).run(start, end, dt_s).to_dict())
            for key, cfg in variants
        }

    baseline = summaries['baseline'][(1.0, 1.0)]
    rows = []
    for scenario_id, scenario in SCENARIOS.items():
        by_variant = summaries[scenario_id]
        nominal = by_variant[(1.0, 1.0)]
        bits = [s['qkd_key_bits'] for s in by_variant.values()]
        qkd_passes = [s['qkd_passes'] for s in by_variant.values()]
        rows.append(dict(
            scenario_id=scenario_id,
            name=scenario.name,
            description=scenario.description,
            nominal=nominal,
            qkd_key_bits_min=min(bits),
            qkd_key_bits_max=max(bits),
            qkd_passes_min=min(qkd_passes),
            qkd_passes_max=max(qkd_passes),
            detection=detection(scenario_id, nominal, baseline),
        ))

    optical = runner_config.optical
    return dict(
        format='scenario_study.v1',
        methods=METHODS,
        rows=rows,
        sweep=dict(
            factors=list(SWEEP_FACTORS),
            sky_background_hz=[optical.sky_background_hz * f for f in SWEEP_FACTORS],
            zenith_atmospheric_loss_db=[optical.zenith_atmospheric_loss_db * f for f in SWEEP_FACTORS],
            variants=len(variants),
            note=('QKD key bits are given for the configured values and as the minimum–maximum over '
                  'sky background × {0.5, 1, 2} and zenith atmospheric loss × {0.5, 1, 2}. '
                  'Classical sessions do not depend on these optical inputs.'),
        ),
    )

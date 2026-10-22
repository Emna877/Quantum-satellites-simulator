"""Initial physical-run contract for future paired comparisons and playback.

Only successful, already-computed snapshots are serialized. Unknown channel or
security results remain unknown; no link or cryptographic result is inferred here.
"""
from dataclasses import asdict, fields, is_dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
from importlib.metadata import version
import json
import math
from pathlib import Path
import platform
import subprocess
import uuid

SCHEMA_VERSION = '1.0'
CHANNELS = ('rf_data', 'quantum_optical', 'qkd_classical_protocol')
STATE_UNITS = {
    'timestamp':'UTC', 'position':'m', 'velocity':'m/s', 'altitude':'m',
    'quaternion':'dimensionless', 'angular_velocity':'rad/s',
    'battery_percent':'percent', 'battery_capacity_wh':'Wh', 'solar_current':'A',
    'power_consumption':'W', 'charging_rate':'W', 'internal_temp':'degC',
    'external_temp':'degC', 'heat_dissipation_rate':'W', 'signal_strength':'dBm',
    'packet_loss':'percent', 'uplink_rate':'kbit/s', 'downlink_rate':'kbit/s',
    'radiation_dose':'mGy', 'radiation_rate_mgy_s':'mGy/s', 'health_percent':'percent',
    'navigation_error_m':'m', 'navigation_time_offset_ms':'ms', 'attitude_error_deg':'deg',
    'sensor_noise_rad_s':'rad/s', 'injected_command_count':'expected_count',
    'drag_coefficient':'dimensionless', 'in_eclipse':'boolean',
    'component_health':'status_map', 'error_counters':'count_map',
    'last_command_time':'UTC', 'last_command_type':'category',
}
# Targets describe implemented surrogate effects, not claimed attack capabilities.
EVENT_MODELS = {
    'solar_flare': (['spacecraft_environment','spacecraft_power','rf_data'],
        dict(radiation_rate_mgy_s='mGy/s',comm_degradation_db='dB',battery_drain_pct_s='percent/s')),
    'eclipse_entry': (['spacecraft_power'], {}),
    'eclipse_exit': (['spacecraft_power'], {}),
    'micrometeoroid_impact': (['spacecraft_attitude','spacecraft_thermal','spacecraft_health'],
        dict(impact_energy_j='J',health_decrease='percent')),
    'atmospheric_drag_spike': (['spacecraft_environment'],dict(drag_multiplier='dimensionless')),
    'geomagnetic_storm': (['spacecraft_environment','spacecraft_navigation','rf_data'],dict(kp_index='index',gps_error_m='m')),
    'gps_spoofing': (['spacecraft_navigation'],dict(position_error_m='m',time_drift_ms='ms')),
    'command_injection': (['spacecraft_attitude','spacecraft_power','spacecraft_health'],dict(command_rate_hz='1/s',actuator_error_deg='deg')),
    'jamming_attack': (['rf_data'],dict(signal_loss_db='dB',throughput_loss_fraction='fraction',packet_loss_pct='percent')),
    'laser_dazzle': (['spacecraft_attitude','spacecraft_thermal','spacecraft_health'],dict(laser_power_w='W',sensor_noise_rad_s='rad/s')),
    'power_drain': (['spacecraft_power','spacecraft_thermal','spacecraft_health'],dict(extra_power_w='W')),
    'thermal_sabotage': (['spacecraft_thermal','spacecraft_health'],dict(temp_excursion_c='degC',direction='sign')),
}


def timestamp(value):
    if isinstance(value,str):
        value = datetime.fromisoformat(value.replace('Z','+00:00'))
    if not isinstance(value,datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('Experiment timestamps must have an explicit timezone')
    return value.astimezone(timezone.utc).isoformat(timespec='microseconds').replace('+00:00','Z')


def json_value(value):
    if isinstance(value,datetime):
        return timestamp(value)
    if isinstance(value,Enum):
        return value.name
    if is_dataclass(value):
        return json_value(asdict(value))
    if isinstance(value,dict):
        return {str(k.name if isinstance(k,Enum) else k):json_value(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):
        return [json_value(v) for v in value]
    if hasattr(value,'tolist'):
        return json_value(value.tolist())
    if isinstance(value,float) and not math.isfinite(value):
        raise ValueError('Non-finite numbers cannot enter experiment records')
    if value is None or isinstance(value,(str,int,float,bool)):
        return value
    raise TypeError(f'Unsupported record value: {type(value).__name__}')


def provenance(config):
    """Fingerprint the installed data/JAR inputs, including uncommitted work state."""
    root = Path(config['project_dir'])
    asset_paths = sorted(root.glob('*.jar'))
    data_root = Path(config['orekit_data_path'])
    assets = {}
    sources = sorted(root.glob('*.py'))
    for folder in ('config','simulation','events','experiments','scripts'):
        sources.extend(sorted((root/folder).rglob('*.py')))
    for label,paths in (('jars',asset_paths),('source',sources),('orekit_data',sorted(p for p in data_root.rglob('*') if p.is_file() and '__pycache__' not in p.parts))):
        digest = hashlib.sha256()
        for path in paths:
            name = path.relative_to(data_root if label == 'orekit_data' else root).as_posix()
            digest.update(name.encode('utf-8')+b'\0'+hashlib.sha256(path.read_bytes()).digest())
        assets[label] = dict(sha256=digest.hexdigest(),file_count=len(paths))
    def git(*arguments):
        try:
            result = subprocess.run(['git',*arguments],cwd=root,capture_output=True,text=True,timeout=5)
            return result.stdout.strip() if result.returncode == 0 else None
        except (OSError,subprocess.TimeoutExpired):
            return None
    return dict(python=platform.python_version(),jpype=version('JPype1'),numpy=version('numpy'),
                selected_jvm=config.get('jvm_path'),git_revision=git('rev-parse','HEAD'),
                git_worktree_status=git('status','--porcelain'),assets=assets)


def event_definition(event):
    targets,units = EVENT_MODELS[event.event_type.value]
    if set(event.parameters)-set(units):
        raise ValueError('Event parameter units must be declared before export')
    return dict(event_id=event.event_id,timestamp=timestamp(event.timestamp),
                event_type=event.event_type.value,severity=event.severity.name,
                is_attack=event.is_attack,duration_seconds=event.duration_seconds,
                parameters=json_value(event.parameters),parameter_units={k:units[k] for k in event.parameters},
                targets=targets.copy(),model_id='event_surrogates.v1',
                model_status='uncalibrated',description=event.description)


def event_from_definition(record):
    """Load an explicitly scoped preset without evaluating arbitrary class names."""
    from events import attacks, environmental
    from events.base import EventSeverity
    registry = dict(solar_flare=environmental.SolarFlare,eclipse_entry=environmental.EclipseEntry,
        eclipse_exit=environmental.EclipseExit,micrometeoroid_impact=environmental.MicrometeoroidImpact,
        atmospheric_drag_spike=environmental.AtmosphericDragSpike,geomagnetic_storm=environmental.GeomagneticStorm,
        gps_spoofing=attacks.GPSSpoofing,command_injection=attacks.CommandInjection,
        jamming_attack=attacks.JammingAttack,laser_dazzle=attacks.LaserDazzle,
        power_drain=attacks.PowerDrain,thermal_sabotage=attacks.ThermalSabotage)
    event = registry[record['event_type']](event_id=record['event_id'],
        timestamp=datetime.fromisoformat(timestamp(record['timestamp']).replace('Z','+00:00')),
        severity=EventSeverity[record['severity']],parameters=record['parameters'])
    expected = event_definition(event)
    for name in ('targets','parameter_units','model_id','model_status','duration_seconds','is_attack'):
        if record[name] != expected[name]:
            raise ValueError(f'Event {name} disagrees with its declared preset')
    return event


def sample_record(state,run_id):
    names = {field.name for field in fields(state)}
    if names != set(STATE_UNITS):
        raise ValueError('State contract changed: update units and schema version deliberately')
    return dict(run_id=run_id,timestamp=timestamp(state.timestamp),
                state=json_value(asdict(state)),frames=dict(position='ITRF',velocity='ITRF'),
                channels={name:None for name in CHANNELS},
                security=dict(confidentiality='not_evaluated',integrity='not_evaluated',
                    authentication='not_evaluated',key_establishment=dict(status='not_implemented',
                    secret_key_bits=None,reason='Physical simulation only')))


def build_experiment(config,states,events=(),*,run_id=None,scenario_id='physical-baseline',source='engine',capture_provenance=True):
    states = list(states)
    if not states:
        raise ValueError('An experiment needs at least one recorded state')
    run_id = run_id or str(uuid.uuid4())
    document = dict(schema_version=SCHEMA_VERSION,metadata=dict(
        run_id=run_id,scenario_id=scenario_id,pair_id=None,source=source,
        start_time=timestamp(states[0].timestamp),end_time=timestamp(states[-1].timestamp),
        mode='physical_baseline',status='completed',orbital_model='orekit.keplerian.v1',
        config=json_value(config),state_units=STATE_UNITS.copy(),
        provenance=provenance(config) if capture_provenance else None,
        application_crypto=dict(algorithm='AES-256-GCM',key_bits=256,nonce_bits=96,tag_bits=128,status='planned'),
        qkd_classical_transport='not_configured',
        assumptions=['Two-body Orekit orbit; ITRF positions and velocities.',
                     'Event effects are uncalibrated surrogate presets.',
                     'Channels and cryptographic results are not implemented by this adapter.']),
        events=[event_definition(event) for event in events],
        samples=[sample_record(state,run_id) for state in states])
    validate_experiment(document)
    return document


def validate_experiment(document):
    if document.get('schema_version') != SCHEMA_VERSION:
        raise ValueError('Unsupported experiment schema version')
    metadata = document['metadata']
    if metadata['state_units'] != STATE_UNITS:
        raise ValueError('State units do not match this schema version')
    start,end = timestamp(metadata['start_time']),timestamp(metadata['end_time'])
    if not metadata['run_id'] or start > end:
        raise ValueError('Invalid experiment identity or time interval')
    samples = document['samples']
    if not samples:
        raise ValueError('Experiment samples must not be empty')
    previous = None
    for sample in samples:
        time = timestamp(sample['timestamp'])
        if sample['run_id'] != metadata['run_id'] or not start <= time <= end or (previous is not None and time <= previous):
            raise ValueError('Samples must belong to this run and have strictly increasing timestamps')
        if timestamp(sample['state']['timestamp']) != time:
            raise ValueError('State and sample timestamps disagree')
        if set(sample['state']) != set(STATE_UNITS):
            raise ValueError('State fields do not match this schema version')
        for name,length in (('position',3),('velocity',3),('quaternion',4),('angular_velocity',3)):
            vector = sample['state'][name]
            if not isinstance(vector,list) or len(vector) != length or any(type(v) not in (int,float) or not math.isfinite(v) for v in vector):
                raise ValueError(f'Invalid state vector: {name}')
        if sample['frames'] != dict(position='ITRF',velocity='ITRF'):
            raise ValueError('Orbital frames must be explicit ITRF')
        if set(sample['channels']) != set(CHANNELS):
            raise ValueError('RF, optical quantum, and QKD classical channels must be distinct')
        for channel in sample['channels'].values():
            if channel is not None and (not isinstance(channel,dict) or type(channel.get('available')) not in (bool,type(None)) or not isinstance(channel.get('metrics'),dict)):
                raise ValueError('Computed channels need available and metrics fields')
        key_result = sample['security']['key_establishment']
        if key_result['status'] not in ('not_implemented','not_attempted','succeeded','aborted','failed'):
            raise ValueError('Unknown key-establishment result')
        bits = key_result['secret_key_bits']
        if bits is not None and (type(bits) is not int or bits < 0):
            raise ValueError('Secret-key bits must be a nonnegative integer or unknown')
        if key_result['status'] in ('not_implemented','not_attempted') and bits is not None:
            raise ValueError('Uncomputed key results must remain unknown')
        if key_result['status'] == 'succeeded' and (bits is None or bits == 0):
            raise ValueError('Successful key establishment needs usable key bits')
        for dimension in ('confidentiality','integrity','authentication'):
            if sample['security'][dimension] not in ('not_evaluated','passed_model_checks','failed_model_checks'):
                raise ValueError('Security dimensions need explicit model-check results, not availability claims')
        if key_result['status'] in ('aborted','failed') and (bits != 0 or not key_result.get('reason')):
            raise ValueError('Abort/failure must retain a reason and zero usable key bits')
        previous = time
    if timestamp(samples[0]['timestamp']) != start or timestamp(samples[-1]['timestamp']) != end:
        raise ValueError('Metadata bounds must match the recorded sample bounds')
    seen = set()
    for event in document['events']:
        if event['event_id'] in seen or not start <= timestamp(event['timestamp']) <= end:
            raise ValueError('Event IDs must be unique and events must belong to the run interval')
        seen.add(event['event_id'])
        targets,units = EVENT_MODELS[event['event_type']]
        if event['targets'] != targets or event['parameter_units'] != {k:units[k] for k in event['parameters']}:
            raise ValueError('Event targets/units disagree with the declared surrogate model')
        if not math.isfinite(event['duration_seconds']) or event['duration_seconds'] < 0:
            raise ValueError('Invalid event duration')
        event_from_definition(event)
    json.dumps(document,allow_nan=False)


def write_experiment(directory,config,states,events=(),**options):
    document = build_experiment(config,states,events,**options)
    path = Path(directory)/'experiment.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(document,indent=2,allow_nan=False),encoding='utf-8')
    return path

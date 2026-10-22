"""Contract tests: python -m unittest scripts.test_experiment_schema."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from experiments.schema import (build_experiment, event_definition, event_from_definition,
                                sample_record, timestamp, validate_experiment, write_experiment)
from simulation.state import SatelliteState
from events.attacks import JammingAttack, GPSSpoofing, LaserDazzle
from scripts.test_engine_events import CLASSES

START = datetime(2025,11,9,12,0,0,123456,tzinfo=timezone.utc)


def document():
    states = [SatelliteState(timestamp=START),SatelliteState(timestamp=START+timedelta(seconds=10))]
    return build_experiment({},states,[JammingAttack(timestamp=START)],run_id='run-1',capture_provenance=False)


class ExperimentSchemaTests(unittest.TestCase):
    def test_timestamp_requires_zone_and_normalizes_offset(self):
        self.assertEqual(timestamp(START.astimezone(timezone(timedelta(hours=1)))),'2025-11-09T12:00:00.123456Z')
        with self.assertRaises(ValueError):
            timestamp(START.replace(tzinfo=None))

    def test_full_state_is_independent_and_uncomputed_stays_unknown(self):
        state = SatelliteState(timestamp=START)
        state.component_health['battery'] = 'DEGRADED'
        state.error_counters['power_anomalies'] = 3
        state.last_command_time = START
        sample = sample_record(state,'run-1')
        state.component_health['battery'] = 'OPERATIONAL'
        self.assertEqual(sample['state']['component_health']['battery'],'DEGRADED')
        self.assertEqual(sample['state']['error_counters']['power_anomalies'],3)
        self.assertTrue(sample['state']['last_command_time'].endswith('Z'))
        self.assertTrue(all(value is None for value in sample['channels'].values()))
        self.assertIsNone(sample['security']['key_establishment']['secret_key_bits'])

    def test_zero_key_abort_is_retained_separately_from_availability(self):
        value = document()
        sample = value['samples'][0]
        sample['channels']['quantum_optical'] = dict(available=True,metrics=dict(secret_key_rate_bit_s=0,qber=0.5))
        sample['security']['key_establishment'] = dict(status='aborted',secret_key_bits=0,reason='Insufficient accepted data')
        validate_experiment(value)
        self.assertEqual(sample['channels']['quantum_optical']['metrics']['secret_key_rate_bit_s'],0)
        self.assertEqual(sample['security']['confidentiality'],'not_evaluated')

    def test_no_fabricated_success_or_abort_without_reason(self):
        for status,bits,reason in [('succeeded',0,None),('not_implemented',256,None),('aborted',0,None)]:
            value = document()
            value['samples'][0]['security']['key_establishment'] = dict(status=status,secret_key_bits=bits,reason=reason)
            with self.subTest(status=status),self.assertRaises(ValueError):
                validate_experiment(value)

    def test_run_and_state_time_must_match(self):
        for change in ('time','identity','order'):
            value = document()
            if change == 'time':
                value['samples'][0]['state']['timestamp'] = timestamp(START+timedelta(seconds=1))
            elif change == 'identity':
                value['samples'][0]['run_id'] = 'other-run'
            else:
                value['samples'].reverse()
            with self.subTest(change=change),self.assertRaises(ValueError):
                validate_experiment(value)

    def test_event_definitions_round_trip_all_presets(self):
        for cls in CLASSES:
            with self.subTest(event=cls.__name__):
                event = cls(timestamp=START,event_id=cls.__name__)
                record = event_definition(event)
                self.assertEqual(event_definition(event_from_definition(record)),record)

    def test_scopes_describe_current_effects_without_claiming_optical_attack(self):
        self.assertEqual(event_definition(JammingAttack(timestamp=START))['targets'],['rf_data'])
        self.assertEqual(event_definition(GPSSpoofing(timestamp=START))['targets'],['spacecraft_navigation'])
        self.assertNotIn('quantum_optical',event_definition(LaserDazzle(timestamp=START))['targets'])
        value = event_definition(JammingAttack(timestamp=START))
        value['targets'].append('quantum_optical')
        with self.assertRaises(ValueError):
            event_from_definition(value)

    def test_duplicate_events_and_unknown_versions_rejected(self):
        value = document()
        value['events'].append(deepcopy(value['events'][0]))
        with self.assertRaises(ValueError):
            validate_experiment(value)
        value = document()
        value['schema_version'] = '999'
        with self.assertRaises(ValueError):
            validate_experiment(value)

    def test_finite_numbers_and_explicit_frames(self):
        state = SatelliteState(timestamp=START)
        state.position[0] = float('nan')
        with self.assertRaises(ValueError):
            sample_record(state,'run-1')
        value = document()
        value['samples'][0]['frames']['position'] = 'unknown'
        with self.assertRaises(ValueError):
            validate_experiment(value)

    def test_json_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_experiment(directory,{},[SatelliteState(timestamp=START)],
                                    run_id='run-1',capture_provenance=False)
            value = json.loads(path.read_text(encoding='utf-8'))
            validate_experiment(value)
            self.assertEqual(value['metadata']['application_crypto']['status'],'planned')

    def test_real_export_records_match_czml_and_effective_duration(self):
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            env = dict(os.environ,CZML_DEFAULT_DURATION_SECONDS='65',CZML_STEP_SECONDS='30',
                       ORBIT_CSV_FILE=str(base/'orbit.csv'),ORBIT_CZML_FILE=str(base/'orbit.czml'),
                       CZML_OUTPUT_FILE=str(base/'events.czml'))
            env.pop('CZML_DURATION_HOURS',None)
            env.pop('ORBIT_PERIOD_MINUTES',None)
            for script,czml_file,run_folder in [('export_czml.py','orbit.czml','orbit'),('export_czml_with_events.py','events.czml','events')]:
                result = subprocess.run([sys.executable,script,'--experiment-dir',str(base/run_folder)],
                                        cwd=root,env=env,text=True,capture_output=True,timeout=60)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                value = json.loads((base/run_folder/'experiment.json').read_text(encoding='utf-8'))
                validate_experiment(value)
                czml = json.loads((base/czml_file).read_text(encoding='utf-8'))
                samples = czml[1]['position']['cartesian']
                self.assertEqual([sample['state']['position'] for sample in value['samples']],
                                 [samples[i+1:i+4] for i in range(0,len(samples),4)])
                self.assertEqual(value['metadata']['config']['duration_seconds'],65)
                self.assertGreater(value['metadata']['provenance']['assets']['orekit_data']['file_count'],0)
                self.assertTrue(Path(value['metadata']['provenance']['selected_jvm']).is_file())


if __name__ == '__main__':
    unittest.main()

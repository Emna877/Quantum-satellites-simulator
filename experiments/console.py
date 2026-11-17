"""Local-console adapter. All science is delegated to existing Python models."""
from dataclasses import asdict, replace
from datetime import timedelta
import json
import math
from pathlib import Path

from config import get_simulation_config, simulation_start
from experiments.scenarios import SCENARIOS

FORMAT = 'console_run.v1'


def defaults():
    config = get_simulation_config()
    return dict(start_time=config['start_time'],hours=24.0,dt_s=60.0,
                altitude_km=(config['orbit']['semi_major_axis']-6378137)/1000,
                inclination_deg=config['orbit']['inclination_deg'],scenario='rf_jamming_moderate',
                station_lat=36.8,station_lon=10.18,min_elevation_deg=5.0,
                rf_power_dbm=30.0,rx_aperture_m=1.0,background_hz=1000.0,
                divergence_urad=10.0,source_rate_hz=1e8)


def validate_request(request):
    values = defaults()
    if not isinstance(request,dict) or set(request)-set(values):
        raise ValueError('Unknown experiment settings')
    values.update(request)
    bounds = dict(hours=(0.1,24),dt_s=(10,300),altitude_km=(200,2000),inclination_deg=(0,180),
                  station_lat=(-89,89),station_lon=(-180,180),min_elevation_deg=(0,80),
                  rf_power_dbm=(-20,60),rx_aperture_m=(0.1,3),background_hz=(0,1e7),
                  divergence_urad=(1,200),source_rate_hz=(1e5,1e10))
    for key,(low,high) in bounds.items():
        value = values[key]
        if type(value) not in (int,float) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f'{key} must be between {low} and {high}')
    if values['scenario'] not in SCENARIOS:
        raise ValueError('Unknown scenario')
    date = simulation_start(values['start_time'])
    if not 1991 <= date.year <= 2148:
        raise ValueError('Start time is outside the bundled solar ephemerides interval')
    values['start_time'] = date.isoformat().replace('+00:00','Z')
    return values


def catalog():
    return [dict(id=key,name=value.name,description=value.description,
                 rf_loss_db=value.rf_signal_loss_db,background_scale=value.optical_background_scale,
                 cloud_blocked=value.optical_cloud_blocked,optical_extra_loss_db=value.optical_extra_loss_db,
                 intercept_resend_fraction=value.qkd_intercept_resend_fraction)
            for key,value in SCENARIOS.items()]


def strict_numbers(value,missing=None,path=''):
    """JSON cannot encode infinity; retain its location and the model's block reason."""
    if isinstance(value,float) and not math.isfinite(value):
        if missing is not None:
            missing.append(path)
        return None
    if isinstance(value,dict):
        return {key:strict_numbers(item,missing,f'{path}.{key}') for key,item in value.items()}
    if isinstance(value,(list,tuple)):
        return [strict_numbers(item,missing,f'{path}[{i}]') for i,item in enumerate(value)]
    return value


def build_console_run(request,run_id):
    from simulation.propagator import OrekitPropagator, iso
    from experiments.runner import ExperimentRunner, RunnerConfig
    from communication.rf_link import RFLinkConfig
    from communication.optical_link import OpticalLinkConfig
    options = validate_request(request)
    config = get_simulation_config()
    config['start_time'] = options['start_time']
    config['orbit']['semi_major_axis'] = 6378137+options['altitude_km']*1000
    config['orbit']['inclination_deg'] = options['inclination_deg']
    station = dict(name='Tunis_GS' if options['station_lat']==36.8 and options['station_lon']==10.18 else 'Selected_GS',
                   lat_deg=options['station_lat'],lon_deg=options['station_lon'],alt_m=20.0)
    runner_config = RunnerConfig(
        rf=RFLinkConfig(tx_power_dbm=options['rf_power_dbm']),
        optical=OpticalLinkConfig(rx_aperture_m=options['rx_aperture_m'],sky_background_hz=options['background_hz'],
                                 beam_divergence_half_angle_rad=options['divergence_urad']*1e-6,
                                 source_rate_hz=options['source_rate_hz']),
        min_elevation_deg=options['min_elevation_deg'])
    propagator = OrekitPropagator.from_config(config)
    try:
        start=propagator.start_time
        end=start+timedelta(hours=options['hours'])
        baseline = ExperimentRunner(propagator,station,SCENARIOS['baseline'],runner_config).run(start,end,options['dt_s'])
        scenario = SCENARIOS[options['scenario']]
        selected = baseline if options['scenario']=='baseline' else ExperimentRunner(propagator,station,scenario,runner_config).run(start,end,options['dt_s'])
        # Include root-found boundaries and model sample instants, not just the
        # nominal grid. Selecting a contact must not show an older orbital state.
        instants={state.timestamp for state in propagator.sample_states(options['hours']*3600,options['dt_s'])}
        for window in selected.passes:
            instants.update((simulation_start(window['window_start']),simulation_start(window['window_end'])))
            instants.update(simulation_start(sample['timestamp']) for sample in window['samples'])
            for marker in scenario.build_events(simulation_start(window['window_start']),simulation_start(window['window_end'])):
                for instant in (marker.timestamp,marker.timestamp+timedelta(seconds=marker.duration_seconds)):
                    if start<=instant<=end:
                        instants.add(instant)
        telemetry=[]
        frame=propagator.station_frame(station)
        for instant in sorted(instants):
            state=propagator.state_at(instant)
            geo=propagator.geodetic(state.position,state.timestamp)
            telemetry.append(dict(timestamp=iso(state.timestamp),position_m=state.position.tolist(),
                velocity_m_s=state.velocity.tolist(),altitude_m=state.altitude,in_eclipse=state.in_eclipse,
                latitude_deg=math.degrees(float(geo.getLatitude())),longitude_deg=math.degrees(float(geo.getLongitude())),
                **propagator.station_geometry(state.timestamp,frame)))
        events=[]
        def event(identity,label,time,end_time,kind,targets,description,severity='INFO',**extra):
            events.append(dict(id=identity,label=label,start=time,end=end_time,kind=kind,targets=targets,
                               description=description,severity=severity,**extra))
        for i,window in enumerate(selected.passes):
            event(f'contact-{i}','Ground-station contact',window['window_start'],window['window_end'],'contact',['geometry'],
                  'Orekit elevation crossing at the configured minimum elevation.')
            # Pass outcomes are shown at pass end, never represented as a detection time.
            finite=window['qkd_finite_pass']
            if finite.get('key_status')=='aborted':
                event(f'abort-{i}','QKD estimate: aborted',window['window_end'],window['window_end'],'protocol',['quantum_optical'],
                      finite.get('abort_reason') or 'No usable estimated key.',severity='WARNING',pass_index=i)
            if not window['classical_session_summary'].get('key_established'):
                event(f'classical-{i}','Classical session estimate: failed',window['window_end'],window['window_end'],
                      'protocol',['rf_data'],window['classical_session_summary'].get('failure_reason') or 'Session not established.',severity='WARNING',pass_index=i)
            if finite.get('classical_dependency',{}).get('satisfied') is False:
                event(f'dependency-{i}','QKD post-processing blocked',window['window_end'],window['window_end'],'protocol',['rf_data','quantum_optical'],
                      'QKD sifting, error correction and privacy amplification need the authenticated RF channel, which was unavailable for this pass.',severity='WARNING',pass_index=i)
            for j,prototype in enumerate(scenario.build_events(simulation_start(window['window_start']),simulation_start(window['window_end']))):
                event(f'prototype-{i}-{j}',prototype.event_type.value.replace('_',' ').title()+' · marker only',iso(prototype.timestamp),
                      iso(prototype.timestamp+timedelta(seconds=prototype.duration_seconds)),'prototype',['spacecraft'],
                      'Scheduled surrogate marker. The existing runner does not route this event through the state engine; channel overrides apply run-wide. No navigation-offset vector or detection time was computed.',severity=prototype.severity.name)
        if scenario.rf_signal_loss_db:
            event('rf-condition','RF loss override',iso(start),iso(end),'disturbance',['rf_data'],
                  f'Existing runner applies {scenario.rf_signal_loss_db:g} dB extra RF loss throughout the experiment. Not a spatial jammer or cryptographic break.',severity='HIGH')
        if scenario.qkd_intercept_resend_fraction:
            event('qkd-intercept','QKD intercept-resend',iso(start),iso(end),'disturbance',['quantum_optical'],
                  f'Eavesdropper intercepts {scenario.qkd_intercept_resend_fraction:.0%} of signal photons, measures in a random basis and resends. Each intercepted sifted bit is wrong with probability 1/4.',severity='CRITICAL')
        if scenario.optical_background_scale>1 or scenario.optical_cloud_blocked or scenario.optical_extra_loss_db:
            event('optical-condition','Optical disturbance',iso(start),iso(end),'disturbance',['quantum_optical'],
                  'Run-wide optical configuration override: background, blockage or additional loss. RF metrics are computed separately.',severity='HIGH')
        for previous,current in zip(telemetry,telemetry[1:]):
            if previous['in_eclipse']!=current['in_eclipse']:
                event('eclipse-'+current['timestamp'],'Eclipse entry' if current['in_eclipse'] else 'Eclipse exit',
                      current['timestamp'],current['timestamp'],'environment',['geometry'],
                      'Full-umbra transition sampled from Orekit. Boundary timing is limited by sampling interval.')
        limitations=list(selected.model_limitations)+[
            'Playback is a simulation recording, not a live satellite feed.',
            'Scenario channel overrides apply to the entire run; prototype event-marker times do not gate those overrides.',
            'Classical ECDH and ML-KEM sessions are engineering estimates; no messages are actually encrypted or authenticated.',
            'The QKD dependency on the authenticated RF channel is enforced as a time and traffic check; the post-processing messages themselves are not executed.',
            'Finite-key estimates use the Tomamichel et al. (2012) bound with infinite-statistics decoy yields, not a composable finite-size decoy proof.',
            'Key buffer is available only as end-of-pass snapshots and uses asymptotic replenishment gated by RF availability; it is not a validated usable-key timeline.',
            'The runner does not export a corrupted navigation-position vector; no spoofed orbit is drawn.',
            'Optical link model is checked against the Micius (Liao et al. 2017) link budget in scripts/test_validation_micius.py; other ground stations and daytime operation are not validated.']
        bundle=dict(format=FORMAT,run_id=run_id,request=options,station=station,
            start_time=iso(start),end_time=iso(end),period_seconds=propagator.period_seconds,
            frames=dict(position='ITRF',velocity='ITRF'),telemetry=telemetry,events=events,
            baseline=baseline.to_dict(),scenario=selected.to_dict(),runner_config=asdict(runner_config),
            limitations=limitations,model_status='engineering_estimates',non_finite_metrics=[])
        from experiments.schema import provenance
        bundle['provenance']=provenance(dict(config,jvm_path=propagator.jvm_path))
        bundle['physical_config']=config
        missing=[]
        bundle=strict_numbers(bundle,missing)
        bundle['non_finite_metrics']=missing
        return bundle
    finally:
        propagator.shutdown()


def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--request',required=True)
    parser.add_argument('--out',required=True)
    parser.add_argument('--id',required=True)
    args=parser.parse_args()
    result=build_console_run(json.loads(Path(args.request).read_text(encoding='utf-8')),args.id)
    Path(args.out).write_text(json.dumps(result,allow_nan=False),encoding='utf-8')


if __name__=='__main__':
    main()

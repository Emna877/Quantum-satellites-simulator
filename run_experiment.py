"""Paired experiment runner entry point.

Executes a baseline run and a named attack scenario over the same Orekit
orbital geometry, writes a JSON result file, generates diagnostic plots, and
optionally exports CZML event markers for the Cesium viewer.

Usage
-----
    python run_experiment.py                            # baseline only
    python run_experiment.py --scenario rf_jamming_moderate
    python run_experiment.py --scenario rf_jamming_moderate --dt 30
    python run_experiment.py --list-scenarios
    python run_experiment.py --scenario optical_interference --no-plots
    python run_experiment.py --scenario baseline --czml

Available scenarios (see experiments/scenarios.py)
---------------------------------------------------
    baseline, rf_jamming_low, rf_jamming_moderate, rf_jamming_severe,
    gnss_spoofing, optical_interference, optical_cloud_blocked,
    combined_rf_and_optical, classical_auth_dependency,
    pointing_error, power_shortage

Output files (all under data/experiments/<scenario>/)
------------------------------------------------------
    result.json          — full ExperimentResult record
    plots/               — diagnostic PNGs (range, elevation, SNR, QBER, key rate)
    events.czml          — CZML event-marker packets (--czml only)
"""
import argparse
import json
import sys
from datetime import timedelta
from pathlib import Path

from config import get_simulation_config, validate_runtime_config
from simulation.propagator import OrekitPropagator
from experiments.scenarios import SCENARIOS
from experiments.runner import ExperimentRunner, RunnerConfig


def list_scenarios():
    print("Available scenarios:")
    for name, scenario in SCENARIOS.items():
        print(f"  {name:<35}  {scenario.description[:70]}...")
    sys.exit(0)


def main():
    ap = argparse.ArgumentParser(
        description="Run a paired classical vs quantum-assisted experiment.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument(
        '--scenario', default='baseline',
        help='Scenario name (default: baseline)',
    )
    ap.add_argument(
        '--list-scenarios', action='store_true',
        help='Print all available scenarios and exit',
    )
    ap.add_argument(
        '--dt', type=float, default=30.0,
        help='Sampling interval in seconds (default: 30)',
    )
    ap.add_argument(
        '--hours', type=float, default=None,
        help='Run duration in hours (default: from SIM config)',
    )
    ap.add_argument(
        '--out', default=None,
        help='Output directory (default: data/experiments/<scenario>/)',
    )
    ap.add_argument(
        '--no-plots', action='store_true',
        help='Skip generating diagnostic plots',
    )
    ap.add_argument(
        '--czml', action='store_true',
        help='Export CZML event markers alongside the result',
    )
    ap.add_argument(
        '--mu', type=float, default=0.0,
        help='WCP mean photon number μ for finite-key model (0 = ideal SPS, default: 0)',
    )
    args = ap.parse_args()

    if args.list_scenarios:
        list_scenarios()

    if args.scenario not in SCENARIOS:
        print(f"Unknown scenario '{args.scenario}'.  Run with --list-scenarios to see options.",
              file=sys.stderr)
        sys.exit(1)

    scenario = SCENARIOS[args.scenario]

    # Determine output directory
    out_dir = Path(args.out) if args.out else Path('data') / 'experiments' / args.scenario
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load configuration and initialise propagator
    config = validate_runtime_config(get_simulation_config())
    print(f"Initialising Orekit propagator…")
    propagator = OrekitPropagator.from_config(config)
    print(f"  orbital period: {propagator.period_seconds / 60:.2f} min")

    start = propagator.start_time
    duration_s = args.hours * 3600 if args.hours else config['duration_seconds']
    end = start + timedelta(seconds=duration_s)
    print(f"  run: {start.isoformat()} → {end.isoformat()}  ({duration_s/3600:.2f} h)")

    station = {"name": "Tunis_GS", "lat_deg": 36.8, "lon_deg": 10.18, "alt_m": 20.0}

    # Build runner config (apply WCP correction if μ > 0)
    from security.qkd_finite_key import BB84FiniteKeyConfig
    runner_cfg = RunnerConfig(
        qkd_finite=BB84FiniteKeyConfig(wcp_mean_photon_number=args.mu),
    )

    print(f"\nRunning scenario: {scenario.name}")
    print(f"  RF extra loss:   {scenario.rf_signal_loss_db:.1f} dB")
    print(f"  Optical bg:      ×{scenario.optical_background_scale:.1f}")
    print(f"  Cloud blocked:   {scenario.optical_cloud_blocked}")
    print(f"  Opt extra loss:  {scenario.optical_extra_loss_db:.1f} dB")
    if args.mu > 0:
        import math
        P1 = args.mu * math.exp(-args.mu)
        print(f"  WCP μ={args.mu:.3f}  P1={P1:.4f}  (decoy-state lower bound)")

    runner = ExperimentRunner(propagator, station, scenario, runner_cfg)
    result = runner.run(start, end, dt_s=args.dt)

    # Save result JSON
    result_path = out_dir / 'result.json'
    result.save(result_path)
    print(f"\nResult saved: {result_path}")
    _print_summary(result)

    # Generate plots
    if not args.no_plots:
        _generate_plots(result, out_dir)

    # Export CZML event markers
    if args.czml:
        _export_czml(result, out_dir, propagator)

    propagator.shutdown()
    print("\nDone.")


def _print_summary(result):
    print(f"\n{'='*55}")
    print(f"  Scenario:     {result.scenario_name}")
    print(f"  Passes found: {result.total_passes}")
    print(f"  Contact:      {result.contact_fraction * 100:.1f}% of run")

    for i, p in enumerate(result.passes):
        dur = p['duration_s']
        fk = p['qkd_finite_pass']
        cls = p['classical_session_summary']
        ks = p['key_store_snapshot']

        # Count per-sample RF availability
        rf_avail = sum(1 for s in p['samples'] if s['rf'].get('available', False))
        total_s = len(p['samples'])

        print(f"\n  Pass {i+1}:  {p['window_start'][:19]}Z  dur={dur:.0f}s")
        print(f"    RF:      {'✓' if cls['key_established'] else '✗'} classical session"
              f"  ({rf_avail}/{total_s} samples available)")
        print(f"    QKD:     finite-key status={fk['key_status']}"
              f"  secure_bits={fk['secure_key_bits']:.0f}")
        print(f"    Key buf: {ks['current_bits']:.0f} bits  exhaustions={ks['exhaustion_count']}")
        if fk['key_status'] == 'aborted':
            print(f"    Abort:   {fk['abort_reason']}")
    print(f"{'='*55}")


def _generate_plots(result, out_dir):
    """Flatten all pass samples into a CSV and run plot_pass on it."""
    import csv as csv_mod

    # Flatten samples from all passes
    rows = []
    for p in result.passes:
        for s in p['samples']:
            rows.append({
                't_s': s['t_s'],
                'elev_deg': s['elev_deg'],
                'range_m': s['range_m'],
                'rf_snr_db': s['rf'].get('snr_db', 0.0),
                'opt_signal_count_hz': s['optical'].get('signal_count_hz', 0.0),
                'opt_qber': s['optical'].get('qber', 0.5),
                'qkd_key_rate_bit_s': s['qkd_asymptotic'].get('secret_key_rate_bit_s', 0.0),
            })

    if not rows:
        print("  No samples — skipping plots.")
        return

    csv_path = out_dir / 'samples.csv'
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv_mod.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    plot_dir = out_dir / 'plots'
    try:
        from scripts.plot_pass import plot_all
        plot_all(csv_path, plot_dir)
        print(f"  Plots written to {plot_dir}/")
    except ImportError as e:
        print(f"  Plots skipped: {e}")


def _export_czml(result, out_dir, propagator):
    """Export CZML event-marker packets from the experiment result."""
    try:
        from exports.czml_events import experiment_result_to_czml_events
        czml_packets = experiment_result_to_czml_events(result, propagator)
        czml_path = out_dir / 'events.czml'
        czml_path.write_text(json.dumps(czml_packets, indent=2, default=str))
        print(f"  CZML markers: {czml_path}  ({len(czml_packets)} packets)")
    except Exception as exc:
        print(f"  CZML export failed: {exc}")


if __name__ == '__main__':
    main()

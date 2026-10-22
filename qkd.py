"""Classical RF and quantum-optical link analysis over one Tunis pass.

Runnable example: python qkd.py

Uses the shared OrekitPropagator for all orbital geometry and then calls the
distinct communication channel models from the communication/ package.
Writes per-sample metrics to COMM_CSV_FILE (default comm_samples.csv).

This is a physical-baseline example, not a security comparison.
All three channel slots are computed; security is not evaluated.
See communication/ modules for model assumptions and limitations.
"""
from pathlib import Path
import csv
from datetime import timedelta

# Configuration
from config import get_simulation_config, validate_runtime_config

RUNTIME_CONFIG = validate_runtime_config(get_simulation_config())
PROJECT_DIR = Path(RUNTIME_CONFIG['project_dir'])
PROP_SECONDS = RUNTIME_CONFIG['duration_seconds']
STEP_SECONDS = RUNTIME_CONFIG['sample_step_seconds']
MIN_ELEV_DEG = 5.0
SAT_NAME = "CubeSat-1"

# Communication channel models
from communication.rf_link import RFLinkConfig, rf_link_budget
from communication.optical_link import OpticalLinkConfig, optical_link_metrics
from communication.qkd_model import QKDModelConfig, qkd_key_metrics

RF_CFG = RFLinkConfig()
OPTICAL_CFG = OpticalLinkConfig()
QKD_CFG = QKDModelConfig()

# Ground stations
GROUND_STATIONS = [
    {"name": "Tunis_GS", "lat_deg": 36.8, "lon_deg": 10.18, "alt_m": 20.0},
]

# Shared Orekit propagator — never change the orbit to force a pass
from simulation.propagator import OrekitPropagator, sample_offsets

runtime = OrekitPropagator.from_config(RUNTIME_CONFIG)
print(f"Orekit orbital period: {runtime.period_seconds / 60:.3f} minutes")

# Pre-build station frames
station_frames = {
    gs['name']: runtime.station_frame(gs)
    for gs in GROUND_STATIONS
}

# Compute contact windows (root-found boundaries)
visibility_windows = {}
run_start = runtime.start_time
run_end = run_start + timedelta(seconds=PROP_SECONDS)
for gs in GROUND_STATIONS:
    name = gs['name']
    windows = runtime.contact_windows(run_start, run_end, gs, MIN_ELEV_DEG)
    visibility_windows[name] = windows
    print(f"Station {name}: {len(windows)} window(s) above {MIN_ELEV_DEG}°")
    for w in windows:
        dur = (w['end'] - w['start']).total_seconds()
        start_t = (w['start'] - run_start).total_seconds()
        end_t = (w['end'] - run_start).total_seconds()
        print(f"  start t={start_t:.0f}s  end t={end_t:.0f}s  duration={dur:.0f}s")

# Per-sample geometry + channel metrics during contact
rows = []
for gs in GROUND_STATIONS:
    name = gs['name']
    frame = station_frames[name]
    for offset in sample_offsets(PROP_SECONDS, STEP_SECONDS):
        timestamp = run_start + timedelta(seconds=offset)
        geom = runtime.station_geometry(timestamp, frame)
        elev = geom['elev_deg']
        if elev < MIN_ELEV_DEG:
            continue
        rng = geom['range_m']

        # RF channel
        rf = rf_link_budget(rng, RF_CFG)

        # Optical / quantum channel
        opt = optical_link_metrics(rng, elev, OPTICAL_CFG)

        # QKD key-rate from optical sifted count and QBER
        qkd = qkd_key_metrics(opt['sifted_count_hz'], opt['qber'], QKD_CFG)

        rows.append({
            "station": name,
            "t_s": offset,
            "elev_deg": elev,
            "azimuth_deg": geom['azimuth_deg'],
            "range_m": rng,
            # RF metrics
            "rf_Pr_dbm": rf['Pr_dbm'],
            "rf_snr_db": rf['snr_db'],
            "rf_shannon_capacity_mbps": rf['shannon_capacity_bps'] / 1e6,
            "rf_available": rf['available'],
            # Optical metrics
            "opt_total_loss_db": opt['total_loss_db'],
            "opt_geometric_loss_db": opt['geometric_loss_db'],
            "opt_atmospheric_loss_db": opt['atmospheric_loss_db'],
            "opt_channel_transmittance": opt['channel_transmittance'],
            "opt_signal_count_hz": opt['signal_count_hz'],
            "opt_qber": opt['qber'],
            "opt_sifted_count_hz": opt['sifted_count_hz'],
            "opt_link_usable": opt['link_usable'],
            # QKD key-rate metrics
            "qkd_key_rate_bit_s": qkd['secret_key_rate_bit_s'],
            "qkd_status": qkd['key_establishment']['key_status'],
            "qkd_secure_fraction": qkd['secure_fraction'],
            "qkd_finite_key_valid": qkd['finite_key_valid'],
        })

# Summary per station
for gs in GROUND_STATIONS:
    name = gs['name']
    station_rows = [r for r in rows if r['station'] == name]
    if not station_rows:
        print(f"{name}: No samples above elevation threshold")
        continue
    best_rf = max(station_rows, key=lambda r: r['rf_snr_db'])
    best_qkd = max(station_rows, key=lambda r: r['qkd_key_rate_bit_s'])
    print(f"\n{name} best RF sample:  t={best_rf['t_s']:.0f}s  elev={best_rf['elev_deg']:.1f}°"
          f"  range={best_rf['range_m']/1000:.2f} km  SNR={best_rf['rf_snr_db']:.2f} dB"
          f"  capacity={best_rf['rf_shannon_capacity_mbps']:.3f} Mbps")
    print(f"{name} best QKD sample: t={best_qkd['t_s']:.0f}s  elev={best_qkd['elev_deg']:.1f}°"
          f"  QBER={best_qkd['opt_qber']:.4f}"
          f"  key_rate={best_qkd['qkd_key_rate_bit_s']:.3f} bit/s"
          f"  finite_key_valid={best_qkd['qkd_finite_key_valid']}")

# Write CSV
csv_path = Path(RUNTIME_CONFIG['comm_csv_file'])
csv_path.parent.mkdir(parents=True, exist_ok=True)
if rows:
    fieldnames = list(rows[0].keys())
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nComm samples CSV written: {csv_path}  ({len(rows)} rows)")
else:
    print(f"\nNo contact samples; CSV not written.")

runtime.shutdown()

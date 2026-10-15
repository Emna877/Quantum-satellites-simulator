from pathlib import Path
import jpype
import math
import datetime
import csv
import os
import statistics
from math import log10

# ---------------- CONFIG ----------------
from config import get_simulation_config, validate_runtime_config, simulation_start

RUNTIME_CONFIG = validate_runtime_config(get_simulation_config())
JVM_PATH = RUNTIME_CONFIG['jvm_path']
PROJECT_DIR = Path(RUNTIME_CONFIG['project_dir'])
DATA_DIR = Path(RUNTIME_CONFIG['orekit_data_path'])
PROP_SECONDS = RUNTIME_CONFIG['duration_seconds']
STEP_SECONDS = RUNTIME_CONFIG['sample_step_seconds']
MIN_ELEV_DEG = 5.0             # visibility threshold (deg)
SAT_NAME = "CubeSat-1"

# Classical comm params (example)
TX_POWER_dBm = 20.0            # transmit power in dBm (100 mW)
TX_ANTENNA_GAIN_dBi = 10.0     # transmit antenna gain
RX_ANTENNA_GAIN_dBi = 20.0     # receive antenna gain
FREQ_HZ = 10e9                 # 10 GHz (X/Ku band) as example
BANDWIDTH_HZ = 10e6            # 10 MHz bandwidth
SYSTEM_NOISE_FIGURE_dB = 3.0   # noise figure in dB
TX_POINTING_LOSS_dB = 2.0      # pointing loss dB
RX_POINTING_LOSS_dB = 2.0

# QKD params (simple model)
SOURCE_RATE_HZ = 1e9           # emitted photons per second (example strong source)
DETECTOR_EFFICIENCY = 0.2      # fraction (20%)
DETECTOR_DARK_COUNTS_HZ = 100  # dark counts per second
ATMOSPHERIC_LOSS_dB = 2.0      # atmospheric loss (clear sky)
POINTING_LOSS_dB_QKD = 3.0     # pointing loss for optical QKD
MISALIGNMENT_ERROR = 0.01      # 1% misalignment error -> contributes to QBER
OPTICAL_WAVELENGTH_M = 1550e-9  # typical telecom wavelength (m). Use ~800e-9..1550e-9 as needed.

# ---------------- Ground stations (B1) ----------------
# Define one or more ground stations. Each entry is a dict with lat/lon/alt and optional antenna params.
GROUND_STATIONS = [
    {
        "name": "Tunis_GS",
        "lat_deg": 36.8,
        "lon_deg": 10.18,
        "alt_m": 20.0,
        # Classical comm params per-station (override defaults if desired)
        "tx_power_dBm": TX_POWER_dBm,
        "tx_antenna_gain_dBi": TX_ANTENNA_GAIN_dBi,
        "rx_antenna_gain_dBi": RX_ANTENNA_GAIN_dBi,
        "bandwidth_hz": BANDWIDTH_HZ,
    }
]

# runtime/config flags
VERBOSE = False            # set True to enable debug prints

# helper functions
def db2lin(db):
    return 10.0 ** (db / 10.0)

def lin2db(x):
    return 10.0 * math.log10(x)

def free_space_path_loss_dB(range_m, freq_hz):
    # FSPL (dB) = 20 log10(4π R / λ)
    c = 299792458.0
    lam = c / freq_hz
    return 20.0 * math.log10(4.0 * math.pi * range_m / lam)

def boltzmann_db_hz():
    # k (Boltzmann) in dB units for noise power per Hz: k = -228.6 dBW/K/Hz; in dBm/Hz: -174 dBm/Hz at 290K
    # We'll return -228.6 dBW/K/Hz converted to dBm/Hz at 290K: -174 dBm/Hz commonly used.
    return -174.0  # dBm/Hz at room temp

def shannon_capacity_bps(bw_hz, snr_linear):
    return bw_hz * math.log2(1.0 + snr_linear)

# Shared Orekit orbit: never change the configured orbit merely to force a pass.
from simulation.propagator import OrekitPropagator, sample_offsets
from datetime import timedelta
runtime = OrekitPropagator.from_config(RUNTIME_CONFIG)
station_frames = {gs['name']: {'frame': runtime.station_frame(gs), 'cfg': gs} for gs in GROUND_STATIONS}
station_samples = {name: [] for name in station_frames}
for t in sample_offsets(PROP_SECONDS, STEP_SECONDS):
    timestamp = runtime.start_time + timedelta(seconds=t)
    for name, info in station_frames.items():
        geometry = runtime.station_geometry(timestamp, info['frame'])
        station_samples[name].append({'t': t, 'date': runtime.absolute_date(timestamp), **geometry})
visibility_windows = {}
for name, info in station_frames.items():
    windows = runtime.contact_windows(runtime.start_time, runtime.start_time + timedelta(seconds=PROP_SECONDS), info['frame'], MIN_ELEV_DEG)
    visibility_windows[name] = [dict(start_t=(w['start']-runtime.start_time).total_seconds(),
        end_t=(w['end']-runtime.start_time).total_seconds(),
        start_date=runtime.absolute_date(w['start']), end_date=runtime.absolute_date(w['end'])) for w in windows]
print(f'Orekit orbital period: {runtime.period_seconds/60:.3f} minutes')

# print summary of windows
for name, windows in visibility_windows.items():
    print(f"Station {name}: found {len(windows)} window(s) (elev >= {MIN_ELEV_DEG}°)")
    for w in windows:
        dur = (w["end_t"] - w["start_t"])
        print(f" - {name}: start t={w['start_t']}s end t={w['end_t']}s duration={dur}s")

# Debug: peek first few samples to help diagnose visibility issues (controlled by VERBOSE)
if VERBOSE:
    for name, samples in station_samples.items():
        print(f"DEBUG {name}: first 8 samples (t_s, elev_deg, range_km):")
        for s in samples[:8]:
            print(f"  t={s['t']}s elev={s['elev_deg']:.3f}° range={s['range_m']/1000.0:.3f} km")
        # show max elevation observed in the sampled window
        max_s = max(samples, key=lambda x: x['elev_deg'])
        print(f"DEBUG {name}: max elev={max_s['elev_deg']:.3f}° at t={max_s['t']}s range={max_s['range_m']/1000.0:.3f} km")


# ---------------- classical link model per sample (SNR, throughput) per station (B3) ----------------
# Precompute constants per-station where needed
c = 299792458.0
# We'll compute noise floor per station using their configured bandwidth or the default

classical_results = {name: [] for name in station_frames}
for name, samples in station_samples.items():
    cfg = station_frames[name]["cfg"]
    bw = cfg.get("bandwidth_hz", BANDWIDTH_HZ)
    kTB_dBm = boltzmann_db_hz() + 10.0 * math.log10(bw)
    noise_floor_dBm = kTB_dBm + SYSTEM_NOISE_FIGURE_dB
    for s in samples:
        elev = s["elev_deg"]
        rng = s["range_m"]
        t = s["t"]
        if elev < MIN_ELEV_DEG:
            continue
        # FSPL at RF freq
        fspl_dB = free_space_path_loss_dB(rng, FREQ_HZ)
        # additional pointing losses (classical)
        loss_dB = fspl_dB + TX_POINTING_LOSS_dB + RX_POINTING_LOSS_dB
        Pr_dBm = cfg.get("tx_power_dBm", TX_POWER_dBm) + cfg.get("tx_antenna_gain_dBi", TX_ANTENNA_GAIN_dBi) + cfg.get("rx_antenna_gain_dBi", RX_ANTENNA_GAIN_dBi) - loss_dB
        snr_dB = Pr_dBm - noise_floor_dBm
        snr_linear = db2lin(snr_dB)
        capacity_bps = shannon_capacity_bps(bw, max(snr_linear, 1e-12))
        classical_results[name].append({
            "t": t,
            "elev_deg": elev,
            "range_m": rng,
            "Pr_dBm": Pr_dBm,
            "snr_dB": snr_dB,
            "capacity_bps": capacity_bps
        })

# Print basic summary per station
for name, arr in classical_results.items():
    if not arr:
        print(f"{name}: No classical link samples (no visibility)")
        continue
    sorted_by_pr = sorted(arr, key=lambda r: r["Pr_dBm"], reverse=True)
    med = arr[len(arr)//2]
    print(f"{name} classical link sample (first / median / best):")
    print(" t(s) elev°  range(km)  Pr(dBm)  SNR(dB)  Capacity(Mbps)")
    for r in [arr[0], med, sorted_by_pr[0]]:
        print(f" {r['t']:4d} {r['elev_deg']:5.1f} {r['range_m']/1000:7.2f}  {r['Pr_dBm']:6.2f}   {r['snr_dB']:6.2f}  {r['capacity_bps']/1e6:7.3f}")

# ---------------- simple QKD model per sample (B4) ----------------
# produce raw detection rate, background rate, QBER, and approximate key rate per sample
def qkd_metrics(range_m, atmospheric_loss_db=ATMOSPHERIC_LOSS_dB,
                 pointing_loss_db=POINTING_LOSS_dB_QKD,
                 detector_eff=DETECTOR_EFFICIENCY,
                 dark_counts_hz=DETECTOR_DARK_COUNTS_HZ,
                 source_rate_hz=SOURCE_RATE_HZ,
                 misalignment_error=MISALIGNMENT_ERROR):
    # Compute free-space path loss for the optical carrier and include it in total loss.
    optical_freq_hz = 299792458.0 / OPTICAL_WAVELENGTH_M
    fspl_dB = free_space_path_loss_dB(range_m, optical_freq_hz)
    total_loss_db = fspl_dB + atmospheric_loss_db + pointing_loss_db
    total_loss_lin = db2lin(-total_loss_db)
    # Effective signal detection rate (photons/sec)
    signal_detect_rate = source_rate_hz * total_loss_lin * detector_eff
    if signal_detect_rate < 0:
        signal_detect_rate = 0.0
    # Background + dark counts
    background_rate = dark_counts_hz
    # QBER: from misalignment + background/(signal+background)
    if signal_detect_rate <= 0:
        qber = 0.5  # hopeless
    else:
        qber = misalignment_error + (background_rate / (signal_detect_rate + background_rate))
        qber = min(qber, 0.5)
    # Raw key rate ~ signal detections * sifting factor (~0.5 for BB84)
    sifting = 0.5
    raw_key_rate = signal_detect_rate * sifting
    # Simplified final key rate estimate (asymptotic): R = raw * [1 - f*H2(QBER) - H2(QBER)]
    # We'll use error correction inefficiency f = 1.15
    def H2(x):
        if x <= 0 or x >= 1:
            return 0.0
        return -(x*math.log2(x) + (1-x)*math.log2(1-x))
    f = 1.15
    leak_ec = f * H2(qber)
    secure_fraction = max(0.0, 1.0 - leak_ec - H2(qber))
    key_rate = raw_key_rate * secure_fraction
    return {"signal_detect_rate": signal_detect_rate,
            "background_rate": background_rate,
            "qber": qber,
            "raw_rate": raw_key_rate,
            "key_rate": key_rate}

# compute QKD metrics per station and sample
qkd_results = {name: [] for name in station_frames}
for name, samples in station_samples.items():
    for s in samples:
        elev = s["elev_deg"]
        rng = s["range_m"]
        t = s["t"]
        if elev < MIN_ELEV_DEG:
            continue
        # elevation-dependent atmospheric loss: approximate airmass = 1/sin(elev)
        elev_rad = math.radians(max(elev, 0.1))
        airmass = 1.0 / max(math.sin(elev_rad), 0.01)
        airmass = min(airmass, 10.0)
        atm_loss = ATMOSPHERIC_LOSS_dB * airmass
        metrics = qkd_metrics(rng, atmospheric_loss_db=atm_loss)
        metrics.update({"t": t, "elev_deg": elev, "range_m": rng})
        qkd_results[name].append(metrics)

for name, arr in qkd_results.items():
    if not arr:
        print(f"{name}: No QKD samples (no visibility)")
        continue
    best = max(arr, key=lambda x: x["key_rate"])
    print(f"{name} QKD best sample:")
    print(f" {name} t={best['t']}s elev={best['elev_deg']:.1f}° range={best['range_m']/1000:.2f} km key_rate={best['key_rate']:.3f} Hz QBER={best['qber']:.4f}")

# write CSV with per-sample per-station classical + QKD metrics
CSV_OUT = Path(RUNTIME_CONFIG['comm_csv_file'])
CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
with open(CSV_OUT, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["station", "t_s", "elev_deg", "range_m", "Pr_dBm", "snr_dB", "capacity_Mbps", "qkd_key_rate_Hz", "qkd_qber"])
    for name in station_frames:
        # build maps for merge
        cls_arr = classical_results.get(name, [])
        qkd_arr = qkd_results.get(name, [])
        cls_map = {int(r["t"]): r for r in cls_arr}
        qk_map = {int(r["t"]): r for r in qkd_arr}
        # use union of times
        times_union = sorted(set(list(cls_map.keys()) + list(qk_map.keys())))
        for t in times_union:
            cls = cls_map.get(t)
            qk = qk_map.get(t)
            writer.writerow([
                name,
                t,
                cls["elev_deg"] if cls else (qk["elev_deg"] if qk else ""),
                cls["range_m"] if cls else (qk["range_m"] if qk else ""),
                cls["Pr_dBm"] if cls else "",
                cls["snr_dB"] if cls else "",
                (cls["capacity_bps"]/1e6) if cls else "",
                qk["key_rate"] if qk else "",
                qk["qber"] if qk else "",
            ])
print("Comm samples CSV written:", CSV_OUT)

# shutdown JVM
runtime.shutdown()

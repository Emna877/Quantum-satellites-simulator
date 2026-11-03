"""Generate diagnostic plots for one or more satellite passes.

Reads the CSV written by qkd.py (comm_samples.csv) or any CSV produced by the
experiment runner and writes one PNG per plot type.  All plots show the same
time axis (seconds since first sample) so they can be compared or stacked.

Usage
-----
    python -m scripts.plot_pass                        # uses default CSV path
    python -m scripts.plot_pass --csv data/comm_samples.csv --out data/plots/

Each plot is saved as:
    range.png, elevation.png, rf_snr.png, optical_signal.png, qber.png, key_rate.png

Requires matplotlib (add to requirements.txt if not already present).
If matplotlib is absent, a clear ImportError is raised rather than a silent failure.

Scientific notes
----------------
- Key-rate plots show the asymptotic BB84 estimate (from qkd_key_rate_bit_s column
  if present, else recomputed from sifted rate and QBER).
- QBER > 0.11 is highlighted in red (above asymptotic security threshold).
- SNR below 0 dB (noise floor) is highlighted in red (link unavailable).
- All values are plotted as-is; no smoothing is applied.
"""
import argparse
import sys
from pathlib import Path

try:
    import matplotlib
    matplotlib.use('Agg')  # headless rendering
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    _HAVE_MATPLOTLIB = True
except ImportError:
    _HAVE_MATPLOTLIB = False


def _require_matplotlib():
    if not _HAVE_MATPLOTLIB:
        raise ImportError(
            "matplotlib is required for plot_pass.py.  "
            "Install it with: pip install matplotlib"
        )


def load_csv(path: Path) -> dict:
    """Load CSV into a dict of column → list of floats/strings."""
    import csv
    with path.open(newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if not rows:
        raise ValueError(f"CSV is empty: {path}")
    columns = {k: [] for k in rows[0]}
    for row in rows:
        for k, v in row.items():
            columns[k].append(v)
    return columns


def _floats(col):
    result = []
    for v in col:
        try:
            result.append(float(v))
        except (ValueError, TypeError):
            result.append(float('nan'))
    return result


def _bools(col):
    return [str(v).lower() in ('true', '1', 'yes') for v in col]


def _time_axis(data: dict):
    """Build t_s axis: use t_s column if present, else derive from index × 30 s."""
    if 't_s' in data:
        return _floats(data['t_s'])
    return [i * 30.0 for i in range(len(next(iter(data.values()))))]


def _style(ax, xlabel='Time (s)', ylabel='', title=''):
    ax.set_xlabel(xlabel, fontsize=10)
    ax.set_ylabel(ylabel, fontsize=10)
    ax.set_title(title, fontsize=11)
    ax.grid(True, alpha=0.35, linestyle='--')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)


def plot_range(data: dict, out_dir: Path):
    _require_matplotlib()
    t = _time_axis(data)
    r = _floats(data.get('range_m', []))
    r_km = [v / 1e3 for v in r]
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.plot(t, r_km, color='#2266cc', linewidth=1.5)
    _style(ax, ylabel='Range (km)', title='Slant Range vs Time')
    fig.tight_layout()
    fig.savefig(out_dir / 'range.png', dpi=120)
    plt.close(fig)


def plot_elevation(data: dict, out_dir: Path):
    _require_matplotlib()
    t = _time_axis(data)
    el = _floats(data.get('elev_deg', []))
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.fill_between(t, 0, el, alpha=0.2, color='#2266cc')
    ax.plot(t, el, color='#2266cc', linewidth=1.5)
    ax.axhline(5, color='grey', linewidth=0.8, linestyle='--', label='5° threshold')
    ax.legend(fontsize=9)
    _style(ax, ylabel='Elevation (°)', title='Ground Station Elevation vs Time')
    fig.tight_layout()
    fig.savefig(out_dir / 'elevation.png', dpi=120)
    plt.close(fig)


def plot_rf_snr(data: dict, out_dir: Path):
    _require_matplotlib()
    t = _time_axis(data)
    snr_col = 'rf_snr_db' if 'rf_snr_db' in data else 'snr_db'
    snr = _floats(data.get(snr_col, []))
    fig, ax = plt.subplots(figsize=(8, 3))
    above = [v if v >= 0 else float('nan') for v in snr]
    below = [v if v < 0 else float('nan') for v in snr]
    ax.plot(t, above, color='#22aa55', linewidth=1.5, label='Available (SNR ≥ 0 dB)')
    ax.plot(t, below, color='#cc2222', linewidth=1.5, label='Unavailable (SNR < 0 dB)')
    ax.axhline(0, color='grey', linewidth=0.8, linestyle='--')
    ax.legend(fontsize=9)
    _style(ax, ylabel='SNR (dB)', title='RF Link SNR vs Time')
    fig.tight_layout()
    fig.savefig(out_dir / 'rf_snr.png', dpi=120)
    plt.close(fig)


def plot_optical_signal(data: dict, out_dir: Path):
    _require_matplotlib()
    t = _time_axis(data)
    sig_col = 'opt_signal_count_hz' if 'opt_signal_count_hz' in data else 'signal_count_hz'
    sig = _floats(data.get(sig_col, []))
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.plot(t, sig, color='#8833cc', linewidth=1.5)
    _style(ax, ylabel='Signal count (photons/s)', title='Optical Signal Detection Rate vs Time')
    fig.tight_layout()
    fig.savefig(out_dir / 'optical_signal.png', dpi=120)
    plt.close(fig)


def plot_qber(data: dict, out_dir: Path):
    _require_matplotlib()
    t = _time_axis(data)
    qber_col = 'opt_qber' if 'opt_qber' in data else 'qber'
    qber = _floats(data.get(qber_col, []))
    fig, ax = plt.subplots(figsize=(8, 3))
    threshold = 0.11
    safe = [v if v < threshold else float('nan') for v in qber]
    danger = [v if v >= threshold else float('nan') for v in qber]
    ax.plot(t, safe, color='#22aa55', linewidth=1.5, label=f'QBER < {threshold:.0%}')
    ax.plot(t, danger, color='#cc2222', linewidth=1.5, label=f'QBER ≥ {threshold:.0%} (abort)')
    ax.axhline(threshold, color='#cc8800', linewidth=0.8, linestyle='--',
               label=f'Threshold {threshold:.0%}')
    ax.set_ylim(0, 0.55)
    ax.legend(fontsize=9)
    _style(ax, ylabel='QBER', title='Quantum Bit Error Rate vs Time')
    fig.tight_layout()
    fig.savefig(out_dir / 'qber.png', dpi=120)
    plt.close(fig)


def plot_key_rate(data: dict, out_dir: Path):
    _require_matplotlib()
    t = _time_axis(data)
    rate_col = 'qkd_key_rate_bit_s' if 'qkd_key_rate_bit_s' in data else 'secret_key_rate_bit_s'
    rate = _floats(data.get(rate_col, []))
    fig, ax = plt.subplots(figsize=(8, 3))
    positive = [v if v > 0 else float('nan') for v in rate]
    zero = [0.0 if v <= 0 else float('nan') for v in rate]
    ax.plot(t, positive, color='#8833cc', linewidth=1.5, label='Key rate (bit/s)')
    ax.fill_between(t, 0, [v if not (v != v) else 0 for v in positive],
                    alpha=0.15, color='#8833cc')
    ax.scatter([tt for tt, v in zip(t, zero) if v == v],
               [0] * sum(1 for v in zero if v == v),
               color='#cc2222', s=8, zorder=5, label='Zero / aborted')
    ax.legend(fontsize=9)
    _style(ax, ylabel='Key rate (bit/s)',
           title='Asymptotic BB84 Secret-Key Rate vs Time\n'
                 '(finite-key effects not shown; finite_key_valid=False)')
    fig.tight_layout()
    fig.savefig(out_dir / 'key_rate.png', dpi=120)
    plt.close(fig)


def plot_all(csv_path: Path, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    data = load_csv(csv_path)
    n = len(next(iter(data.values())))
    print(f"Loaded {n} rows from {csv_path}")

    plotters = [
        ('range.png', plot_range),
        ('elevation.png', plot_elevation),
        ('rf_snr.png', plot_rf_snr),
        ('optical_signal.png', plot_optical_signal),
        ('qber.png', plot_qber),
        ('key_rate.png', plot_key_rate),
    ]
    for fname, fn in plotters:
        try:
            fn(data, out_dir)
            print(f"  wrote {out_dir / fname}")
        except Exception as exc:
            print(f"  SKIP {fname}: {exc}")


def main():
    ap = argparse.ArgumentParser(
        description='Generate diagnostic plots from a communication CSV.'
    )
    ap.add_argument('--csv', default='data/comm_samples.csv',
                    help='Input CSV file (default: data/comm_samples.csv)')
    ap.add_argument('--out', default='data/plots/',
                    help='Output directory for PNG files (default: data/plots/)')
    args = ap.parse_args()

    _require_matplotlib()
    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"CSV not found: {csv_path}", file=sys.stderr)
        print("Run `python qkd.py` first to generate communication samples.", file=sys.stderr)
        sys.exit(1)

    plot_all(csv_path, Path(args.out))
    print("Done.")


if __name__ == '__main__':
    main()

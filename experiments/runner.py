"""Paired experiment runner: baseline vs attack, classical vs quantum-assisted.

Executes both communication pipelines on the same physical scenario (same
Orekit geometry, same timestamps, same event schedule) and returns aligned,
time-stamped metric records.

Architecture
------------
The runner is deliberately thin: it consumes already-initialised objects (an
OrekitPropagator, station config, channel configs, security configs, and a
scenario definition) and calls the existing communication and security modules
in dependency order.  It never computes orbital mechanics itself.

Design rules (from ARCHITECTURE.md)
-------------------------------------
- One UTC clock and one OrekitPropagator serve both pipelines.
- Channel-specific parameters (RFLinkConfig, OpticalLinkConfig) are the only
  differences between the two pipelines at the physical layer.
- Attack disturbances are applied to channel configs at each sample step via
  the channel_effects module.
- True Orekit position is never modified; only navigation_error_m (state) is
  affected by spoofing events.
- Zero-key and abort results are valid outcomes and are preserved in records.
- finite_key_valid=False records are kept; the UI must not replace them with
  positive values.

Usage
-----
    from experiments.runner import ExperimentRunner, RunnerConfig
    from experiments.scenarios import SCENARIOS

    runner = ExperimentRunner(
        propagator=shared_propagator,
        station=tunis_station,
        scenario=SCENARIOS['rf_jamming_moderate'],
        config=RunnerConfig(),
    )
    result = runner.run(start_time, end_time, dt_s=30.0)
    # result.to_dict() → JSON-serialisable experiment record
"""
from __future__ import annotations

import json
import math
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from communication.rf_link import RFLinkConfig, rf_link_budget
from communication.optical_link import OpticalLinkConfig, optical_link_metrics
from communication.qkd_model import QKDModelConfig, qkd_key_metrics
from communication.channel_effects import (
    rf_config_with_jamming,
    optical_config_with_background_increase,
    optical_config_with_extra_loss,
)
from security.classical_session import ClassicalSessionConfig, classical_key_establishment
from security.qkd_finite_key import BB84FiniteKeyConfig, bb84_finite_key_metrics
from security.key_store import KeyStore, KeyStoreConfig
from experiments.scenarios import ScenarioDefinition, SCENARIOS


@dataclass
class RunnerConfig:
    """Runner-level parameters shared by both pipelines."""
    rf: RFLinkConfig = field(default_factory=RFLinkConfig)
    optical: OpticalLinkConfig = field(default_factory=OpticalLinkConfig)
    qkd_asymptotic: QKDModelConfig = field(default_factory=QKDModelConfig)
    qkd_finite: BB84FiniteKeyConfig = field(default_factory=BB84FiniteKeyConfig)
    classical_session: ClassicalSessionConfig = field(default_factory=ClassicalSessionConfig)
    key_store: KeyStoreConfig = field(default_factory=KeyStoreConfig)
    min_elevation_deg: float = 5.0


@dataclass
class SampleRecord:
    """One timestamped sample from the paired runner."""
    timestamp: str                # UTC ISO-8601
    t_s: float                    # seconds since run start
    elev_deg: float
    azimuth_deg: float
    range_m: float
    # Classical pipeline
    rf: dict
    classical_session: dict
    # Quantum-assisted pipeline
    optical: dict
    qkd_asymptotic: dict
    qkd_finite: dict              # per-sample rate only; finite-key pass totals are in PassRecord
    # State disturbances active at this sample
    rf_jamming_db: float = 0.0
    optical_background_scale: float = 1.0
    optical_cloud_blocked: bool = False


@dataclass
class PassRecord:
    """Aggregated results for one contact window."""
    pass_id: str
    window_start: str             # UTC ISO-8601
    window_end: str
    duration_s: float
    samples: List[dict]           # list of SampleRecord.to_dict() for each sample in this pass
    # Finite-key totals (accumulate over the whole pass, not per sample)
    qkd_finite_pass: dict
    # Classical session established?
    classical_session_summary: dict
    # Key-store state at end of pass
    key_store_snapshot: dict


@dataclass
class ExperimentResult:
    """Full paired-run result."""
    experiment_id: str
    scenario_name: str
    scenario_description: str
    start_time: str
    end_time: str
    dt_s: float
    total_passes: int
    contact_fraction: float       # fraction of run duration in contact
    passes: List[dict]
    key_store_final: dict
    config_summary: dict
    model_limitations: list

    def to_dict(self) -> dict:
        return {
            "experiment_id": self.experiment_id,
            "scenario_name": self.scenario_name,
            "scenario_description": self.scenario_description,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "dt_s": self.dt_s,
            "total_passes": self.total_passes,
            "contact_fraction": self.contact_fraction,
            "passes": self.passes,
            "key_store_final": self.key_store_final,
            "config_summary": self.config_summary,
            "model_limitations": self.model_limitations,
        }

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, default=str))


_LIMITATIONS = [
    "QKD key rate is asymptotic (communication/qkd_model.py) or finite-key corrected "
    "(security/qkd_finite_key.py); finite_key_valid=False means no security claim.",
    "Finite-key model uses simplified Chernoff bounds; a rigorous composable proof is not included.",
    "RF link budget uses fixed pointing loss; no rain fade, Doppler, or fading model.",
    "Optical link uses far-field Gaussian beam; no seeing, partial cloud, or wavefront error.",
    "Classical session model is a protocol-engineering model; no actual cryptographic operations.",
    "Key-store consumption rate is constant; traffic shaping or burst models are not included.",
    "Two-body Keplerian orbit; no J2, drag, or solar radiation pressure.",
    "Attack effects are deterministic surrogate presets; not calibrated spacecraft physics.",
    "QKD classical post-processing authentication overhead is not subtracted from key budget.",
    "Navigation spoofing affects reported position estimate; true Orekit orbit is unmodified.",
]


class ExperimentRunner:
    """Paired experiment runner for one physical scenario and one attack scenario.

    Parameters
    ----------
    propagator : OrekitPropagator
        Shared Orekit propagator (already initialised, JVM running).
    station : dict
        Ground-station dict with keys: name, lat_deg, lon_deg, alt_m.
    scenario : ScenarioDefinition
        Attack/disturbance definition from experiments.scenarios.
    config : RunnerConfig
        Channel and protocol parameters.
    """

    def __init__(self, propagator, station: dict, scenario: ScenarioDefinition,
                 config: Optional[RunnerConfig] = None):
        self._prop = propagator
        self._station = station
        self._scenario = scenario
        self._cfg = config or RunnerConfig()

    def run(self, start: datetime, end: datetime, dt_s: float = 30.0) -> ExperimentResult:
        """Execute the paired run and return structured results.

        Parameters
        ----------
        start : datetime
            UTC start time (timezone-aware).
        end : datetime
            UTC end time (timezone-aware).
        dt_s : float
            Sampling interval, seconds.
        """
        if start.tzinfo is None:
            raise ValueError("start must be timezone-aware")
        if end.tzinfo is None:
            raise ValueError("end must be timezone-aware")
        if dt_s <= 0:
            raise ValueError("dt_s must be positive")

        experiment_id = str(uuid.uuid4())
        total_s = (end - start).total_seconds()

        # Find contact windows
        windows = self._prop.contact_windows(start, end, self._station,
                                             self._cfg.min_elevation_deg)

        # Build events for each window (scenario factories receive window boundaries)
        all_events = []
        for w in windows:
            all_events.extend(self._scenario.build_events(w['start'], w['end']))

        # Key store starts empty
        key_store = KeyStore(config=self._cfg.key_store)

        passes = []
        total_contact_s = 0.0

        for w in windows:
            pass_start = w['start']
            pass_end = w['end']
            duration_s = (pass_end - pass_start).total_seconds()
            total_contact_s += duration_s

            samples, finite_pass, classical_summary = self._run_pass(
                pass_start, pass_end, dt_s, all_events, key_store
            )

            passes.append({
                "pass_id": str(uuid.uuid4()),
                "window_start": _iso(pass_start),
                "window_end": _iso(pass_end),
                "duration_s": duration_s,
                "samples": samples,
                "qkd_finite_pass": finite_pass,
                "classical_session_summary": classical_summary,
                "key_store_snapshot": key_store.snapshot(),
            })

        contact_fraction = total_contact_s / total_s if total_s > 0 else 0.0

        return ExperimentResult(
            experiment_id=experiment_id,
            scenario_name=self._scenario.name,
            scenario_description=self._scenario.description,
            start_time=_iso(start),
            end_time=_iso(end),
            dt_s=dt_s,
            total_passes=len(passes),
            contact_fraction=contact_fraction,
            passes=passes,
            key_store_final=key_store.snapshot(),
            config_summary=self._config_summary(),
            model_limitations=_LIMITATIONS,
        )

    def _run_pass(self, pass_start, pass_end, dt_s, events, key_store):
        """Sample one contact window and return (samples, finite_key_pass_result, classical_summary)."""
        duration_s = (pass_end - pass_start).total_seconds()

        # Accumulate sifted bits for the finite-key calculation over the whole pass
        total_sifted_hz_sum = 0.0
        total_qber_sum = 0.0
        n_optical_samples = 0
        samples = []

        t = pass_start
        while t <= pass_end + timedelta(seconds=dt_s * 0.01):
            geom = self._prop.station_geometry(t, self._station)
            range_m = geom['range_m']
            elev_deg = geom['elev_deg']
            t_s = (t - pass_start).total_seconds()

            # Determine active disturbances at this sample
            rf_loss_db = self._scenario.rf_signal_loss_db
            bg_scale = self._scenario.optical_background_scale
            cloud = self._scenario.optical_cloud_blocked
            extra_opt_loss = self._scenario.optical_extra_loss_db

            # Apply to channel configs
            rf_cfg = rf_config_with_jamming(self._cfg.rf, rf_loss_db)
            opt_cfg = self._cfg.optical
            if cloud:
                from dataclasses import replace
                opt_cfg = replace(opt_cfg, cloud_blocked=True)
            if bg_scale > 1.0:
                opt_cfg = optical_config_with_background_increase(opt_cfg, bg_scale)
            if extra_opt_loss > 0.0:
                opt_cfg = optical_config_with_extra_loss(opt_cfg, extra_opt_loss)

            # Classical RF
            rf = rf_link_budget(range_m, rf_cfg)

            # Optical / QKD
            opt = optical_link_metrics(range_m, elev_deg, opt_cfg)
            qkd_asym = qkd_key_metrics(opt['sifted_count_hz'], opt['qber'], self._cfg.qkd_asymptotic)

            # Accumulate for finite-key pass total
            total_sifted_hz_sum += opt['sifted_count_hz']
            total_qber_sum += opt['qber']
            n_optical_samples += 1

            # Per-sample finite-key estimate (uses dt_s as the interval)
            qkd_fin_sample = bb84_finite_key_metrics(
                opt['sifted_count_hz'], opt['qber'], dt_s, self._cfg.qkd_finite
            )

            # Key store: replenish from asymptotic rate, consume at data rate
            key_store.update(
                dt_s=dt_s,
                replenishment_rate_bit_s=qkd_asym['secret_key_rate_bit_s'],
                transmitting=rf['available'],
            )

            samples.append({
                "timestamp": _iso(t),
                "t_s": t_s,
                "elev_deg": elev_deg,
                "azimuth_deg": geom.get('azimuth_deg', 0.0),
                "range_m": range_m,
                "rf": rf,
                "optical": opt,
                "qkd_asymptotic": qkd_asym,
                "qkd_finite_sample": qkd_fin_sample,
                "rf_jamming_db": rf_loss_db,
                "optical_background_scale": bg_scale,
                "optical_cloud_blocked": cloud,
            })

            t += timedelta(seconds=dt_s)
            if t > pass_end and (t - timedelta(seconds=dt_s)) < pass_end:
                break

        # Finite-key analysis over the whole pass
        avg_sifted = total_sifted_hz_sum / n_optical_samples if n_optical_samples else 0.0
        avg_qber = total_qber_sum / n_optical_samples if n_optical_samples else 0.5
        finite_pass = bb84_finite_key_metrics(
            avg_sifted, avg_qber, duration_s, self._cfg.qkd_finite
        )
        finite_pass["note"] = (
            "Computed from pass-average sifted rate and QBER over "
            f"{duration_s:.0f} s.  Instantaneous variation is in per-sample records."
        )

        # Classical session establishment (uses pass geometry midpoint)
        mid = pass_start + timedelta(seconds=duration_s / 2)
        mid_geom = self._prop.station_geometry(mid, self._station)
        mid_rf = rf_link_budget(mid_geom['range_m'],
                                rf_config_with_jamming(self._cfg.rf, self._scenario.rf_signal_loss_db))
        classical_summary = classical_key_establishment(
            link_available=mid_rf['available'],
            snr_db=mid_rf['snr_db'],
            range_m=mid_geom['range_m'],
            contact_duration_s=duration_s,
            cfg=self._cfg.classical_session,
        )

        return samples, finite_pass, classical_summary

    def _config_summary(self) -> dict:
        return {
            "rf": {
                "tx_power_dbm": self._cfg.rf.tx_power_dbm,
                "frequency_hz": self._cfg.rf.frequency_hz,
                "bandwidth_hz": self._cfg.rf.bandwidth_hz,
            },
            "optical": {
                "source_rate_hz": self._cfg.optical.source_rate_hz,
                "rx_aperture_m": self._cfg.optical.rx_aperture_m,
                "beam_divergence_half_angle_rad": self._cfg.optical.beam_divergence_half_angle_rad,
            },
            "qkd_finite": {
                "eps_sec": self._cfg.qkd_finite.eps_sec,
                "n_min_sifted": self._cfg.qkd_finite.n_min_sifted,
            },
            "scenario": {
                "name": self._scenario.name,
                "rf_signal_loss_db": self._scenario.rf_signal_loss_db,
                "optical_background_scale": self._scenario.optical_background_scale,
                "optical_cloud_blocked": self._scenario.optical_cloud_blocked,
            },
        }


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def run_comparison(propagator, station: dict, start: datetime, end: datetime,
                   dt_s: float = 30.0, scenario_name: str = 'rf_jamming_moderate',
                   config: Optional[RunnerConfig] = None) -> Dict[str, ExperimentResult]:
    """Convenience function: run baseline + named scenario and return both results.

    Returns
    -------
    dict with keys 'baseline' and <scenario_name>, each an ExperimentResult.
    """
    cfg = config or RunnerConfig()
    results = {}
    for name in ('baseline', scenario_name):
        if name == scenario_name and name == 'baseline':
            break  # avoid running baseline twice if scenario_name IS baseline
        scenario = SCENARIOS[name]
        runner = ExperimentRunner(propagator, station, scenario, cfg)
        results[name] = runner.run(start, end, dt_s)
    return results

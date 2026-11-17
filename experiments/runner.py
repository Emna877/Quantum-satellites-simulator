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
- QKD post-processing (sifting, error correction, privacy amplification) runs
  over the authenticated classical RF channel.  A pass produces QKD key only if
  that channel is available long enough to carry the post-processing traffic;
  otherwise the pass result is aborted even when photons were detected.
- The classical pipeline is evaluated twice per pass: with pre-quantum ECDH and
  with post-quantum ML-KEM, so QKD is compared against both baselines.

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
    optical_config_with_intercept_resend,
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
    pqc_session: ClassicalSessionConfig = field(
        default_factory=lambda: ClassicalSessionConfig(key_exchange='ML-KEM-768'))
    key_store: KeyStoreConfig = field(default_factory=KeyStoreConfig)
    min_elevation_deg: float = 5.0
    # QKD post-processing over the authenticated RF channel
    min_post_processing_link_s: float = 10.0   # minimum RF-available time in the pass
    post_processing_bits_per_detection: float = 2.0  # detection index + basis announcement


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
    # Classical session established? (pre-quantum ECDH and post-quantum ML-KEM)
    classical_session_summary: dict
    pqc_session_summary: dict
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
    "Finite-key model applies the Tomamichel et al. (2012) error-rate bound; decoy-state "
    "yields use infinite statistics, so this is not a composable finite-size decoy proof.",
    "RF link budget uses fixed pointing loss; no rain fade, Doppler, or fading model.",
    "Optical link uses far-field Gaussian beam; no seeing, partial cloud, or wavefront error.",
    "Classical session model (ECDH and ML-KEM) is a protocol-engineering model; no actual "
    "cryptographic operations.",
    "Key-store consumption rate is constant; traffic shaping or burst models are not included.",
    "Two-body Keplerian orbit; no J2, drag, or solar radiation pressure.",
    "Attack effects are deterministic surrogate presets; not calibrated spacecraft physics.",
    "QKD post-processing requires the RF channel (time and traffic check); its authentication "
    "key consumption is not subtracted from the key budget.",
    "Intercept-resend is the only eavesdropping attack modelled; PNS, detector blinding and "
    "Trojan-horse attacks are not.",
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

            samples, finite_pass, classical_summary, pqc_summary = self._run_pass(
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
                "pqc_session_summary": pqc_summary,
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

    def _channel_configs(self):
        """Apply the scenario's run-wide disturbances to the channel configs."""
        sc = self._scenario
        rf_cfg = rf_config_with_jamming(self._cfg.rf, sc.rf_signal_loss_db)
        opt_cfg = self._cfg.optical
        if sc.optical_cloud_blocked:
            from dataclasses import replace
            opt_cfg = replace(opt_cfg, cloud_blocked=True)
        if sc.optical_background_scale > 1.0:
            opt_cfg = optical_config_with_background_increase(opt_cfg, sc.optical_background_scale)
        if sc.optical_extra_loss_db > 0.0:
            opt_cfg = optical_config_with_extra_loss(opt_cfg, sc.optical_extra_loss_db)
        if sc.qkd_intercept_resend_fraction > 0.0:
            opt_cfg = optical_config_with_intercept_resend(opt_cfg, sc.qkd_intercept_resend_fraction)
        return rf_cfg, opt_cfg

    def _run_pass(self, pass_start, pass_end, dt_s, events, key_store):
        """Sample one contact window.

        Returns (samples, finite_key_pass_result, ecdh_summary, pqc_summary).
        """
        duration_s = (pass_end - pass_start).total_seconds()
        rf_cfg, opt_cfg = self._channel_configs()
        sc = self._scenario

        # Count-weighted accumulators for the whole-pass finite-key calculation
        sifted_sum = 0.0          # Σ sifted rate
        errors_sum = 0.0          # Σ sifted rate × QBER
        single_sum = 0.0          # Σ sifted rate × Δ1
        single_err_sum = 0.0      # Σ sifted rate × Δ1 × e1
        detections_sum = 0.0      # Σ total click rate
        rf_available_s = 0.0
        rf_capacity_bits = 0.0
        n_samples = 0
        samples = []

        t = pass_start
        while t <= pass_end + timedelta(seconds=dt_s * 0.01):
            geom = self._prop.station_geometry(t, self._station)
            range_m = geom['range_m']
            elev_deg = geom['elev_deg']
            t_s = (t - pass_start).total_seconds()

            rf = rf_link_budget(range_m, rf_cfg)
            opt = optical_link_metrics(range_m, elev_deg, opt_cfg)
            qkd_asym = qkd_key_metrics(opt['sifted_count_hz'], opt['qber'], self._cfg.qkd_asymptotic,
                                       opt['single_photon_fraction'], opt['single_photon_qber'])

            sifted = opt['sifted_count_hz']
            sifted_sum += sifted
            errors_sum += sifted * opt['qber']
            single_sum += sifted * opt['single_photon_fraction']
            single_err_sum += sifted * opt['single_photon_fraction'] * opt['single_photon_qber']
            detections_sum += opt['total_count_hz']
            if rf['available']:
                rf_available_s += dt_s
                rf_capacity_bits += (rf['shannon_capacity_bps']
                                     * self._cfg.classical_session.link_coding_efficiency * dt_s)
            n_samples += 1

            # Per-sample finite-key estimate (uses dt_s as the interval)
            qkd_fin_sample = bb84_finite_key_metrics(
                sifted, opt['qber'], dt_s, self._cfg.qkd_finite,
                opt['single_photon_fraction'], opt['single_photon_qber'],
            )

            # Key store: replenish only while the authenticated classical channel
            # can carry post-processing; consume at data rate while transmitting.
            key_store.update(
                dt_s=dt_s,
                replenishment_rate_bit_s=qkd_asym['secret_key_rate_bit_s'] if rf['available'] else 0.0,
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
                "qkd_classical_channel_available": rf['available'],
                "rf_jamming_db": sc.rf_signal_loss_db,
                "optical_background_scale": sc.optical_background_scale,
                "optical_cloud_blocked": sc.optical_cloud_blocked,
                "qkd_intercept_resend_fraction": sc.qkd_intercept_resend_fraction,
            })

            t += timedelta(seconds=dt_s)
            if t > pass_end and (t - timedelta(seconds=dt_s)) < pass_end:
                break

        # Finite-key analysis over the whole pass.  Pass statistics are weighted
        # by detection counts: low-elevation samples with few clicks contribute
        # few bits, as in a real pass.
        avg_sifted = sifted_sum / n_samples if n_samples else 0.0
        pass_qber = errors_sum / sifted_sum if sifted_sum > 0 else 0.5
        pass_delta1 = single_sum / sifted_sum if sifted_sum > 0 else 0.0
        pass_e1 = single_err_sum / single_sum if single_sum > 0 else 0.5
        finite_pass = bb84_finite_key_metrics(
            avg_sifted, pass_qber, duration_s, self._cfg.qkd_finite, pass_delta1, pass_e1,
        )
        finite_pass["note"] = (
            "Computed from count-weighted pass QBER and pass-average sifted rate over "
            f"{duration_s:.0f} s.  Instantaneous variation is in per-sample records."
        )

        # QKD depends on the authenticated classical channel for post-processing.
        detections = detections_sum / n_samples * duration_s if n_samples else 0.0
        pp_bits = (detections * self._cfg.post_processing_bits_per_detection
                   + finite_pass['n_key_bits'] * self._cfg.qkd_finite.ec_efficiency * _h2(pass_qber))
        dependency = {
            "channel": "rf_data (authenticated classical)",
            "rf_available_s": rf_available_s,
            "required_s": self._cfg.min_post_processing_link_s,
            "post_processing_bits": pp_bits,
            "rf_deliverable_bits": rf_capacity_bits,
        }
        dependency["satisfied"] = (rf_available_s >= self._cfg.min_post_processing_link_s
                                   and rf_capacity_bits >= pp_bits)
        finite_pass["classical_dependency"] = dependency
        if not dependency["satisfied"] and finite_pass["key_status"] == "succeeded":
            finite_pass.update(
                key_status="aborted",
                secure_key_bits=0.0,
                secure_key_rate_bit_s=0.0,
                finite_key_valid=False,
                abort_reason=(
                    "Authenticated classical channel unavailable: QKD post-processing "
                    "(sifting, error correction, privacy amplification) needs the RF link; "
                    f"RF available {rf_available_s:.0f} s of {duration_s:.0f} s"),
            )

        # Classical session establishment (uses pass geometry midpoint)
        mid = pass_start + timedelta(seconds=duration_s / 2)
        mid_geom = self._prop.station_geometry(mid, self._station)
        mid_rf = rf_link_budget(mid_geom['range_m'], rf_cfg)
        summaries = [
            classical_key_establishment(
                link_available=mid_rf['available'],
                snr_db=mid_rf['snr_db'],
                range_m=mid_geom['range_m'],
                contact_duration_s=duration_s,
                cfg=session_cfg,
                capacity_bps=mid_rf['shannon_capacity_bps'],
            )
            for session_cfg in (self._cfg.classical_session, self._cfg.pqc_session)
        ]

        return samples, finite_pass, summaries[0], summaries[1]

    def _config_summary(self) -> dict:
        return {
            "rf": {
                "tx_power_dbm": self._cfg.rf.tx_power_dbm,
                "rx_antenna_gain_dbi": self._cfg.rf.rx_antenna_gain_dbi,
                "frequency_hz": self._cfg.rf.frequency_hz,
                "bandwidth_hz": self._cfg.rf.bandwidth_hz,
            },
            "optical": {
                "source_rate_hz": self._cfg.optical.source_rate_hz,
                "rx_aperture_m": self._cfg.optical.rx_aperture_m,
                "beam_divergence_half_angle_rad": self._cfg.optical.beam_divergence_half_angle_rad,
                "mean_photon_number": self._cfg.optical.mean_photon_number,
                "timing_resolution_s": self._cfg.optical.timing_resolution_s,
            },
            "classical": {
                "pre_quantum": self._cfg.classical_session.key_exchange,
                "post_quantum": self._cfg.pqc_session.key_exchange,
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
                "qkd_intercept_resend_fraction": self._scenario.qkd_intercept_resend_fraction,
            },
        }


def _h2(p: float) -> float:
    if p <= 0.0 or p >= 1.0:
        return 0.0
    return -(p * math.log2(p) + (1.0 - p) * math.log2(1.0 - p))


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

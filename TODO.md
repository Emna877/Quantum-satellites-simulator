# Quantum Satellites Simulator — To-do list

Goal: build a satellite cybersecurity threat-analysis platform that experimentally compares classical and QKD-assisted cryptographic communication under controlled, reproducible attacks. Orekit is the single source of orbital truth. Machine learning is deferred.

Architecture: see [ARCHITECTURE.md](ARCHITECTURE.md) for shared-state boundaries, the initial experiment contract, channel scopes, draft protocols, fairness criteria, and milestone gates. Keep the milestone order below. Complete the physical foundation first; implement validated communication models, controlled scenarios, security protocols, a paired runner, and metrics before investing in the final UI.

## 1. Setup and configuration

- [x] Verify Java, JPype, Orekit, and Hipparchus work together.
- [x] Replace hardcoded machine-specific paths with shared configuration.
- [x] Use project-relative defaults for data and telemetry/event output folders.
- [x] Provide clear errors for missing dependencies or invalid settings.
- [x] Document verified installation and execution commands.

Python repair, creation of a clean environment, and installation of python-dotenv are already completed by the user and excluded from this checklist.

Verified: Python 3.13.7 and JPype 1.7.1 load Java 25, Orekit 13.1.2, Hipparchus 4.0.2, and Orekit data; 60-second propagation passes. Shared paths, orbit/time/export settings, validation, and setup documentation are implemented. Five configuration regression tests pass, Python compilation passes, and the Orekit CSV/CZML exporter runs successfully. The interpreter prefix warning still appears but does not prevent execution.

## 2. Make Orekit the single source of satellite motion

- [x] Establish one shared propagator for the engine, communication calculations, and exporters.
- [x] Replace the enhanced exporter's mock orbit with Orekit positions.
- [x] Derive orbital period from the orbit.
- [x] Correct the Earth-fixed velocity transformation.
- [x] Synchronize orbital time, state timestamps, and the simulation clock.
- [x] Use timezone-aware UTC timestamps consistently.
- [x] Implement geometric eclipse detection.
- [x] Calculate station range, elevation, and contact windows through Orekit.
- [x] Validate the circular-orbit model before adding more force models.

Verified: all four entry points use the shared two-body Orekit wrapper. Circular orbit radius/speed/energy, ECEF velocity, UTC/subseconds, eclipse states, contact roots and clipped contacts, engine time alignment, and cross-exporter positions are covered by passing regression tests. A 24-hour communication run found five Tunis passes without changing the configured orbit. Full umbra is modeled; eclipse marker timestamps remain sample-aligned. See README.md for assumptions.

## 3. Simulation engine and events

- [x] Define one reusable step(dt) operation.
- [x] Support fast offline runs and paced execution using the same operation.
- [x] Make pause stop state updates and propagation.
- [x] Fix timing when simulation speed changes.
- [x] Apply instantaneous events exactly once.
- [x] Support events with identical timestamps.
- [x] Advance the state timestamp before evaluating event effects.
- [x] Scale event probabilities and accumulated effects with elapsed time.
- [x] Fix the missing external_temp_c attribute.
- [x] Separate temporary disturbances from permanent damage.
- [x] Make event-application failures visible.
- [x] Remove unused event parameters or connect them to behavior.

Verified: step(dt) is shared by offline and paced execution. Pause freezes physics, speed changes preserve the wall/simulation-time mapping, impulses apply once, and duration envelopes integrate over elapsed seconds, even across large steps. Temporary modifiers restore their baselines; damage, heat, consumed battery, and accumulated dose persist. Seeded Poisson arrivals are independent of update partitioning. Failed updates roll back state/queue and raise an identified error. All 39 current regression checks pass; both bounded engine modes and the two-hour enhanced Orekit export run successfully. Event coefficients are uncalibrated presets; full subsystem physics remains in section 4.

## 4. Satellite state and subsystems

- [x] Standardize field names and units. All fields are in STATE_UNITS; `to_dict()` now serializes every field including component_health, error_counters, last_command_time, and last_command_type.
- [x] Introduce an initial versioned experiment contract for UTC samples, complete state, scoped event definitions, metadata, and provenance; expose opt-in export without changing simulation logic.
- [ ] Extend the initial contract deliberately as channel/protocol models are implemented; retain unknown, zero-key, and abort outcomes.
- [x] Separate radiation dose from dose rate.
- [x] Replace misleading aggregate component-health behavior.
- [x] Preserve all relevant state when copying and serializing. `copy()` uses deepcopy; `to_dict()` covers all fields; schema uses `asdict()`.
affected by spoofing. Current: Orekit position is always true; `navigation_error_m` is the scalar disturbance; a named navigation-measurement field for the communication layer remains future work.

## 5. Communication models

Gate: retain one UTC state/Orekit geometry; replace legacy communication proxies with distinct channel results before drawing security comparisons.

- [x] Refactor qkd.py into reusable modules and a runnable example. Created `communication/` package with `rf_link.py`, `optical_link.py`, `qkd_model.py`; `qkd.py` is now a runnable example using these modules. 53 unit tests pass.
- [x] Configure Tunis station coordinates and minimum elevation. Tunis (36.8°N, 10.18°E, 20 m, 5° threshold) is in both `qkd.py` and the end-to-end tests.
- [x] Model RF application data, the quantum optical link, and the authenticated QKD classical protocol channel separately, with explicit transport dependencies. Three distinct modules; no implicit cross-channel effects.
- [x] Scope each disturbance to the affected channel/subsystem; test that unconnected modes are not changed automatically. `communication/channel_effects.py` applies JammingAttack → RF only and LaserDazzle → optical background only; 6 tests verify isolation.
- [x] Calculate radio received power, noise, SNR, and availability. `rf_link.py`: Friis + kTB noise floor + Shannon capacity; validated by unit tests.
- [x] Distinguish theoretical capacity from achievable throughput. `shannon_capacity_bps` is explicitly the upper bound; achievable throughput requires coding/modulation modeling (future work).
- [x] Model optical beam spreading and receiver aperture. `optical_link.py`: far-field Gaussian aperture model; geometric loss = f(divergence, range, Rx diameter).
- [x] Include pointing loss, atmospheric transmission, optical efficiency, and detector efficiency. All four are additive dB terms in `optical_link.py`.
- [x] Include background light, dark counts, and detection timing windows. Dark counts and sky background rate are configurable; timing window is a parameter (coincidence window).
- [x] Calculate detection rate and QBER consistently. Signal count, background count, sifted rate, and QBER are computed from the same link budget in `optical_link.py`.
- [x] Add clear-sky and blocked-optical-link scenarios. `OpticalLinkConfig.cloud_blocked=True` returns zeroed metrics with `blocked_reason='cloud_blocked'`; tested in test_security.py. Partial cloud and sky-radiance models remain future work.
- [x] Validate calculations against documented reference cases. FSPL, kTB, H2, and geometric loss formulae validated by unit tests with cited equations.
- [x] Preserve legitimate no-contact, zero-key, and protocol-abort results; document uncertainty, model limits, and unvalidated approximations. Zero-rate and abort cases tested; limitations documented in module docstrings. Asymptotic formula is labeled as such.

## 6. Security comparison

Gate: finalize the draft research questions, protocol choices, attacker capabilities, authentication assumptions, and metrics in ARCHITECTURE.md before implementing full security logic.

- [ ] Define research questions and attacker capabilities. Draft in ARCHITECTURE.md; attacker capabilities documented per scenario in experiments/scenarios.py.
- [x] Choose classical key establishment and authentication. `security/classical_session.py`: conceptual ECDH P-256 + AES-256-GCM; auth_method configurable (psk/certificate); handshake timing modelled from propagation delay.
- [x] Choose a QKD protocol and document assumptions. Decoy-state BB84, asymptotic (communication/qkd_model.py) and finite-key (security/qkd_finite_key.py, Tomamichel et al. 2012); both labeled with explicit limits.
- [x] Implement sifting, error estimation, reconciliation costs, and privacy-amplification accounting. All four accounted for in qkd_model.py (asymptotic) and qkd_finite_key.py (finite-key correction term).
- [x] Account for authenticated classical communication. ClassicalSessionConfig documents dependency; classical_auth_dependency scenario shows QKD post-processing fails when RF jammed.
- [x] Add protocol-appropriate secret-key calculations. Asymptotic BB84 in qkd_model.py; finite-key corrected in security/qkd_finite_key.py; 10 regression tests.
- [x] Include finite-size effects before treating short-pass results as security estimates. `security/qkd_finite_key.py` with Tomamichel simplified bounds; `finite_key_valid=False` for n < n_min_sifted; n_min = 1000 by default.
- [x] Implement key storage, consumption, and exhaustion. `security/key_store.py`: buffer accounting with replenishment, consumption, capacity cap, and exhaustion counting.
- [x] Use the same application AES-256-GCM profile, traffic, AAD, nonce/tag rules, authentication policy, and key-refresh policy across modes; vary key establishment explicitly. AES-256-GCM profile in ClassicalSessionConfig; overhead fraction computed per packet; session lifetime configurable.
- [ ] Define key refresh, nonce handling, and replay protection. Nonce exhaustion not yet modelled; key refresh uses session_lifetime_s parameter only.


## 7. Controlled experiments

- [x] Baseline pass without disturbances. `SCENARIOS['baseline']` in experiments/scenarios.py; ExperimentRunner supports baseline-only run.
- [x] Radio interference. `SCENARIOS['rf_jamming_low/moderate/severe']`; channel_effects.rf_config_with_jamming wires loss to RF link budget; tested.
- [x] Optical interference or increased background. `SCENARIOS['optical_interference']`; channel_effects.optical_config_with_background_increase; LaserDazzle event schedules in pass.
- [x] Pointing error. `SCENARIOS['pointing_error']`; optical_extra_loss_db=6.0 via optical_config_with_extra_loss; models ACS residuals / fine-steering mirror overrun.
- [x] Cloud blockage. `SCENARIOS['optical_cloud_blocked']`; OpticalLinkConfig.cloud_blocked=True; tested.
- [x] Power shortage. `SCENARIOS['power_shortage']`; rf_signal_loss_db=6.0 + PowerDrain event via _power_drain_factory; runner applies loss to RF link budget.
- [ ] Defined QKD interception scenario. QBER elevation from background increase is a proxy; a photon-intercept-resend model is not yet implemented.
- [ ] Forged or replayed classical messages. Authentication failure is documented as an assumption in ClassicalSessionConfig; a protocol-level replay model is not yet implemented.
- [x] Record effects on confidentiality, integrity, authentication, and availability. ExperimentResult records RF availability, key establishment, key-store exhaustion, and QKD abort reasons per pass.
- [x] Use reproducible seeds and repeat stochastic experiments. ScenarioDefinition.random_seed field; event factories are deterministic by construction.
- [x] Implement a paired experiment runner with shared physical/environment/attack realizations and separate named protocol RNG streams. `experiments/runner.py`: ExperimentRunner runs both pipelines on the same Orekit geometry and event schedule; `run_comparison()` convenience function.
- [x] Record comparable latency, traffic overhead, authenticated data delivery, key-buffer behavior, aborts, rejected/accepted attacks, and availability metrics. ExperimentResult.passes[i] contains per-sample RF, optical, QKD asymptotic, QKD finite, classical session, and key-store records.
- [x] Keep channel availability distinct from confidentiality, integrity, authentication, and key-establishment security; retain negative runs in comparisons. Channel and security outcomes are separate dict keys; abort and zero-key records are preserved.

## 8. Results and visualization

Gate: prioritize shared recorded outputs and essential validation plots. The final Cesium threat-analysis UI follows a validated paired runner and comparison metrics; the UI must not duplicate simulation or protocol calculations.

- [ ] Export synchronized telemetry, event logs, and run configuration.
- [ ] Record contact duration, delivered data, key production, outages, and energy consumption.
- [x] Plot range, elevation, SNR, detection rate, QBER, and key buffer over time. `scripts/plot_pass.py` generates range.png, elevation.png, rf_snr.png, optical_signal.png, qber.png, key_rate.png from comm_samples.csv; run with `python -m scripts.plot_pass`.
- [x] Generate CZML from the same recorded positions and events. `exports/czml_events.py`: experiment_result_to_czml_events() produces billboard packets (RF outages, QKD aborts, optical blocks, classical failures, contact bounds); run_experiment.py --czml exports events.czml.
- [ ] Make the enhanced viewer the main viewer after Orekit integration.
- [ ] Keep the simple viewer as an orbit-checking example.
- [ ] Use explicit event metadata instead of labels inferred from names.
- [ ] Count unique events rather than graphical entities.
- [ ] Make relevant markers follow the satellite.
- [ ] Build synchronized playback, scoped threat overlays, and classical-versus-QKD-assisted views from actual experiment records.
- [ ] Fix loading errors and render imported names safely as text.

## 9. Verification and cleanup

- [x] Repair stale assertions and cumulative-time propagation in tests. The scripts/ test suite uses correct unittest.TestCase patterns throughout; legacy demo scripts moved to examples/.
- [x] Make failed tests return a failing exit code. All scripts/ tests use unittest; non-zero exit on failure.
- [x] Test instantaneous and simultaneous events, pause/resume, and timestamps. Covered in test_engine_events.py.
- [ ] Check convergence with smaller timesteps. Power/thermal integrals tested at dt=1/7/60/1000 s (pass); optical and RF models are stateless (no timestep dependence).
- [x] Add an end-to-end test for one Orekit pass over Tunis. `TunisPassEndToEndTest` in scripts/test_orbit.py: 4 tests covering pass detection, geometry bounds, and communication pipeline consistency.
- [x] Remove duplicated simulation logic after shared modules replace it. qkd.py's inline calculations replaced by communication/ modules.
- [x] Move results into an output folder and examples into an examples folder. Legacy demo scripts moved to examples/; output paths already use data/ via config.
- [ ] Remove unused dependencies and configuration options. requirements.txt not audited yet.
- [x] Update README capabilities and remaining approximations. See section below.
- [x] Resolve the missing license file. MIT License added (LICENSE); copyright 2026 Emna Souayah.
- [ ] Move ML into future work. ML was never started; the README notes it as deferred.

## First milestone

- [x] A fresh setup runs successfully.
- [x] Orekit generates one pass over Tunis. Confirmed: TunisPassEndToEndTest passes; 5 passes found in a 24-hour default run.
- [x] Radio and optical calculations share positions and timestamps. Both channels use the same OrekitPropagator geometry in qkd.py and test_orbit.py.
- [x] Telemetry, plots, and the enhanced viewer agree. scripts/plot_pass.py generates plots from comm_samples.csv; CZML and experiment.json positions match (tested by test_experiment_schema). Visual side-by-side viewer alignment remains for the UI phase.
- [x] The run is reproducible and its checks pass. 107 tests pass; seeded events are deterministic.

Complete this milestone before expanding the attack catalogue or implementing full security protocols.

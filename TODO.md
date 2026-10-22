# Quantum Satellites Simulator — To-do list

Goal: compare classical and QKD-assisted satellite communication security using one Orekit simulation. Machine learning is deferred.

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

- [ ] Standardize field names and units.
- [x] Separate radiation dose from dose rate.
- [x] Replace misleading aggregate component-health behavior.
- [ ] Preserve all relevant state when copying and serializing.
- [ ] Add a battery energy model.
- [ ] Add a basic thermal model.
- [ ] Define equipment operating limits and shutdown behavior.
- [ ] Separate true position from navigation measurements affected by spoofing.

## 5. Communication models

- [ ] Refactor qkd.py into reusable modules and a runnable example.
- [ ] Configure Tunis station coordinates and minimum elevation.
- [ ] Calculate radio received power, noise, SNR, and availability.
- [ ] Distinguish theoretical capacity from achievable throughput.
- [ ] Model optical beam spreading and receiver aperture.
- [ ] Include pointing loss, atmospheric transmission, optical efficiency, and detector efficiency.
- [ ] Include background light, dark counts, and detection timing windows.
- [ ] Calculate detection rate and QBER consistently.
- [ ] Add clear-sky and blocked-optical-link scenarios.
- [ ] Validate calculations against documented reference cases.

## 6. Security comparison

- [ ] Define research questions and attacker capabilities.
- [ ] Choose classical key establishment and authentication.
- [ ] Choose a QKD protocol and document assumptions.
- [ ] Implement sifting, error estimation, reconciliation costs, and privacy-amplification accounting.
- [ ] Account for authenticated classical communication.
- [ ] Add protocol-appropriate secret-key calculations.
- [ ] Include finite-size effects before treating short-pass results as security estimates.
- [ ] Add decoy-state modeling if using weak laser pulses.
- [ ] Implement key storage, consumption, and exhaustion.
- [ ] Use consistent data encryption and authentication across modes.
- [ ] Define key refresh, nonce handling, and replay protection.
- [ ] Add post-quantum cryptography as a separate option after the baseline works.

## 7. Controlled experiments

- [ ] Baseline pass without disturbances.
- [ ] Radio interference.
- [ ] Optical interference or increased background.
- [ ] Pointing error.
- [ ] Cloud blockage.
- [ ] Power shortage.
- [ ] Defined QKD interception scenario.
- [ ] Forged or replayed classical messages.
- [ ] Record effects on confidentiality, integrity, authentication, and availability.
- [ ] Use reproducible seeds and repeat stochastic experiments.

## 8. Results and visualization

- [ ] Export synchronized telemetry, event logs, and run configuration.
- [ ] Record contact duration, delivered data, key production, outages, and energy consumption.
- [ ] Plot range, elevation, SNR, detection rate, QBER, and key buffer over time.
- [ ] Generate CZML from the same recorded positions and events.
- [ ] Make the enhanced viewer the main viewer after Orekit integration.
- [ ] Keep the simple viewer as an orbit-checking example.
- [ ] Use explicit event metadata instead of labels inferred from names.
- [ ] Count unique events rather than graphical entities.
- [ ] Make relevant markers follow the satellite.
- [ ] Fix loading errors and render imported names safely as text.

## 9. Verification and cleanup

- [ ] Repair stale assertions and cumulative-time propagation in tests.
- [ ] Make failed tests return a failing exit code.
- [ ] Test instantaneous and simultaneous events, pause/resume, and timestamps.
- [ ] Check convergence with smaller timesteps.
- [ ] Add an end-to-end test for one Orekit pass over Tunis.
- [ ] Remove duplicated simulation logic after shared modules replace it.
- [ ] Move results into an output folder and examples into an examples folder.
- [ ] Remove unused dependencies and configuration options.
- [ ] Update README capabilities and remaining approximations.
- [ ] Resolve the missing license file.
- [ ] Move ML into future work.

## First milestone

- [ ] A fresh setup runs successfully.
- [ ] Orekit generates one pass over Tunis.
- [ ] Radio and optical calculations share positions and timestamps.
- [ ] Telemetry, plots, and the enhanced viewer agree.
- [ ] The run is reproducible and its checks pass.

Complete this milestone before expanding the attack catalogue or implementing full security protocols.

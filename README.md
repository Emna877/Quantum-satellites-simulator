# Quantum Satellites Simulator

Orekit-based satellite motion with experimental radio/QKD link calculations and Cesium visualization. The long-term goal is a reproducible satellite cybersecurity threat-analysis platform comparing classical and QKD-assisted cryptographic communication under controlled attacks. Encryption, full QKD protocols, and unified subsystem/event physics remain future work. Machine learning is deferred; see [TODO.md](TODO.md).

## Setup

Use Python 3.10+ with a compatible 64-bit Java installation (Java 9+ is required by the installed JPype; Java 25 is verified here). From the project root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If the environment already works, activate it without recreating it. Keep Orekit 13.1.2 and the matching Hipparchus 4.0.2 JAR files in the project root, with the extracted data in `orekit-data/orekit-data-main`. The repository's scientific-data bundle is separate from the JAR files.

## Configuration

Defaults work from the repository location. Optionally copy `.env.template` to `.env` and edit it. Existing process environment variables override `.env`. Relative paths are resolved against PROJECT_DIR; a relative PROJECT_DIR is resolved against the repository root. No system Java or Python settings are changed by the project.

JVM selection order:

1. Explicit JVM_PATH: the JVM shared library, not java.exe.
2. JAVA_HOME: the selected Java installation directory.
3. Automatic discovery: compatible Java installations on PATH, standard Windows installation folders, and JPype's default.

Automatic discovery selects the highest detected compatible version. An explicit Java 8 override is rejected with a clear error instead of silently ignored. On Windows, JPype's registry default can point to Java 8 even when `java -version` reports Java 25. To select Java explicitly in `.env`:

```text
JVM_PATH=C:/Program Files/Java/jdk-25/bin/server/jvm.dll
```

Shared settings include SIM_START_TIME (UTC), SIM_TIME_STEP, SIM_SPEED_MULTIPLIER, orbital elements, CZML_DEFAULT_DURATION_SECONDS, CZML_STEP_SECONDS, and output paths. The engine and Orekit scripts use the same runtime path configuration. The engine, both exporters, and communication example use the same OrekitPropagator and orbital elements. The communication example preserves the configured orbit and epoch; no visible pass is a valid result. To examine a full day, set CZML_DEFAULT_DURATION_SECONDS=86400 before running qkd.py.

## Verify compatibility

```powershell
python -m scripts.check_runtime
python -m unittest scripts.test_runtime_config scripts.test_orbit scripts.test_engine_events
```

The checker prints the selected JVM, loads the 11 bundled JAR files and Orekit data, propagates a satellite for 60 seconds, and exits with code 0 and PASS on success. It runs in its own process because JPype cannot restart a stopped JVM in the same Python process.

Verified in this workspace: Python 3.13.7, JPype 1.7.1, Java 25, Orekit 13.1.2, Hipparchus 4.0.2, configuration regression checks, and the Orekit orbit export. Python currently prints `Could not find platform independent libraries <prefix>` but continues successfully; that interpreter warning is independent of Java selection. Java 25 may also print a native-access warning from JPype.

## Run the Orekit orbit and viewer

```powershell
python export_czml.py
python -m http.server 8000
```

Open http://localhost:8000/czml_viewer.html. The export writes `cubesat.czml` and `orbit_positions.csv`. Both can be redirected with ORBIT_CZML_FILE and ORBIT_CSV_FILE; if the CZML filename changes, update the simple viewer's load URL too. Output parent directories are created automatically. Cesium and map imagery require internet access.

Run the engine with `python -m simulation.engine`; stop it with Ctrl+C. Its full battery, thermal, and operating-limit models remain in TODO section 4. `python qkd.py` runs the separate experimental link calculation; it is not yet a complete security comparison.

## Enhanced event demonstration

```powershell
python export_czml_with_events.py --hours 6
```

Open http://localhost:8000/czml_viewer_enhanced.html. Both viewers now display Orekit orbital positions. The enhanced exporter adds manually scheduled demonstration attacks and sample-aligned eclipse transition markers. Event presets now run through the same engine step as paced execution; their numerical coefficients remain uncalibrated demonstration values. CLI duration overrides CZML_DURATION_HOURS, which overrides CZML_DEFAULT_DURATION_SECONDS. CZML_STEP_SECONDS sets sampling; the exact run endpoint is always included. Orbit period is derived from the orbital elements (about 98.773 minutes at the default 700 km altitude). The obsolete --orbit-minutes and ORBIT_PERIOD_MINUTES settings are rejected; remove them and configure orbital elements instead.

The enhanced viewer defaults to `cubesat_with_events.czml`; use Load CZML for custom output files. Space toggles playback, R resets the view, and arrow keys adjust speed.

## Layout

- `config/`: environment loading, paths, validation, Java discovery.
- `simulation/`: state, clock, Orekit wrapper, engine.
- `events/`: environmental and attack event prototypes.
- `qkd.py`: separate visibility, RF, and approximate optical/QKD calculations.
- `export_czml.py`: Orekit orbit export.
- `export_czml_with_events.py`: Orekit orbit with demonstration event markers.
- `scripts/check_runtime.py`: runtime smoke check.
- `scripts/test_runtime_config.py`: configuration regression checks.
- `scripts/test_orbit.py`: orbital invariants, ECEF velocity, UTC, eclipse, contact, engine, and exporter regression checks.

The legacy phase tests have known issues tracked in TODO.md. A license has not yet been selected/provided; resolving this is also tracked there.

## Orbital model and verification

The shared baseline is an analytical two-body Keplerian orbit. J2, atmospheric drag,
solar radiation pressure, and other force models are deliberately not enabled yet.
ECEF position and velocity are requested together from Orekit in ITRF, including the
Earth rotation contribution to velocity. Absolute-time queries do not advance the
incremental cursor. Dates are normalized to UTC (legacy naive dates are interpreted
as UTC), and fractional seconds are preserved.

Eclipse state uses Orekit EclipseDetector with solar ephemerides and the Earth
ellipsoid, classifying full umbra. Partial shadow is not yet a fractional solar-power
model. Displayed eclipse transitions are sampled, with timing accuracy limited by
CZML_STEP_SECONDS. Station visibility uses TopocentricFrame and root-found
ElevationDetector crossings at the configured threshold (currently 5 degrees in
qkd.py), including contact already underway at the start or end of a run. Detection
uses a 30-second maximum check interval and 1-microsecond root tolerance; this is
not a guarantee of physical accuracy or detection of arbitrarily short grazing passes.

Orbital validation: regression checks pass, including matching positions between both
exporters and correct final samples for a 65-second run sampled every 30 seconds.
A 24-hour run from the default epoch produced five Tunis contacts above 5 degrees.
The current approximate QKD model still produces zero secret keys in that scenario;
communication-model corrections remain in TODO section 5.

## Engine and event lifecycle

```powershell
# Fast bounded run (no wall-clock pacing)
python -m simulation.engine --offline --seconds 3600

# Paced bounded run (SIM_SPEED_MULTIPLIER controls playback speed)
python -m simulation.engine --seconds 60

# Current regression suite
python -m unittest scripts.test_runtime_config scripts.test_orbit scripts.test_engine_events
```

Programmatic entry points are `engine.setup()`, `engine.step(dt)`,
`engine.run_offline(duration, time_step=None)` (independent snapshots including the
initial and exact final state), and `await engine.run(duration=None, paced=True)`.
Call `await engine.shutdown()` after a programmatic offline run. The asynchronous
run closes its JVM owner in a finally block, including on errors. JPype does not
support restarting that JVM in the same process, so start a new process for a new
standalone run after shutdown.

`engine.clock.pause()`, `.resume()`, and `.set_speed(multiplier)` control paced
execution. Paused steps do not propagate, apply events, or advance time. The clock
uses monotonic wall time and anchors speed changes to the current expected simulated
time; waits reevaluate controls every 50 ms. Offline execution uses the same physical
step and does not sleep. Run durations and steps must advance datetime's microsecond
resolution.

EventManager takes one persistent state object. `update(timestamp, state, dt_seconds)`
processes the interval since its previous update; an initial call without dt is an
observation with no elapsed time. Equal timestamps do not integrate twice. Instant
impulses, including impacts and eclipse transitions, execute exactly once through the
manager. Duration effects use an exactly integrated linear decay envelope. Events
that start and finish between observations still contribute their accumulated effects.
An impulse at an interior boundary is applied in chronological order.

Temporary effects (radio loss, throughput reduction, navigation error, sensor noise,
extra power demand, drag coefficient) combine at each endpoint and restore their
baselines after expiry. Call `clear_modifiers(state)` before replacing subsystem
baselines; the engine does this before computing each new orbital state. Damage,
battery consumption, heating, command activity, and dose increments persist. Eclipse
state temporarily gates solar current to zero; geometric shadow transitions remain
sample-aligned rather than root-found in the engine.

Random rates are events per simulated day. EventConfig validates nonnegative finite
rates and a normalized severity distribution; `random_seed` defaults to 0. The
manager uses exponential waiting times for a Poisson arrival stream, so it supports
multiple arrivals within a step and reproduces arrival logs across step partitions.
Manually constructed event IDs are unique UUIDs unless supplied by the caller.
Duplicate IDs and scheduling before the last processed time are rejected.

Event application failures raise EventApplicationError with event identity and
preserve the original exception. State, queue, RNG, and history roll back. Failure
diagnostics remain in `manager.failures`; the engine also leaves its clock and orbital
cursor unchanged when a step fails. Statistics count scheduled events separately from
executed history. Exceptions are not converted into successful process exits.

### Model limits and state changes

Event coefficients are deterministic, configurable demonstration presets, not
validated attack likelihoods or spacecraft physics. Parameter names and units are
explicit in `events/attacks.py` and `events/environmental.py`; unknown parameters
are rejected. Old unused parameters, random per-call damage, synthetic periodic
eclipse rates, and the approximate eclipse scheduler have been removed. Use Orekit
shadow transitions instead of `schedule_eclipse_events`.

Radiation dose is accumulated mGy, and `radiation_rate_mgy_s` (also exposed by the
compatibility name `radiation_dose_rate`) is mGy/s. Aggregate health is a continuous
percentage budget, independent of the component status dictionary; detailed failure
thresholds remain future work. Navigation disturbances change reported error/time
uncertainty without moving the true Orekit position. State copies are deep copies.

Power-drain events account for extra energy using a 20 Wh battery-capacity preset;
this is not a complete charge/discharge model. Thermal events integrate a specified
excursion; there is no radiative heat balance or recovery controller yet. Drag spikes
change the recorded drag coefficient; the shared two-body orbit does not decay.
These limitations belong to subsystem/force modeling, not event scheduling.

The 39 current regression checks cover timestep invariance, all 12 event types,
expiry/recovery, simultaneous impulses, Poisson reproducibility, state snapshots,
transaction rollback, pause/speed timing, offline/paced agreement, and the existing
Orekit and export checks. The legacy `test_phase*.py` scripts still contain obsolete
assumptions and require the cleanup tracked in TODO section 9.

## Experiment architecture and records

See [ARCHITECTURE.md](ARCHITECTURE.md) for the shared-state design, explicit channel
boundaries, draft protocol choices, fairness rules, model assumptions, and milestone
gates. The TODO order is unchanged. Complete the physical milestone, validated
communication models, protocols/scenarios, paired runner, and metrics before the
final interface. Subsystem detail must support a named experiment.

Both exporters support an optional record alongside their normal CSV/CZML output:

```powershell
python export_czml.py --experiment-dir data/experiments/orbit
python export_czml_with_events.py --hours 2 --experiment-dir data/experiments/events
python -m unittest scripts.test_experiment_schema scripts.test_runtime_config scripts.test_orbit scripts.test_engine_events
```

Each directory receives `experiment.json` (schema 1.0) from the actual recorded
snapshots. It contains full UTC state, ITRF frames, units, effective configuration,
scoped event definitions and parameter units, source/JAR/data fingerprints, software
provenance, and separate RF/quantum-optical/QKD-classical channel slots. The optional
export does not recompute physics or change simulation behavior. Existing viewer
commands continue to work.

These are physical-baseline records: channel results are null and security is not
evaluated. AES-256-GCM is recorded as a planned common application profile, not an
implemented encryption feature. Zero-key and explicit abort results are valid future
records and must not be replaced with successful outcomes. Current generic RF/event
proxies are not yet the three distinct communication models; that work remains in
section 5. The event scope metadata describes current surrogate effects rather than
claiming that every attack affects every channel.

`experiments.schema.validate_experiment` checks the contract;
`event_from_definition` reconstructs supported event presets without arbitrary class
loading. Preserve the input assets matching recorded hashes when retaining an
experiment. Do not include cryptographic secrets in future configuration records.

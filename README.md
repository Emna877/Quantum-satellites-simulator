# Quantum Satellites Simulator

Orekit-based satellite motion with experimental radio/QKD link calculations and Cesium visualization. The intended comparison is classical versus QKD-assisted communication security. Encryption, full QKD protocols, and a unified communication pipeline remain future work. Machine learning is deferred; see [TODO.md](TODO.md).

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

Shared settings include SIM_START_TIME (UTC), SIM_TIME_STEP, SIM_SPEED_MULTIPLIER, orbital elements, CZML_DEFAULT_DURATION_SECONDS, CZML_STEP_SECONDS, and output paths. The engine and Orekit scripts use the same runtime path configuration. The exporter and communication example now read common orbital elements and start time; the communication example still searches for a visible pass and may adjust its example orbit/epoch.

## Verify compatibility

```powershell
python -m scripts.check_runtime
python -m unittest scripts.test_runtime_config
```

The checker prints the selected JVM, loads the 11 bundled JAR files and Orekit data, propagates a satellite for 60 seconds, and exits with code 0 and PASS on success. It runs in its own process because JPype cannot restart a stopped JVM in the same Python process.

Verified in this workspace: Python 3.13.7, JPype 1.7.1, Java 25, Orekit 13.1.2, Hipparchus 4.0.2, configuration regression checks, and the Orekit orbit export. Python currently prints `Could not find platform independent libraries <prefix>` but continues successfully; that interpreter warning is independent of Java selection. Java 25 may also print a native-access warning from JPype.

## Run the Orekit orbit and viewer

```powershell
python export_czml.py
python -m http.server 8000
```

Open http://localhost:8000/czml_viewer.html. The export writes `cubesat.czml` and `orbit_positions.csv`. Both can be redirected with ORBIT_CZML_FILE and ORBIT_CSV_FILE; if the CZML filename changes, update the simple viewer's load URL too. Output parent directories are created automatically. Cesium and map imagery require internet access.

Run the engine with `python -m simulation.engine`; stop it with Ctrl+C. Its event and subsystem correctness work is tracked in TODO sections 2-4. `python qkd.py` runs the separate experimental link calculation; it is not yet a complete security comparison.

## Enhanced event demonstration

```powershell
python export_czml_with_events.py --hours 6
```

Open http://localhost:8000/czml_viewer_enhanced.html. This exporter still uses mock orbital positions and manually scheduled demonstration events. It must be connected to Orekit before use as the scientific simulation. CLI duration overrides CZML_DURATION_HOURS, which overrides CZML_DEFAULT_DURATION_SECONDS. CZML_STEP_SECONDS sets sampling. The demo-only orbit period can be set with --orbit-minutes or ORBIT_PERIOD_MINUTES; physical Orekit orbits derive their period from their elements.

The enhanced viewer defaults to `cubesat_with_events.czml`; use Load CZML for custom output files. Space toggles playback, R resets the view, and arrow keys adjust speed.

## Layout

- `config/`: environment loading, paths, validation, Java discovery.
- `simulation/`: state, clock, Orekit wrapper, engine.
- `events/`: environmental and attack event prototypes.
- `qkd.py`: separate visibility, RF, and approximate optical/QKD calculations.
- `export_czml.py`: Orekit orbit export.
- `export_czml_with_events.py`: event visualization demo.
- `scripts/check_runtime.py`: runtime smoke check.
- `scripts/test_runtime_config.py`: configuration regression checks.

The legacy phase tests have known issues tracked in TODO.md. A license has not yet been selected/provided; resolving this is also tracked there.

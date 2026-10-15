# Quantum Satellite Simulator

A real-time satellite simulation with event system and 3D visualization for quantum key distribution (QKD) satellites.

## Runtime setup and compatibility check

Configuration is shared by the engine, the Orekit exporter, and the communication example.
Copy `.env.template` to `.env` only if you need overrides. Existing environment variables
have precedence. Relative paths are resolved against the project directory, not your terminal directory.
The default Orekit data folder is `orekit-data/orekit-data-main`. Keep the bundled Orekit
13.1.2 and Hipparchus 4.0.2 JARs together in the project root. Java is discovered by JPype;
set `JAVA_HOME` or explicitly set `JVM_PATH` to the JVM shared library if discovery fails.

From the project root, using your working Python environment:

```powershell
python -m scripts.check_runtime
python export_czml.py
python -m http.server 8000
```

Open `http://localhost:8000/czml_viewer.html` for the Orekit orbit export.
Run `python qkd.py` for the separate communication calculation example.
The enhanced exporter still uses mock positions until checklist section 2 is completed.

Verification status: Java 25 was detected. The compatibility check has not passed in the
assistant session because its Python executable fails before imports with an `encodings`
startup error. Run the checker with the repaired Python environment; a successful run prints
`PASS` and exits with code 0. No installation or Python configuration was changed here.
See [TODO.md](TODO.md) for the full implementation checklist.
## 🚀 Quick Start

### 1. Setup Environment

```bash
# Create and activate virtual environment
python -m venv .venv_orekit
.venv_orekit\Scripts\Activate.ps1  # Windows PowerShell

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure (Optional)

Copy `.env.template` to `.env` and customize paths:
```bash
copy .env.template .env
```

### 3. Run Simulation

```bash
# Generate CZML with events
python export_czml_with_events.py

# Start web server
python -m http.server 8000

# Open browser to: http://localhost:8000/czml_viewer_enhanced.html
```

### Generating longer (continuous) CZML runs

You can control the duration and orbital period when generating CZML so the
satellite orbit appears continuous for many hours. The exporter accepts CLI
options and environment variables:

- `--hours <float>` : duration in hours for the generated CZML (overrides env)
- `--orbit-minutes <float>` : orbital period in minutes (default: 90)
- `CZML_DURATION_HOURS` : same as `--hours`, set via environment variable
- `ORBIT_PERIOD_MINUTES` : same as `--orbit-minutes`, set via environment
- `CZML_STEP_SECONDS` : sampling step in seconds (default: 30)

Examples (PowerShell):

```powershell
# Generate a 6-hour CZML with default 90-minute orbit
python export_czml_with_events.py --hours 6

# Generate a 12-hour CZML with a 60-minute orbit and 10s sampling
$env:ORBIT_PERIOD_MINUTES = "60"
$env:CZML_STEP_SECONDS = "10"
python export_czml_with_events.py --hours 12

# Or set duration via env var instead of CLI
$env:CZML_DURATION_HOURS = "4"
python export_czml_with_events.py
```

Notes:
- The exporter currently uses a simple circular orbit model for demo
	positions; for physically accurate propagation, integrate Orekit
	(`simulation/propagator.py`) into the exporter.
- Increasing `--hours` will increase the CZML `clock.interval` and produce
	a longer animation. Using `--orbit-minutes` makes the satellite complete
	repeated orbits over the entire duration so the motion appears continuous.

## 📊 Features

### Simulation Engine
- **Orbital Propagation**: Satellite position calculation
- **Real-time Event System**: 12 event types (6 environmental + 6 attacks)
- **State Management**: Complete satellite telemetry tracking
- **Ground Truth Labels**: Attack vs natural event classification

### Event Types

**Environmental (Natural)**
- ☀️ Solar Flare - Radiation dose increase
- 💥 Micrometeoroid Impact - Physical damage
- 🌑 Eclipse Entry/Exit - Power changes
- 🌪️ Atmospheric Drag - Altitude loss
- ⚡ Geomagnetic Storm - Navigation errors

**Attacks (Adversarial)**
- ⚠️ GPS Spoofing - False navigation signals
- 🔴 Laser Dazzle - Optical sensor blinding
- 📡 RF Jamming - Communication disruption
- 💉 Command Injection - Unauthorized commands
- 🔋 Power Drain - Battery depletion
- 🌡️ Thermal Sabotage - Temperature attacks

### 3D Visualization
- **Cesium-based viewer** with ArcGIS World Imagery
- **Real-time monitoring** - Telemetry panel with live updates
- **Event shapes** - 3D visual representations of events
- **Interactive controls** - Play/pause, speed adjustment, camera controls

## 📁 Project Structure

```
Quantum-satellites-simulator/
├── simulation/          # Core simulation engine
│   ├── engine.py       # Main simulation loop
│   ├── state.py        # Satellite state management
│   ├── propagator.py   # Orbital mechanics
│   └── clock.py        # Time management
├── events/             # Event system
│   ├── base.py        # Base event classes
│   ├── environmental.py # Natural events
│   ├── attacks.py      # Attack events
│   └── manager.py      # Event orchestration
├── export_czml_with_events.py  # CZML generator
├── czml_viewer_enhanced.html   # 3D visualization
└── test_phase2_simple.py       # Event system tests
```

## 🎮 Viewer Controls

### Keyboard Shortcuts
- **SPACE** - Play/Pause animation
- **R** - Reset camera to home view
- **↑** - Increase playback speed (2x)
- **↓** - Decrease playback speed (0.5x)

### Interface
- **Control Panel** (left side) - Telemetry and event monitoring
- **Timeline** (bottom) - Scrub through simulation time
- **Animation Controls** (bottom left) - Play/pause and speed
- **Base Layer Picker** (top right) - Change map imagery

## 🧪 Testing

```bash
# Run event system tests
python test_phase2_simple.py

# Expected: All 6 tests pass ✅
```

## 🔧 Configuration (.env)

```bash
# CZML Output
CZML_OUTPUT_FILE=cubesat_with_events.czml
CZML_VIEWER_FILE=czml_viewer_enhanced.html

# Simulation Parameters
ORBIT_ALTITUDE_KM=460
ORBIT_INCLINATION_DEG=51.6
CZML_DEFAULT_DURATION_SECONDS=3600

# Paths
PROJECT_DIR=D:\programming\python\Quantum-satellites-simulator
OREKIT_DATA_PATH=D:\programming\python\Quantum-satellites-simulator\orekit-data\orekit-data-main
```

## 📈 Next Steps: Machine Learning

The event system provides labeled training data for ML:
- **Feature Engineering**: Time series telemetry → ML features
- **Model**: LSTM/Transformer for anomaly detection
- **Training**: Supervised learning with ground truth labels (0=natural, 1=attack)
- **Inference**: Real-time attack vs natural classification

## 🛠️ Technologies

- **Python 3.10+** - Core language
- **Orekit** - Orbital mechanics (via JPype)
- **Cesium** - 3D globe visualization
- **CZML** - Time-dynamic visualization format
- **NumPy/SciPy** - Scientific computing
- **scikit-learn** - ML framework (future)

## 📄 License

MIT License - See LICENSE file for details

## 🤝 Contributing

1. Create feature branch
2. Make changes with tests
3. Submit pull request

---

**Status**: ✅ Phase 1 Complete | ✅ Phase 2 Complete | ⏳ Phase 3 ML (Pending)

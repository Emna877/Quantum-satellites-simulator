# Configuration Setup

## Environment Configuration with .env Files

The simulation now uses environment variables for configuration, making it easy to customize paths and settings without modifying code.

## Quick Start

### 1. Copy the template
```powershell
Copy-Item .env.template .env
```

### 2. Edit `.env` with your paths
Open `.env` and update these key settings:

```bash
# Your Java JDK path
JVM_PATH=C:\Program Files\Java\jdk-23\bin\server\jvm.dll

# Your project directory
PROJECT_DIR=D:\programming\python\Quantum-satellites-simulator

# Orekit data location
OREKIT_DATA_PATH=D:\programming\python\Quantum-satellites-simulator\orekit-data\orekit-data-main
```

### 3. Run the simulation
```powershell
python test_phase1.py
```

The configuration will be automatically loaded from `.env`!

## Configuration Options

### Paths
- **JVM_PATH**: Path to Java Virtual Machine DLL
- **PROJECT_DIR**: Absolute path to this repository
- **OREKIT_DATA_PATH**: Path to orekit-data directory

### Simulation Timing
- **SIM_START_TIME**: ISO 8601 timestamp (e.g., `2025-11-09T12:00:00Z`)
- **SIM_TIME_STEP**: Time step in seconds (default: `1.0`)
- **SIM_SPEED_MULTIPLIER**: Simulation speed multiplier (1.0 = real-time, 2.0 = 2x speed)

### Orbital Elements
- **ORBIT_ALTITUDE_KM**: Satellite altitude in kilometers (default: `700`)
- **ORBIT_ECCENTRICITY**: Orbital eccentricity, 0 = circular (default: `0.0`)
- **ORBIT_INCLINATION_DEG**: Inclination in degrees (default: `98.0` for sun-synchronous)
- **ORBIT_RAAN_DEG**: Right Ascension of Ascending Node in degrees
- **ORBIT_ARG_PERIGEE_DEG**: Argument of perigee in degrees
- **ORBIT_MEAN_ANOMALY_DEG**: Mean anomaly in degrees

### Logging (Phase 3+)
- **LOG_TELEMETRY**: Enable telemetry logging (`true`/`false`)
- **LOG_EVENTS**: Enable event logging (`true`/`false`)
- **TELEMETRY_FILE**: Path to telemetry CSV output
- **EVENTS_FILE**: Path to events JSON output

### Streaming (Phase 5+)
- **ENABLE_STREAMING**: Enable real-time WebSocket streaming (`true`/`false`)
- **WEBSOCKET_HOST**: WebSocket server host (default: `localhost`)
- **WEBSOCKET_PORT**: WebSocket server port (default: `8080`)

## Using Configuration in Code

### Load configuration
```python
from config import get_simulation_config

config = get_simulation_config()
```

### Print current configuration
```python
from config import print_config

config = get_simulation_config()
print_config(config)
```

### Access configuration values
```python
config = get_simulation_config()

jvm_path = config['jvm_path']
time_step = config['time_step']
altitude = (config['orbit']['semi_major_axis'] - 6378137) / 1000  # km
```

## Git Integration

The `.env` file is **gitignored** and won't be committed to version control. This keeps your local paths private.

### What's tracked:
- ✅ `.env.template` - Template with example values
- ✅ `.gitignore` - Ignores `.env` and virtual environments

### What's ignored:
- ❌ `.env` - Your local configuration
- ❌ `.venv_orekit/` - Virtual environment
- ❌ `*.csv`, `*.json` - Simulation outputs
- ❌ `__pycache__/` - Python cache files

## Finding Your JVM Path

### Windows
```powershell
# Find Java installation
where java

# JVM DLL is usually at:
# C:\Program Files\Java\jdk-XX\bin\server\jvm.dll
```

### Linux
```bash
# Find Java installation
which java
readlink -f $(which java)

# JVM shared library is usually at:
# /usr/lib/jvm/java-XX-openjdk/lib/server/libjvm.so
```

### macOS
```bash
# Find Java installation
/usr/libexec/java_home

# JVM library is usually at:
# /Library/Java/JavaVirtualMachines/jdkXX.jdk/Contents/Home/lib/server/libjvm.dylib
```

## Troubleshooting

### "Warning: .env file not found"
- Copy `.env.template` to `.env`
- Or: create `.env` with your settings

### "JVM not found" error
- Verify `JVM_PATH` points to correct `jvm.dll` file
- Check that Java JDK is installed (not just JRE)
- Use absolute path, not relative

### "Orekit data not found"
- Verify `OREKIT_DATA_PATH` exists
- Should contain files like `tai-utc.dat`, `Earth-Orientation-Parameters/`, etc.
- Use absolute path

### Configuration not loading
- Ensure `.env` file is in project root directory
- Check file encoding (should be UTF-8)
- Remove quotes around values in `.env`

## Example Configurations

### Fast Simulation (10x speed)
```bash
SIM_SPEED_MULTIPLIER=10.0
```

### ISS-like Orbit
```bash
ORBIT_ALTITUDE_KM=400
ORBIT_INCLINATION_DEG=51.6
```

### Highly Elliptical Orbit
```bash
ORBIT_ALTITUDE_KM=500
ORBIT_ECCENTRICITY=0.7
ORBIT_ARG_PERIGEE_DEG=270
```

## Next Steps

When implementing Phase 2 (Events) and beyond, additional configuration options will be added to `.env.template` for:
- Event probabilities
- Attack scenarios
- Subsystem parameters
- Ground station locations
- ML model paths

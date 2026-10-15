"""
Configuration loader - Load settings from .env file.

This module provides functions to load configuration from environment variables
and .env files, with fallback to sensible defaults.
"""

import os
from pathlib import Path
from typing import Optional
import re
import shutil
import subprocess
import math
from datetime import datetime, timezone


def number(key, default, integer=False):
    raw = os.getenv(key) or str(default)
    try:
        value = int(raw) if integer else float(raw)
    except ValueError as exc:
        raise ValueError(f"{key} must be {'an integer' if integer else 'a number'}, got {raw!r}") from exc
    if not math.isfinite(value):
        raise ValueError(f"{key} must be finite")
    return value


def simulation_start(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("SIM_START_TIME must be an ISO date, e.g. 2025-11-09T12:00:00Z") from exc
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def java_major_version(jvm_path: Path) -> int:
    """Read the selected installation's version, not an unrelated PATH Java."""
    for parent in jvm_path.parents:
        release = parent / "release"
        if release.is_file():
            match = re.search(r'JAVA_VERSION="([^"]+)"', release.read_text(encoding="utf-8"))
            if match:
                parts = match.group(1).split(".")
                return int(parts[1] if parts[0] == "1" else parts[0])
    executable = jvm_path.parent.parent / ("java.exe" if os.name == "nt" else "java")
    if not executable.is_file():
        raise ValueError(f"Cannot determine Java version for {jvm_path}")
    result = subprocess.run([str(executable), "-version"], capture_output=True, text=True, timeout=10)
    match = re.search(r'version "(?:1\.)?(\d+)', result.stderr + result.stdout)
    if not match:
        raise ValueError(f"Cannot determine Java version for {jvm_path}")
    return int(match.group(1))


def discover_jvm(explicit=None) -> str:
    """Honor overrides; otherwise choose a modern Java rather than registry Java 8."""
    import jpype
    suffixes = ("bin/server/jvm.dll", "lib/server/libjvm.so", "lib/server/libjvm.dylib")
    def libraries(home):
        return [Path(home) / suffix for suffix in suffixes]
    if explicit:
        candidates = [Path(explicit).expanduser()]
    elif os.getenv("JAVA_HOME"):
        candidates = libraries(os.environ["JAVA_HOME"])
    else:
        candidates = []
        java = shutil.which("java")
        if java:
            candidates.extend(libraries(Path(java).resolve().parent.parent))
        if os.name == "nt":
            for folder in ("Java", "Eclipse Adoptium", "Microsoft", "Amazon Corretto"):
                root = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / folder
                if root.is_dir():
                    for home in root.iterdir():
                        candidates.extend(libraries(home))
        try:
            candidates.append(Path(jpype.getDefaultJVMPath()))
        except Exception:
            pass
    usable = []
    for candidate in candidates:
        if candidate.is_file():
            version = java_major_version(candidate)
            if version >= 9:
                usable.append((version, str(candidate.resolve())))
    if not usable:
        raise ValueError("No Java 9+ JVM found. Set JVM_PATH to a modern JVM library or JAVA_HOME to its installation; remove obsolete Java 8 overrides.")
    return max(usable)[1]


def load_env_file(env_path: Optional[Path] = None):
    """
    Load environment variables from .env file.
    
    Args:
        env_path: Path to .env file. If None, looks for .env in project root.
    """
    if env_path is None:
        project_root = Path(__file__).parent.parent
        env_path = project_root / ".env"
    
    if env_path.exists():
        from dotenv import load_dotenv
        load_dotenv(env_path, override=False, encoding="utf-8-sig")

def project_directory() -> Path:
    """Resolve an optional project override relative to this repository."""
    root = Path(__file__).resolve().parent.parent
    value = Path(os.getenv("PROJECT_DIR") or root).expanduser()
    return (root / value).resolve() if not value.is_absolute() else value.resolve()


def resolve_project_path(key: str, default: str) -> Path:
    value = Path(os.getenv(key) or default).expanduser()
    return (project_directory() / value).resolve()


def validate_runtime_config(config: dict) -> dict:
    """Validate settings and discover Java without starting its JVM."""
    import math
    try:
        import jpype
    except ImportError as exc:
        raise RuntimeError("JPype is missing. Install requirements.txt using your active Python.") from exc
    for key in ("time_step", "speed_multiplier"):
        if not math.isfinite(config[key]) or config[key] <= 0:
            raise ValueError(f"{key} must be finite and greater than zero")
    orbit = config["orbit"]
    if not math.isfinite(orbit["semi_major_axis"]) or orbit["semi_major_axis"] <= 6378137:
        raise ValueError("ORBIT_ALTITUDE_KM must be finite and positive")
    if not 0 <= orbit["eccentricity"] < 1:
        raise ValueError("ORBIT_ECCENTRICITY must be in [0, 1)")
    if not 0 <= orbit["inclination_deg"] <= 180:
        raise ValueError("ORBIT_INCLINATION_DEG must be in [0, 180]")
    for key in ('raan_deg', 'arg_perigee_deg', 'mean_anomaly_deg'):
        if not math.isfinite(orbit[key]):
            raise ValueError(f"{key} must be finite")
    if orbit['semi_major_axis'] * (1 - orbit['eccentricity']) <= 6378137:
        raise ValueError('Orbit perigee must be above the Earth surface; check altitude and eccentricity')
    if not Path(config["orekit_data_path"]).is_dir():
        raise ValueError("OREKIT_DATA_PATH must point to the extracted Orekit data directory")
    if not any(Path(config['orekit_data_path']).rglob('tai-utc.dat')):
        raise ValueError('OREKIT_DATA_PATH has no tai-utc.dat; use the extracted Orekit data bundle')
    jars = list(Path(config.get("project_dir", project_directory())).glob("*.jar"))
    if not any(p.name.startswith("orekit-") for p in jars) or not any(p.name.startswith("hipparchus-core-") for p in jars):
        raise ValueError("Place Orekit and Hipparchus JARs in PROJECT_DIR")
    config["jvm_path"] = discover_jvm(config.get("jvm_path"))
    return config

def get_simulation_config() -> dict:
    """
    Get simulation configuration from environment variables.
    
    Returns:
        Dictionary with all simulation configuration
    """
    # Load .env file if exists
    load_env_file()
    
    # Get Earth radius constant
    EARTH_RADIUS = 6378137.0  # WGS84 in meters
    
    # Parse altitude and convert to semi-major axis
    altitude_km = number('ORBIT_ALTITUDE_KM', 700)
    semi_major_axis = EARTH_RADIUS + (altitude_km * 1000)
    
    config = {
        # Paths
        "jvm_path": os.getenv('JVM_PATH') or None,
        "project_dir": str(project_directory()),
        "orekit_data_path": str(resolve_project_path('OREKIT_DATA_PATH', 'orekit-data/orekit-data-main')),
        
        # Simulation timing
        "start_time": os.getenv('SIM_START_TIME', '2025-11-09T12:00:00Z'),
        "time_step": number('SIM_TIME_STEP', 1),
        "speed_multiplier": number('SIM_SPEED_MULTIPLIER', 1),
        
        # Orbital elements
        "orbit": {
            "semi_major_axis": semi_major_axis,
            "eccentricity": number('ORBIT_ECCENTRICITY', 0),
            "inclination_deg": number('ORBIT_INCLINATION_DEG', 98),
            "raan_deg": number('ORBIT_RAAN_DEG', 10),
            "arg_perigee_deg": number('ORBIT_ARG_PERIGEE_DEG', 0),
            "mean_anomaly_deg": number('ORBIT_MEAN_ANOMALY_DEG', 0),
        },
        
        # Logging
        "log_telemetry": os.getenv('LOG_TELEMETRY', 'true').lower() == 'true',
        "log_events": os.getenv('LOG_EVENTS', 'true').lower() == 'true',
        "telemetry_file": str(resolve_project_path('TELEMETRY_FILE', 'data/telemetry.csv')),
        "events_file": str(resolve_project_path('EVENTS_FILE', 'data/events.json')),
        
        # Streaming
        "enable_streaming": os.getenv('ENABLE_STREAMING', 'false').lower() == 'true',
        "websocket_host": os.getenv('WEBSOCKET_HOST', 'localhost'),
        "websocket_port": number('WEBSOCKET_PORT', 8080, integer=True),
        "duration_seconds": number('CZML_DEFAULT_DURATION_SECONDS', 3600, integer=True),
        "sample_step_seconds": number('CZML_STEP_SECONDS', 30, integer=True),
        "orbit_csv_file": str(resolve_project_path('ORBIT_CSV_FILE', 'orbit_positions.csv')),
        "orbit_czml_file": str(resolve_project_path('ORBIT_CZML_FILE', 'cubesat.czml')),
        "comm_csv_file": str(resolve_project_path('COMM_CSV_FILE', 'comm_samples.csv')),
        "czml_output_file": str(resolve_project_path('CZML_OUTPUT_FILE', 'cubesat_with_events.czml')),
        "czml_viewer_file": str(resolve_project_path('CZML_VIEWER_FILE', 'czml_viewer_enhanced.html')),
    }
    simulation_start(config['start_time'])
    for key in ('time_step', 'speed_multiplier', 'duration_seconds', 'sample_step_seconds'):
        if config[key] <= 0:
            raise ValueError(f"{key} must be greater than zero")
    if not 1 <= config['websocket_port'] <= 65535:
        raise ValueError('WEBSOCKET_PORT must be between 1 and 65535')
    return config


def print_config(config: dict):
    """Print configuration in a readable format."""
    print("\n" + "="*60)
    print("CONFIGURATION")
    print("="*60)
    print(f"\nPaths:")
    print(f"  JVM: {config['jvm_path']}")
    print(f"  Project: {config['project_dir']}")
    print(f"  Orekit Data: {config['orekit_data_path']}")
    
    print(f"\nTiming:")
    print(f"  Start Time: {config['start_time']}")
    print(f"  Time Step: {config['time_step']}s")
    print(f"  Speed Multiplier: {config['speed_multiplier']}x")
    
    print(f"\nOrbit:")
    orbit = config['orbit']
    altitude = (orbit['semi_major_axis'] - 6378137) / 1000
    print(f"  Altitude: {altitude:.1f} km")
    print(f"  Eccentricity: {orbit['eccentricity']:.4f}")
    print(f"  Inclination: {orbit['inclination_deg']:.1f}°")
    print(f"  RAAN: {orbit['raan_deg']:.1f}°")
    
    print(f"\nLogging:")
    print(f"  Telemetry: {config['log_telemetry']} -> {config['telemetry_file']}")
    print(f"  Events: {config['log_events']} -> {config['events_file']}")
    
    print(f"\nStreaming:")
    print(f"  Enabled: {config['enable_streaming']}")
    if config['enable_streaming']:
        print(f"  WebSocket: ws://{config['websocket_host']}:{config['websocket_port']}")
    
    print("="*60 + "\n")


if __name__ == "__main__":
    # Test configuration loading
    config = get_simulation_config()
    print_config(config)

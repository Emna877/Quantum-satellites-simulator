"""
Configuration loader - Load settings from .env file.

This module provides functions to load configuration from environment variables
and .env files, with fallback to sensible defaults.
"""

import os
from pathlib import Path
from typing import Optional


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
    if not Path(config["orekit_data_path"]).is_dir():
        raise ValueError("OREKIT_DATA_PATH must point to the extracted Orekit data directory")
    jars = list(Path(config.get("project_dir", project_directory())).glob("*.jar"))
    if not any(p.name.startswith("orekit-") for p in jars) or not any(p.name.startswith("hipparchus-core-") for p in jars):
        raise ValueError("Place Orekit and Hipparchus JARs in PROJECT_DIR")
    try:
        config["jvm_path"] = config.get("jvm_path") or jpype.getDefaultJVMPath()
    except Exception as exc:
        raise ValueError("Java was not found. Set JAVA_HOME or JVM_PATH.") from exc
    if not Path(config["jvm_path"]).is_file():
        raise ValueError("JVM_PATH must point to the JVM shared library (Windows: bin/server/jvm.dll)")
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
    altitude_km = float(os.getenv('ORBIT_ALTITUDE_KM', '700'))
    semi_major_axis = EARTH_RADIUS + (altitude_km * 1000)
    
    config = {
        # Paths
        "jvm_path": os.getenv('JVM_PATH') or None,
        "project_dir": str(project_directory()),
        "orekit_data_path": str(resolve_project_path('OREKIT_DATA_PATH', 'orekit-data/orekit-data-main')),
        
        # Simulation timing
        "start_time": os.getenv('SIM_START_TIME', '2025-11-09T12:00:00Z'),
        "time_step": float(os.getenv('SIM_TIME_STEP', '1.0')),
        "speed_multiplier": float(os.getenv('SIM_SPEED_MULTIPLIER', '1.0')),
        
        # Orbital elements
        "orbit": {
            "semi_major_axis": semi_major_axis,
            "eccentricity": float(os.getenv('ORBIT_ECCENTRICITY', '0.0')),
            "inclination_deg": float(os.getenv('ORBIT_INCLINATION_DEG', '98.0')),
            "raan_deg": float(os.getenv('ORBIT_RAAN_DEG', '10.0')),
            "arg_perigee_deg": float(os.getenv('ORBIT_ARG_PERIGEE_DEG', '0.0')),
            "mean_anomaly_deg": float(os.getenv('ORBIT_MEAN_ANOMALY_DEG', '0.0')),
        },
        
        # Logging
        "log_telemetry": os.getenv('LOG_TELEMETRY', 'true').lower() == 'true',
        "log_events": os.getenv('LOG_EVENTS', 'true').lower() == 'true',
        "telemetry_file": str(resolve_project_path('TELEMETRY_FILE', 'data/telemetry.csv')),
        "events_file": str(resolve_project_path('EVENTS_FILE', 'data/events.json')),
        
        # Streaming
        "enable_streaming": os.getenv('ENABLE_STREAMING', 'false').lower() == 'true',
        "websocket_host": os.getenv('WEBSOCKET_HOST', 'localhost'),
        "websocket_port": int(os.getenv('WEBSOCKET_PORT', '8080')),
    }
    
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

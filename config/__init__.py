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
    
    if not env_path.exists():
        print(f"Warning: .env file not found at {env_path}")
        print("Using default values or environment variables")
        return
    
    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith('#'):
                continue
            
            # Parse KEY=VALUE
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                
                # Only set if not already in environment
                if key not in os.environ:
                    os.environ[key] = value


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
        "jvm_path": os.getenv('JVM_PATH', r"C:\Program Files\Java\jdk-23\bin\server\jvm.dll"),
        "project_dir": os.getenv('PROJECT_DIR', str(Path(__file__).parent.parent)),
        "orekit_data_path": os.getenv('OREKIT_DATA_PATH', ''),
        
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
        "telemetry_file": os.getenv('TELEMETRY_FILE', 'data/telemetry.csv'),
        "events_file": os.getenv('EVENTS_FILE', 'data/events.json'),
        
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

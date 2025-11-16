"""
Enhanced CZML Export with Event Visualization

This script generates a CZML file that includes:
- Satellite orbit and position
- Visual representations of events:
  * Solar flares (glowing ellipsoids)
  * Micrometeoroids (small spheres with trails)
  * GPS spoofing (warning cones)
  * Laser attacks (beam cylinders)
  * Eclipse zones (shadow cones)
  * Jamming (signal wave ellipsoids)
"""

from pathlib import Path
import json
import datetime
from datetime import timedelta
from typing import List, Dict, Any
import random
import sys
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import event system
sys.path.insert(0, str(Path(__file__).parent))
from events.manager import EventManager, EventConfig
from events.base import EventType, EventSeverity
from simulation.state import SatelliteState


def create_czml_document(
    satellite_positions: List[tuple],  # [(datetime, x, y, z), ...]
    events: List[Dict[str, Any]],  # Event dictionaries
    duration_seconds: int = 3600
) -> List[Dict]:
    """
    Create enhanced CZML document with event visualizations.
    
    Args:
        satellite_positions: List of (timestamp, x, y, z) tuples in ECEF
        events: List of event dictionaries with timestamp, type, severity, position
        duration_seconds: Total simulation duration
        
    Returns:
        CZML document as list of packets
    """
    czml = []
    
    # Document packet
    epoch = satellite_positions[0][0]
    end_time = satellite_positions[-1][0]
    
    doc = {
        "id": "document",
        "name": "Quantum Satellite Simulation with Events",
        "version": "1.0",
        "clock": {
            "interval": f"{iso(epoch)}/{iso(end_time)}",
            "currentTime": iso(epoch),
            "multiplier": 10,  # 10x speed
            "range": "LOOP_STOP",
            "step": "SYSTEM_CLOCK_MULTIPLIER"
        }
    }
    czml.append(doc)
    
    # Satellite packet
    sat_packet = create_satellite_packet(satellite_positions, epoch)
    czml.append(sat_packet)
    
    # Add event visualizations
    for event in events:
        event_packets = create_event_visualization(event, satellite_positions, epoch)
        czml.extend(event_packets)
    
    return czml


def create_satellite_packet(positions: List[tuple], epoch: datetime.datetime) -> Dict:
    """Create the main satellite packet with position data."""
    
    # Build cartesian position array: [seconds, x, y, z, seconds, x, y, z, ...]
    cartesian_samples = []
    for (dt, x, y, z) in positions:
        seconds = (dt - epoch).total_seconds()
        cartesian_samples.extend([seconds, x, y, z])
    
    end_time = positions[-1][0]
    
    return {
        "id": "satellite",
        "name": "Quantum CubeSat",
        "availability": f"{iso(epoch)}/{iso(end_time)}",
        "position": {
            "epoch": iso(epoch),
            "cartesian": cartesian_samples,
            "referenceFrame": "FIXED"
        },
        "billboard": {
            "image": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAACXBIWXMAAAsTAAALEwEAmpwYAAAAB3RJTUUH3QQODhkVY3s7zwAAAB1pVFh0Q29tbWVudAAAAAAAQ3JlYXRlZCB3aXRoIEdJTVBkLmUHAAAA50lEQVQ4y62TMU4DMRBF/zOb3UqJBEWKFClSpEiRIkWKFC5cuXDhwpULV65cuXLhwpULFy5cuHDhwoULV65cuXLlypUrV65cuXLlypUrV65cuXLlypUrV65cuXLlypUrV65cuXLlypUrV65cuXLlypUrV65cuXLlypUrV65cuXLlypUrV65cuXLlypUrV65cuXLlypUrV65cuXLlypUrV65cuXLlypUrV65cuXLlypUrV65cuXLlypUrV65cuXLlypUrV65cuXLlypUrV65cuXLlypUrV65c+T/U1AAAAP//AwBKHAVwmfRi3AAAAABJRU5ErkJggg==",
            "scale": 1.5,
            "show": True
        },
        "label": {
            "text": "Quantum CubeSat",
            "font": "14pt monospace",
            "fillColor": {"rgba": [255, 255, 255, 255]},
            "outlineColor": {"rgba": [0, 0, 0, 200]},
            "outlineWidth": 2,
            "pixelOffset": {"cartesian2": [0, -25]},
            "show": True
        },
        "path": {
            "show": True,
            "leadTime": 300,  # 5 minutes ahead
            "trailTime": 1800,  # 30 minutes behind
            "width": 3,
            "material": {
                "solidColor": {
                    "color": {"rgba": [0, 255, 255, 200]}
                }
            },
            "resolution": 120
        }
    }


def create_event_visualization(event: Dict[str, Any], sat_positions: List[tuple], epoch: datetime.datetime) -> List[Dict]:
    """
    Create CZML packets for visualizing an event.
    
    Returns list of packets (could be multiple for one event).
    """
    event_type = event.get('event_type', 'unknown')
    event_id = event.get('event_id', 'event')
    timestamp = datetime.datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
    severity = event.get('severity', 'MEDIUM')
    duration = event.get('duration_seconds', 60)
    
    # Find satellite position at event time
    sat_pos = find_satellite_position(timestamp, sat_positions)
    
    # Create visualization based on event type
    if event_type == 'solar_flare':
        return create_solar_flare_viz(event_id, timestamp, sat_pos, severity, duration, epoch)
    elif event_type == 'micrometeoroid_impact':
        return create_micrometeoroid_viz(event_id, timestamp, sat_pos, severity, epoch)
    elif event_type == 'gps_spoofing':
        return create_gps_spoofing_viz(event_id, timestamp, sat_pos, severity, duration, epoch)
    elif event_type == 'laser_dazzle':
        return create_laser_attack_viz(event_id, timestamp, sat_pos, severity, duration, epoch)
    elif event_type == 'jamming_attack':
        return create_jamming_viz(event_id, timestamp, sat_pos, severity, duration, epoch)
    elif event_type == 'eclipse_entry' or event_type == 'eclipse_exit':
        return create_eclipse_viz(event_id, timestamp, sat_pos, event_type, epoch)
    elif event_type in ['command_injection', 'power_drain', 'thermal_sabotage']:
        return create_attack_marker(event_id, timestamp, sat_pos, event_type, severity, duration, epoch)
    else:
        return create_generic_event_marker(event_id, timestamp, sat_pos, event_type, severity, epoch)


def create_solar_flare_viz(event_id: str, timestamp: datetime.datetime, sat_pos: tuple, 
                           severity: str, duration: int, epoch: datetime.datetime) -> List[Dict]:
    """Solar flare: Orange glowing ellipsoid around satellite."""
    start = (timestamp - epoch).total_seconds()
    end = start + duration
    
    # Color based on severity
    severity_colors = {
        'LOW': [255, 200, 100, 150],
        'MEDIUM': [255, 165, 0, 200],
        'HIGH': [255, 100, 0, 230],
        'CRITICAL': [255, 50, 0, 255]
    }
    color = severity_colors.get(severity, [255, 165, 0, 200])
    
    # Size based on severity
    severity_scale = {'LOW': 50, 'MEDIUM': 100, 'HIGH': 150, 'CRITICAL': 200}
    scale = severity_scale.get(severity, 100)
    
    return [{
        "id": f"solar-flare-{event_id}",
        "name": f"Solar Flare ({severity})",
        "availability": f"{iso(timestamp)}/{iso(timestamp + timedelta(seconds=duration))}",
        "position": {
            "cartesian": list(sat_pos)
        },
        "ellipsoid": {
            "radii": {"cartesian": [scale, scale, scale]},
            "material": {
                "solidColor": {
                    "color": {"rgba": color}
                }
            },
            "outline": True,
            "outlineColor": {"rgba": [255, 255, 0, 255]},
            "outlineWidth": 2
        },
        "label": {
            "text": f"☀️ Solar Flare ({severity})",
            "font": "12pt monospace",
            "fillColor": {"rgba": [255, 200, 0, 255]},
            "pixelOffset": {"cartesian2": [0, -60]},
            "show": True
        }
    }]


def create_micrometeoroid_viz(event_id: str, timestamp: datetime.datetime, sat_pos: tuple,
                              severity: str, epoch: datetime.datetime) -> List[Dict]:
    """Micrometeoroid: Small sphere with impact trail."""
    packets = []
    
    # Micrometeoroid coming from random direction
    x, y, z = sat_pos
    offset = 5000  # 5km away initially
    angle = random.uniform(0, 6.28)
    
    # Starting position (approaching)
    start_pos = [
        x + offset * random.uniform(-1, 1),
        y + offset * random.uniform(-1, 1),
        z + offset * random.uniform(0.5, 1)
    ]
    
    # Impact happens over 1 second
    impact_time = timestamp + timedelta(seconds=1)
    
    # Micrometeoroid object
    packets.append({
        "id": f"micrometeoroid-{event_id}",
        "name": f"Micrometeoroid ({severity})",
        "availability": f"{iso(timestamp)}/{iso(impact_time)}",
        "position": {
            "epoch": iso(timestamp),
            "cartesian": [
                0, start_pos[0], start_pos[1], start_pos[2],  # t=0
                1, x, y, z  # t=1: impact
            ]
        },
        "ellipsoid": {
            "radii": {"cartesian": [2, 2, 2]},
            "material": {
                "solidColor": {
                    "color": {"rgba": [150, 150, 150, 255]}
                }
            }
        },
        "path": {
            "show": True,
            "material": {
                "solidColor": {
                    "color": {"rgba": [255, 255, 255, 200]}
                }
            },
            "width": 3,
            "trailTime": 1
        }
    })
    
    # Impact flash
    packets.append({
        "id": f"impact-flash-{event_id}",
        "name": "Impact Flash",
        "availability": f"{iso(impact_time)}/{iso(impact_time + timedelta(seconds=0.5))}",
        "position": {
            "cartesian": list(sat_pos)
        },
        "ellipsoid": {
            "radii": {"cartesian": [30, 30, 30]},
            "material": {
                "solidColor": {
                    "color": {"rgba": [255, 255, 0, 255]}
                }
            }
        }
    })
    
    return packets


def create_gps_spoofing_viz(event_id: str, timestamp: datetime.datetime, sat_pos: tuple,
                            severity: str, duration: int, epoch: datetime.datetime) -> List[Dict]:
    """GPS Spoofing: Red warning cone below satellite."""
    
    return [{
        "id": f"gps-spoof-{event_id}",
        "name": f"⚠️ GPS Spoofing ({severity})",
        "availability": f"{iso(timestamp)}/{iso(timestamp + timedelta(seconds=duration))}",
        "position": {
            "cartesian": list(sat_pos)
        },
        "cylinder": {
            "length": 100,
            "topRadius": 20,
            "bottomRadius": 50,
            "material": {
                "solidColor": {
                    "color": {"rgba": [255, 0, 0, 180]}
                }
            },
            "outline": True,
            "outlineColor": {"rgba": [255, 255, 0, 255]},
            "outlineWidth": 2
        },
        "label": {
            "text": f"⚠️ GPS SPOOFING ({severity})",
            "font": "bold 14pt monospace",
            "fillColor": {"rgba": [255, 0, 0, 255]},
            "pixelOffset": {"cartesian2": [0, -80]},
            "show": True,
            "style": "FILL_AND_OUTLINE",
            "outlineColor": {"rgba": [0, 0, 0, 255]},
            "outlineWidth": 3
        }
    }]


def create_laser_attack_viz(event_id: str, timestamp: datetime.datetime, sat_pos: tuple,
                            severity: str, duration: int, epoch: datetime.datetime) -> List[Dict]:
    """Laser attack: Bright beam from ground to satellite."""
    
    # Ground position (roughly below satellite, on Earth surface)
    earth_radius = 6378137
    x, y, z = sat_pos
    ground_scale = earth_radius / ((x**2 + y**2 + z**2) ** 0.5)
    ground_pos = [x * ground_scale, y * ground_scale, z * ground_scale]
    
    return [{
        "id": f"laser-beam-{event_id}",
        "name": f"🔴 Laser Attack ({severity})",
        "availability": f"{iso(timestamp)}/{iso(timestamp + timedelta(seconds=duration))}",
        "polyline": {
            "positions": {
                "cartesian": ground_pos + list(sat_pos)
            },
            "width": 8,
            "material": {
                "solidColor": {
                    "color": {"rgba": [255, 0, 100, 220]}
                }
            },
            "arcType": "NONE"  # Straight line
        },
        "label": {
            "text": f"🔴 LASER DAZZLE ({severity})",
            "font": "bold 14pt monospace",
            "fillColor": {"rgba": [255, 50, 50, 255]},
            "position": {"cartesian": list(sat_pos)},
            "pixelOffset": {"cartesian2": [0, -100]},
            "show": True
        }
    }]


def create_jamming_viz(event_id: str, timestamp: datetime.datetime, sat_pos: tuple,
                      severity: str, duration: int, epoch: datetime.datetime) -> List[Dict]:
    """Jamming: Pulsating red ellipsoid representing RF interference."""
    
    return [{
        "id": f"jamming-{event_id}",
        "name": f"📡 Jamming Attack ({severity})",
        "availability": f"{iso(timestamp)}/{iso(timestamp + timedelta(seconds=duration))}",
        "position": {
            "cartesian": list(sat_pos)
        },
        "ellipsoid": {
            "radii": {"cartesian": [200, 200, 80]},  # Flattened ellipsoid (RF wave)
            "material": {
                "solidColor": {
                    "color": {"rgba": [255, 0, 0, 100]}
                }
            },
            "outline": True,
            "outlineColor": {"rgba": [255, 0, 0, 200]},
            "outlineWidth": 3
        },
        "label": {
            "text": f"📡 RF JAMMING ({severity})",
            "font": "bold 12pt monospace",
            "fillColor": {"rgba": [255, 0, 0, 255]},
            "pixelOffset": {"cartesian2": [0, -90]},
            "show": True
        }
    }]


def create_eclipse_viz(event_id: str, timestamp: datetime.datetime, sat_pos: tuple,
                      event_type: str, epoch: datetime.datetime) -> List[Dict]:
    """Eclipse: Dark sphere or label."""
    
    if event_type == 'eclipse_entry':
        label_text = "🌑 ECLIPSE ENTRY"
        color = [50, 50, 100, 200]
    else:
        label_text = "🌞 ECLIPSE EXIT"
        color = [255, 255, 150, 200]
    
    return [{
        "id": f"eclipse-{event_id}",
        "name": label_text,
        "availability": f"{iso(timestamp)}/{iso(timestamp + timedelta(seconds=30))}",
        "position": {
            "cartesian": list(sat_pos)
        },
        "ellipsoid": {
            "radii": {"cartesian": [60, 60, 60]},
            "material": {
                "solidColor": {
                    "color": {"rgba": color}
                }
            }
        },
        "label": {
            "text": label_text,
            "font": "bold 14pt monospace",
            "fillColor": {"rgba": [200, 200, 255, 255]},
            "pixelOffset": {"cartesian2": [0, -70]},
            "show": True
        }
    }]


def create_attack_marker(event_id: str, timestamp: datetime.datetime, sat_pos: tuple,
                        event_type: str, severity: str, duration: int, epoch: datetime.datetime) -> List[Dict]:
    """Generic attack marker: Red warning symbol."""
    
    event_labels = {
        'command_injection': '💉 CMD INJECTION',
        'power_drain': '🔋 POWER DRAIN',
        'thermal_sabotage': '🌡️ THERMAL ATTACK'
    }
    
    return [{
        "id": f"attack-{event_id}",
        "name": f"{event_labels.get(event_type, 'ATTACK')} ({severity})",
        "availability": f"{iso(timestamp)}/{iso(timestamp + timedelta(seconds=duration))}",
        "position": {
            "cartesian": list(sat_pos)
        },
        "box": {
            "dimensions": {"cartesian": [40, 40, 40]},
            "material": {
                "solidColor": {
                    "color": {"rgba": [255, 0, 0, 180]}
                }
            },
            "outline": True,
            "outlineColor": {"rgba": [255, 255, 0, 255]},
            "outlineWidth": 2
        },
        "label": {
            "text": f"{event_labels.get(event_type, 'ATTACK')} ({severity})",
            "font": "bold 12pt monospace",
            "fillColor": {"rgba": [255, 0, 0, 255]},
            "pixelOffset": {"cartesian2": [0, -75]},
            "show": True
        }
    }]


def create_generic_event_marker(event_id: str, timestamp: datetime.datetime, sat_pos: tuple,
                               event_type: str, severity: str, epoch: datetime.datetime) -> List[Dict]:
    """Generic event marker."""
    
    return [{
        "id": f"event-{event_id}",
        "name": f"Event: {event_type}",
        "availability": f"{iso(timestamp)}/{iso(timestamp + timedelta(seconds=60))}",
        "position": {
            "cartesian": list(sat_pos)
        },
        "point": {
            "pixelSize": 15,
            "color": {"rgba": [255, 255, 0, 255]},
            "outlineColor": {"rgba": [0, 0, 0, 255]},
            "outlineWidth": 2
        },
        "label": {
            "text": f"{event_type} ({severity})",
            "font": "11pt monospace",
            "fillColor": {"rgba": [255, 255, 255, 255]},
            "pixelOffset": {"cartesian2": [0, -50]},
            "show": True
        }
    }]


def find_satellite_position(event_time: datetime.datetime, sat_positions: List[tuple]) -> tuple:
    """Find satellite position closest to event time."""
    closest = min(sat_positions, key=lambda p: abs((p[0] - event_time).total_seconds()))
    return closest[1:]  # Return (x, y, z)


def iso(dt: datetime.datetime) -> str:
    """Convert datetime to ISO8601 string for CZML."""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def main():
    """
    Main function to generate CZML with events.
    This is a simplified version - in real use, integrate with your full simulation.
    """
    print("="*60)
    print("Enhanced CZML Export with Event Visualization")
    print("="*60)
    
    # For demonstration, create mock satellite positions (replace with actual propagation)
    epoch = datetime.datetime.utcnow()
    duration = 3600  # 1 hour
    step = 30  # 30 seconds
    
    print("\n[1/4] Generating satellite positions...")
    sat_positions = []
    earth_radius = 6378137
    altitude = 700000
    orbit_radius = earth_radius + altitude
    
    for t in range(0, duration + 1, step):
        timestamp = epoch + timedelta(seconds=t)
        # Simple circular orbit (replace with Orekit propagation)
        angle = (t / duration) * 6.28  # One full orbit
        x = orbit_radius * 0.9659  # cos(15°) * radius
        y = orbit_radius * 0.2588 * (1 if t % 5400 < 2700 else -1)  # sin(15°)
        z = orbit_radius * 0.6  # Slight tilt
        
        # Rotate
        import math
        rot_x = x * math.cos(angle) - y * math.sin(angle)
        rot_y = x * math.sin(angle) + y * math.cos(angle)
        
        sat_positions.append((timestamp, rot_x, rot_y, z))
    
    print(f"  Generated {len(sat_positions)} position samples")
    
    # Generate sample events
    print("\n[2/4] Generating sample events...")
    config = EventConfig(
        solar_flare_rate=3.0,
        micrometeoroid_rate=2.0,
        gps_spoofing_rate=1.0,
        jamming_attack_rate=1.0,
        laser_dazzle_rate=0.5
    )
    
    manager = EventManager(config=config)
    state = SatelliteState(timestamp=epoch)
    
    # Schedule some events manually for demo
    from events.environmental import SolarFlare, MicrometeoroidImpact
    from events.attacks import GPSSpoofing, JammingAttack, LaserDazzle
    
    manager.schedule_event(SolarFlare(timestamp=epoch + timedelta(seconds=300), severity=EventSeverity.MEDIUM))
    manager.schedule_event(MicrometeoroidImpact(timestamp=epoch + timedelta(seconds=600), severity=EventSeverity.HIGH))
    manager.schedule_event(GPSSpoofing(timestamp=epoch + timedelta(seconds=900), severity=EventSeverity.HIGH))
    manager.schedule_event(JammingAttack(timestamp=epoch + timedelta(seconds=1200), severity=EventSeverity.CRITICAL))
    manager.schedule_event(LaserDazzle(timestamp=epoch + timedelta(seconds=1800), severity=EventSeverity.HIGH))
    manager.schedule_event(SolarFlare(timestamp=epoch + timedelta(seconds=2400), severity=EventSeverity.LOW))
    
    # Process all events
    for t in range(0, duration + 1, step):
        current_time = epoch + timedelta(seconds=t)
        manager.update(current_time, state)
    
    # Export events
    event_log = manager.export_event_log()
    print(f"  Generated {len(event_log)} events")
    
    # Create CZML
    print("\n[3/4] Creating CZML document...")
    czml = create_czml_document(sat_positions, event_log, duration)
    print(f"  Created CZML with {len(czml)} packets")
    
    # Write to file
    output_filename = os.getenv('CZML_OUTPUT_FILE', 'cubesat_with_events.czml')
    output_file = Path(__file__).parent / output_filename
    print(f"\n[4/4] Writing CZML to {output_file}...")
    with open(output_file, 'w') as f:
        json.dump(czml, f, indent=2)
    
    print(f"\n✅ CZML file created successfully!")
    print(f"\nTo view:")
    viewer_file = os.getenv('CZML_VIEWER_FILE', 'czml_viewer_enhanced.html')
    print(f"1. Open {viewer_file} in a web browser")
    print(f"2. Or upload to https://sandcastle.cesium.com/")
    print(f"3. Look for event markers:")
    print(f"   ☀️  Solar Flares (orange glow)")
    print(f"   💥 Micrometeoroids (impact trails)")
    print(f"   ⚠️  GPS Spoofing (red cones)")
    print(f"   🔴 Laser Attacks (red beams)")
    print(f"   📡 Jamming (red ellipsoids)")
    print(f"\n" + "="*60)


if __name__ == "__main__":
    main()

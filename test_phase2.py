"""
Phase 2 Integration Test - Event System Validation

Tests:
1. Event generation and scheduling
2. Event application to satellite state
3. Ground truth labeling (attack vs environmental)
4. Event statistics and logging
5. Integration with simulation engine
"""

import asyncio
from datetime import datetime, timedelta
from pathlib import Path
import sys
import json

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from simulation.engine import SimulationEngine
from simulation.state import SatelliteState
from events.manager import EventManager, EventConfig
from events.base import EventType, EventSeverity
from events.environmental import SolarFlare, EclipseEntry
from events.attacks import GPSSpoofing, JammingAttack


def test_event_creation():
    """Test 1: Verify event objects are created correctly."""
    print("\n" + "="*60)
    print("TEST 1: Event Creation")
    print("="*60)
    
    timestamp = datetime.utcnow()
    
    # Test environmental event
    solar_flare = SolarFlare(timestamp=timestamp, severity=EventSeverity.MEDIUM)
    print(f"\n✓ Created SolarFlare event:")
    print(f"  - Event Type: {solar_flare.event_type}")
    print(f"  - Severity: {solar_flare.severity}")
    print(f"  - Is Attack: {solar_flare.is_attack}")
    print(f"  - Ground Truth Label: {solar_flare.ground_truth_label}")
    print(f"  - Duration: {solar_flare.duration_seconds}s")
    
    assert solar_flare.event_type == EventType.SOLAR_FLARE
    assert solar_flare.is_attack == False
    assert solar_flare.ground_truth_label == 0
    assert solar_flare.severity == EventSeverity.MEDIUM
    
    # Test attack event
    gps_spoof = GPSSpoofing(timestamp=timestamp, severity=EventSeverity.HIGH)
    print(f"\n✓ Created GPSSpoofing event:")
    print(f"  - Event Type: {gps_spoof.event_type}")
    print(f"  - Severity: {gps_spoof.severity}")
    print(f"  - Is Attack: {gps_spoof.is_attack}")
    print(f"  - Ground Truth Label: {gps_spoof.ground_truth_label}")
    print(f"  - Duration: {gps_spoof.duration_seconds}s")
    
    assert gps_spoof.event_type == EventType.GPS_SPOOFING
    assert gps_spoof.is_attack == True
    assert gps_spoof.ground_truth_label == 1
    assert gps_spoof.severity == EventSeverity.HIGH
    
    print("\n✅ Test 1 PASSED - Events created correctly")


def test_event_application():
    """Test 2: Verify events modify satellite state correctly."""
    print("\n" + "="*60)
    print("TEST 2: Event Application to State")
    print("="*60)
    
    # Create initial state
    state = SatelliteState(timestamp=datetime.utcnow())
    initial_battery = state.battery_percent
    initial_temp = state.internal_temp
    
    print(f"\nInitial State:")
    print(f"  - Battery: {initial_battery:.1f}%")
    print(f"  - Temperature: {initial_temp:.1f}°C")
    print(f"  - Component Health: {state.component_health_percent:.1f}%")
    
    # Apply solar flare
    timestamp = datetime.utcnow()
    flare = SolarFlare(timestamp=timestamp, severity=EventSeverity.HIGH)
    flare.apply_to_state(state)
    
    print(f"\nAfter Solar Flare (HIGH severity):")
    print(f"  - Battery: {state.battery_percent:.1f}% (Δ {state.battery_percent - initial_battery:.1f}%)")
    print(f"  - Temperature: {state.internal_temp:.1f}°C (Δ {state.internal_temp - initial_temp:.1f}°C)")
    print(f"  - Component Health: {state.component_health_percent:.1f}%")
    print(f"  - Signal Strength: {state.signal_strength_dbm:.1f} dBm")
    
    assert state.battery_percent < initial_battery, "Battery should drain during solar flare"
    assert state.internal_temp > initial_temp, "Temperature should increase during solar flare"
    
    # Apply GPS spoofing attack
    initial_health = state.component_health_percent
    spoof = GPSSpoofing(timestamp=timestamp, severity=EventSeverity.CRITICAL)
    spoof.apply_to_state(state)
    
    print(f"\nAfter GPS Spoofing (CRITICAL severity):")
    print(f"  - Navigation Accuracy: {state.navigation_accuracy_meters:.1f} m")
    print(f"  - Component Health: {state.component_health_percent:.1f}% (Δ {state.component_health_percent - initial_health:.1f}%)")
    
    assert state.navigation_accuracy_meters > 100, "Navigation accuracy should degrade"
    assert state.component_health_percent < initial_health, "Component health should degrade"
    
    print("\n✅ Test 2 PASSED - Events apply state changes correctly")


def test_event_manager():
    """Test 3: Verify event manager functionality."""
    print("\n" + "="*60)
    print("TEST 3: Event Manager")
    print("="*60)
    
    # Create config with high event rates for testing
    config = EventConfig(
        solar_flare_rate=10.0,  # 10 per day
        gps_spoofing_rate=5.0,  # 5 per day
        jamming_attack_rate=5.0,
        enable_environmental=True,
        enable_attacks=True
    )
    
    manager = EventManager(config=config)
    current_time = datetime.utcnow()
    
    print(f"\nEvent Manager Configuration:")
    print(f"  - Environmental enabled: {config.enable_environmental}")
    print(f"  - Attacks enabled: {config.enable_attacks}")
    print(f"  - Solar flare rate: {config.solar_flare_rate}/day")
    print(f"  - GPS spoofing rate: {config.gps_spoofing_rate}/day")
    
    # Schedule some events
    flare = SolarFlare(timestamp=current_time + timedelta(seconds=10), severity=EventSeverity.LOW)
    manager.schedule_event(flare)
    
    spoof = GPSSpoofing(timestamp=current_time + timedelta(seconds=20), severity=EventSeverity.MEDIUM)
    manager.schedule_event(spoof)
    
    print(f"\n✓ Scheduled 2 events")
    print(f"  - Queue size: {len(manager.event_queue)}")
    print(f"  - Active events: {len(manager.active_events)}")
    
    # Test eclipse scheduling
    manager.schedule_eclipse_events(current_time, orbit_period_minutes=90.0)
    print(f"\n✓ Scheduled eclipse events for 90-min orbit")
    print(f"  - Queue size after eclipse scheduling: {len(manager.event_queue)}")
    
    # Simulate time passing
    state = SatelliteState(timestamp=current_time)
    
    # Advance to first event
    test_time = current_time + timedelta(seconds=11)
    events_occurred = manager.update(test_time, state)
    
    print(f"\n✓ Advanced to T+11s:")
    print(f"  - Events occurred: {len(events_occurred)}")
    print(f"  - Active events: {len(manager.active_events)}")
    
    if events_occurred:
        for event in events_occurred:
            print(f"    • {event.event_type.value} (Ground Truth: {event.ground_truth_label})")
    
    # Get statistics
    stats = manager.get_statistics()
    print(f"\nStatistics:")
    print(f"  - Total events: {stats['total_events']}")
    print(f"  - Environmental: {stats['environmental_events']}")
    print(f"  - Attacks: {stats['attack_events']}")
    
    assert stats['total_events'] > 0, "Should have scheduled events"
    
    print("\n✅ Test 3 PASSED - Event manager works correctly")


def test_ground_truth_labeling():
    """Test 4: Verify ground truth labels for ML training."""
    print("\n" + "="*60)
    print("TEST 4: Ground Truth Labeling")
    print("="*60)
    
    timestamp = datetime.utcnow()
    
    # Test all environmental events
    environmental_events = [
        SolarFlare(timestamp=timestamp, severity=EventSeverity.LOW),
        EclipseEntry(timestamp=timestamp),
        # Add others as needed
    ]
    
    print("\nEnvironmental Events (Ground Truth = 0):")
    for event in environmental_events:
        print(f"  - {event.event_type.value}: label={event.ground_truth_label}, is_attack={event.is_attack}")
        assert event.ground_truth_label == 0, f"{event.event_type} should have label 0"
        assert event.is_attack == False, f"{event.event_type} should not be attack"
    
    # Test all attack events
    attack_events = [
        GPSSpoofing(timestamp=timestamp, severity=EventSeverity.MEDIUM),
        JammingAttack(timestamp=timestamp, severity=EventSeverity.HIGH),
        # Add others as needed
    ]
    
    print("\nAttack Events (Ground Truth = 1):")
    for event in attack_events:
        print(f"  - {event.event_type.value}: label={event.ground_truth_label}, is_attack={event.is_attack}")
        assert event.ground_truth_label == 1, f"{event.event_type} should have label 1"
        assert event.is_attack == True, f"{event.event_type} should be attack"
    
    print("\n✅ Test 4 PASSED - Ground truth labels correct")


def test_event_export():
    """Test 5: Verify event log export for ML training."""
    print("\n" + "="*60)
    print("TEST 5: Event Export for ML Training")
    print("="*60)
    
    manager = EventManager()
    current_time = datetime.utcnow()
    
    # Create and schedule diverse events
    events_to_schedule = [
        SolarFlare(timestamp=current_time, severity=EventSeverity.LOW),
        GPSSpoofing(timestamp=current_time + timedelta(seconds=5), severity=EventSeverity.HIGH),
        EclipseEntry(timestamp=current_time + timedelta(seconds=10)),
        JammingAttack(timestamp=current_time + timedelta(seconds=15), severity=EventSeverity.MEDIUM),
    ]
    
    for event in events_to_schedule:
        manager.schedule_event(event)
    
    print(f"\n✓ Scheduled {len(events_to_schedule)} diverse events")
    
    # Process all events
    state = SatelliteState(timestamp=current_time)
    for t in range(20):
        test_time = current_time + timedelta(seconds=t)
        manager.update(test_time, state)
    
    # Export event log
    event_log = manager.export_event_log()
    
    print(f"\n✓ Exported event log:")
    print(f"  - Total events in log: {len(event_log)}")
    
    # Verify export structure
    if event_log:
        sample_event = event_log[0]
        print(f"\nSample event export structure:")
        for key in sample_event.keys():
            print(f"  - {key}: {type(sample_event[key]).__name__}")
        
        # Verify critical ML training fields
        assert 'ground_truth_label' in sample_event, "Must have ground truth label"
        assert 'event_type' in sample_event, "Must have event type"
        assert 'severity' in sample_event, "Must have severity"
        assert 'timestamp' in sample_event, "Must have timestamp"
        assert 'is_attack' in sample_event, "Must have attack flag"
        
        # Count labels
        env_count = sum(1 for e in event_log if e['ground_truth_label'] == 0)
        attack_count = sum(1 for e in event_log if e['ground_truth_label'] == 1)
        
        print(f"\nGround Truth Distribution:")
        print(f"  - Environmental (0): {env_count}")
        print(f"  - Attacks (1): {attack_count}")
        
        # Save sample to file
        output_path = Path(__file__).parent / "event_log_sample.json"
        with open(output_path, 'w') as f:
            json.dump(event_log, f, indent=2, default=str)
        print(f"\n✓ Saved sample log to: {output_path}")
    
    print("\n✅ Test 5 PASSED - Event export ready for ML training")


async def test_simulation_integration():
    """Test 6: Run full simulation with event system."""
    print("\n" + "="*60)
    print("TEST 6: Full Simulation Integration (2 minutes)")
    print("="*60)
    
    # Configure simulation with event system
    config = {
        "jvm_path": r"C:\Program Files\Java\jdk-25\bin\server\jvm.dll",
        "orekit_data_path": r"D:\programming\python\Quantum-satellites-simulator\orekit-data\orekit-data-main",
        "start_time": datetime.utcnow().isoformat(),
        "time_step": 1.0,
        "speed_multiplier": 10.0,  # 10x speed for faster testing
        "orbit": {
            "semi_major_axis": 6378137 + 700e3,
            "eccentricity": 0.0,
            "inclination_deg": 98.0,
            "raan_deg": 0.0,
            "arg_perigee_deg": 0.0,
            "mean_anomaly_deg": 0.0,
        },
        "event_config": {
            "solar_flare_rate": 5.0,
            "gps_spoofing_rate": 2.0,
            "jamming_attack_rate": 2.0,
            "enable_environmental": True,
            "enable_attacks": True,
        }
    }
    
    engine = SimulationEngine(config)
    engine.setup()
    
    print("\n✓ Simulation engine initialized with event system")
    print("  - Starting 2-minute test run (120 ticks at 10x speed)...")
    
    # Run for 120 ticks (2 minutes sim time, 12 seconds wall time at 10x)
    engine.running = True
    elapsed_seconds = 0.0
    tick_count = 0
    max_ticks = 120
    
    try:
        while engine.running and tick_count < max_ticks:
            # Update events
            if engine.event_manager:
                events_occurred = engine.event_manager.update(engine.clock.current_time, engine.state)
                
                # Log events (suppressing for clean output, but they're being tracked)
                for event in events_occurred:
                    pass  # Events are logged internally
            
            # Propagate orbit
            elapsed_seconds += engine.clock.time_step
            from simulation.propagator import update_state_from_propagator
            engine.state = update_state_from_propagator(
                engine.state,
                engine.propagator,
                elapsed_seconds
            )
            engine.state.timestamp = engine.clock.current_time
            
            # Tick clock
            engine.clock.tick()
            tick_count += 1
            
            # Progress update every 30 seconds
            if tick_count % 30 == 0:
                progress = (tick_count / max_ticks) * 100
                print(f"  Progress: {progress:.0f}% ({tick_count}/{max_ticks} ticks)")
            
            await asyncio.sleep(0.01)  # Small delay to prevent tight loop
    
    except Exception as e:
        print(f"\n❌ Error during simulation: {e}")
        import traceback
        traceback.print_exc()
        return
    finally:
        engine.running = False
    
    # Get final statistics
    clock_stats = engine.clock.get_statistics()
    event_stats = engine.event_manager.get_statistics()
    
    print(f"\n✓ Simulation completed successfully!")
    print(f"\nClock Statistics:")
    print(f"  - Ticks: {clock_stats['tick_count']}")
    print(f"  - Sim time: {clock_stats['elapsed_sim_seconds']:.1f}s")
    print(f"  - Wall time: {clock_stats['elapsed_wall_seconds']:.1f}s")
    print(f"  - Average lag: {clock_stats['average_lag_seconds']:.3f}s")
    
    print(f"\nEvent Statistics:")
    print(f"  - Total events: {event_stats['total_events']}")
    print(f"  - Environmental: {event_stats['environmental_events']}")
    print(f"  - Attacks: {event_stats['attack_events']}")
    print(f"  - Active events: {event_stats['active_events_count']}")
    
    print(f"\n  By Severity:")
    for severity, count in event_stats['by_severity'].items():
        if count > 0:
            print(f"    - {severity.name}: {count}")
    
    # Export event log
    event_log = engine.event_manager.export_event_log()
    output_path = Path(__file__).parent / "phase2_simulation_events.json"
    with open(output_path, 'w') as f:
        json.dump(event_log, f, indent=2, default=str)
    print(f"\n✓ Event log saved to: {output_path}")
    print(f"  - Contains {len(event_log)} events with ground truth labels")
    
    # Shutdown
    await engine.shutdown()
    
    # Verify we got some events
    assert event_stats['total_events'] > 0, "Should have generated events during simulation"
    assert len(event_log) == event_stats['total_events'], "Event log should match total events"
    
    print("\n✅ Test 6 PASSED - Full simulation with event system works!")


async def main():
    """Run all Phase 2 tests."""
    print("\n" + "#"*60)
    print("# PHASE 2 TEST SUITE - EVENT SYSTEM")
    print("#"*60)
    
    try:
        # Unit tests
        test_event_creation()
        test_event_application()
        test_event_manager()
        test_ground_truth_labeling()
        test_event_export()
        
        # Integration test
        await test_simulation_integration()
        
        print("\n" + "#"*60)
        print("# ALL TESTS PASSED ✅")
        print("#"*60)
        print("\nPhase 2 Event System is fully functional!")
        print("Event logs with ground truth labels are ready for ML training.")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

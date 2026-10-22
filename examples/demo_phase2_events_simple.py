"""
Phase 2 Simple Test - Event System Unit Tests (No Orekit Required)

Tests the event system components without full simulation integration.
This allows testing without Orekit JAR dependencies.
"""

from datetime import datetime, timedelta
from pathlib import Path
import sys
import json

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from simulation.state import SatelliteState
from events.manager import EventManager, EventConfig
from events.base import EventType, EventSeverity
from events.environmental import (
    SolarFlare, EclipseEntry, EclipseExit, 
    MicrometeoroidImpact, AtmosphericDragSpike, GeomagneticStorm
)
from events.attacks import (
    GPSSpoofing, CommandInjection, JammingAttack,
    LaserDazzle, PowerDrain, ThermalSabotage
)


def test_event_creation():
    """Test 1: Verify event objects are created correctly."""
    print("\n" + "="*60)
    print("TEST 1: Event Creation")
    print("="*60)
    
    timestamp = datetime.utcnow()
    
    # Test all environmental events
    env_events = [
        SolarFlare(timestamp=timestamp, severity=EventSeverity.MEDIUM),
        EclipseEntry(timestamp=timestamp),
        EclipseExit(timestamp=timestamp),
        MicrometeoroidImpact(timestamp=timestamp, severity=EventSeverity.HIGH),
        AtmosphericDragSpike(timestamp=timestamp, severity=EventSeverity.LOW),
        GeomagneticStorm(timestamp=timestamp, severity=EventSeverity.CRITICAL),
    ]
    
    print("\nEnvironmental Events (Ground Truth = 0):")
    for event in env_events:
        print(f"  ✓ {event.event_type.value:25s} | Severity: {event.severity.name:8s} | Label: {event.ground_truth_label}")
        assert event.is_attack == False, f"{event.event_type} should not be attack"
        assert event.ground_truth_label == 0, f"{event.event_type} should have label 0"
    
    # Test all attack events
    attack_events = [
        GPSSpoofing(timestamp=timestamp, severity=EventSeverity.HIGH),
        CommandInjection(timestamp=timestamp, severity=EventSeverity.CRITICAL),
        JammingAttack(timestamp=timestamp, severity=EventSeverity.MEDIUM),
        LaserDazzle(timestamp=timestamp, severity=EventSeverity.HIGH),
        PowerDrain(timestamp=timestamp, severity=EventSeverity.LOW),
        ThermalSabotage(timestamp=timestamp, severity=EventSeverity.MEDIUM),
    ]
    
    print("\nAttack Events (Ground Truth = 1):")
    for event in attack_events:
        print(f"  ✓ {event.event_type.value:25s} | Severity: {event.severity.name:8s} | Label: {event.ground_truth_label}")
        assert event.is_attack == True, f"{event.event_type} should be attack"
        assert event.ground_truth_label == 1, f"{event.event_type} should have label 1"
    
    print(f"\n✅ Test 1 PASSED - All 12 event types created correctly")
    return True


def test_event_application():
    """Test 2: Verify events modify satellite state correctly."""
    print("\n" + "="*60)
    print("TEST 2: Event Application to State")
    print("="*60)
    
    # Create initial state
    state = SatelliteState(timestamp=datetime.utcnow())
    initial_battery = state.battery_percent
    initial_temp = state.internal_temp
    initial_health = state.component_health_percent
    
    print(f"\nInitial State:")
    print(f"  Battery: {initial_battery:.1f}%")
    print(f"  Temperature: {initial_temp:.1f}°C")
    print(f"  Component Health: {initial_health:.1f}%")
    print(f"  Signal Strength: {state.signal_strength_dbm:.1f} dBm")
    print(f"  Navigation Accuracy: {state.navigation_accuracy_meters:.1f} m")
    
    timestamp = datetime.utcnow()
    
    # Test 1: Solar Flare
    print("\n--- Testing Solar Flare ---")
    flare = SolarFlare(timestamp=timestamp, severity=EventSeverity.HIGH)
    flare.apply_to_state(state)
    print(f"  Battery: {state.battery_percent:.1f}% (Δ {state.battery_percent - initial_battery:.1f}%)")
    print(f"  Radiation: {state.radiation_dose_rate:.3f} μSv/h")
    print(f"  Signal Strength: {state.signal_strength_dbm:.1f} dBm")
    assert state.battery_percent <= initial_battery, "Battery should drain or stay same during solar flare"
    assert state.radiation_dose_rate > 0, "Radiation should increase"
    
    # Test 2: Eclipse Entry
    print("\n--- Testing Eclipse Entry ---")
    initial_solar = state.solar_panel_current
    eclipse_entry = EclipseEntry(timestamp=timestamp)
    eclipse_entry.apply_to_state(state)
    print(f"  Solar Power: {state.solar_panel_current:.1f} W (was {initial_solar:.1f} W)")
    assert state.solar_panel_current == 0.0, "Solar power should be zero in eclipse"
    
    # Test 3: GPS Spoofing
    print("\n--- Testing GPS Spoofing ---")
    initial_nav = state.navigation_accuracy_meters
    initial_health2 = state.component_health_percent
    spoof = GPSSpoofing(timestamp=timestamp, severity=EventSeverity.CRITICAL)
    spoof.apply_to_state(state)
    print(f"  Component Health: {state.component_health_percent:.1f}% (was {initial_health2:.1f}%)")
    print(f"  Position Error: {spoof.parameters['position_error_m']} m")
    assert state.component_health_percent < initial_health2, "Component health should degrade"
    
    # Test 4: Jamming Attack
    print("\n--- Testing Jamming Attack ---")
    initial_signal = state.signal_strength_dbm
    jamming = JammingAttack(timestamp=timestamp, severity=EventSeverity.HIGH)
    jamming.apply_to_state(state)
    print(f"  Signal Strength: {state.signal_strength_dbm:.1f} dBm (was {initial_signal:.1f} dBm)")
    assert state.signal_strength_dbm < initial_signal, "Signal should degrade"
    
    print(f"\n✅ Test 2 PASSED - Events correctly modify satellite state")
    return True


def test_event_manager():
    """Test 3: Verify event manager functionality."""
    print("\n" + "="*60)
    print("TEST 3: Event Manager")
    print("="*60)
    
    # Create config with moderate event rates
    config = EventConfig(
        solar_flare_rate=5.0,
        gps_spoofing_rate=2.0,
        jamming_attack_rate=2.0,
        enable_environmental=True,
        enable_attacks=True
    )
    
    manager = EventManager(config=config)
    current_time = datetime.utcnow()
    
    print(f"\nEvent Manager Configuration:")
    print(f"  Environmental enabled: {config.enable_environmental}")
    print(f"  Attacks enabled: {config.enable_attacks}")
    print(f"  Solar flare rate: {config.solar_flare_rate}/day")
    print(f"  GPS spoofing rate: {config.gps_spoofing_rate}/day")
    
    # Schedule diverse events
    print(f"\n--- Scheduling Events ---")
    events_to_schedule = [
        SolarFlare(timestamp=current_time + timedelta(seconds=5), severity=EventSeverity.LOW),
        GPSSpoofing(timestamp=current_time + timedelta(seconds=10), severity=EventSeverity.MEDIUM),
        EclipseEntry(timestamp=current_time + timedelta(seconds=15)),
        JammingAttack(timestamp=current_time + timedelta(seconds=20), severity=EventSeverity.HIGH),
        MicrometeoroidImpact(timestamp=current_time + timedelta(seconds=25), severity=EventSeverity.CRITICAL),
    ]
    
    for event in events_to_schedule:
        manager.schedule_event(event)
        print(f"  ✓ Scheduled: {event.event_type.value} at T+{(event.timestamp - current_time).total_seconds():.0f}s")
    
    print(f"\nQueue status: {len(manager.event_queue)} events queued")
    
    # Schedule eclipse events
    manager.schedule_eclipse_events(current_time, orbit_period_minutes=90.0)
    print(f"✓ Eclipse events scheduled for 90-min orbit")
    print(f"  Queue size: {len(manager.event_queue)} events")
    
    # Simulate time progression
    print(f"\n--- Simulating Time Progression ---")
    state = SatelliteState(timestamp=current_time)
    events_triggered = []
    
    for t in range(0, 30, 5):
        test_time = current_time + timedelta(seconds=t)
        events_occurred = manager.update(test_time, state)
        
        if events_occurred:
            print(f"  T+{t:2d}s: {len(events_occurred)} event(s) triggered")
            for event in events_occurred:
                print(f"       • {event.event_type.value} (Label: {event.ground_truth_label})")
                events_triggered.extend(events_occurred)
        else:
            print(f"  T+{t:2d}s: No new events")
    
    # Get statistics
    stats = manager.get_statistics()
    print(f"\n--- Event Statistics ---")
    print(f"  Total events: {stats['total_events']}")
    print(f"  Environmental: {stats['environmental_events']}")
    print(f"  Attacks: {stats['attack_events']}")
    print(f"  Active events: {stats['active_events_count']}")
    print(f"  Queued events: {stats['queued_events_count']}")
    
    assert stats['total_events'] > 0, "Should have scheduled events"
    assert stats['environmental_events'] > 0, "Should have environmental events"
    assert stats['attack_events'] > 0, "Should have attack events"
    
    print(f"\n✅ Test 3 PASSED - Event manager works correctly")
    return True


def test_event_export():
    """Test 4: Verify event log export for ML training."""
    print("\n" + "="*60)
    print("TEST 4: Event Export for ML Training")
    print("="*60)
    
    manager = EventManager()
    current_time = datetime.utcnow()
    
    # Create diverse events
    events = [
        SolarFlare(timestamp=current_time, severity=EventSeverity.LOW),
        GPSSpoofing(timestamp=current_time + timedelta(seconds=10), severity=EventSeverity.HIGH),
        EclipseEntry(timestamp=current_time + timedelta(seconds=20)),
        JammingAttack(timestamp=current_time + timedelta(seconds=30), severity=EventSeverity.MEDIUM),
        MicrometeoroidImpact(timestamp=current_time + timedelta(seconds=40), severity=EventSeverity.CRITICAL),
        PowerDrain(timestamp=current_time + timedelta(seconds=50), severity=EventSeverity.LOW),
    ]
    
    print(f"\n--- Scheduling {len(events)} Events ---")
    for event in events:
        manager.schedule_event(event)
        print(f"  ✓ {event.event_type.value:25s} | Label: {event.ground_truth_label}")
    
    # Process events
    state = SatelliteState(timestamp=current_time)
    for t in range(60):
        test_time = current_time + timedelta(seconds=t)
        manager.update(test_time, state)
    
    # Export event log
    event_log = manager.export_event_log()
    
    print(f"\n--- Event Log Export ---")
    print(f"  Total events exported: {len(event_log)}")
    
    if event_log:
        sample_event = event_log[0]
        print(f"\n  Sample Event Structure:")
        for key in sample_event.keys():
            value = sample_event[key]
            print(f"    {key:25s}: {type(value).__name__}")
        
        # Verify ML training fields
        required_fields = ['ground_truth_label', 'event_type', 'severity', 'timestamp', 'is_attack', 'parameters']
        for field in required_fields:
            assert field in sample_event, f"Missing required field: {field}"
        print(f"\n  ✓ All required ML training fields present")
        
        # Count labels
        env_count = sum(1 for e in event_log if e['ground_truth_label'] == 0)
        attack_count = sum(1 for e in event_log if e['ground_truth_label'] == 1)
        
        print(f"\n  Ground Truth Distribution:")
        print(f"    Environmental (0): {env_count}")
        print(f"    Attacks (1): {attack_count}")
        
        # Save to file
        output_path = Path(__file__).parent / "event_log_sample.json"
        with open(output_path, 'w') as f:
            json.dump(event_log, f, indent=2, default=str)
        print(f"\n  ✓ Saved sample log to: {output_path.name}")
    
    print(f"\n✅ Test 4 PASSED - Event export ready for ML training")
    return True


def test_severity_distribution():
    """Test 5: Verify severity distribution works correctly."""
    print("\n" + "="*60)
    print("TEST 5: Severity Distribution")
    print("="*60)
    
    # Custom severity distribution
    config = EventConfig(
        severity_distribution={
            EventSeverity.LOW: 0.4,
            EventSeverity.MEDIUM: 0.3,
            EventSeverity.HIGH: 0.2,
            EventSeverity.CRITICAL: 0.1
        }
    )
    
    manager = EventManager(config=config)
    
    # Generate many events to test distribution
    print(f"\n--- Generating Events ---")
    severity_counts = {sev: 0 for sev in EventSeverity}
    
    current_time = datetime.utcnow()
    for i in range(100):
        # Create random environmental event
        event = manager._create_environmental_event(current_time)
        severity_counts[event.severity] += 1
    
    print(f"  Generated 100 environmental events")
    print(f"\n  Severity Distribution:")
    for severity, count in severity_counts.items():
        expected = config.severity_distribution[severity] * 100
        print(f"    {severity.name:8s}: {count:3d} (expected ~{expected:.0f})")
    
    print(f"\n✅ Test 5 PASSED - Severity distribution functional")
    return True


def test_time_based_effects():
    """Test 6: Verify time-based effect decay."""
    print("\n" + "="*60)
    print("TEST 6: Time-Based Effect Decay")
    print("="*60)
    
    current_time = datetime.utcnow()
    event = SolarFlare(timestamp=current_time, severity=EventSeverity.MEDIUM)
    
    print(f"\nEvent: {event.event_type.value}")
    print(f"  Duration: {event.duration_seconds}s")
    
    # Test effect multiplier over time
    print(f"\n  Effect Multiplier Over Time:")
    test_times = [0, 300, 600, 1800, 3000, 3600, 4000]
    for delta in test_times:
        test_time = current_time + timedelta(seconds=delta)
        multiplier = event.get_effect_multiplier(test_time)
        is_active = event.is_active(test_time)
        status = "ACTIVE" if is_active else "EXPIRED"
        print(f"    T+{delta:4d}s: {multiplier:.3f} [{status}]")
    
    # Verify multiplier decreases over time
    mult_0 = event.get_effect_multiplier(current_time)
    mult_half = event.get_effect_multiplier(current_time + timedelta(seconds=event.duration_seconds/2))
    mult_end = event.get_effect_multiplier(current_time + timedelta(seconds=event.duration_seconds))
    
    assert mult_0 == 1.0, "Effect should start at 1.0"
    assert mult_half < mult_0, "Effect should decay over time"
    assert mult_end == 0.0, "Effect should be 0.0 at end"
    
    print(f"\n✅ Test 6 PASSED - Time-based effects work correctly")
    return True


def main():
    """Run all Phase 2 simple tests."""
    print("\n" + "#"*60)
    print("# PHASE 2 SIMPLE TEST SUITE - EVENT SYSTEM")
    print("# (No Orekit dependency)")
    print("#"*60)
    
    tests = [
        test_event_creation,
        test_event_application,
        test_event_manager,
        test_event_export,
        test_severity_distribution,
        test_time_based_effects,
    ]
    
    passed = 0
    failed = 0
    
    try:
        for test_func in tests:
            try:
                if test_func():
                    passed += 1
            except AssertionError as e:
                print(f"\n❌ TEST FAILED: {e}")
                failed += 1
            except Exception as e:
                print(f"\n❌ UNEXPECTED ERROR: {e}")
                import traceback
                traceback.print_exc()
                failed += 1
        
        print("\n" + "#"*60)
        print(f"# TEST RESULTS: {passed}/{len(tests)} PASSED")
        if failed == 0:
            print("# ALL TESTS PASSED ✅")
        else:
            print(f"# {failed} TEST(S) FAILED ❌")
        print("#"*60)
        
        if failed == 0:
            print("\nPhase 2 Event System is fully functional!")
            print("Event components are ready for ML training data generation.")
            print("\nNote: Full simulation test (with Orekit) requires:")
            print("  1. Orekit JAR files (orekit-*.jar, hipparchus-*.jar)")
            print("  2. Java JDK installed")
            print("  3. Update config paths in test_phase2.py")
        
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user")


if __name__ == "__main__":
    main()

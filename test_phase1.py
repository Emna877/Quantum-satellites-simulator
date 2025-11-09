"""
Test script for Phase 1: Core Simulation Infrastructure

This script tests the basic propagation loop without events or subsystems.
It should propagate a satellite orbit in real-time and print status updates.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from simulation.engine import SimulationEngine
from config import get_simulation_config, print_config


async def test_phase1():
    """
    Test Phase 1 implementation.
    
    This will:
    1. Initialize Orekit with your local paths
    2. Create a 700km circular orbit at 98° inclination
    3. Propagate for 2 minutes in real-time
    4. Print status every 10 seconds
    """
    
    print("\n" + "="*70)
    print(" PHASE 1 TEST: Core Simulation Infrastructure")
    print("="*70 + "\n")
    
    # Load configuration from .env file
    config = get_simulation_config()
    print_config(config)
    
    # Create and setup engine
    engine = SimulationEngine(config)
    
    try:
        engine.setup()
        
        # Run for limited time (2 minutes for testing)
        print("\nRunning simulation for 2 minutes...")
        print("Watch for status updates every 60 seconds")
        print("Press Ctrl+C to stop early\n")
        
        # Run simulation in a task with timeout
        try:
            await asyncio.wait_for(engine.run(), timeout=120.0)
        except asyncio.TimeoutError:
            print("\n[Test] 2-minute test completed successfully!")
            engine.running = False
    
    except KeyboardInterrupt:
        print("\n[Test] Interrupted by user")
    except Exception as e:
        print(f"\n[Test] ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n" + "="*70)
    print(" PHASE 1 TEST COMPLETE")
    print("="*70 + "\n")
    
    return True


if __name__ == "__main__":
    success = asyncio.run(test_phase1())
    sys.exit(0 if success else 1)

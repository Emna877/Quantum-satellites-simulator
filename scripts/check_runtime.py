"""Run with: python -m scripts.check_runtime (does not write simulation output)."""
import sys
from datetime import datetime, timezone
from pathlib import Path


def main():
    propagator = None
    try:
        from config import get_simulation_config, validate_runtime_config, simulation_start
        from simulation.propagator import OrekitPropagator
        config = validate_runtime_config(get_simulation_config())
        print(f"Python: {sys.executable}")
        print(f"Selected JVM: {config['jvm_path']}")
        propagator = OrekitPropagator(config['jvm_path'], Path(config['orekit_data_path']))
        propagator.create_propagator_from_keplerian(
            epoch=simulation_start(config['start_time']),
            **config['orbit'],
        )
        import numpy as np
        initial, _ = propagator.propagate_step(0.0)
        later, velocity = propagator.propagate_step(60.0)
        if not np.isfinite(later).all() or not np.isfinite(velocity).all():
            raise RuntimeError('Propagation returned non-finite coordinates')
        if np.linalg.norm(later - initial) < 1:
            raise RuntimeError('Satellite did not move during 60 seconds')
        print('PASS: Java, JPype, Orekit, Hipparchus, data loading, and propagation work together.')
        return 0
    except Exception as exc:
        print(f'FAIL: {exc}', file=sys.stderr)
        return 1
    finally:
        if propagator is not None:
            propagator.shutdown()


if __name__ == '__main__':
    sys.exit(main())

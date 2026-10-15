"""Export the configured Orekit orbit to CSV and CZML."""
import csv
import json
import math
from pathlib import Path
from config import get_simulation_config
from simulation.propagator import OrekitPropagator, iso
from export_czml_with_events import create_czml_document


def main():
    config = get_simulation_config()
    propagator = OrekitPropagator.from_config(config)
    try:
        states = propagator.sample_states(config['duration_seconds'], config['sample_step_seconds'])
        positions = [(state.timestamp, *state.position.tolist()) for state in states]
        output = Path(config['orbit_csv_file'])
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('w', newline='', encoding='utf-8') as stream:
            writer = csv.writer(stream)
            writer.writerow(['t_s', 'x_m', 'y_m', 'z_m', 'lat_deg', 'lon_deg', 'alt_m',
                             'timestamp', 'vx_m_s', 'vy_m_s', 'vz_m_s', 'in_eclipse'])
            for state in states:
                geo = propagator.geodetic(state.position, state.timestamp)
                writer.writerow([(state.timestamp-states[0].timestamp).total_seconds(),
                    *state.position.tolist(), math.degrees(float(geo.getLatitude())),
                    math.degrees(float(geo.getLongitude())), state.altitude, iso(state.timestamp),
                    *state.velocity.tolist(), int(state.in_eclipse)])
        document = create_czml_document(positions, [], config['duration_seconds'])
        output = Path(config['orbit_czml_file'])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(document, indent=2), encoding='utf-8')
        print(f"Orekit period: {propagator.period_seconds/60:.3f} minutes")
        print(f"CSV written: {config['orbit_csv_file']}")
        print(f"CZML written: {output}")
    finally:
        propagator.shutdown()


if __name__ == '__main__':
    main()

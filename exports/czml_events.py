"""Convert ExperimentResult records to CZML billboard/polyline event markers.

The packets produced here can be appended to any existing CZML document (e.g.
one produced by export_czml_with_events.py) so that the Cesium viewer shows
time-aligned event markers alongside the orbital track.

Each event-type gets a distinct colour and icon:
  RF jamming         — red billboard at satellite position
  Optical blocked    — orange billboard
  QKD abort          — violet billboard
  Classical failure  — amber billboard
  Contact start/end  — cyan billboard

The satellite position at each event timestamp is queried from the propagator so
that the marker follows the orbital track, not a fixed ground location.

CZML reference: https://github.com/AnalyticalGraphicsInc/czml-writer/wiki/CZML-Guide
"""
import json
import math
import uuid
from datetime import datetime, timezone


# Colour palette (RGBA 0-255)
_COLOURS = {
    "rf_jamming":         [220, 50,  50,  230],  # red
    "optical_blocked":    [230, 140, 30,  230],  # orange
    "qkd_abort":          [160, 80,  220, 230],  # violet
    "classical_failure":  [220, 180, 30,  230],  # amber
    "contact_start":      [30,  220, 220, 200],  # cyan
    "contact_end":        [30,  220, 220, 200],  # cyan
    "default":            [200, 200, 200, 200],  # grey
}

# Simple SVG data-URI icons (single-char emoji-like squares for each type)
_ICON_B64 = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAoAAAAKCAYAAACNMs+9AAAAFklEQVR42mNkYPhfz0AEYBxV"
    "SGQUABZ4BASmFNbhAAAAAElFTkSuQmCC"
)  # 10×10 white square placeholder; replace with real icons in the UI phase


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def _satellite_position_at(propagator, dt: datetime) -> list:
    """Return ECEF [x, y, z] in metres at the given UTC datetime."""
    try:
        pos, _ = propagator.propagate_at(dt)
        return [float(pos[0]), float(pos[1]), float(pos[2])]
    except Exception:
        return [0.0, 0.0, 0.0]


def _billboard_packet(packet_id: str, name: str, description: str,
                      availability: str, position_xyz: list,
                      colour: list, label_text: str) -> dict:
    """Return a CZML packet showing a billboard at a fixed ECEF position."""
    x, y, z = position_xyz
    return {
        "id": packet_id,
        "name": name,
        "description": description,
        "availability": availability,
        "position": {
            "cartesian": [x, y, z],
            "referenceFrame": "FIXED",
        },
        "billboard": {
            "image": _ICON_B64,
            "scale": 1.2,
            "color": {"rgba": colour},
            "show": True,
            "pixelOffset": {"cartesian2": [0, 15]},
            "heightReference": "NONE",
        },
        "label": {
            "text": label_text,
            "font": "11px monospace",
            "fillColor": {"rgba": colour},
            "outlineColor": {"rgba": [0, 0, 0, 180]},
            "outlineWidth": 1,
            "pixelOffset": {"cartesian2": [12, 0]},
            "show": True,
        },
    }


def _pass_markers(pass_record: dict, propagator) -> list:
    """Generate contact-window start/end markers for a pass."""
    packets = []
    for boundary, label in (
        (pass_record['window_start'], '▶ contact start'),
        (pass_record['window_end'],   '■ contact end'),
    ):
        dt = datetime.fromisoformat(boundary.replace('Z', '+00:00'))
        avail = f"{boundary}/{pass_record['window_end']}"
        pos = _satellite_position_at(propagator, dt)
        packets.append(_billboard_packet(
            packet_id=str(uuid.uuid4()),
            name=label,
            description=(
                f"Station contact {'started' if '▶' in label else 'ended'} at {boundary[:19]}Z\n"
                f"Duration: {pass_record['duration_s']:.0f} s"
            ),
            availability=avail,
            position_xyz=pos,
            colour=_COLOURS['contact_start'],
            label_text=label,
        ))
    return packets


def _qkd_abort_marker(pass_record: dict, propagator) -> list:
    """Generate a QKD abort marker at pass start when the protocol aborted."""
    fk = pass_record.get('qkd_finite_pass', {})
    if fk.get('key_status') != 'aborted':
        return []
    reason = fk.get('abort_reason', 'unknown')
    dt = datetime.fromisoformat(pass_record['window_start'].replace('Z', '+00:00'))
    avail = f"{pass_record['window_start']}/{pass_record['window_end']}"
    pos = _satellite_position_at(propagator, dt)
    return [_billboard_packet(
        packet_id=str(uuid.uuid4()),
        name='QKD abort',
        description=f"QKD protocol aborted\nReason: {reason}",
        availability=avail,
        position_xyz=pos,
        colour=_COLOURS['qkd_abort'],
        label_text='✗ QKD abort',
    )]


def _rf_failure_markers(pass_record: dict, propagator) -> list:
    """Generate RF-failure markers at each sample where the link is down."""
    packets = []
    samples = pass_record.get('samples', [])
    run_end = pass_record['window_end']
    in_outage = False
    outage_start = None

    for s in samples:
        ts = s['timestamp']
        rf_ok = s.get('rf', {}).get('available', True)
        if not rf_ok and not in_outage:
            in_outage = True
            outage_start = ts
        elif rf_ok and in_outage:
            in_outage = False
            if outage_start:
                dt = datetime.fromisoformat(outage_start.replace('Z', '+00:00'))
                pos = _satellite_position_at(propagator, dt)
                loss = s.get('rf_jamming_db', 0.0)
                packets.append(_billboard_packet(
                    packet_id=str(uuid.uuid4()),
                    name='RF outage',
                    description=(
                        f"RF link outage {outage_start[:19]}Z → {ts[:19]}Z\n"
                        f"Jamming: {loss:.0f} dB additional loss"
                    ),
                    availability=f"{outage_start}/{ts}",
                    position_xyz=pos,
                    colour=_COLOURS['rf_jamming'],
                    label_text=f'⚡ RF jammed ({loss:.0f} dB)',
                ))
    if in_outage and outage_start:
        dt = datetime.fromisoformat(outage_start.replace('Z', '+00:00'))
        pos = _satellite_position_at(propagator, dt)
        loss = samples[-1].get('rf_jamming_db', 0.0) if samples else 0.0
        packets.append(_billboard_packet(
            packet_id=str(uuid.uuid4()),
            name='RF outage',
            description=f"RF link outage from {outage_start[:19]}Z (pass end)\nJamming: {loss:.0f} dB",
            availability=f"{outage_start}/{run_end}",
            position_xyz=pos,
            colour=_COLOURS['rf_jamming'],
            label_text=f'⚡ RF jammed ({loss:.0f} dB)',
        ))
    return packets


def _optical_block_markers(pass_record: dict, propagator) -> list:
    """Generate optical-block marker for cloud-blocked passes."""
    samples = pass_record.get('samples', [])
    if not samples:
        return []
    first = samples[0]
    if not first.get('optical_cloud_blocked', False):
        return []
    dt = datetime.fromisoformat(pass_record['window_start'].replace('Z', '+00:00'))
    pos = _satellite_position_at(propagator, dt)
    return [_billboard_packet(
        packet_id=str(uuid.uuid4()),
        name='Optical blocked',
        description="Optical/QKD channel blocked (cloud or obstruction)",
        availability=f"{pass_record['window_start']}/{pass_record['window_end']}",
        position_xyz=pos,
        colour=_COLOURS['optical_blocked'],
        label_text='☁ optical blocked',
    )]


def _classical_failure_marker(pass_record: dict, propagator) -> list:
    """Generate a classical-session-failure marker."""
    cls = pass_record.get('classical_session_summary', {})
    if cls.get('key_established', True):
        return []
    reason = cls.get('failure_reason', 'unknown')
    dt = datetime.fromisoformat(pass_record['window_start'].replace('Z', '+00:00'))
    pos = _satellite_position_at(propagator, dt)
    return [_billboard_packet(
        packet_id=str(uuid.uuid4()),
        name='Classical session failed',
        description=f"Classical key establishment failed\nReason: {reason}",
        availability=f"{pass_record['window_start']}/{pass_record['window_end']}",
        position_xyz=pos,
        colour=_COLOURS['classical_failure'],
        label_text='✗ no session key',
    )]


def experiment_result_to_czml_events(result, propagator) -> list:
    """Convert an ExperimentResult to a list of CZML event-marker packets.

    Parameters
    ----------
    result : ExperimentResult
        Returned by ExperimentRunner.run().
    propagator : OrekitPropagator
        The same propagator used for the run (still alive, JVM running).

    Returns
    -------
    list of CZML packet dicts, ready to be JSON-serialised and appended to a
    CZML document or loaded into the Cesium viewer as a standalone layer.
    """
    packets = []

    for p in result.passes:
        packets.extend(_pass_markers(p, propagator))
        packets.extend(_qkd_abort_marker(p, propagator))
        packets.extend(_rf_failure_markers(p, propagator))
        packets.extend(_optical_block_markers(p, propagator))
        packets.extend(_classical_failure_marker(p, propagator))

    return packets

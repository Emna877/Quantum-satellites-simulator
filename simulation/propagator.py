"""Shared two-body Orekit propagation, UTC dates, eclipses and station geometry."""
from datetime import datetime, timedelta
from pathlib import Path
import math
import jpype
import numpy as np
from config import simulation_start, validate_runtime_config, project_directory
from .state import SatelliteState

_registered_data_paths = set()


def utc(value):
    return simulation_start(value.isoformat() if isinstance(value, datetime) else value)


def iso(value):
    return utc(value).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def sample_offsets(duration, step):
    if not math.isfinite(duration) or not math.isfinite(step) or duration <= 0 or step <= 0:
        raise ValueError('Duration and sampling step must be finite and positive')
    count = int(math.ceil(duration / step))
    return [min(k * step, duration) for k in range(count + 1)]


class OrekitPropagator:
    def __init__(self, jvm_path, orekit_data_path):
        self.jvm_path = jvm_path
        self.orekit_data_path = Path(orekit_data_path)
        self.propagator = None
        self._owns_jvm = not jpype.isJVMStarted()
        if self._owns_jvm:
            jars = sorted(str(p) for p in project_directory().glob('*.jar'))
            jpype.startJVM(jvm_path, '-ea', classpath=jars)
        J = jpype.JClass
        self.JFile = J('java.io.File')
        manager = J('org.orekit.data.DataContext').getDefault().getDataProvidersManager()
        # Do not repeatedly register the same directory in a shared JVM.
        data_key = str(self.orekit_data_path.resolve())
        if data_key not in _registered_data_paths:
            manager.addProvider(J('org.orekit.data.DirectoryCrawler')(self.JFile(data_key)))
            _registered_data_paths.add(data_key)
        self.FramesFactory = J('org.orekit.frames.FramesFactory')
        self.AbsoluteDate = J('org.orekit.time.AbsoluteDate')
        self.TimeScalesFactory = J('org.orekit.time.TimeScalesFactory')
        self.Constants = J('org.orekit.utils.Constants')
        self.Vector3D = J('org.hipparchus.geometry.euclidean.threed.Vector3D')
        self.KeplerianOrbit = J('org.orekit.orbits.KeplerianOrbit')
        self.PositionAngleType = J('org.orekit.orbits.PositionAngleType')
        self.KeplerianPropagator = J('org.orekit.propagation.analytical.KeplerianPropagator')
        self.gcrf = self.FramesFactory.getGCRF()
        self.itrf = self.FramesFactory.getITRF(J('org.orekit.utils.IERSConventions').IERS_2010, True)
        self.mu = float(self.Constants.WGS84_EARTH_MU)
        self.earth_radius = float(self.Constants.WGS84_EARTH_EQUATORIAL_RADIUS)
        self.earth = J('org.orekit.bodies.OneAxisEllipsoid')(
            self.earth_radius, float(self.Constants.WGS84_EARTH_FLATTENING), self.itrf)
        sun = J('org.orekit.bodies.CelestialBodyFactory').getSun()
        self.eclipse_detector = J('org.orekit.propagation.events.EclipseDetector')(
            sun, float(self.Constants.SUN_RADIUS), self.earth).withUmbra()

    @classmethod
    def from_config(cls, config):
        config = validate_runtime_config(dict(config))
        result = cls(config['jvm_path'], Path(config['orekit_data_path']))
        result.create_propagator_from_keplerian(utc(config['start_time']), **config['orbit'])
        return result

    def absolute_date(self, value):
        value = utc(value)
        return self.AbsoluteDate(value.year, value.month, value.day, value.hour,
                                 value.minute, value.second + value.microsecond / 1e6,
                                 self.TimeScalesFactory.getUTC())

    def create_propagator_from_keplerian(self, epoch, semi_major_axis, eccentricity,
                                         inclination_deg, raan_deg, arg_perigee_deg,
                                         mean_anomaly_deg):
        self.start_time = utc(epoch)
        self.current_time = self.start_time
        self.epoch = self.absolute_date(epoch)
        self.orbit = self.KeplerianOrbit(
            semi_major_axis, eccentricity, math.radians(inclination_deg),
            math.radians(arg_perigee_deg), math.radians(raan_deg),
            math.radians(mean_anomaly_deg), self.PositionAngleType.MEAN,
            self.gcrf, self.epoch, self.mu)
        self.propagator = self.KeplerianPropagator(self.orbit)
        self.period_seconds = float(self.orbit.getKeplerianPeriod())
        return self.propagator

    @staticmethod
    def array(vector):
        return np.array([float(vector.getX()), float(vector.getY()), float(vector.getZ())])

    def pv_at(self, timestamp, frame=None):
        if self.propagator is None:
            raise RuntimeError('Create an orbit before propagation')
        return self.propagator.getPVCoordinates(self.absolute_date(timestamp), frame or self.itrf)

    def propagate_at(self, timestamp):
        """Absolute-time query; leaves the incremental propagation cursor unchanged."""
        pv = self.pv_at(timestamp)
        return self.array(pv.getPosition()), self.array(pv.getVelocity())

    def propagate_step(self, dt_seconds):
        if not math.isfinite(dt_seconds) or dt_seconds < 0:
            raise ValueError('Propagation delta must be finite and nonnegative')
        self.current_time += timedelta(seconds=dt_seconds)
        self.epoch = self.absolute_date(self.current_time)
        return self.propagate_at(self.current_time)

    def geodetic(self, position, timestamp=None):
        vector = self.Vector3D(*[float(v) for v in position])
        return self.earth.transform(vector, self.itrf, self.absolute_date(timestamp or self.current_time))

    def get_altitude(self, position):
        return float(self.geodetic(position).getAltitude())

    def is_in_eclipse(self, position, current_time):
        """Full Earth umbra using solar ephemerides and Orekit's occultation geometry.

        Position is retained for API compatibility; the configured orbit is evaluated
        at current_time so no mismatched position/date pair enters eclipse geometry.
        Partial shadow (penumbra) is not modeled as a power fraction yet.
        """
        state = self.propagator.propagate(self.absolute_date(current_time))
        return float(self.eclipse_detector.g(state)) < 0

    def state_at(self, timestamp, state=None):
        timestamp = utc(timestamp)
        state = state if state is not None else SatelliteState(timestamp=timestamp)
        state.position, state.velocity = self.propagate_at(timestamp)
        state.timestamp = timestamp
        state.altitude = float(self.geodetic(state.position, timestamp).getAltitude())
        state.in_eclipse = self.is_in_eclipse(state.position, timestamp)
        return state

    def sample_states(self, duration, step):
        return [self.state_at(self.start_time + timedelta(seconds=t))
                for t in sample_offsets(duration, step)]

    def station_frame(self, station):
        point = jpype.JClass('org.orekit.bodies.GeodeticPoint')(
            math.radians(station['lat_deg']), math.radians(station['lon_deg']), float(station['alt_m']))
        return jpype.JClass('org.orekit.frames.TopocentricFrame')(self.earth, point, station['name'])

    def station_geometry(self, timestamp, station):
        frame = self.station_frame(station) if isinstance(station, dict) else station
        date = self.absolute_date(timestamp)
        position = self.pv_at(timestamp).getPosition()
        return {'range_m': float(frame.getRange(position, self.itrf, date)),
                'elev_deg': math.degrees(float(frame.getElevation(position, self.itrf, date))),
                'azimuth_deg': math.degrees(float(frame.getAzimuth(position, self.itrf, date)))}

    def contact_windows(self, start, end, station, min_elevation_deg=5.0):
        """Orekit root-found rise/set boundaries, clipped to the requested interval."""
        start, end = utc(start), utc(end)
        if end <= start:
            raise ValueError('Contact end must be after start')
        if not math.isfinite(min_elevation_deg) or not 0 <= min_elevation_deg < 90:
            raise ValueError('Minimum elevation must be in [0, 90) degrees')
        frame = self.station_frame(station) if isinstance(station, dict) else station
        recorder = jpype.JClass('org.orekit.propagation.events.handlers.RecordAndContinue')()
        detector = jpype.JClass('org.orekit.propagation.events.ElevationDetector')(frame)
        detector = detector.withConstantElevation(math.radians(min_elevation_deg)).withMaxCheck(30.0).withThreshold(1e-6).withHandler(recorder)
        # A separate instance prevents detectors from modifying the shared propagator.
        worker = self.KeplerianPropagator(self.orbit)
        worker.addEventDetector(detector)
        worker.propagate(self.absolute_date(start), self.absolute_date(end))
        opened = start if self.station_geometry(start, frame)['elev_deg'] >= min_elevation_deg else None
        windows = []
        for event in recorder.getEvents():
            offset = float(event.getState().getDate().durationFrom(self.absolute_date(start)))
            timestamp = start + timedelta(seconds=offset)
            timestamp = min(end, max(start, timestamp))
            if event.isIncreasing():
                if opened is None:
                    opened = timestamp
            elif opened is not None:
                if timestamp > opened:
                    windows.append({'start': opened, 'end': timestamp})
                opened = None
        if opened is not None and opened < end:
            windows.append({'start': opened, 'end': end})
        return windows

    def shutdown(self):
        # Only the creator owns JVM teardown. Shared users must finish before this call.
        if self._owns_jvm and jpype.isJVMStarted():
            jpype.shutdownJVM()


def initialize_state_from_propagator(propagator, initial_time):
    return propagator.state_at(initial_time)


def update_state_from_propagator(state, propagator, dt_seconds):
    propagator.propagate_step(dt_seconds)
    return propagator.state_at(propagator.current_time, state)

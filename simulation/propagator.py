"""
Orekit Propagation Wrapper - Interface to Orekit astrodynamics library.

This module provides high-level functions to:
- Initialize Orekit JVM and data
- Create orbital propagators from TLE or Keplerian elements
- Step propagation forward in time
- Convert between Orekit and Python data structures
"""

import jpype
import math
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Tuple
from .state import SatelliteState


class OrekitPropagator:
    """
    Wrapper for Orekit propagation functionality.
    """
    
    def __init__(self, jvm_path: str, orekit_data_path: Path):
        """
        Initialize Orekit environment.
        
        Args:
            jvm_path: Path to JVM DLL (e.g., "C:/Program Files/Java/jdk-25/bin/server/jvm.dll")
            orekit_data_path: Path to orekit-data directory
        """
        self.jvm_path = jvm_path
        self.orekit_data_path = orekit_data_path
        self.propagator = None
        self.earth = None
        self.mu = None
        
        # JVM and Orekit classes
        self.JFile = None
        self.DataContext = None
        self.FramesFactory = None
        self.KeplerianOrbit = None
        self.NumericalPropagator = None
        self.AbsoluteDate = None
        self.TimeScalesFactory = None
        self.Constants = None
        self.Vector3D = None
        
        self._initialize_jvm()
        self._load_orekit_data()
        self._cache_classes()
    
    def _initialize_jvm(self):
        """Start JVM with Orekit JARs."""
        if jpype.isJVMStarted():
            print("JVM already started")
            return
        
        # Find all JAR files in project directory
        from config import project_directory
        project_dir = project_directory()
        jars = [str(p) for p in project_dir.glob("*.jar")]
        
        if not jars:
            raise RuntimeError(f"No JAR files found in {project_dir}. Ensure Orekit and Hipparchus JARs are present.")
        
        print(f"Found {len(jars)} JAR files")
        jpype.startJVM(self.jvm_path, "-ea", classpath=jars)
        print("JVM started successfully")
    
    def _load_orekit_data(self):
        """Load Orekit data files."""
        self.JFile = jpype.JClass("java.io.File")
        DataContext = jpype.JClass("org.orekit.data.DataContext")
        DirectoryCrawler = jpype.JClass("org.orekit.data.DirectoryCrawler")
        
        dm = DataContext.getDefault().getDataProvidersManager()
        dm.addProvider(DirectoryCrawler(self.JFile(str(self.orekit_data_path))))
        print(f"Orekit data loaded from {self.orekit_data_path}")
    
    def _cache_classes(self):
        """Cache frequently used Java classes."""
        self.DataContext = jpype.JClass("org.orekit.data.DataContext")
        self.FramesFactory = jpype.JClass("org.orekit.frames.FramesFactory")
        self.KeplerianOrbit = jpype.JClass("org.orekit.orbits.KeplerianOrbit")
        self.PositionAngleType = jpype.JClass("org.orekit.orbits.PositionAngleType")
        self.KeplerianPropagator = jpype.JClass("org.orekit.propagation.analytical.KeplerianPropagator")
        self.NumericalPropagator = jpype.JClass("org.orekit.propagation.numerical.NumericalPropagator")
        self.AbsoluteDate = jpype.JClass("org.orekit.time.AbsoluteDate")
        self.TimeScalesFactory = jpype.JClass("org.orekit.time.TimeScalesFactory")
        self.Constants = jpype.JClass("org.orekit.utils.Constants")
        self.Vector3D = jpype.JClass("org.hipparchus.geometry.euclidean.threed.Vector3D")
        self.IERSConventions = jpype.JClass("org.orekit.utils.IERSConventions")
        self.OneAxisEllipsoid = jpype.JClass("org.orekit.bodies.OneAxisEllipsoid")
        
        # Cache constants
        self.mu = float(self.Constants.WGS84_EARTH_MU)
        self.earth_radius = float(self.Constants.WGS84_EARTH_EQUATORIAL_RADIUS)
        
        # Create Earth ellipsoid for coordinate transformations
        self.earth = self.OneAxisEllipsoid(
            self.Constants.WGS84_EARTH_EQUATORIAL_RADIUS,
            self.Constants.WGS84_EARTH_FLATTENING,
            self.FramesFactory.getITRF(self.IERSConventions.IERS_2010, True)
        )
        print("Orekit classes cached")
    
    def create_propagator_from_keplerian(
        self,
        epoch: datetime,
        semi_major_axis: float,
        eccentricity: float,
        inclination_deg: float,
        raan_deg: float,
        arg_perigee_deg: float,
        mean_anomaly_deg: float
    ):
        """
        Create Keplerian propagator from orbital elements.
        
        Args:
            epoch: Start time for propagation
            semi_major_axis: Semi-major axis in meters
            eccentricity: Orbital eccentricity (0 = circular)
            inclination_deg: Inclination in degrees
            raan_deg: Right Ascension of Ascending Node in degrees
            arg_perigee_deg: Argument of perigee in degrees
            mean_anomaly_deg: Mean anomaly in degrees
        """
        # Convert to radians
        i = math.radians(inclination_deg)
        raan = math.radians(raan_deg)
        pa = math.radians(arg_perigee_deg)
        ma = math.radians(mean_anomaly_deg)
        
        # Create AbsoluteDate
        orekit_epoch = self.AbsoluteDate(
            epoch.year, epoch.month, epoch.day,
            epoch.hour, epoch.minute, float(epoch.second),
            self.TimeScalesFactory.getUTC()
        )
        
        # Create orbit
        orbit = self.KeplerianOrbit(
            semi_major_axis,
            eccentricity,
            i,
            pa,
            raan,
            ma,
            self.PositionAngleType.MEAN,
            self.FramesFactory.getGCRF(),
            orekit_epoch,
            self.mu
        )
        
        # Create propagator (using simple Keplerian for now)
        self.propagator = self.KeplerianPropagator(orbit)
        self.epoch = orekit_epoch
        
        print(f"Propagator created: a={semi_major_axis/1e3:.1f} km, e={eccentricity:.4f}, i={inclination_deg:.1f}°")
        return self.propagator
    
    def propagate_step(self, dt_seconds: float) -> Tuple[np.ndarray, np.ndarray]:
        """
        Propagate orbit forward by dt_seconds.
        
        Args:
            dt_seconds: Time step in seconds
            
        Returns:
            Tuple of (position, velocity) in ECEF frame
        """
        if self.propagator is None:
            raise RuntimeError("Propagator not initialized. Call create_propagator_from_keplerian first.")
        
        # Get current state
        current_date = self.epoch.shiftedBy(dt_seconds)
        pv = self.propagator.getPVCoordinates(current_date, self.FramesFactory.getGCRF())
        
        # Extract position and velocity in GCRF
        pos_gcrf = pv.getPosition()
        vel_gcrf = pv.getVelocity()
        
        # Convert to ECEF (ITRF)
        gcrf = self.FramesFactory.getGCRF()
        itrf = self.FramesFactory.getITRF(self.IERSConventions.IERS_2010, True)
        transform = gcrf.getTransformTo(itrf, current_date)
        
        pos_itrf = transform.transformPosition(pos_gcrf)
        vel_itrf = transform.transformVector(vel_gcrf)
        
        # Convert to numpy arrays
        position = np.array([
            float(pos_itrf.getX()),
            float(pos_itrf.getY()),
            float(pos_itrf.getZ())
        ])
        
        velocity = np.array([
            float(vel_itrf.getX()),
            float(vel_itrf.getY()),
            float(vel_itrf.getZ())
        ])
        
        # Update epoch for next step
        self.epoch = current_date
        
        return position, velocity
    
    def get_altitude(self, position: np.ndarray) -> float:
        """
        Calculate altitude above reference ellipsoid.
        
        Args:
            position: Position vector in ECEF frame [x, y, z]
            
        Returns:
            Altitude in meters
        """
        pos_vec = self.Vector3D(float(position[0]), float(position[1]), float(position[2]))
        
        # Get geodetic point
        itrf = self.FramesFactory.getITRF(self.IERSConventions.IERS_2010, True)
        geo_point = self.earth.transform(pos_vec, itrf, self.epoch)
        
        return float(geo_point.getAltitude())
    
    def is_in_eclipse(self, position: np.ndarray, current_time: datetime) -> bool:
        """
        Determine if satellite is in Earth's shadow.
        
        Args:
            position: Position vector in ECEF frame
            current_time: Current simulation time
            
        Returns:
            True if in eclipse, False otherwise
        """
        # Simple umbra check: if Earth blocks direct sunlight
        # More sophisticated implementation would use Orekit's EclipseDetector
        
        # Get Sun position (simplified - use Orekit's CelestialBodyFactory in full implementation)
        pos_magnitude = np.linalg.norm(position)
        
        # Rough check: if satellite is on night side and below ~1000 km
        # Full implementation should use proper solar position
        if pos_magnitude < self.earth_radius + 1000e3:
            # Use simple geometric check
            # This is a placeholder - proper implementation needs Sun ephemeris
            return False
        
        return False
    
    def shutdown(self):
        """Shutdown JVM."""
        if jpype.isJVMStarted():
            jpype.shutdownJVM()
            print("JVM shutdown")


def initialize_state_from_propagator(
    propagator: OrekitPropagator,
    initial_time: datetime
) -> SatelliteState:
    """
    Create initial SatelliteState from propagator.
    
    Args:
        propagator: Initialized OrekitPropagator
        initial_time: Starting time for simulation
        
    Returns:
        SatelliteState with orbital parameters populated
    """
    # Get initial position and velocity
    position, velocity = propagator.propagate_step(0.0)
    altitude = propagator.get_altitude(position)
    in_eclipse = propagator.is_in_eclipse(position, initial_time)
    
    # Create state with default subsystem values
    state = SatelliteState(
        timestamp=initial_time,
        position=position,
        velocity=velocity,
        altitude=altitude,
        in_eclipse=in_eclipse,
        battery_percent=100.0,  # Start fully charged
        internal_temp=20.0,  # Nominal starting temperature
        external_temp=20.0,
    )
    
    return state


def update_state_from_propagator(
    state: SatelliteState,
    propagator: OrekitPropagator,
    dt_seconds: float
) -> SatelliteState:
    """
    Update SatelliteState by advancing the propagator by a delta time.

    This function expects `dt_seconds` to be the time increment (seconds)
    since the last propagation step (i.e. a per-tick delta), not the
    cumulative elapsed time since initialization. The propagator maintains
    its own internal epoch/state between calls.

    Args:
        state: Current satellite state
        propagator: OrekitPropagator instance
        dt_seconds: Time step in seconds to advance the propagator

    Returns:
        Updated SatelliteState with new position/velocity
    """
    # Advance propagator by the delta time and get new position/velocity
    position, velocity = propagator.propagate_step(dt_seconds)
    altitude = propagator.get_altitude(position)
    in_eclipse = propagator.is_in_eclipse(position, state.timestamp)

    # Update state
    state.position = position
    state.velocity = velocity
    state.altitude = altitude
    state.in_eclipse = in_eclipse

    return state

# setup Orekit with JPype
from pathlib import Path
import jpype

# Paths
JVM_PATH = r"C:\Program Files\Java\jdk-25\bin\server\jvm.dll"
PROJECT_DIR = Path(r"C:\Users\Emna\Documents\QuantumSatellites").resolve()
DATA_DIR = PROJECT_DIR / "orekit-data"

# Start JVM and add Orekit/Hipparchus JARs
jars = [str(p) for p in PROJECT_DIR.rglob("*.jar")]
if not jpype.isJVMStarted():
    jpype.startJVM(JVM_PATH, "-ea", classpath=jars)

# Load Orekit data
JFile = jpype.JClass("java.io.File")
DataContext = jpype.JClass("org.orekit.data.DataContext")
DirectoryCrawler = jpype.JClass("org.orekit.data.DirectoryCrawler")

dm = DataContext.getDefault().getDataProvidersManager()
dm.addProvider(DirectoryCrawler(JFile(str(DATA_DIR))))

print("Orekit initialized and data loaded ✅")


# create a simple orbit and propagator
import math

FramesFactory = jpype.JClass("org.orekit.frames.FramesFactory")
KeplerianOrbit = jpype.JClass("org.orekit.orbits.KeplerianOrbit")
PositionAngleType = jpype.JClass("org.orekit.orbits.PositionAngleType")
AbsoluteDate = jpype.JClass("org.orekit.time.AbsoluteDate")
TimeScalesFactory = jpype.JClass("org.orekit.time.TimeScalesFactory")
Constants = jpype.JClass("org.orekit.utils.Constants")
KeplerianPropagator = jpype.JClass("org.orekit.propagation.analytical.KeplerianPropagator")

# Orbit: circular, 700 km altitude, sun-synchronous
earth_radius = Constants.WGS84_EARTH_EQUATORIAL_RADIUS
mu = Constants.WGS84_EARTH_MU
altitude = 700e3
a = earth_radius + altitude
e = 0.0
i = math.radians(98.0)

epoch = AbsoluteDate(2025, 10, 29, 0, 0, 0.0, TimeScalesFactory.getUTC())
orbit = KeplerianOrbit(a, e, i, 0, 0, 0, PositionAngleType.MEAN, FramesFactory.getGCRF(), epoch, mu)
propagator = KeplerianPropagator(orbit)

print("Orbit and propagator ready ✅")



# propagate orbit and get positions
future = epoch.shiftedBy(600)  # 10 minutes later
pv = propagator.getPVCoordinates(future, FramesFactory.getGCRF())
pos = pv.getPosition()

x, y, z = float(pos.getX()), float(pos.getY()), float(pos.getZ())
print(f"Position after 10 min (GCRF frame): x={x:.1f}, y={y:.1f}, z={z:.1f} m")


# convert positions to geodetic coordinates (lat, lon, alt)
Geo = jpype.JClass("org.orekit.bodies.OneAxisEllipsoid")
IERSConventions = jpype.JClass("org.orekit.utils.IERSConventions")

earth = Geo(
    Constants.WGS84_EARTH_EQUATORIAL_RADIUS,
    Constants.WGS84_EARTH_FLATTENING,
    FramesFactory.getITRF(IERSConventions.IERS_2010, True)
)

itrf = FramesFactory.getITRF(IERSConventions.IERS_2010, True)
transform = FramesFactory.getGCRF().getTransformTo(itrf, future)
itrf_pos = transform.transformPosition(pos)

geo_point = earth.transform(itrf_pos, itrf, future)
lat = float(geo_point.getLatitude() * 180 / math.pi)
lon = float(geo_point.getLongitude() * 180 / math.pi)
alt = float(geo_point.getAltitude())

print(f"Lat: {lat:.6f}, Lon: {lon:.6f}, Alt: {alt:.1f} m")



# Shutdown JVM
if jpype.isJVMStarted():
    jpype.shutdownJVM()
    print("JVM shut down ✅")

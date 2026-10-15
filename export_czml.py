from pathlib import Path
import jpype
import math
import json
import datetime
import os

# ---------- CONFIG ----------
from config import get_simulation_config, validate_runtime_config

RUNTIME_CONFIG = validate_runtime_config(get_simulation_config())
JVM_PATH = RUNTIME_CONFIG['jvm_path']
PROJECT_DIR = Path(RUNTIME_CONFIG['project_dir'])
DATA_DIR = Path(RUNTIME_CONFIG['orekit_data_path'])
OUT_CSV = PROJECT_DIR / "orbit_positions.csv"
OUT_CZML = PROJECT_DIR / "cubesat.czml"
PROP_SECONDS = 3600 # propagation duration in seconds (1 hour)
STEP_SECONDS = 30             # sampling step (s)
# satellite visual properties
SAT_NAME = "CubeSat-1"
# ----------------------------

# helper: ISO timestamp for CZML epoch
def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

# 1) collect JARs and start JVM
jars = [str(p) for p in PROJECT_DIR.rglob("*.jar")]
if not jars:
    raise SystemExit("No JARs found in project folder. Put orekit + hipparchus jars here.")
if not jpype.isJVMStarted():
    jpype.startJVM(JVM_PATH, "-ea", classpath=jars)

# 2) JClasses
JFile = jpype.JClass("java.io.File")
DataContext = jpype.JClass("org.orekit.data.DataContext")
DirectoryCrawler = jpype.JClass("org.orekit.data.DirectoryCrawler")
FramesFactory = jpype.JClass("org.orekit.frames.FramesFactory")
KeplerianOrbit = jpype.JClass("org.orekit.orbits.KeplerianOrbit")
PositionAngleType = jpype.JClass("org.orekit.orbits.PositionAngleType")
KeplerianPropagator = jpype.JClass("org.orekit.propagation.analytical.KeplerianPropagator")
AbsoluteDate = jpype.JClass("org.orekit.time.AbsoluteDate")
TimeScalesFactory = jpype.JClass("org.orekit.time.TimeScalesFactory")
Constants = jpype.JClass("org.orekit.utils.Constants")
Geo = jpype.JClass("org.orekit.bodies.OneAxisEllipsoid")
IERSConventions = jpype.JClass("org.orekit.utils.IERSConventions")
Vector3D = jpype.JClass("org.hipparchus.geometry.euclidean.threed.Vector3D")

# 3) load orekit data
dm = DataContext.getDefault().getDataProvidersManager()
dm.addProvider(DirectoryCrawler(JFile(str(DATA_DIR))))
print("Orekit data loaded.")

# 4) define a circular LEO CubeSat orbit (700 km alt)
earth_radius = Constants.WGS84_EARTH_EQUATORIAL_RADIUS
mu = Constants.WGS84_EARTH_MU
alt = 700e3
a = earth_radius + alt
e = 0.0
i = math.radians(98.0)   # inclination
raan = 0.0
pa = 0.0
ma = 0.0
epoch = AbsoluteDate(2025, 10, 29, 0, 0, 0.0, TimeScalesFactory.getUTC())

orbit = KeplerianOrbit(a, e, i, pa, raan, ma, PositionAngleType.MEAN, FramesFactory.getGCRF(), epoch, mu)
prop = KeplerianPropagator(orbit)
print("Propagator ready.")

# 5) prepare Earth ellipsoid for geodetic conversions
earth_ellipsoid = Geo(Constants.WGS84_EARTH_EQUATORIAL_RADIUS,
                      Constants.WGS84_EARTH_FLATTENING,
                      FramesFactory.getITRF(IERSConventions.IERS_2010, True)
                      )

# 6) sampling loop -> prepare arrays for CSV and CZML (cartesian positions)
samples = []
times_iso = []
t = 0
# define epoch_py once
epoch_py = datetime.datetime(2025, 10, 29, 0, 0, 0)  # match epoch above
while t <= PROP_SECONDS:
    date = epoch.shiftedBy(t)
    # inertial frame positions
    pv = prop.getPVCoordinates(date, FramesFactory.getGCRF())
    pos = pv.getPosition()
    # convert to ITRF & geodetic
    itrf = FramesFactory.getITRF(IERSConventions.IERS_2010, True)
    transform = FramesFactory.getGCRF().getTransformTo(itrf, date)
    itrf_pos = transform.transformPosition(pos)
    # use ITRF (ECEF) coordinates for CSV and CZML so Cesium can render correctly
    x = float(itrf_pos.getX()); y = float(itrf_pos.getY()); z = float(itrf_pos.getZ())
    try:
        geo = earth_ellipsoid.transform(itrf_pos, itrf, date)
    except TypeError:
        geo = earth_ellipsoid.transform(itrf_pos, itrf)
    lat = float(geo.getLatitude() * 180.0 / math.pi)
    lon = float(geo.getLongitude() * 180.0 / math.pi)
    alt_m = float(geo.getAltitude())
    samples.append((t, x, y, z, lat, lon, alt_m))
    # for CZML we use absolute ISO times and cartesian ECEF positions
    sample_time = epoch_py + datetime.timedelta(seconds=int(t))
    times_iso.append((sample_time, (x, y, z)))
    t += STEP_SECONDS

# 7) write CSV
import csv
with open(OUT_CSV, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["t_s", "x_m", "y_m", "z_m", "lat_deg", "lon_deg", "alt_m"])
    for row in samples:
        w.writerow(row)
print("CSV written:", OUT_CSV)

# 8) create CZML document
# CZML expects timestamps in ISO8601 (Z) and positions in fixed reference frame.
# We'll create a simple CZML with a time-tagged list of cartesian positions.
czml = []
# Document packet
doc = {
    "id": "document",
    "name": "CubeSat orbit CZML",
    "version": "1.0"
}
czml.append(doc)

# Satellite packet
# Build position array: [timeISO, x, y, z, timeISO2, x2,y2,z2, ...]
position_array = []
for (dt, (x, y, z)) in times_iso:
    iso_t = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    position_array.extend([iso_t, x, y, z])

sat_packet = {
    "id": SAT_NAME,
    "name": SAT_NAME,
    "availability": "{}".format(iso(epoch_py)) + "/" + iso((epoch_py + datetime.timedelta(seconds=PROP_SECONDS))),
    "position": {
        "epoch": iso(epoch_py),
        "cartesian": [],
        # Explicitly state FIXED reference frame (ECEF) so Cesium interprets samples correctly
        "referenceFrame": "FIXED"
    },
    "point": {"pixelSize": 10, "color": {"rgba": [255, 0, 0, 255]}},
    "label": {
        "text": SAT_NAME,
        "font": "12pt Helvetica, Arial, sans-serif",
        "fillColor": {"rgba": [255, 255, 255, 255]},
        "outlineColor": {"rgba": [0, 0, 0, 200]},
        "outlineWidth": 2,
        "pixelOffset": [0, -30]
    },
    
    "path": {
        "show": True,
        "leadTime": 0,
        "trailTime": PROP_SECONDS,
        "width": 2,
        "material": {
            "solidColor": {
                "color": {"rgba": [255, 0, 0, 255]}
            }
        }
    },  
}

# Convert position_array into numeric seconds from epoch (safer)
epoch_dt = epoch_py
cartesian_samples = []
for (dt, (x, y, z)) in times_iso:
    seconds = (dt - epoch_dt).total_seconds()
    cartesian_samples.extend([seconds, x, y, z])

sat_packet["position"]["epoch"] = iso(epoch_dt)
sat_packet["position"]["cartesian"] = cartesian_samples

czml.append(sat_packet)

# write CZML
with open(OUT_CZML, "w", newline="") as f:
    json.dump(czml, f, indent=2)
print("CZML written:", OUT_CZML)

# 9) shutdown
if jpype.isJVMStarted():
    jpype.shutdownJVM()

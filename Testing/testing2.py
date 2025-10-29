# first_orbit.py
from pathlib import Path
import jpype
import csv
import math
import sys
import traceback
import os

# ---------- CONFIG ----------
JVM_PATH = r"C:\Program Files\Java\jdk-25\bin\server\jvm.dll"
PROJECT_DIR = Path(r"C:\Users\Emna\Documents\QuantumSatellites").resolve()
DATA_DIR = PROJECT_DIR / "orekit-data"   # must be unzipped orekit-data folder
OUT_CSV = PROJECT_DIR / "orbit_positions.csv"
# ----------------------------

# quick diagnostics to surface environment problems
print("Project dir:", PROJECT_DIR)
print("JVM path:", JVM_PATH)
print("JVM exists:", Path(JVM_PATH).exists())
print("Data dir:", DATA_DIR)
print("Data dir exists:", DATA_DIR.exists())

# 1) collect JARs and start JVM
jars = [str(p) for p in PROJECT_DIR.rglob("*.jar")]
print(f"Found {len(jars)} jar(s) under project dir.")
if jars:
    for j in jars[:10]:
        print(" -", j)
if not jars:
    print("No JARs found in project folder. Put orekit + hipparchus jars here.")
    sys.exit(1)

try:
    if not jpype.isJVMStarted():
        try:
            jpype.startJVM(JVM_PATH, "-ea", classpath=jars)
            print("JVM started.")
        except Exception as e:
            print("Failed to start JVM:", e)
            traceback.print_exc()
            sys.exit(1)

    # 2) get Java classes via JClass (after JVM started)
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

    # 3) load orekit-data using DataContext (Orekit 10.1+)
    DM = DataContext.getDefault().getDataProvidersManager()
    DM.addProvider(DirectoryCrawler(JFile(str(DATA_DIR))))
    print("Orekit data provider configured.")

    # 4) define orbit (circular, 700 km, sun-synch-ish)
    earth_radius = Constants.WGS84_EARTH_EQUATORIAL_RADIUS
    mu = Constants.WGS84_EARTH_MU
    altitude = 700e3
    a = earth_radius + altitude
    e = 0.0
    i = math.radians(98.0)
    raan = 0.0
    pa = 0.0
    ma = 0.0
    epoch = AbsoluteDate(2025, 10, 21, 0, 0, 0.0, TimeScalesFactory.getUTC())

    orbit = KeplerianOrbit(a, e, i, pa, raan, ma, PositionAngleType.MEAN, FramesFactory.getGCRF(), epoch, mu)
    prop = KeplerianPropagator(orbit)
    print("Orbit and propagator ready.")

    # 5) propagate and write CSV: t (s), x,y,z (meters), lat, lon, alt (deg,deg,m)
    Geo = jpype.JClass("org.orekit.bodies.OneAxisEllipsoid")
    IERSConventions = jpype.JClass("org.orekit.utils.IERSConventions")
    WGS84_ELLIPSOID = Geo(
        Constants.WGS84_EARTH_EQUATORIAL_RADIUS,
        Constants.WGS84_EARTH_FLATTENING,
        FramesFactory.getITRF(IERSConventions.IERS_2010, True)
    )

    transform_frame = FramesFactory.getGCRF()

    # ensure output directory exists
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)

    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["t_s", "x_m", "y_m", "z_m", "lat_deg", "lon_deg", "alt_m"])
        for t in range(0, 601, 60):  # 0..600s every 60s (10 minutes)
            future = epoch.shiftedBy(t)
            pv = prop.getPVCoordinates(future, transform_frame)
            pos = pv.getPosition()
            x = float(pos.getX()); y = float(pos.getY()); z = float(pos.getZ())
            # convert to geodetic (lat, lon, alt) via transform to ITRF at that date and ellipsoid
            itrf = FramesFactory.getITRF(IERSConventions.IERS_2010, True)
            transform = transform_frame.getTransformTo(itrf, future)
            # transformPosition returns a Vector3D-like object; keep as-is
            itrf_pos = transform.transformPosition(pos)
            # OneAxisEllipsoid.transform signatures vary by Orekit version; catch exceptions to reveal mismatches
            try:
                geodetic_point = WGS84_ELLIPSOID.transform(itrf_pos, itrf, future)
            except TypeError:
                # try alternate common signature
                geodetic_point = WGS84_ELLIPSOID.transform(itrf_pos, itrf)
            lat = float(geodetic_point.getLatitude() * 180.0 / math.pi)
            lon = float(geodetic_point.getLongitude() * 180.0 / math.pi)
            alt = float(geodetic_point.getAltitude())
            writer.writerow([t, x, y, z, lat, lon, alt])

    print(f"CSV written: {OUT_CSV}")

except Exception as e:
    print("Unhandled exception during execution:", e)
    traceback.print_exc()
finally:
    if jpype.isJVMStarted():
        try:
            jpype.shutdownJVM()
            print("JVM shut down.")
        except Exception:
            # ignore shutdown errors but print traceback for diagnosis
            traceback.print_exc()

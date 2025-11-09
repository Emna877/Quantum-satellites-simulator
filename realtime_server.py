from pathlib import Path
import asyncio
import jpype
import math
import datetime
import json
from typing import List

from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
import uvicorn

# Simple real-time streamer using Orekit -> WebSocket -> Cesium client
# Config
JVM_PATH = r"C:\Program Files\Java\jdk-23\bin\server\jvm.dll"
PROJECT_DIR = Path(r"D:\programming\python\Quantum-satellites-simulator\.venv_orekit").resolve()
DATA_DIR = PROJECT_DIR / "orekit-data"
PROP_SECONDS = 2 * 3600
STEP_SECONDS = 5  # smaller step for smoother streaming
MIN_ELEV_DEG = 5.0
SAT_NAME = "CubeSat-1"

GROUND_STATIONS = [
    {"name": "Tunis_GS", "lat_deg": 36.8, "lon_deg": 10.18, "alt_m": 20.0},
]

# Start JVM and load jars
jars = [str(p) for p in PROJECT_DIR.rglob("*.jar")]
if not jars:
    raise SystemExit("No JARs found in project folder. Put orekit + hipparchus jars here.")
if not jpype.isJVMStarted():
    jpype.startJVM(JVM_PATH, "-ea", classpath=jars)

# JClasses
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
TopocentricFrame = jpype.JClass("org.orekit.frames.TopocentricFrame")
GeodeticPoint = jpype.JClass("org.orekit.bodies.GeodeticPoint")
Vector3D = jpype.JClass("org.hipparchus.geometry.euclidean.threed.Vector3D")

# load orekit data
dm = DataContext.getDefault().getDataProvidersManager()
dm.addProvider(DirectoryCrawler(JFile(str(DATA_DIR))))
print("Orekit data loaded.")

# Build Earth ellipsoid and station frames
earth = Geo(Constants.WGS84_EARTH_EQUATORIAL_RADIUS,
            Constants.WGS84_EARTH_FLATTENING,
            FramesFactory.getITRF(IERSConventions.IERS_2010, True))
station_frames = {}
for gs in GROUND_STATIONS:
    gp = GeodeticPoint(math.radians(gs["lat_deg"]), math.radians(gs["lon_deg"]), gs["alt_m"])
    frame = TopocentricFrame(earth, gp, gs.get("name", "GS"))
    station_frames[gs["name"]] = {"frame": frame, "geodetic": gp, "cfg": gs}

# Create orbit (similar to qkd.py)
earth_radius = Constants.WGS84_EARTH_EQUATORIAL_RADIUS
mu = Constants.WGS84_EARTH_MU
alt = 700e3
a = earth_radius + alt
e = 0.0
i = math.radians(98.0)
raan = math.radians(GROUND_STATIONS[0]["lon_deg"]) if GROUND_STATIONS else 0.0
pa = 0.0
# coarse mean anomaly sweep to pick a geometry that may pass over the station
epoch = AbsoluteDate(2025, 10, 29, 0, 0, 0.0, TimeScalesFactory.getUTC())
best_ma = 0.0
best_max_elev = -1e9
for k in range(36):
    ma_try = math.radians((360.0 / 36) * k)
    orbit_try = KeplerianOrbit(a, e, i, pa, raan, ma_try, PositionAngleType.MEAN, FramesFactory.getGCRF(), epoch, mu)
    prop_try = KeplerianPropagator(orbit_try)
    max_elev = -1e9
    ttmp = 0
    while ttmp <= PROP_SECONDS:
        date_tmp = epoch.shiftedBy(ttmp)
        pv_tmp = prop_try.getPVCoordinates(date_tmp, FramesFactory.getGCRF())
        pos_tmp = pv_tmp.getPosition()
        for name, info in station_frames.items():
            topo_tmp = info["frame"]
            elev_rad_tmp = topo_tmp.getElevation(pos_tmp, FramesFactory.getGCRF(), date_tmp)
            elev_deg_tmp = math.degrees(elev_rad_tmp)
            if elev_deg_tmp > max_elev:
                max_elev = elev_deg_tmp
        ttmp += STEP_SECONDS
    if max_elev > best_max_elev:
        best_max_elev = max_elev
        best_ma = ma_try

orbit = KeplerianOrbit(a, e, i, pa, raan, best_ma, PositionAngleType.MEAN, FramesFactory.getGCRF(), epoch, mu)
prop = KeplerianPropagator(orbit)
print(f"Propagator ready (ma set to {math.degrees(best_ma):.1f}°) - best max elev={best_max_elev:.2f}°")

# FastAPI app
app = FastAPI()
app.mount("/static", StaticFiles(directory=str(PROJECT_DIR)), name="static")

clients: List[WebSocket] = []

async def broadcaster():
    # stream positions in real time (blocking loop)
    print("Broadcaster started")
    t = 0.0
    # epoch as python datetime for ISO strings
    epoch_py = datetime.datetime(2025, 10, 29, 0, 0, 0)
    while True:
        # produce packet for current time
        date = epoch.shiftedBy(t)
        pv = prop.getPVCoordinates(date, FramesFactory.getGCRF())
        pos = pv.getPosition()
        # convert to ITRF
        itrf = FramesFactory.getITRF(IERSConventions.IERS_2010, True)
        transform = FramesFactory.getGCRF().getTransformTo(itrf, date)
        itrf_pos = transform.transformPosition(pos)
        x = float(itrf_pos.getX()); y = float(itrf_pos.getY()); z = float(itrf_pos.getZ())
        iso = (epoch_py + datetime.timedelta(seconds=int(t))).strftime("%Y-%m-%dT%H:%M:%SZ")
        msg = {"type": "position", "time": iso, "position": [x, y, z], "sat": SAT_NAME}
        if clients:
            payload = json.dumps(msg)
            # broadcast
            for ws in clients.copy():
                try:
                    await ws.send_text(payload)
                except Exception:
                    try:
                        await ws.close()
                    except Exception:
                        pass
                    clients.remove(ws)
        await asyncio.sleep(STEP_SECONDS)
        t += STEP_SECONDS
        if t > PROP_SECONDS:
            # loop around for long-running demo
            t = 0.0

@app.on_event("startup")
async def startup_event():
    # start broadcaster background task
    asyncio.create_task(broadcaster())

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    clients.append(websocket)
    # send initial ground station list to client
    await websocket.send_text(json.dumps({"type": "stations", "stations": GROUND_STATIONS}))
    try:
        while True:
            # keep connection alive
            await websocket.receive_text()
    except Exception:
        try:
            await websocket.close()
        except Exception:
            pass
        if websocket in clients:
            clients.remove(websocket)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

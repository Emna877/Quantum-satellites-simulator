# QuantumSatellites Simulator

This repository contains a CubeSat orbit simulator with classical and QKD link models and a real-time CesiumJS visualization.
Files of interest

- `qkd.py` — main script that computes visibility windows, classical link SNR/capacity and a simple QKD model per-sample. Writes `comm_samples.csv`.
Requirements

Install dependencies into a virtual environment. On Windows PowerShell:
```powershell
python -m venv .venv_orekit
.\.venv_orekit\Scripts\Activate.ps1
Notes:
- `orekit` itself is Java-based. You must place the Orekit and Hipparchus JARs in the repository (so the scripts can find them via globbing `*.jar`). The `orekit-data` folder (provided) must be present.
Run the QKD simulation (batch)

```powershell
& .\.venv_orekit\Scripts\python.exe .\qkd.py
Start the real-time server and viewer

1. Start the server (this will also start the Orekit JVM and an internal propagator):
```powershell
& .\.venv_orekit\Scripts\python.exe .\realtime_server.py
```
2. Open the viewer in your browser:

- http://localhost:8000/realtime_viewer.html
- or (if you prefer the static mount) http://localhost:8000/static/realtime_viewer.html
How it works

- `realtime_server.py` computes satellite positions in Earth-fixed ECEF (ITRF) coordinates and broadcasts JSON messages over `/ws` WebSocket:
Next steps / tips

- For reproducible runs, set `AUTO_FIND_PASS = False` in `qkd.py` and use deterministic orbital elements/epoch.
- If you want the server to also stream per-sample classical/QKD metrics, I can refactor `qkd.py` into reusable functions and have `realtime_server.py` call them and stream additional JSON fields (e.g., `qber`, `key_rate`, `snr`, `capacity`).
- Consider running the server behind a reverse proxy or enabling TLS (wss) for secure remote access.

If you want, I can now:
- Refactor `qkd.py` to expose functions used by `realtime_server.py` so both use identical model parameters.
- Add UI controls to `realtime_viewer.html` to show QKD/classical metrics in real time.
# AI-Quantum-Secured-Satellite-Comms

Project that simulates a LEO CubeSat QKD link (BB84) with AI-based anomaly detection and CesiumJS visualization.


## Setup
See `setup_instructions.sh` for automated environment setup notes.

- A top-level `requirements.txt` is provided for Python dependencies.
- A top-level `.gitignore` has been added to avoid committing virtual environments, node_modules, editor configs, and build artifacts.

Recommended quick setup:
- Create and activate a virtual environment: `python -m venv .venv && .\.venv\Scripts\activate` (Windows) or `python3 -m venv .venv && source .venv/bin/activate` (Unix).
- Install Python deps: `pip install -r requirements.txt`

## Quick start (development)
- Backend: cd backend && pip install -r ../requirements.txt && uvicorn api.main:app --reload
- QKD test: python qkd/bb84_simulator.py
- AI test: python ai/model_train.py
- Orbit sim (Java): javac -cp lib/orekit.jar orekit/orbit_simulator.java && java -cp .;lib/orekit.jar OrbitSimulator
- Frontend: cd frontend && npm install && npm start

## Project structure
See repository root for folders: `backend/`, `qkd/`, `ai/`, `orekit/`, `frontend/`.

## Notes
This repository scaffold contains minimal "Hello World" skeletons. Replace placeholders with real implementations as needed.

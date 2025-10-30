# AI-Quantum-Secured-Satellite-Comms

Project that simulates a LEO CubeSat QKD link (BB84) with AI-based anomaly detection and CesiumJS visualization.


## Setup
See `setup_instructions.sh` for automated environment setup notes.

## Quick start (development)
- Backend: cd backend && pip install -r requirements.txt && uvicorn api.main:app --reload
- QKD test: python qkd/bb84_simulator.py
- AI test: python ai/model_train.py
- Orbit sim (Java): javac -cp lib/orekit.jar orekit/orbit_simulator.java && java -cp .;lib/orekit.jar OrbitSimulator
- Frontend: cd frontend && npm install && npm start

## Project structure
See repository root for folders: `backend/`, `qkd/`, `ai/`, `orekit/`, `frontend/`.

## Notes
This repository scaffold contains minimal "Hello World" skeletons. Replace placeholders with real implementations as needed.

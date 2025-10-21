from fastapi import FastAPI
from fastapi.responses import JSONResponse

from . import qkd_service, ai_service, satellite_service

app = FastAPI(title="AI-Quantum-Secured-Satellite-Comms API")


@app.get("/health")
def health():
    return JSONResponse({"status": "ok"})


@app.get("/qkd/run")
def run_qkd():
    summary = qkd_service.run_bb84_test()
    return JSONResponse(summary)


@app.get("/ai/infer")
def ai_infer():
    result = ai_service.run_inference()
    return JSONResponse(result)


@app.get("/sat/orbit")
def get_pass():
    czml = satellite_service.generate_sample_czml()
    return JSONResponse(czml)

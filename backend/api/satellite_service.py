import json

def generate_sample_czml():
    # Minimal CZML-like JSON for demo. Frontend Cesium can load this.
    czml = [
        {
            "id": "document",
            "version": "1.0"
        },
        {
            "id": "satellite",
            "name": "DemoSat",
            "position": {
                "cartesian": [7000000, 0, 0, 0, 0, 0]
            }
        }
    ]
    return czml

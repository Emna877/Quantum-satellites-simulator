import json

def export_sample_czml(path='frontend/czml/sample_pass.czml'):
    czml = [
        {"id": "document", "version": "1.0"},
        {"id": "sat1", "name": "DemoSat", "position": {"cartographicDegrees": [0, 0, 7000000]}}
    ]
    with open(path, 'w') as f:
        json.dump(czml, f, indent=2)
    print(f'Wrote sample CZML to {path}')


if __name__ == '__main__':
    export_sample_czml()

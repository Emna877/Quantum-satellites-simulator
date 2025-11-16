# Enhanced CZML Visualization Guide

## 🎨 What Was Created

### Files
1. **`export_czml_with_events.py`** - Enhanced CZML generator with event visualization
2. **`czml_viewer_enhanced.html`** - Interactive 3D viewer with event tracking
3. **`cubesat_with_events.czml`** - Generated CZML file with 3D event shapes

## 🌟 Event Visualizations

### Environmental Events (Blue-tinted)
- **☀️ Solar Flare** - Orange glowing ellipsoid around satellite
  - Size varies by severity (50-200m radius)
  - Color intensity: LOW=light orange → CRITICAL=bright red-orange
  
- **💥 Micrometeoroid Impact** - Small sphere with trajectory
  - Approaches from 5km away
  - Impact flash (yellow sphere, 0.5 seconds)
  - Trajectory trail visible
  
- **🌑 Eclipse Entry** - Dark blue sphere
- **🌞 Eclipse Exit** - Bright yellow sphere
- **🌪️ Atmospheric Drag** - (Generic marker)
- **⚡ Geomagnetic Storm** - (Generic marker)

### Attack Events (Red-tinted)
- **⚠️ GPS Spoofing** - Red warning cone/cylinder below satellite
  - Top radius: 20m, bottom: 50m, height: 100m
  - Yellow outline for visibility
  - Bold red label
  
- **🔴 Laser Dazzle** - Bright beam from ground to satellite
  - Red polyline (8px width)
  - Shows attack origin point on Earth
  - Duration: 30s - 5 minutes
  
- **📡 RF Jamming** - Flattened red ellipsoid (RF wave shape)
  - Dimensions: 200x200x80m
  - Pulsating appearance
  - Semi-transparent
  
- **💉 Command Injection** - Red box with warning label
- **🔋 Power Drain** - Red box marker
- **🌡️ Thermal Sabotage** - Red box marker

## 🎮 How to Use

### Method 1: Local Viewing (Recommended)
```bash
# 1. Generate CZML with events
python export_czml_with_events.py

# 2. Open the enhanced viewer
# Double-click: czml_viewer_enhanced.html
# Or open in browser: file:///path/to/czml_viewer_enhanced.html
```

### Method 2: Cesium Sandcastle
1. Go to https://sandcastle.cesium.com/
2. Click "Open File"
3. Upload `cubesat_with_events.czml`
4. Watch the 3D visualization

### Method 3: Upload to Cesium Ion
1. Go to https://ion.cesium.com/
2. Upload CZML file
3. Get shareable link

## 🎯 Viewer Features

### Control Panel (Top Right)
- **📁 Load CZML** - Load custom CZML files
- **⏯️ Play/Pause** - Toggle animation
- **🏠 Reset View** - Return to satellite overview

### Live Telemetry
- **Time** - Current simulation time
- **Speed** - Playback multiplier (1x - 100x)
- **Altitude** - Satellite altitude in km
- **Active Events** - Events currently affecting satellite
- **Total Events** - All events in timeline

### Event Log
- Real-time scrolling list
- Color-coded by type:
  - 🔴 Red border = Attack
  - 🔵 Blue border = Environmental
- Severity indicators: LOW (green) → CRITICAL (red)

### Keyboard Shortcuts
- **SPACE** - Play/Pause
- **R** - Reset view
- **↑** - Increase speed (2x)
- **↓** - Decrease speed (0.5x)

## 🔧 Customization

### Adding More Event Types

Edit `export_czml_with_events.py`:

```python
def create_custom_event_viz(event_id, timestamp, sat_pos, ...):
    return [{
        "id": f"custom-{event_id}",
        "position": {"cartesian": list(sat_pos)},
        "ellipsoid": {  # or "box", "cylinder", "polyline"
            "radii": {"cartesian": [100, 100, 100]},
            "material": {
                "solidColor": {
                    "color": {"rgba": [255, 0, 255, 200]}  # Purple
                }
            }
        },
        "label": {
            "text": "Custom Event",
            "fillColor": {"rgba": [255, 0, 255, 255]}
        }
    }]
```

### Available CZML Shapes
- **Ellipsoid** - Spheres/ellipses (solar flares, jamming)
- **Box** - Cubic markers (warnings, attacks)
- **Cylinder** - Tubes (cones, beams)
- **Polyline** - Lines (laser beams, trajectories)
- **Point** - Simple markers
- **Billboard** - 2D images
- **Model** - 3D GLTF models (future enhancement)

### Color Schemes
```javascript
// RGBA format [Red, Green, Blue, Alpha]
[255, 0, 0, 255]     // Solid red (attacks)
[255, 165, 0, 200]   // Semi-transparent orange (solar flares)
[0, 150, 255, 180]   // Semi-transparent blue (environmental)
[255, 255, 0, 255]   // Yellow (warnings)
```

## 📊 Integration with Full Simulation

### Option 1: Real-time CZML Updates
```python
# In simulation loop
def update_czml_stream(state, events, timestamp):
    # Generate CZML packets for current state
    packets = []
    packets.append(update_satellite_position(state))
    for event in events:
        packets.append(create_event_viz(event))
    
    # Send via WebSocket or write to file
    websocket.send(json.dumps(packets))
```

### Option 2: Post-Simulation Export
```python
# After simulation completes
from export_czml_with_events import create_czml_document

# Use actual propagated positions from Orekit
sat_positions = [(dt, x, y, z) for dt, x, y, z in simulation_results]

# Use actual events from EventManager
event_log = manager.export_event_log()

# Create CZML
czml = create_czml_document(sat_positions, event_log, duration)
with open('simulation_results.czml', 'w') as f:
    json.dump(czml, f)
```

### Option 3: Live Streaming (Future)
- WebSocket server in `realtime_server.py`
- Send CZML packets at 1-10 Hz
- Viewer updates in real-time

## 🎨 Visual Examples

### Solar Flare Event
```
      ☀️ Label
       ╱│╲
      ╱ │ ╲
     ╱  🛰️  ╲    ← Orange glowing ellipsoid
    ╱   │   ╲      (semi-transparent)
   ╱____│____╲
```

### Micrometeoroid Impact
```
  💥→→→🛰️           ← Trajectory with trail
  ↑                 Yellow impact flash
  5km away          Gray 2m sphere
```

### Laser Attack
```
     🛰️              ← Satellite
      ▼
   🔴🔴🔴            ← Red beam (polyline)
      ▼
   🌍 Ground         ← Attack origin
```

### GPS Spoofing
```
     🛰️              ← Satellite
      ▲
     ╱ ╲             ← Red warning cone
    ╱   ╲               (cylinder)
   ╱_____╲
```

## 📈 Performance Tips

1. **Reduce sampling rate** for longer simulations:
   ```python
   step = 60  # 60 seconds instead of 30
   ```

2. **Limit event visibility duration**:
   ```python
   duration = min(event.duration_seconds, 300)  # Max 5 minutes
   ```

3. **Use simpler shapes** for many events:
   - Point instead of Ellipsoid
   - Billboard instead of 3D model

4. **Batch events** - Group similar events:
   ```python
   if len(solar_flares) > 10:
       # Show aggregate indicator instead
   ```

## 🐛 Troubleshooting

### CZML file doesn't load
- Check JSON syntax: `python -m json.tool cubesat_with_events.czml`
- Verify timestamps are in ISO8601 format
- Ensure positions are in meters (not km)

### Events not visible
- Check availability intervals
- Verify position coordinates are in ECEF frame
- Increase shape size (radii values)
- Check color alpha channel (> 100 for visibility)

### Performance issues
- Reduce number of position samples
- Simplify event shapes
- Use lower polygon resolution
- Disable terrain (`terrainProvider: false`)

## 🚀 Next Steps

1. **Integrate with Orekit** - Use actual orbital propagation
2. **Add more event types** - Thermal, power, debris
3. **Interactive controls** - Click events for details
4. **Data export** - Save screenshots, telemetry CSV
5. **Multi-satellite** - Add ground stations, other satellites
6. **3D Models** - Custom GLTF models for satellite
7. **Particle systems** - Advanced effects (future Cesium feature)

## 📚 Resources

- [Cesium CZML Guide](https://github.com/AnalyticalGraphicsInc/czml-writer/wiki/CZML-Guide)
- [CZML Schema](https://github.com/AnalyticalGraphicsInc/czml-writer/wiki/CZML-Content)
- [Cesium Sandcastle](https://sandcastle.cesium.com/) - Examples
- [Cesium Forum](https://community.cesium.com/) - Support

---

**Status:** ✅ Phase 2.5 Enhanced Visualization Complete

*Ready to visualize satellite events in beautiful 3D!* 🌍🛰️✨

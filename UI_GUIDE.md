# Threat Analysis Console: running and testing

The main interface is now the local **Threat Analysis Console**. Keep `czml_viewer.html` for checking a simple orbit and `czml_viewer_enhanced.html` for the older CZML event demonstration. Neither legacy page is needed for the console.

## 1. Start the application

Open PowerShell in the project directory:

```powershell
cd C:\Users\Emna\Documents\QuantumSatellites
.\.venv\Scripts\Activate.ps1
python -m scripts.check_runtime
python -m scripts.serve_console --port 8000
```

The runtime check should end in PASS. Leave the server terminal open and visit **http://127.0.0.1:8000** in Chrome or Edge. Use this server rather than `python -m http.server`: it also provides the simulation API. Stop it with Ctrl+C when finished. If port 8000 is occupied, choose `--port 8001` and open the matching address.

The globe requires internet access for Cesium and map imagery, and a browser with WebGL enabled. No Cesium account/token is required by the configured imagery provider. Fonts have system fallbacks. If the renderer fails, the application displays an explanation; recorded data, charts, imports and exports remain usable.

## 2. Generate a real experiment

1. Open **Settings**. Keep the initial orbit, Tunis station, 24-hour duration and 60-second sample interval for the first run. The default epoch is a simulation date, not today's date.
2. Select **RF jamming / moderate** in the left sidebar. This compares the unchanged baseline with an additional RF loss condition.
3. Press **Run experiment**. Wait for the Orekit worker to finish. An existing recording stays visible while a replacement is computed. A failed run displays its error rather than generating substitute data.
4. The completed recording opens at its first station contact, if one exists. The latest completed recording is loaded again on a page refresh.
5. Confirm the console says **SIMULATION / NOT LIVE**. Its UTC clock follows the experiment, not your computer clock.

Python computes one shared orbital reference and evaluates both cases at matching communication timestamps. Each worker uses a separate process because the Java bridge cannot restart a JVM inside one Python process. Requests are bounded to keep local experiments manageable.

## 3. Check each workspace

| Workspace | What to try | Expected behavior |
|---|---|---|
| Overview | Drag the globe, follow the satellite, toggle scene layers | Earth, orbit, station and contact path use recorded Orekit positions. A contact path indicates geometry, not secure communication. |
| Threat Analysis | Inspect the disturbance and click an event | The inspector identifies targets, timestamps and model assumptions. The RF loss condition is explicitly labeled run-wide. Prototype attack markers are labeled marker-only. |
| Communication | Choose a contact and compare baseline/scenario curves | RF SNR changes under RF jamming; optical values remain unchanged for this RF-only scenario. Unavailable RF links are legitimate results. |
| QKD Laboratory | Inspect detection, QBER, key-rate curves and pass estimates | Zero keys and aborted estimates remain visible. Finite-pass estimates and buffer snapshots are not presented as instantaneous measurements. |
| Events | Filter records and click a row | Playback seeks to its timestamp; the inspector shows its explicit subsystem scope. Counts represent unique events. |
| Analysis & Reports | Review pass tables, availability, history and downloads | Summaries use actual recorded values. Unsupported delivery/security metrics are explained rather than invented. |
| Settings | Change aperture or background, then run again | Python recomputes results. Editing a field alone never changes an existing recording. |

The sidebar shows the timestamp of the physical sample being inspected. The globe interpolates between recorded positions for smooth animation; numerical telemetry uses the most recent recorded sample. Contact boundaries and communication sample instants are included in the physical recording.

## 4. Test synchronized playback

1. Press **Next contact** to seek to a visible station pass.
2. Press Play, then Pause. Confirm that the clock and numerical telemetry stop changing.
3. Change speed and resume. This changes playback speed; it does not recompute physics.
4. Drag the shared timeline, or use the previous/next sample buttons. Space toggles playback; arrow keys step when you are not editing a field.
5. Open Communication or QKD Laboratory and click a chart. The same UTC clock, globe, event inspector and chart cursors follow that time.
6. Seek outside a contact. Communication values should show no contact rather than reuse the last successful link measurement.

## 5. Test negative results and isolation

Run **Optical cloud blocked** next. Optical detection/key results should reflect blockage, while the RF model is computed independently. Then try **Optical interference**: background light can increase errors and eliminate estimated key production. Do not expect QKD to win every scenario.

The existing runner applies scenario channel overrides throughout the run. Scheduled prototype event times do **not** currently switch those conditions on/off, and those markers are not engine-applied attacks. The console discloses this distinction. Power/navigation/combined scenarios are engineering surrogates, not validated spacecraft damage or detection models.

## 6. Export and reload

Use **Export JSON** for the complete console record, or Analysis & Reports for telemetry CSV, events JSON, scenario results and a text summary. Import the complete console JSON and confirm the same timeline and results reappear. Exported zero values must stay zero.

Worker records are stored in `data/console_runs/<run-id>/`:

- `request.json`: requested inputs;
- `run.json`: UTC geometry, both result cases, events, model configuration, provenance and limitations;
- `worker.log`: runtime diagnostics.

The console format is `console_run.v1`. The existing version-1.0 physical experiment contract can also be imported; absent communication results remain unknown. A standalone legacy channel-result JSON is insufficient to reconstruct an orbital recording and is rejected. Non-finite numerical results become JSON null with their original field paths recorded in `non_finite_metrics`; they are never turned into successful measurements.

## 7. Run automated checks

In a second activated PowerShell terminal:

```powershell
python -m unittest discover -s scripts -p "test_*.py"
node --test scripts/test_console.mjs
```

Node is only needed for the frontend data-logic tests, not to serve or use the application. To include a real **RF jamming / moderate** recording in those checks (the optional integration assertions expect that scenario's 20 dB RF-only loss):

```powershell
$env:CONSOLE_RUN = "data/console_runs/<your-run-id>/run.json"
node --test scripts/test_console.mjs
```

Checks cover request validation, localhost API boundaries, import validation, timestamp alignment, no future-data leakage, contact handling, time-weighted availability and preservation of zero/negative results. Existing scientific regressions remain part of the Python suite. Browser layout, camera controls and actual WebGL rendering still require the manual checks above; automated browser verification was unavailable in the implementation session.

## Concepts and scientific limits

- **Orekit / orbital truth:** Python's orbital library supplies where the satellite really is in the model. The UI displays those results instead of creating another orbit.
- **UTC:** one shared time reference, preventing plots, attacks and satellite positions from drifting apart.
- **Contact / elevation:** a station can see the satellite above a configured angle over its horizon. Visibility alone does not guarantee a usable channel.
- **RF / SNR:** the radio data channel and its signal strength relative to noise. Shannon capacity is a mathematical upper limit, not delivered application data.
- **Optical / QBER:** photons form the quantum channel; QBER is the fraction of estimated wrong bits. Loss and noise can leave no usable secret key.
- **QKD versus encryption:** QKD aims to establish keys. It does not replace data encryption, and it needs authenticated ordinary communication. A fair future comparison uses the same application encryption in both modes and changes the key-establishment method.
- **Availability versus security:** receiving a signal says nothing by itself about confidentiality, tampering, sender identity or whether a key is secure.

The console is implemented, but the platform is not yet a validated end-to-end security experiment. Actual ECDH/AES-GCM packet exchanges, authenticated QKD post-processing, replay tests and a rigorous finite-key/decoy-state implementation are missing. The runner does not enforce its authenticated QKD classical-channel dependency. Its current key buffer uses asymptotic replenishment and exposes only pass-end snapshots. Neither the simplified finite-key estimate nor a positive key count proves security. The optical model still needs independent reference validation.

Next, preserve the TODO milestone order: validate the physical/communication foundation, connect time-scoped events to the paired runner, enforce channel dependencies, validate key accounting, and then implement the shared application encryption and controlled protocol attacks. Add delivery, integrity/authentication and recovery metrics only when the models actually produce them. Spatial jammer footprints, corrupted navigation vectors and richer threat visuals should follow real model outputs. Detailed subsystem physics and ML remain deferred unless a defined experiment needs them.

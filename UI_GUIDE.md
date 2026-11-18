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

Python computes one shared orbital reference and evaluates the baseline and the chosen scenario at matching communication timestamps. It also runs **every** scenario under 9 optical-uncertainty variants (sky background × 0.5/1/2, zenith atmospheric loss × 0.5/1/2) on the same cached geometry for the results table; this adds a few seconds. Each worker uses a separate process because the Java bridge cannot restart a JVM inside one Python process. Requests are bounded to keep local experiments manageable.

## 3. Check each view

The console has four tabs: Globe, Pass explorer, Results, and Model & assumptions. Events, History and Settings live in a side drawer (**☰ Events · History · Settings**, or press Escape to close it).

| View | What to try | Expected behavior |
|---|---|---|
| Globe | Drag the globe, follow the satellite, toggle scene layers, press Play | Full-screen Earth, orbit, ground track, station and contact path from recorded Orekit positions. A contact path indicates geometry, not secure communication. |
| Results | Read the method cards, the results table and the key figure | One row per scenario: ECDH and ML-KEM sessions, QKD key (nominal and sweep range), passes with key, an "attack detected?" verdict and the main abort reason. The loaded scenario row is highlighted. |
| Pass explorer | Choose a contact, click a chart | ECDH / ML-KEM / QKD cards and six baseline-vs-scenario charts, with telemetry and playback still visible. "Now" values follow the cursor, "this pass" values cover the contact. |
| Model & assumptions | Check the Micius table and the formulas | Every formula has a source; every parameter of this run is listed; the five Micius checks show model vs paper with tolerance. |
| Drawer · Events | Filter and click an event; tick "Show surrogate attack markers" | Surrogate markers (scheduled times that do not change results) are hidden by default and appear on the globe and timeline only when ticked. |
| Drawer · History | Load an earlier run | Older runs without a results table still open; the Results tab says so. |
| Drawer · Settings | Change aperture or background, then run again | Python recomputes results. Editing a field alone never changes an existing recording. |

The sidebar shows the timestamp of the physical sample being inspected. The globe interpolates between recorded positions for smooth animation; numerical telemetry uses the most recent recorded sample. Contact boundaries and communication sample instants are included in the physical recording.

### Executed cryptography and event-level BB84

The two detailed runs (baseline and the scenario chosen on the left) also execute real cryptography and simulate BB84 photon by photon. A run therefore takes about 30–40 s instead of a few seconds.

1. Run **RF Jamming (Moderate)** or **QKD Intercept-Resend (20 %)**, then open **Results** and scroll to the bottom.
2. **Executed cryptography** lists, per method, how many passes ran a real handshake and whether the decryption, tamper, header-change, forgery and replay checks passed. Every ✓ must read n/n.
3. **Event-level BB84: formula vs simulation** compares the formula prediction with the simulated sifted bits, QBER and secret key per pass. QBER should agree within a few tenths of a percent; the simulated key is usually 0–25 % smaller because real error correction leaks more than the formula assumes.
4. In the **Pass explorer**, the ECDH and ML-KEM cards show the executed handshake time and attack results; the QKD card shows simulated vs formula QBER and key, and whether a message encrypted with the QKD key was sent.

## 4. Test synchronized playback

1. Press **Next contact** to seek to a visible station pass.
2. Press Play, then Pause. Confirm that the clock and numerical telemetry stop changing.
3. Change speed and resume. This changes playback speed; it does not recompute physics.
4. Drag the shared timeline, or use the previous/next sample buttons. Space toggles playback; arrow keys step when you are not editing a field.
5. Open the Pass explorer and click a chart, then switch to the Globe tab. The same UTC clock drives the globe, event inspector and chart cursors.
6. Seek outside a contact. Communication values should show no contact rather than reuse the last successful link measurement.

## 5. Test negative results and isolation

Run **Optical cloud blocked** next. Optical detection/key results should reflect blockage, while the RF model is computed independently. Then try **Optical interference**: background light can increase errors and eliminate estimated key production. Do not expect QKD to win every scenario.

The existing runner applies scenario channel overrides throughout the run. Scheduled prototype event times do **not** currently switch those conditions on/off, and those markers are not engine-applied attacks. The console discloses this distinction. Power/navigation/combined scenarios are engineering surrogates, not validated spacecraft damage or detection models.

## 6. Export and reload

On the Results tab, export the results table (CSV), the full run (JSON), detailed samples (CSV) and a text summary. Every chart has **↧ SVG** and **↧ PNG** buttons that export a white-background figure with title, axis titles, units and legend, ready for a paper. Import the complete console JSON and confirm the same timeline and results reappear. Exported zero values must stay zero.

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

The console is implemented, but the platform is not yet a validated end-to-end security experiment. Actual ECDH/ML-KEM/AES-GCM packet exchanges, executed QKD post-processing messages, replay tests and a composable finite-size decoy-state analysis are missing. The runner enforces the QKD dependency on the authenticated RF channel as a time and traffic check. The key buffer uses asymptotic replenishment gated by RF availability and exposes only pass-end snapshots. Neither the finite-key estimate nor a positive key count proves security. The optical and finite-key models are checked against the published Micius results (scripts/test_validation_micius.py), but not against other stations or daytime operation.

Next, preserve the TODO milestone order: validate the physical/communication foundation, connect time-scoped events to the paired runner, validate key accounting, and then implement the shared application encryption and controlled protocol attacks. Add delivery, integrity/authentication and recovery metrics only when the models actually produce them. Spatial jammer footprints, corrupted navigation vectors and richer threat visuals should follow real model outputs. Detailed subsystem physics and ML remain deferred unless a defined experiment needs them.

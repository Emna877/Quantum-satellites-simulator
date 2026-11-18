# Threat Analysis Console: running and testing

## 1. Start the application

Open PowerShell in the project directory:

```powershell
cd C:\Users\Emna\Documents\QuantumSatellites
.\.venv\Scripts\Activate.ps1
python -m scripts.check_runtime
python -m scripts.serve_console --port 8000
```

The runtime check should end in PASS. Leave the server terminal open and visit **http://127.0.0.1:8000** in Chrome or Edge. Use this server rather than `python -m http.server`: it also provides the simulation API. Stop it with Ctrl+C when finished. If port 8000 is occupied, choose another port (for example `--port 8001`) and open the matching address.

The globe needs internet access for Cesium and map imagery, and a browser with WebGL. No Cesium account or token is required. If the 3D renderer fails, the console says so; recorded data, charts, imports and exports remain usable.

## 2. Generate an experiment

1. Open **☰ Events · History · Settings → Settings**. Keep the default orbit, Tunis station, 24-hour duration and 60-second sample interval for a first run. The default epoch is a simulation date, not today's date.
2. Choose a scenario in the left sidebar, for example **RF Jamming (Moderate)**. Choosing a scenario starts a run straight away; **Run experiment** reruns with the current settings.
3. While the run computes (about 30–40 s; about 20 s for the baseline alone), a loading box shows photons travelling down a beam, with a progress bar, the current step (for example "pass 2 of 5") and the estimated time left, based on recent runs on the same server. The previous recording stays visible until the new one is ready. A failed run shows its error rather than substitute data.
4. The new recording starts at the beginning of its timeline and plays automatically. On a page refresh, the latest recording is loaded again.
5. The console says **SIMULATION · NOT LIVE**: its UTC clock follows the experiment, not your computer clock.

Each run computes one shared orbit and then:

- the **baseline** and the **chosen scenario** in detail, with real cryptography executed and BB84 simulated photon by photon;
- **every** scenario under 9 optical-uncertainty variants (sky background × 0.5/1/2, zenith atmospheric loss × 0.5/1/2) with the fast formulas, for the results table.

Each run uses a separate worker process because the Java bridge cannot restart inside one Python process.

## 3. Check each view

The console has four tabs: Globe, Pass explorer, Results, and Model & assumptions. Events, History and Settings live in a side drawer (**☰ Events · History · Settings**; Escape closes it).

| View | What to try | Expected behavior |
|---|---|---|
| Globe | Drag the globe, use Free orbit / Follow satellite / Reset view, toggle scene layers | Full-screen Earth with the satellite's past orbit, the station and the contact path from recorded Orekit positions. The ground track is off until ticked. A contact path indicates geometry, not secure communication. |
| Pass explorer | Choose a contact, click a chart | ECDH / ML-KEM / QKD cards and six baseline-vs-scenario charts, with telemetry and playback still visible. "Now" values follow the cursor; "this pass" values cover the contact. |
| Results | Read the method cards, the results table, the key figure and the tables at the bottom | One row per scenario: ECDH and ML-KEM sessions, QKD key (nominal and sweep range), passes with key, an "attack detected?" verdict and the main abort reason. The loaded scenario row is highlighted. |
| Model & assumptions | Check the Micius table and the formulas | Every formula has a source; every parameter of this run is listed; the five Micius checks show model vs paper with tolerance. |
| Drawer · Events | Filter and click an event; tick "Show surrogate attack markers" | Surrogate markers (scheduled times that do not change results) are hidden by default. |
| Drawer · History | Load an earlier run | Older runs without newer sections still open; missing tables are explained. The local server lists every run; a public deployment (started with `--host 0.0.0.0`) lists only the runs started in the same browser, so each visitor starts with an empty console. |
| Drawer · Settings | Change aperture or background, then **Run with these settings** | Python recomputes results. Editing a field alone never changes an existing recording. |

### Executed cryptography and event-level BB84

1. Run **QKD Intercept-Resend (20 %)** or **RF Jamming (Moderate)**, open **Results** and scroll to the bottom.
2. **Executed cryptography** lists, per method, how many passes ran a real handshake and whether the decryption, tamper, header-change, forgery and replay checks passed. Every ✓ must read n/n. A "—" means the step never happened (for example, no radio link, so no handshake).
3. **Event-level BB84: formula vs simulation** compares the formula prediction with the simulated sifted bits, QBER and secret key per pass. QBER should agree within a few tenths of a percent; the simulated key is usually 0–25 % smaller because real error correction leaks more than the formula assumes.
4. In the **Pass explorer**, the ECDH and ML-KEM cards show the executed handshake time and attack results; the QKD card shows simulated vs formula QBER and key, and whether a message encrypted with the QKD key was sent.

## 4. Test synchronized playback

1. Press **Next contact** to jump to a station pass.
2. Pause and play with ▶ or Space. Confirm that the clock and telemetry stop and resume.
3. Change speed and resume. This changes playback speed; it does not recompute physics.
4. Drag the timeline or use the previous/next sample buttons (← →). Seeking pauses playback.
5. Click a chart in the Pass explorer, then switch to the Globe tab. The same UTC clock drives the globe, event inspector and chart cursors.
6. Seek outside a contact. Communication values should show "No contact" rather than reuse the last measurement.

## 5. Test negative results and isolation

Run **Optical Path Blocked (Cloud)**: QKD produces no key while the RF methods keep working. Run **Optical Interference (LaserDazzle)**: background light raises the QBER above 11 % and QKD aborts. Run **Classical Authentication Dependency**: the radio is jammed, so ECDH and ML-KEM fail, and QKD also produces no key because its post-processing needs the radio. Do not expect QKD to win every scenario.

Scenario disturbances apply to the whole run; scheduled event times do not switch them on or off.

## 6. Export and reload

On the Results tab, export the results table (CSV), the full run (JSON), detailed samples (CSV) and a text summary. Every chart has **↧ SVG** and **↧ PNG** buttons that export a white-background figure with title, axis titles, units and legend. Import the full JSON with **Import run** and confirm the same timeline and results reappear. Exported zero values must stay zero.

Runs are stored in `data/console_runs/<run-id>/`:

- `request.json`: requested inputs;
- `run.json`: UTC geometry, both detailed cases, the scenario study, the model card, events, configuration, provenance and limitations;
- `worker.log`: runtime diagnostics.

Non-finite numbers become JSON null, with their field paths recorded in `non_finite_metrics`; they are never turned into successful measurements.

## 7. Run automated checks

In a second activated PowerShell terminal, run the test command from the README, then:

```powershell
node scripts/test_console.mjs
```

Node is only needed for these front-end data tests, not to run the console. Browser layout, camera controls and WebGL rendering still need the manual checks above.

## Concepts

- **Orekit / orbital truth:** the orbit library supplies where the satellite is. The browser displays those results instead of computing another orbit.
- **UTC:** one shared time reference, so plots, attacks and satellite positions stay aligned.
- **Contact / elevation:** the station can see the satellite above a minimum angle over its horizon. Visibility alone does not guarantee a usable channel.
- **RF / SNR:** the radio channel and its signal strength relative to noise. Shannon capacity is a theoretical upper limit, not delivered data.
- **Optical / QBER:** photons form the quantum channel; QBER is the fraction of compared bits that disagree. Above 11 %, BB84 aborts.
- **QKD versus encryption:** QKD establishes keys; AES-256-GCM still encrypts the data. QKD also needs an authenticated radio link for its post-processing.
- **Availability versus security:** a failed link is a loss of availability, not a loss of secrecy. Receiving a signal says nothing by itself about confidentiality or authenticity.

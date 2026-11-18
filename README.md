# Quantum Satellites Simulator

A reproducible satellite cybersecurity threat-analysis platform. It compares three ways to establish a secret key between a low-Earth-orbit satellite and a ground station in Tunis, on the same Orekit orbit and the same passes, under controlled attacks:

1. **Pre-quantum classical**: ECDH P-256 over the RF link (breakable by a future quantum computer).
2. **Post-quantum classical**: ML-KEM-768 (NIST FIPS 203) over the RF link.
3. **Quantum key distribution**: decoy-state BB84 over an optical link, with post-processing over the authenticated RF link.

The every-scenario results table uses fast formulas. The scenario inspected in detail is also **executed**: real ECDH, ML-KEM-768 and AES-256-GCM sessions (via the `cryptography` library) are attacked with tampered, forged and replayed packets, and BB84 is **simulated photon by photon** (random bits and bases, sifting, error correction, privacy amplification), so formula predictions can be compared with simulated outcomes.

## Threat Analysis Console

```powershell
.\.venv\Scripts\Activate.ps1
python -m scripts.serve_console --port 8000
```

Open **http://127.0.0.1:8000**. The console has four tabs:

- **Globe**: full-screen Cesium Earth with the Orekit orbit, ground station and shared UTC playback.
- **Pass explorer**: ECDH / ML-KEM / QKD cards and baseline-vs-scenario charts for the selected pass.
- **Results**: one row per scenario for ECDH, ML-KEM and QKD, with an uncertainty range, an "attack detected?" column, executed-cryptography results and formula-vs-simulation BB84 tables.
- **Model & assumptions**: formulas with citations, run parameters and the Micius validation.

Events, history and settings are in a side drawer. Tables export as CSV and charts as publication SVG/PNG. All calculations happen in Python; the browser only displays recorded outputs. See [UI_GUIDE.md](UI_GUIDE.md) for a walkthrough and manual checks.

## Setup

Use Python 3.10+ with a 64-bit Java installation (Java 9+; Java 25 is verified). From the project root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m scripts.fetch_dependencies
```

`fetch_dependencies` downloads Orekit 13.1.2 and the matching Hipparchus 4.0.2 JAR files from Maven Central into the project root and verifies their SHA-1 checksums; the JARs are not stored in git. The Orekit data bundle (`orekit-data/orekit-data-main`) stays in git so every run uses the same Earth-orientation and ephemeris files.

## Configuration

Defaults work from the repository location. Optionally copy `.env.template` to `.env` and edit it; existing environment variables override `.env`. Relative paths are resolved against PROJECT_DIR.

JVM selection order:

1. Explicit JVM_PATH: the JVM shared library, not java.exe.
2. JAVA_HOME: the selected Java installation directory.
3. Automatic discovery: compatible Java installations on PATH, standard Windows installation folders, and JPype's default.

On Windows, JPype's registry default can point to Java 8 even when `java -version` reports a newer Java; an explicit Java 8 override is rejected with a clear error. To select Java explicitly in `.env`:

```text
JVM_PATH=C:/Program Files/Java/jdk-25/bin/server/jvm.dll
```

The default orbit, epoch and console inputs (altitude, inclination, station, power, telescope, background) can also be changed per run in the console's Settings drawer.

## Verify

```powershell
python -m scripts.check_runtime
python -m unittest scripts.test_runtime_config scripts.test_orbit scripts.test_engine_events scripts.test_experiment_schema scripts.test_communication scripts.test_security scripts.test_console scripts.test_validation_micius scripts.test_study scripts.test_crypto_exec scripts.test_bb84_event
node scripts/test_console.mjs
```

The runtime check loads the JAR files and Orekit data, propagates a satellite for 60 seconds, and prints PASS. It runs in its own process because JPype cannot restart a stopped JVM. Python may print `Could not find platform independent libraries <prefix>` and Java may print a native-access warning; both are harmless.

## Layout

- `console/`: the browser interface (HTML, CSS, JavaScript, logo).
- `config/`: environment loading, paths, validation, Java discovery.
- `simulation/`: satellite state and the shared Orekit propagator.
- `communication/`: `rf_link.py` (RF link budget), `optical_link.py` (quantum optical beam, detector gating, decoy-state and intercept-resend model), `qkd_model.py` (asymptotic BB84 key rate), `channel_effects.py` (attack → channel mapping).
- `security/`: `classical_session.py` (ECDH and ML-KEM session models), `crypto_exec.py` (executed handshakes and AES-256-GCM with attacks), `qkd_finite_key.py` (finite-key BB84), `bb84_protocol.py` (event-level BB84 and the QKD key pool), `key_store.py` (key buffer).
- `experiments/`: scenarios, paired runner, every-scenario study, model card, Micius validation, console adapter, record schema.
- `events/`: scheduled attack and environment event presets (shown as optional surrogate markers; they do not drive results).
- `scripts/`: console server, dependency download, runtime check, and the test suites.

Older standalone tools from before the console (`czml_viewer*.html`, `export_czml*.py`, `exports/`, `qkd.py`, `run_experiment.py`, `examples/`) are not needed to use the project.

Licensed under the MIT License; see [LICENSE](LICENSE).

## Communication and security models

| Model | File | Main assumptions |
|---|---|---|
| RF link | `communication/rf_link.py` | Friis + kTB noise; 1 W, 10 dBi satellite, 48 dBi (≈3 m dish) X-band ground station; Shannon capacity as upper bound |
| Optical link | `communication/optical_link.py` | Gaussian beam, airmass atmosphere, fixed pointing/optics loss; background clicks gated by the detection window and wrong half the time |
| Decoy-state single-photon bounds | `communication/optical_link.py` | Infinite-decoy limit (Lo, Ma & Chen 2005) |
| Asymptotic key rate | `communication/qkd_model.py` | GLLP: Δ1 (1 − H2(e1)) − f H2(E) |
| Finite-key length | `security/qkd_finite_key.py` | Tomamichel et al. (2012) error-rate bound; decoy yields with infinite statistics (not a composable decoy proof) |
| Classical sessions | `security/classical_session.py` | ECDH-P256 / ML-KEM-768 / hybrid; FIPS 203/204 message sizes; PSK or certificate authentication |
| QKD → RF dependency | `experiments/runner.py` | A pass yields QKD key only if the RF link is available ≥ 10 s and can carry the post-processing traffic |
| Intercept-resend attack | `communication/optical_link.py` | Error on intercepted bits 1/4 + e_d/2; full interception gives QBER ≈ 25 % |
| Executed cryptography | `security/crypto_exec.py` | Real ECDH / ML-KEM-768 / X25519+ML-KEM handshakes with PSK or ECDSA / ML-DSA-65 authentication, HKDF, AES-256-GCM; tamper, header-change, forgery and replay attempts must all fail |
| Event-level BB84 | `security/bb84_protocol.py` | Poisson detections, random bits and bases, intercept-resend, sifting, sampled QBER, Cascade-style error correction with measured leakage, Toeplitz privacy amplification; seeded and reproducible |
| Uncertainty sweep | `experiments/study.py` | Every scenario × sky background (×0.5/1/2) × zenith atmospheric loss (×0.5/1/2) on one cached geometry |

**Validation against Micius** (Liao et al. 2017, `scripts/test_validation_micius.py`). Using the paper's published link budget, the model reproduces the measured sifted key rates (≈12 kbit/s at 645 km, ≈1 kbit/s at 1200 km) within a factor of 2, the measured QBER range (1–3 %), and the reported 300,939-bit final key of the 273 s pass within 50 %. An ideal Gaussian beam with the quoted 10 µrad divergence gives 18.6 dB diffraction loss at 1200 km, 3.4 dB less than the paper's own 22 dB estimate. The night-time sky background (500 counts/s before gating) is an assumption; the paper does not report it.

## Orbital model

The shared orbit is an analytical two-body Keplerian orbit; J2, drag and solar radiation pressure are not enabled. Positions and velocities come from Orekit in the Earth-fixed ITRF frame, with UTC timestamps. Eclipses use Orekit's EclipseDetector (full umbra). Station visibility uses Orekit's ElevationDetector at the configured minimum elevation (5° by default), including contacts already in progress at the start or end of a run.

A 24-hour run from the default epoch gives five Tunis contacts above 5°. In the baseline scenario, four of them yield a finite-key QKD key; the 5.8° grazing pass aborts on finite-size statistics.

## Main limitations

- Scenario disturbances apply to the whole run, not to specific minutes; the scheduled event markers do not drive results.
- One ground station, night-time optical conditions and a single day per run; no weather statistics.
- Decoy-state statistics are not finite-size (Lim et al. 2014 is not implemented); error correction is Cascade-style without back-tracking.
- Executed cryptography covers one handshake and one 1 KiB message per pass; it does not model a traffic load or rekeying.
- No result is a security proof.

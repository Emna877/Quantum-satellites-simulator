# Architecture

How the simulator is organised, which rules keep the comparison fair, and where each result comes from.

## Data flow

```
Settings (console)  →  experiments/console.py  (worker process, one per run)
                         │
                         ├─ simulation/propagator.py   Orekit orbit, station geometry, contacts, eclipses
                         │
                         ├─ experiments/runner.py      per pass and per sample:
                         │     communication/  rf_link, optical_link, qkd_model, channel_effects
                         │     security/       classical_session, qkd_finite_key, key_store
                         │     detailed runs:  crypto_exec (executed sessions), bb84_protocol (event-level BB84)
                         │
                         ├─ experiments/study.py       every scenario × optical uncertainty sweep (formulas only)
                         ├─ experiments/model_card.py  formulas, parameters, Micius validation
                         │
                         └─ data/console_runs/<id>/run.json   (console_run.v1)
                                                         ↓
                                             console/ (browser: displays only)
```

## Shared truth

- **One orbit, one clock.** Every model receives the same UTC instant and the same Orekit geometry (range, elevation, eclipse). Communication and security models never advance their own clock or recompute the orbit.
- **The browser computes nothing scientific.** It reads `run.json` and displays it. Charts, tables and the globe all use the same recorded values.
- **Negative results are kept.** No contact, zero key, protocol aborts and failed sessions stay in the records and in the denominators. Zero is a real value; a missing step is shown as "—".
- **Non-finite numbers** become JSON null, with their paths listed in `non_finite_metrics`.

## Three logical channels

| Channel | Purpose | Model |
|---|---|---|
| `rf_data` | ECDH and ML-KEM handshakes and application data | `communication/rf_link.py`: Friis link budget, noise, SNR, Shannon capacity |
| `quantum_optical` | QKD photons | `communication/optical_link.py`: beam spreading, atmosphere, pointing, optics, detectors, gated background, decoy bounds, intercept-resend |
| `qkd_classical_protocol` | QKD sifting, error correction and privacy amplification | Carried over the authenticated RF link; the runner credits QKD key only if RF is available ≥ 10 s and can carry the post-processing traffic |

Disturbances are scoped to one channel (`communication/channel_effects.py`): jamming affects RF only, laser dazzle and clouds affect the optical link only. There is no implicit cross-channel effect; the only coupling is the explicit QKD → RF dependency above.

## Fair comparison

- All three methods use the **same orbit, passes, station and scenario**. Only the key-establishment method changes.
- ECDH and ML-KEM use the same authentication policy (PSK by default), the same HKDF key derivation and the same AES-256-GCM data protection.
- Event-level BB84 uses the **same random seed per pass in every scenario**, so scenarios are compared on the same random realisation.
- Each method is described by its security basis: ECDH is breakable by a future quantum computer; ML-KEM is computational (FIPS 203); QKD is information-theoretic given authenticated post-processing, but needs a pre-shared key, special hardware, clear skies and night-time conditions.

## Two levels of detail

| Level | Used for | What it does |
|---|---|---|
| Formulas | The results table (13 scenarios × 9 uncertainty variants) | Link budgets, asymptotic and finite-key BB84, session models. Fast. |
| Execution and event simulation | The baseline and the scenario chosen in the console | Real handshakes and AES-256-GCM messages attacked four ways; BB84 played out photon by photon with measured error-correction leakage. About 30–40 s per run. |

Comparing the two levels checks the formulas independently ("formula vs simulation" in the Results tab).

## Attacker model and evaluation

Each scenario in `experiments/scenarios.py` states what the attacker or disturbance affects: RF signal loss, optical background, extra optical loss, cloud blockage, or the fraction of photons intercepted and resent. Results are reported separately for:

- **availability:** did a session or key happen at all;
- **detection:** did QBER rise above 11 % (QKD aborts) or below it (key shrinks through privacy amplification);
- **integrity and authenticity:** were tampered, forged and replayed packets rejected (executed sessions);
- **key production:** secret bits per pass and per run, with an uncertainty range.

A failed link is reported as a loss of availability, never as a loss of secrecy. Labelling an attacker "quantum-capable" never breaks a protocol by itself; ECDH is marked as exposed to future decryption, not as broken.

## Record format

`run.json` (`console_run.v1`) contains the request, station, UTC telemetry, events, the two detailed experiment cases (per-pass samples, finite-key results, session summaries, executed sessions and event-level BB84 records), the scenario study, the model card, the runner configuration, provenance (software versions and file fingerprints) and the list of limitations. Key material is never written to the record: final QKD key bits and session keys stay in memory.

## Known limits

Two-body orbit; one station; night-time optics; run-wide disturbances; infinite-statistics decoy bounds; Cascade-style error correction without back-tracking; one executed handshake and message per pass. See the README.

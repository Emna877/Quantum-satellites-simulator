# Satellite cybersecurity threat-analysis architecture

This records the intended experiment design and the boundary between working code
and planned features. Milestones in TODO.md retain their existing order. ML is
deferred. The physical milestone comes first; a final dashboard comes after a
validated paired comparison, not before it.

## Existing foundation and gaps

OrekitPropagator is the orbital authority. Engine.step(dt) owns mutable state and
events; offline and paced execution use that step. The enhanced exporter already
uses the engine. The simple exporter queries the same propagator. qkd.py still
contains a separate communication-calculation example, not security protocols or
the final comparison engine. Its generic RF state fields and approximate optical
loss/QBER formulas must not become a universal channel or a security verdict.

The additive experiments/schema.py adapter establishes a versioned record format
now. It serializes actual snapshots; it does not propagate, apply attacks, calculate
keys, or infer security outcomes. Existing CSV, CZML, commands, and simulation
behavior remain supported. Both exporters optionally write experiment.json from
the same snapshots used for their visual outputs.

## Shared truth and module boundaries

All models receive the same committed UTC simulation instant and Orekit state.
Ground-station range, elevation, eclipse, environment realization, and event
schedule are shared inputs. Navigation measurements may be corrupted without
changing true position. Communication/protocol models return channel-specific
results; they never advance an independent clock or recreate orbital dynamics.

The future paired runner owns experiment configuration and calls the engine.
It supplies identical exogenous physical inputs, attack realizations, application
traffic, and endpoint policies to both modes. Separate named RNG streams for
environment, attack scheduling, and each protocol prevent protocol implementation
details from changing weather or attack timing. Equal seeds alone are not evidence
of a fair pair: store and verify the common realization and its fingerprint.

Telemetry, CSV/CZML adapters, plots, and Cesium consume the recorded outputs. They
must not recompute QKD, synthesize favorable results, or run another orbit. Future
sampled comparisons must specify alignment/interpolation rather than silently
matching nearby timestamps. Event start time and observation time are distinct:
the current output lists scheduled start times for executed events, not exact
continuous-time detection timestamps.

## Initial record contract (schema 1.0)

`experiment.json` contains:

- `schema_version`: explicitly checked by the reader/validator.
- `metadata`: run/scenario identity, reserved pair ID, UTC bounds, mode, effective
  configuration, units, model assumptions, software versions, git revision/dirty
  status, and SHA-256 fingerprints of source, JARs, and Orekit data.
- `samples`: ordered UTC timestamps, complete dataclass snapshots, explicit ITRF
  orbital frames, three separate channel slots, and distinct security result slots.
- `events`: stable IDs, UTC start, duration, severity, parameters and their units,
  explicit targets, model identity, and calibration status. The same scoped preset
  definitions can be loaded with event_from_definition; unsupported parameters,
  altered scopes, and mismatched severity-derived preset durations are rejected.

Null channels mean not computed. A computed channel has `available` (boolean or
unknown) and `metrics` (a dictionary with unit-bearing names). Zero is a real value,
not missing data. Key establishment has a status, secret-key bit count, and reason;
abort/failure retains zero usable bits and its reason. Confidentiality, integrity,
and authentication are separate model-check results, initially not evaluated.
Neither availability nor a low QBER proves any of those properties.

Initial exports are physical_baseline runs. AES-256-GCM metadata is a **planned**
common application profile, not evidence of encryption. There are no computed
channel/security results until the corresponding models are implemented and tested.
The v1 state block retains legacy field names with a units map. Make breaking field,
unit, or semantic changes deliberately with a schema migration/version increment.
An old version must not be silently interpreted using new assumptions.

This is a successful-run format, not a durable resumable journal. Future failed-run
records must distinguish simulation/model failure from a valid protocol abort.
Do not put private keys, session-key bytes, plaintext secrets, or credentials into
metadata. Reproducibility requires retaining the matching inputs, not just hashes.

## Three distinct logical channels

| Channel ID | Purpose | Model requirements |
| --- | --- | --- |
| rf_data | Application data in both comparison modes | RF link budget, noise/interference, coding/modulation, actual throughput and outages |
| quantum_optical | Quantum signals used for QKD key establishment | Telescope apertures, beam spreading, pointing, atmosphere/clouds, optics, detector/timing/background models |
| qkd_classical_protocol | Authenticated QKD discussion, reconciliation, and control | Explicit transport binding, bandwidth, delay, loss, authentication, transcript and traffic overhead |

Planned baseline: application traffic uses the same RF transport in both modes.
The QKD protocol channel can share that RF bearer, but this binding must be configured
and recorded. An RF jammer can then disrupt QKD discussion through a modeled
dependency; it does not directly damage quantum photons. No implicit cross-channel
effect is permitted. The initial schema declares the binding not_configured.

Current event exports describe implemented surrogate scopes. JammingAttack is an RF
proxy. GPSSpoofing affects navigation uncertainty. LaserDazzle currently affects
attitude/sensor noise, heat, and health; it is **not** yet a quantum detector attack.
Solar/geomagnetic presets affect the recorded spacecraft/RF proxies. New optical
background, pointing, interception, and protocol-message attacks need their own
channel adapter, assumptions, and tests before any comparative security conclusion.

## Research questions and planned security profile

Before implementing full protocols, finalize these questions against section 5
reference cases and encode each as a paired experiment:

1. How do range, contact duration, and channel loss change the ability to establish
   keys and deliver authenticated encrypted application data?
2. How do RF interference, optical blockage/background, and pointing errors change
   each channel and the resulting availability, overhead, and key exhaustion?
3. Under declared interception, impersonation, modification, and replay capabilities,
   which checks detect/reject the modeled action, and under which assumptions?

Planned first protocol choices (not implemented): authenticated ephemeral ECDH on
P-256 for classical key establishment; decoy-state BB84 for the QKD-assisted mode.
Use the same endpoint identity/authentication policy in both modes, initially a
specified P-256 signature/trust configuration. QKD's public discussion is authenticated;
any bootstrap credentials and authentication overhead are explicit. A future
information-theoretic authentication variant is a separate declared experiment.

Use AES-256-GCM for application encryption/authentication in both modes, with the
same payloads, AAD, 96-bit nonce policy, 128-bit tags, key-refresh policy, usage limits,
and replay checks. Nonces must be unique per key; never reuse a key/nonce tuple
across paired runs. Plan key derivation and key-buffer accounting explicitly.
The changing experimental variable is key establishment and its costs, not an
unannounced change of cipher or data transport. PQC stays a later separate option.

Specify protocol versions, trusted components, entropy assumptions, source/detector
imperfections, finite-size parameters, authentication resources, and library versions
before claiming a validated security comparison. These choices are a starting design,
not implemented guarantees or approval of the present QKD equations.

## Attacker capabilities and evaluation

Each scenario defines actor placement/visibility, targeted bearer/subsystem,
capability (observe, inject, modify, replay, interfere), intensity/budget, timing,
and endpoint access. Boundaries such as compromised endpoint versus remote link
attacker must be explicit. CommandInjection currently simulates consequences of an
already successful command compromise; it does not demonstrate a broken protocol.
Do not simulate a cryptographic break merely by labelling an actor quantum-capable.

Report contact duration and channel availability separately from confidentiality,
integrity, authentication, and key-establishment results. Comparison metrics include
delivered authenticated application bits, handshake latency/bytes, protocol overhead,
secret bits produced/consumed, buffer exhaustion, abort reasons, rejected/accepted
forgeries and replays, modeled energy cost, and outage duration. Preserve zero-key,
no-contact, failed-authentication, and protocol-abort runs in the denominators.
Repeated stochastic experiments need uncertainty summaries, not cherry-picked passes.

Validate optical loss and QKD results against independent documented calculations
before tuning scenarios. Keep asymptotic toy estimates distinct from finite-key
protocol bounds. Security model failures, unavailable links, insufficient key, and
software exceptions must have different recorded reasons.

## Milestone gates and scope control

1. Sections 1-3 remain the tested foundation; this architecture/schema is additive.
2. Finish section 4 with only power/thermal/measurement fidelity needed for a named
   experiment (e.g. a power outage, pointing disturbance, or corrupted navigation).
   Do not build detailed spacecraft engineering for its own sake.
3. Section 5 supplies distinct, validated communication models using the shared
   state/schema and explicit protocol-channel transport dependencies.
4. Section 6 finalizes the choices/assumptions above and implements actual protocols
   and common application protection. Reusable controlled scenario definitions are
   specified before those protocols, then exercised fully in section 7.
5. Section 7 adds the paired runner, common realizations/seeds, baseline and controlled
   attacks, comparison metrics, and reproducibility/negative-result tests.
6. Section 8 initially supplies recorded outputs and essential comparison plots.
   Build the final synchronized Cesium interface, threat overlays, and comparison
   views only after the underlying runner/metrics pass validation. UI reads the same
   output contract and does not contain a second simulator.
7. Section 9 performs the broader cleanup. The existing physical milestone remains
   first; it does not require a finished cryptographic stack or final UI.

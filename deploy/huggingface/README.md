---
title: Quantum Satellites Simulator
emoji: 🛰️
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: ECDH vs ML-KEM vs BB84 QKD on one LEO satellite orbit
---

# Quantum Satellites Simulator

Compares pre-quantum (ECDH P-256), post-quantum (ML-KEM-768) and quantum (decoy-state BB84) key establishment between a low-Earth-orbit satellite and a ground station in Tunis, on one Orekit orbit and under controlled attacks.

Choose a scenario in the left sidebar to start a run (about 30–40 s). Only one simulation runs at a time on this Space; if another visitor's run is in progress, wait for it to finish. Runs are stored temporarily and disappear when the Space restarts.

Source code, documentation and the write-up: https://github.com/Emna877/Quantum-satellites-simulator

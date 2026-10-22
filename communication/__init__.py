"""Satellite communication models for RF, quantum-optical, and QKD classical protocol channels.

These are three logically distinct channels as required by ARCHITECTURE.md:
  rf_data             — RF link budget, noise, SNR, Shannon capacity.
  quantum_optical     — optical beam loss, detector model, detection rate, QBER.
  qkd_classical_protocol — authenticated QKD discussion overhead (transport binding not yet configured).

All modules accept range_m and return channel-specific metric dictionaries with explicit units.
No module recreates orbital dynamics or advances a simulation clock.

Limitations documented per module; asymptotic QKD formula, no finite-key bounds yet.
"""
from .rf_link import RFLinkConfig, rf_link_budget
from .optical_link import OpticalLinkConfig, optical_link_metrics
from .qkd_model import QKDModelConfig, qkd_key_metrics

"""Security protocol models for the classical and quantum-assisted pipelines.

Modules
-------
classical_session
    Session-key establishment model for a classical RF link (conceptual ECDH +
    AES-256-GCM profile).  Models handshake timing, session lifetime, and
    authentication assumptions, not actual cryptographic operations.

qkd_finite_key
    BB84 secret-key rate with finite-key corrections (Tomamichel et al. 2012).
    Replaces the asymptotic bound in communication/qkd_model.py for realistic
    pass-length analysis.

key_store
    Key-buffer accounting model: tracks QKD key accumulation, consumption by
    data encryption, exhaustion, and recovery across simulation intervals.
"""
from security.classical_session import ClassicalSessionConfig, classical_key_establishment
from security.qkd_finite_key import BB84FiniteKeyConfig, bb84_finite_key_metrics
from security.key_store import KeyStore, KeyStoreConfig

__all__ = [
    "ClassicalSessionConfig", "classical_key_establishment",
    "BB84FiniteKeyConfig", "bb84_finite_key_metrics",
    "KeyStore", "KeyStoreConfig",
]

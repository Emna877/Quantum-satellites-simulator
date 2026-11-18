"""Executed cryptography for the classical, post-quantum and QKD-keyed sessions.

security/classical_session.py *models* key establishment (message sizes,
propagation delay, link availability).  This module *executes* it with the
same primitives real systems use, from the ``cryptography`` package (OpenSSL):

  Key exchange     ECDH P-256, ML-KEM-768 (FIPS 203), or X25519 + ML-KEM-768
  Authentication   PSK (HMAC-SHA256 over the handshake transcript), or
                   certificate-style signatures (ECDSA P-256 / ML-DSA-65, FIPS 204)
  Session key      HKDF-SHA256 over the shared secret and the transcript hash
  Data             AES-256-GCM with a 12-byte header used as nonce and as
                   associated data: 4-byte sender id + 8-byte message counter

Every exchange is then attacked:
  tamper    one bit of the ciphertext is flipped       → must fail (GCM tag)
  header    the counter in the header is changed       → must fail (header is AAD)
  forgery   an attacker without the key builds a packet → must fail (GCM tag)
  replay    an accepted packet is delivered again      → must fail (counter seen)

The handshake uses fresh operating-system randomness, so keys differ between
runs; the pass/fail results do not.  CPU timings are measured on this machine
and do not include radio transmission, which classical_session.py models.

Limitations
-----------
- One handshake and one 1 KiB message per pass; no traffic model or rekeying.
- Long-term signing keys are generated per handshake (standing in for
  pre-provisioned credentials); there is no certificate chain or revocation.
- The replay window keeps every accepted counter for the session; real systems
  use a bounded sliding window.
"""
import hashlib
import hmac
import os
import struct
import time

import cryptography
from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, mldsa, mlkem, x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

BACKEND = f'cryptography {cryptography.__version__} (OpenSSL)'
MESSAGE_BYTES = 1024
_HEADER = struct.Struct('>4sQ')          # sender id, counter → 12-byte GCM nonce


class ReplayError(Exception):
    """An authentic packet was delivered a second time."""


class HandshakeAuthenticationError(Exception):
    """The peer could not prove possession of the shared credential."""


def _hkdf(secret: bytes, info: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=info).derive(secret)


def _ec_point(public_key) -> bytes:
    return public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def _ecdh(transcript: list) -> tuple:
    satellite = ec.generate_private_key(ec.SECP256R1())
    ground = ec.generate_private_key(ec.SECP256R1())
    sat_pub, gs_pub = _ec_point(satellite.public_key()), _ec_point(ground.public_key())
    transcript += [sat_pub, gs_pub]
    sat_secret = satellite.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), gs_pub))
    gs_secret = ground.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), sat_pub))
    return sat_secret, gs_secret


def _mlkem(transcript: list) -> tuple:
    # The ground station publishes an encapsulation key; the satellite encapsulates to it.
    ground = mlkem.MLKEM768PrivateKey.generate()
    encapsulation_key = ground.public_key().public_bytes_raw()
    sat_secret, ciphertext = mlkem.MLKEM768PublicKey.from_public_bytes(encapsulation_key).encapsulate()
    transcript += [encapsulation_key, ciphertext]
    gs_secret = ground.decapsulate(ciphertext)
    return sat_secret, gs_secret


def _x25519(transcript: list) -> tuple:
    satellite, ground = x25519.X25519PrivateKey.generate(), x25519.X25519PrivateKey.generate()
    sat_pub, gs_pub = satellite.public_key().public_bytes_raw(), ground.public_key().public_bytes_raw()
    transcript += [sat_pub, gs_pub]
    return (satellite.exchange(x25519.X25519PublicKey.from_public_bytes(gs_pub)),
            ground.exchange(x25519.X25519PublicKey.from_public_bytes(sat_pub)))


def _authenticate(transcript: list, key_exchange: str, auth_method: str,
                  satellite_psk: bytes, ground_psk: bytes) -> tuple:
    """Each side proves it took part in this transcript. Returns (scheme, bytes sent)."""
    digest = hashlib.sha256(b''.join(transcript)).digest()
    if auth_method == 'psk':
        sat_tag = hmac.new(satellite_psk, b'sat' + digest, hashlib.sha256).digest()
        gs_tag = hmac.new(ground_psk, b'gs' + digest, hashlib.sha256).digest()
        ok = (hmac.compare_digest(sat_tag, hmac.new(ground_psk, b'sat' + digest, hashlib.sha256).digest())
              and hmac.compare_digest(gs_tag, hmac.new(satellite_psk, b'gs' + digest, hashlib.sha256).digest()))
        if not ok:
            raise HandshakeAuthenticationError('PSK transcript MAC mismatch')
        return 'PSK-HMAC-SHA256', len(sat_tag) + len(gs_tag)
    sent = 0
    for role in (b'sat', b'gs'):
        if key_exchange == 'ECDH-P256':
            signer = ec.generate_private_key(ec.SECP256R1())
            signature = signer.sign(role + digest, ec.ECDSA(hashes.SHA256()))
            public = _ec_point(signer.public_key())
            # Raw r||s size for comparison with the model (DER adds a few bytes).
            sent += len(public) + 64
            try:
                ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), public).verify(
                    signature, role + digest, ec.ECDSA(hashes.SHA256()))
            except InvalidSignature as error:
                raise HandshakeAuthenticationError('ECDSA signature invalid') from error
        else:
            signer = mldsa.MLDSA65PrivateKey.generate()
            signature = signer.sign(role + digest)
            public = signer.public_key().public_bytes_raw()
            sent += len(public) + len(signature)
            try:
                mldsa.MLDSA65PublicKey.from_public_bytes(public).verify(signature, role + digest)
            except InvalidSignature as error:
                raise HandshakeAuthenticationError('ML-DSA signature invalid') from error
    return ('ECDSA-P256' if key_exchange == 'ECDH-P256' else 'ML-DSA-65'), sent


def execute_handshake(key_exchange: str, auth_method: str = 'psk', psk: bytes = None,
                      ground_psk: bytes = None) -> dict:
    """Run one real authenticated handshake. ``ground_psk`` differs from ``psk`` only in tests."""
    psk = psk if psk is not None else os.urandom(32)
    ground_psk = psk if ground_psk is None else ground_psk
    transcript = []
    start = time.perf_counter()
    if key_exchange == 'ECDH-P256':
        sat_secret, gs_secret = _ecdh(transcript)
    elif key_exchange == 'ML-KEM-768':
        sat_secret, gs_secret = _mlkem(transcript)
    elif key_exchange == 'X25519+ML-KEM-768':
        classic_sat, classic_gs = _x25519(transcript)
        pq_sat, pq_gs = _mlkem(transcript)
        sat_secret, gs_secret = classic_sat + pq_sat, classic_gs + pq_gs
    else:
        raise ValueError(f'Unknown key exchange {key_exchange!r}')
    exchange_bytes = sum(len(message) for message in transcript)
    auth_scheme, auth_bytes = _authenticate(transcript, key_exchange, auth_method, psk, ground_psk)
    info = b'qsat-session' + hashlib.sha256(b''.join(transcript)).digest()
    sat_key, gs_key = _hkdf(sat_secret, info), _hkdf(gs_secret, info)
    elapsed_ms = (time.perf_counter() - start) * 1e3
    return {
        'key_exchange': key_exchange,
        'auth_scheme': auth_scheme,
        'handshake_bytes': exchange_bytes + auth_bytes,
        'handshake_cpu_ms': elapsed_ms,
        'keys_match': hmac.compare_digest(sat_key, gs_key),
        '_satellite_key': sat_key,
        '_ground_key': gs_key,
    }


class SecureChannel:
    """AES-256-GCM endpoint with counter nonces, an authenticated header and replay rejection."""

    def __init__(self, key: bytes, sender_id: bytes):
        if len(key) != 32:
            raise ValueError('AES-256 needs a 32-byte key')
        self._aead = AESGCM(key)
        self._sender_id = sender_id
        self._counter = 0
        self._accepted = set()

    def seal(self, plaintext: bytes) -> bytes:
        self._counter += 1
        header = _HEADER.pack(self._sender_id, self._counter)
        return header + self._aead.encrypt(header, plaintext, header)

    def open(self, packet: bytes) -> bytes:
        header, body = packet[:_HEADER.size], packet[_HEADER.size:]
        plaintext = self._aead.decrypt(header, body, header)   # InvalidTag on any change
        sender, counter = _HEADER.unpack(header)
        if (sender, counter) in self._accepted:
            raise ReplayError(f'counter {counter} already accepted')
        self._accepted.add((sender, counter))
        return plaintext


def _rejects(action) -> bool:
    try:
        action()
    except (InvalidTag, ReplayError):
        return True
    return False


def exercise_channel(satellite_key: bytes, ground_key: bytes) -> dict:
    """Send one message, then attack the channel four ways. True = attack rejected."""
    satellite, ground = SecureChannel(satellite_key, b'SAT1'), SecureChannel(ground_key, b'SAT1')
    message = os.urandom(MESSAGE_BYTES)
    start = time.perf_counter()
    packet = satellite.seal(message)
    decrypted_ok = ground.open(packet) == message
    aead_ms = (time.perf_counter() - start) * 1e3

    tampered = bytearray(packet)
    tampered[_HEADER.size + 7] ^= 0x01                    # flip one ciphertext bit
    header_changed = bytearray(satellite.seal(message))
    header_changed[11] ^= 0x01                             # change the counter in the header
    forger = SecureChannel(os.urandom(32), b'SAT1')        # attacker without the key
    forger._counter = 99
    return {
        'message_bytes': MESSAGE_BYTES,
        'packet_bytes': len(packet),
        'decrypted_ok': decrypted_ok,
        'aead_cpu_ms': aead_ms,
        'tamper_rejected': _rejects(lambda: ground.open(bytes(tampered))),
        'header_tamper_rejected': _rejects(lambda: ground.open(bytes(header_changed))),
        'forgery_rejected': _rejects(lambda: ground.open(forger.seal(b'forged command: deorbit'))),
        'replay_rejected': _rejects(lambda: ground.open(packet)),
    }


def execute_session(key_exchange: str, auth_method: str = 'psk', psk: bytes = None) -> dict:
    """Real handshake + one encrypted message + four attacks. JSON-serialisable result."""
    handshake = execute_handshake(key_exchange, auth_method, psk)
    channel = exercise_channel(handshake.pop('_satellite_key'), handshake.pop('_ground_key'))
    return {'executed': True, 'backend': BACKEND, **handshake, **channel,
            'all_attacks_rejected': all(channel[k] for k in
                                        ('tamper_rejected', 'header_tamper_rejected',
                                         'forgery_rejected', 'replay_rejected'))}


def execute_qkd_keyed_session(key_bytes: bytes) -> dict:
    """Encrypt with 256 bits of QKD key (both sides hold the same bits) and attack the channel."""
    if len(key_bytes) != 32:
        raise ValueError('need exactly 256 bits of QKD key')
    channel = exercise_channel(key_bytes, bytes(key_bytes))
    return {'executed': True, 'backend': BACKEND, 'key_source': 'QKD (event-level BB84)',
            'key_bits_used': 256, **channel,
            'all_attacks_rejected': all(channel[k] for k in
                                        ('tamper_rejected', 'header_tamper_rejected',
                                         'forgery_rejected', 'replay_rejected'))}


def not_executed(reason: str) -> dict:
    return {'executed': False, 'reason': reason}

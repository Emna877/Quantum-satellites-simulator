"""Executed cryptography: real handshakes, AES-256-GCM, and rejection of attacks."""
import os
import unittest

from cryptography.exceptions import InvalidTag

from security.classical_session import ClassicalSessionConfig, handshake_profile
from security.crypto_exec import (
    HandshakeAuthenticationError, ReplayError, SecureChannel, execute_handshake,
    execute_qkd_keyed_session, execute_session,
)

KEY_EXCHANGES = ('ECDH-P256', 'ML-KEM-768', 'X25519+ML-KEM-768')
AUTH_METHODS = ('psk', 'certificate')


class HandshakeTests(unittest.TestCase):

    def test_both_sides_derive_the_same_key(self):
        for kex in KEY_EXCHANGES:
            for auth in AUTH_METHODS:
                with self.subTest(kex=kex, auth=auth):
                    result = execute_handshake(kex, auth)
                    self.assertTrue(result['keys_match'])
                    self.assertEqual(len(result['_satellite_key']), 32)

    def test_executed_bytes_match_the_model(self):
        # The modelled handshake sizes (FIPS 203/204, SP 800-56A) are what really goes on the wire.
        for kex in KEY_EXCHANGES:
            for auth in AUTH_METHODS:
                with self.subTest(kex=kex, auth=auth):
                    model = handshake_profile(ClassicalSessionConfig(key_exchange=kex, auth_method=auth))
                    self.assertEqual(execute_handshake(kex, auth)['handshake_bytes'], model['handshake_bytes'])

    def test_wrong_psk_is_detected(self):
        # A man-in-the-middle without the pre-shared key cannot complete the handshake.
        for kex in KEY_EXCHANGES:
            with self.subTest(kex=kex), self.assertRaises(HandshakeAuthenticationError):
                execute_handshake(kex, 'psk', psk=os.urandom(32), ground_psk=os.urandom(32))

    def test_fresh_keys_every_handshake(self):
        first = execute_handshake('ML-KEM-768')['_satellite_key']
        second = execute_handshake('ML-KEM-768')['_satellite_key']
        self.assertNotEqual(first, second)


class SecureChannelTests(unittest.TestCase):

    def setUp(self):
        key = os.urandom(32)
        self.sender, self.receiver = SecureChannel(key, b'SAT1'), SecureChannel(key, b'SAT1')

    def test_round_trip(self):
        self.assertEqual(self.receiver.open(self.sender.seal(b'telemetry')), b'telemetry')

    def test_every_single_bit_flip_is_rejected(self):
        packet = self.sender.seal(b'command: point telescope')
        for byte in range(len(packet)):
            for bit in range(8):
                tampered = bytearray(packet)
                tampered[byte] ^= 1 << bit
                with self.subTest(byte=byte, bit=bit), self.assertRaises(InvalidTag):
                    self.receiver.open(bytes(tampered))

    def test_replay_is_rejected(self):
        packet = self.sender.seal(b'unlock payload')
        self.receiver.open(packet)
        with self.assertRaises(ReplayError):
            self.receiver.open(packet)

    def test_forgery_without_key_is_rejected(self):
        forger = SecureChannel(os.urandom(32), b'SAT1')
        with self.assertRaises(InvalidTag):
            self.receiver.open(forger.seal(b'forged command'))

    def test_counters_make_every_nonce_unique(self):
        packets = [self.sender.seal(b'x') for _ in range(100)]
        self.assertEqual(len({p[:12] for p in packets}), 100)


class SessionTests(unittest.TestCase):

    def test_every_method_rejects_all_attacks(self):
        for kex in KEY_EXCHANGES:
            for auth in AUTH_METHODS:
                with self.subTest(kex=kex, auth=auth):
                    result = execute_session(kex, auth)
                    self.assertTrue(result['executed'])
                    self.assertTrue(result['decrypted_ok'])
                    for attack in ('tamper_rejected', 'header_tamper_rejected', 'forgery_rejected', 'replay_rejected'):
                        self.assertTrue(result[attack], attack)
                    self.assertNotIn('_satellite_key', result)   # keys never leave the module

    def test_qkd_keyed_session(self):
        result = execute_qkd_keyed_session(os.urandom(32))
        self.assertTrue(result['all_attacks_rejected'])
        self.assertEqual(result['key_bits_used'], 256)
        with self.assertRaises(ValueError):
            execute_qkd_keyed_session(os.urandom(16))


if __name__ == '__main__':
    unittest.main()

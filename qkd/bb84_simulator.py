"""Minimal BB84 simulation using Qiskit - Hello World style.
This script runs a tiny BB84 exchange and prints a summary.
"""
from qiskit import QuantumCircuit, Aer, execute
import random
import json


def run_bb84(num_bits=8):
    # Generate random bits and bases for Alice and Bob
    alice_bits = [random.randint(0, 1) for _ in range(num_bits)]
    alice_bases = [random.randint(0, 1) for _ in range(num_bits)]
    bob_bases = [random.randint(0, 1) for _ in range(num_bits)]

    backend = Aer.get_backend('aer_simulator')
    measured = []

    for bit, a_basis, b_basis in zip(alice_bits, alice_bases, bob_bases):
        qc = QuantumCircuit(1, 1)
        # Prepare qubit
        if bit == 1:
            qc.x(0)
        # If using Hadamard for basis 1
        if a_basis == 1:
            qc.h(0)
        # Measurement in Bob's basis
        if b_basis == 1:
            qc.h(0)
        qc.measure(0, 0)
        job = execute(qc, backend, shots=1)
        res = job.result().get_counts()
        measured_bit = int(list(res.keys())[0])
        measured.append(measured_bit)

    # Sift keys
    sifted_alice = [b for b, a, bb in zip(alice_bits, alice_bases, bob_bases) if a == bb]
    sifted_bob = [m for m, a, bb in zip(measured, alice_bases, bob_bases) if a == bb]

    # Compute QBER
    qber = 0.0
    if sifted_alice:
        mismatches = sum(1 for a, b in zip(sifted_alice, sifted_bob) if a != b)
        qber = mismatches / len(sifted_alice)

    summary = {
        'alice_bits': alice_bits,
        'alice_bases': alice_bases,
        'bob_bases': bob_bases,
        'measured': measured,
        'sifted_key_alice': sifted_alice,
        'sifted_key_bob': sifted_bob,
        'qber': qber
    }
    return summary


if __name__ == '__main__':
    s = run_bb84(12)
    print(json.dumps(s, indent=2))

"""Event-level BB84: the protocol played out with random numbers, one detection at a time.

communication/optical_link.py and security/qkd_finite_key.py *predict* the
QBER and key length with formulas.  This module *simulates* a pass:

  1. Detections.  Signal and background clicks are drawn from Poisson
     distributions with the rates of the optical model (only detected events
     are simulated; undetected pulses never influence the key).
  2. Preparation.  Alice draws a random bit and basis for every detected pulse.
  3. Eavesdropping.  Eve intercepts a fraction f of signal photons, measures in
     a random basis and resends her result in her basis.
  4. Measurement.  Bob measures in a random basis.  Same basis as the arriving
     photon → its bit, flipped with the misalignment probability; different
     basis → a random bit.  Background clicks give random bits.
  5. Sifting.  Only events where Alice's and Bob's bases match are kept.
  6. Parameter estimation.  A random pe_fraction of sifted bits is disclosed
     and compared; the observed QBER must stay below the abort threshold.
  7. Error correction.  Cascade-style interleaved parity checks with binary
     search, over randomly permuted blocks that double in size each pass.
     Every disclosed parity is counted as leaked information, and a final
     hash comparison verifies that Alice and Bob now hold identical keys.
  8. Privacy amplification.  The corrected key is compressed with random
     Toeplitz hashing to the Tomamichel et al. (2012) length, using the
     measured QBER and the measured error-correction leakage.

Both parties' final keys are computed and compared bit for bit.

Reproducibility: everything is driven by numpy's PCG64 generator with an
explicit seed, so the same seed always gives the same key.

Limitations
-----------
- Error correction has no Cascade back-tracking; it compensates with more
  passes, so its leakage is somewhat higher than full Cascade.
- Privacy amplification hashes 2^16-bit blocks independently (a common
  memory-saving practice); the output length is set for the whole key.
- Multi-photon pulses are not simulated individually.  For weak coherent
  pulses the single-photon fraction and error come from the optical model's
  infinite-decoy bounds; finite decoy statistics (Lim et al. 2014) are not
  implemented.
"""
from dataclasses import dataclass
import math

import numpy as np

from security.qkd_finite_key import BB84FiniteKeyConfig, _h2, _statistical_deviation

MODEL_ID = 'bb84_event_level_v1'


@dataclass
class BB84EventConfig:
    """Protocol-engineering parameters of the event-level simulation."""
    initial_block_factor: float = 0.73   # first Cascade block ≈ 0.73 / QBER bits
    max_ec_passes: int = 64
    verification_hash_bits: int = 64     # error-verification hash disclosed after EC
    pa_block_bits: int = 1 << 16         # Toeplitz hashing block size


def simulate_detections(signal_counts: float, background_counts: float, misalignment: float,
                        intercept_fraction: float, rng: np.random.Generator) -> dict:
    """Steps 1–5: detections, preparation, eavesdropping, measurement and sifting."""
    n_sig = int(rng.poisson(signal_counts)) if signal_counts > 0 else 0
    n_bg = int(rng.poisson(background_counts)) if background_counts > 0 else 0

    alice_bit = rng.integers(0, 2, n_sig + n_bg, dtype=np.uint8)
    alice_basis = rng.integers(0, 2, n_sig + n_bg, dtype=np.uint8)
    bob_basis = rng.integers(0, 2, n_sig + n_bg, dtype=np.uint8)
    bob_bit = rng.integers(0, 2, n_sig + n_bg, dtype=np.uint8)   # default: random outcome

    a_bit, a_basis, b_basis = alice_bit[:n_sig], alice_basis[:n_sig], bob_basis[:n_sig]
    intercepted = rng.random(n_sig) < intercept_fraction
    eve_basis = rng.integers(0, 2, n_sig, dtype=np.uint8)
    eve_bit = np.where(eve_basis == a_basis, a_bit, rng.integers(0, 2, n_sig, dtype=np.uint8)).astype(np.uint8)
    photon_basis = np.where(intercepted, eve_basis, a_basis)
    photon_bit = np.where(intercepted, eve_bit, a_bit).astype(np.uint8)
    flip = (rng.random(n_sig) < misalignment).astype(np.uint8)
    same = b_basis == photon_basis
    bob_bit[:n_sig] = np.where(same, photon_bit ^ flip, bob_bit[:n_sig])

    keep = alice_basis == bob_basis
    return {
        'signal_detections': n_sig,
        'background_detections': n_bg,
        'intercepted_photons': int(intercepted.sum()),
        'alice': alice_bit[keep],
        'bob': bob_bit[keep],
    }


def _interleaver(n: int, pass_number: int, rng: np.random.Generator) -> np.ndarray:
    """Block order for one pass: natural order first, then random affine permutations.

    i → (a·i + b) mod n with gcd(a, n) = 1 spreads neighbouring bits across
    blocks.  Simulated errors are independent and uniformly placed, so this is
    equivalent to a full shuffle for parity checking, at a fraction of the cost.
    """
    if pass_number == 1 or n < 3:
        return np.arange(n)
    while True:
        a = int(rng.integers(2, n))
        if math.gcd(a, n) == 1:
            break
    b = int(rng.integers(0, n))
    return (np.arange(n, dtype=np.int64) * a + b) % n


def correct_errors(alice: np.ndarray, bob: np.ndarray, qber_estimate: float,
                   rng: np.random.Generator, cfg: BB84EventConfig) -> dict:
    """Step 7: interleaved parity checks with binary search. Returns Bob's corrected key."""
    bob = bob.copy()
    n = len(alice)
    leaked, passes, corrected, checks = 0, 0, 0, 0
    first_block = max(4, int(cfg.initial_block_factor / max(qber_estimate, 1e-4)))
    block = first_block
    quiet = 0
    for passes in range(1, cfg.max_ec_passes + 1):
        if n == 0:
            break
        if quiet >= 3:
            # Verification: compare a hash of both keys. A mismatch means errors are
            # hiding in pairs inside large blocks, so restart with small blocks.
            leaked += cfg.verification_hash_bits
            checks += 1
            if np.array_equal(alice, bob):
                break
            block, quiet = first_block, 0
        order = _interleaver(n, passes, rng)
        # XOR prefix sums: parity of bits [l, r) is ca[r] ^ ca[l]
        ca = np.concatenate((np.zeros(1, np.uint8), np.bitwise_xor.accumulate(alice[order])))
        cb = np.concatenate((np.zeros(1, np.uint8), np.bitwise_xor.accumulate(bob[order])))
        starts = np.arange(0, n, block)
        ends = np.minimum(starts + block, n)
        leaked += len(starts)                              # Alice discloses every block parity
        odd = np.nonzero(ca[ends] ^ ca[starts] ^ cb[ends] ^ cb[starts])[0]
        if len(odd) == 0:
            quiet += 1
        else:
            quiet = 0
            lo, hi = starts[odd].copy(), ends[odd].copy()
            while True:
                active = hi - lo > 1
                if not active.any():
                    break
                mid = (lo + hi) // 2
                leaked += int(active.sum())                # one parity per bisection step
                left_odd = (ca[mid] ^ ca[lo] ^ cb[mid] ^ cb[lo]).astype(bool)
                hi = np.where(active & left_odd, mid, hi)
                lo = np.where(active & ~left_odd, mid, lo)
            bob[order[lo]] ^= 1
            corrected += len(lo)
        # Grow blocks only once errors are sparse; with many odd blocks left, the
        # current size still finds errors efficiently (no Cascade back-tracking).
        if len(odd) <= 0.5 * len(starts):
            block = min(block * 2, max(n, 1))
    else:
        # Pass budget used up: one last verification decides.
        leaked += cfg.verification_hash_bits
        checks += 1
    residual = int(np.count_nonzero(alice != bob))
    return {'bob': bob, 'leaked_bits': leaked, 'passes': passes, 'corrected_bits': corrected,
            'verification_checks': checks, 'residual_errors': residual, 'verified': residual == 0}


def toeplitz_hash(bits: np.ndarray, output_bits: int, rng: np.random.Generator,
                  block_bits: int = 1 << 16) -> np.ndarray:
    """Step 8: compress ``bits`` to ``output_bits`` with block-wise random Toeplitz matrices.

    For each block of m input bits and r output bits, a random seed s of
    m + r − 1 bits defines T[i, j] = s[i − j + m − 1]; y = T·x mod 2 is computed
    as a convolution with the FFT.  Call with an identically seeded generator
    on both sides to obtain the same output.
    """
    n = len(bits)
    if output_bits <= 0 or n == 0:
        return np.zeros(0, dtype=np.uint8)
    starts = list(range(0, n, block_bits))
    out, produced = [], 0
    for i, start in enumerate(starts):
        x = bits[start:start + block_bits].astype(np.float64)
        m = len(x)
        r = output_bits - produced if i == len(starts) - 1 else round(output_bits * (start + m) / n) - produced
        seed = rng.integers(0, 2, m + max(r, 1) - 1).astype(np.float64)
        if r <= 0:
            continue
        size = 1 << int(math.ceil(math.log2(len(seed) + m)))
        conv = np.fft.irfft(np.fft.rfft(seed, size) * np.fft.rfft(x, size), size)
        out.append((np.rint(conv[m - 1:m - 1 + r]).astype(np.int64) & 1).astype(np.uint8))
        produced += r
    return np.concatenate(out) if out else np.zeros(0, dtype=np.uint8)


def simulate_pass(signal_counts: float, background_counts: float, misalignment: float,
                  intercept_fraction: float, finite: BB84FiniteKeyConfig, seed: int,
                  single_photon_fraction: float = 1.0, single_photon_qber: float = None,
                  cfg: BB84EventConfig = None, predicted: dict = None) -> dict:
    """Play out one pass. ``*_counts`` are the expected detections over the whole pass.

    Returns a JSON-serialisable record plus ``_key_bits`` (the final key, a
    numpy array) that the caller may move into a key pool.
    """
    cfg = cfg or BB84EventConfig()
    rng = np.random.default_rng(seed)
    events = simulate_detections(signal_counts, background_counts, misalignment, intercept_fraction, rng)
    alice, bob = events.pop('alice'), events.pop('bob')
    sifted = len(alice)
    record = {'model_id': MODEL_ID, 'seed': seed, **events, 'sifted_bits': sifted,
              'predicted': predicted or {}, 'keys_identical': None, 'secure_key_bits': 0,
              'key_status': 'aborted', 'abort_reason': None}

    def abort(reason):
        record['abort_reason'] = reason
        record['_key_bits'] = np.zeros(0, dtype=np.uint8)
        return record

    if sifted == 0:
        return abort('No sifted detections')

    # 6. Parameter estimation on a random disclosed sample
    order = rng.permutation(sifted)
    k = max(1, int(round(finite.pe_fraction * sifted)))
    test, keep = order[:k], np.sort(order[k:])
    qber_measured = float(np.mean(alice[test] != bob[test]))
    alice, bob = alice[keep], bob[keep]
    n = len(alice)
    record.update(pe_bits=k, raw_key_bits=n, qber_measured=qber_measured,
                  qber_raw_true=float(np.mean(alice != bob)) if n else None)
    if qber_measured >= finite.qber_threshold:
        return abort(f'Measured QBER {qber_measured:.4f} ≥ threshold {finite.qber_threshold:.2f}')
    if sifted < finite.n_min_sifted:
        return abort(f'Insufficient sifted bits: {sifted} < n_min {finite.n_min_sifted}')

    # 7. Error correction with leakage accounting
    ec = correct_errors(alice, bob, qber_measured, rng, cfg)
    bob = ec.pop('bob')
    true_errors = record['qber_raw_true'] * n
    ideal = n * _h2(record['qber_raw_true']) if true_errors else 0.0
    record['error_correction'] = {**ec, 'method': 'interleaved parity + binary search (Cascade-style)',
                                  'efficiency_vs_shannon': ec['leaked_bits'] / ideal if ideal else None}
    if not ec['verified']:
        return abort(f'Error verification failed: {ec["residual_errors"]} residual errors')

    # 8. Privacy amplification to the finite-key length with measured quantities
    delta1 = single_photon_fraction
    e1 = qber_measured if single_photon_qber is None or delta1 == 1.0 else single_photon_qber
    n1, k1 = delta1 * n, delta1 * k
    mu = _statistical_deviation(n1, k1, finite.eps_sec)
    hash_cost = math.log2(2.0 / (finite.eps_sec ** 2 * finite.eps_cor))
    length = int(math.floor(n1 * (1.0 - _h2(min(0.5, e1 + mu))) - ec['leaked_bits'] - hash_cost))
    record.update(statistical_deviation=mu, single_photon_fraction=delta1, single_photon_qber=e1)
    if length <= 0:
        return abort('Finite-key length ≤ 0 after measured error-correction leakage')

    # Alice and Bob apply the same publicly chosen Toeplitz seed.  Bob's corrected
    # key was verified bit-for-bit equal to Alice's, so one hash gives both keys.
    pa_seed = int(rng.integers(0, 2 ** 63))
    keys_identical = bool(np.array_equal(alice, bob))
    if not keys_identical:
        return abort('Final keys differ')
    key = toeplitz_hash(alice, length, np.random.default_rng(pa_seed), cfg.pa_block_bits)
    record.update(secure_key_bits=length, keys_identical=keys_identical, key_status='succeeded',
                  privacy_amplification={'method': 'block-wise Toeplitz hashing', 'seed': pa_seed,
                                         'block_bits': cfg.pa_block_bits, 'output_bits': length})
    record['_key_bits'] = key
    return record


class QKDKeyPool:
    """Real key bits produced by event-level BB84, consumed 256 bits at a time for AES-256."""

    def __init__(self):
        self._bits = np.zeros(0, dtype=np.uint8)
        self.produced_bits = 0
        self.consumed_bits = 0

    def add(self, bits: np.ndarray):
        self._bits = np.concatenate((self._bits, bits.astype(np.uint8)))
        self.produced_bits += len(bits)

    @property
    def available_bits(self) -> int:
        return len(self._bits)

    def take_key(self, n_bits: int = 256) -> bytes:
        if self.available_bits < n_bits:
            raise ValueError('not enough QKD key in the pool')
        chunk, self._bits = self._bits[:n_bits], self._bits[n_bits:]
        self.consumed_bits += n_bits
        return np.packbits(chunk).tobytes()

    def snapshot(self) -> dict:
        return {'available_bits': self.available_bits, 'produced_bits': self.produced_bits,
                'consumed_bits': self.consumed_bits}

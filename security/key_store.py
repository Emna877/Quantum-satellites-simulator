"""Key-buffer accounting model.

Tracks the lifecycle of keying material produced by QKD and consumed by data
encryption over a simulation interval.  Does not implement cryptographic
operations.

Key lifecycle
-------------
1. QKD produces secret bits at ``replenishment_rate_bit_s`` whenever a pass is
   active and the protocol succeeds.
2. Data encryption consumes bits at ``consumption_rate_bit_s`` whenever the
   satellite is transmitting.
3. The buffer is bounded at ``capacity_bits``.  Overflow is discarded (a real
   system would pause production or discard old keys, but the effect on the
   comparison experiment is the same).
4. When the buffer is empty and the system needs to encrypt, a key-exhaustion
   event is recorded.

Model limits
------------
- Key freshness, key scheduling, and multi-session key splitting are not modelled.
- Authentication key consumption (for the QKD classical protocol channel) is
  not tracked separately.
- Key material is treated as a homogeneous pool of bits; no per-purpose
  partitioning.
- Key zeroing / secure erasure on exhaustion is not modelled.
"""
from dataclasses import dataclass, field
from typing import List


@dataclass
class KeyStoreConfig:
    capacity_bits: float = 1e9          # maximum buffer size, bits
    consumption_rate_bit_s: float = 1e3 # bits/s consumed during active transmission


@dataclass
class KeyStore:
    """Mutable key buffer with accounting over simulation intervals.

    Attributes
    ----------
    current_bits : float
        Bits currently in the buffer.
    total_produced_bits : float
        Cumulative bits ever added.
    total_consumed_bits : float
        Cumulative bits ever consumed.
    exhaustion_count : int
        Number of intervals where the buffer ran dry during consumption.
    """
    config: KeyStoreConfig = field(default_factory=KeyStoreConfig)
    current_bits: float = 0.0
    total_produced_bits: float = 0.0
    total_consumed_bits: float = 0.0
    exhaustion_count: int = 0

    def replenish(self, rate_bit_s: float, dt_s: float) -> float:
        """Add QKD-produced bits for an interval of duration *dt_s*.

        Returns the bits actually added (may be less than the rate × dt if the
        buffer is full).
        """
        if rate_bit_s < 0:
            raise ValueError("rate_bit_s must be nonneg")
        if dt_s < 0:
            raise ValueError("dt_s must be nonneg")
        added = min(rate_bit_s * dt_s, self.config.capacity_bits - self.current_bits)
        added = max(0.0, added)
        self.current_bits += added
        self.total_produced_bits += added
        return added

    def consume(self, dt_s: float, transmitting: bool = True) -> dict:
        """Consume encryption key material for an interval of duration *dt_s*.

        Returns a result dict describing what happened during the interval.
        """
        if dt_s < 0:
            raise ValueError("dt_s must be nonneg")

        if not transmitting:
            return {"consumed_bits": 0.0, "exhausted": False, "dt_s": dt_s,
                    "buffer_bits_before": self.current_bits, "buffer_bits_after": self.current_bits}

        demand = self.config.consumption_rate_bit_s * dt_s
        before = self.current_bits
        consumed = min(demand, self.current_bits)
        self.current_bits -= consumed
        self.total_consumed_bits += consumed
        exhausted = consumed < demand
        if exhausted:
            self.exhaustion_count += 1
        return {
            "consumed_bits": consumed,
            "demanded_bits": demand,
            "shortfall_bits": demand - consumed,
            "exhausted": exhausted,
            "dt_s": dt_s,
            "buffer_bits_before": before,
            "buffer_bits_after": self.current_bits,
        }

    def update(self, dt_s: float, replenishment_rate_bit_s: float,
               transmitting: bool = True) -> dict:
        """Replenish then consume for one simulation interval.

        Replenishment is applied first (key bits arrive before they are used in
        the same interval) to avoid falsely triggering exhaustion at the start
        of a productive pass.
        """
        added = self.replenish(replenishment_rate_bit_s, dt_s)
        consumption_result = self.consume(dt_s, transmitting)
        return {
            "added_bits": added,
            **consumption_result,
            "total_produced_bits": self.total_produced_bits,
            "total_consumed_bits": self.total_consumed_bits,
            "exhaustion_count": self.exhaustion_count,
        }

    @property
    def fill_fraction(self) -> float:
        """Current buffer fill as a fraction of capacity (0–1)."""
        cap = self.config.capacity_bits
        if cap <= 0:
            return 0.0
        return self.current_bits / cap

    def snapshot(self) -> dict:
        """Return a JSON-serialisable point-in-time snapshot."""
        return {
            "current_bits": self.current_bits,
            "capacity_bits": self.config.capacity_bits,
            "fill_fraction": self.fill_fraction,
            "total_produced_bits": self.total_produced_bits,
            "total_consumed_bits": self.total_consumed_bits,
            "exhaustion_count": self.exhaustion_count,
        }

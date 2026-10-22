"""RF link budget for the rf_data channel.

Models classical radio application data transport using the Friis equation.
This is a physical-layer capacity estimate, not a protocol throughput model.

Channel ID: rf_data
Units: SI throughout; dB values are dBm or dB relative to a 1 mW reference.

Limitations
-----------
- Two-way link (uplink / downlink) uses the same link budget; asymmetry not modeled.
- Rain fade, multipath, Doppler shift, and coding gain are not included.
- Shannon capacity is an upper bound on achievable throughput.
- Pointing loss is a fixed attenuation, not a beam-shape model.
- System temperature uses a fixed noise figure, not a sky-noise model.

Reference: Pratt, T., Bostian, C., Allnutt, J. "Satellite Communications", 2e (Wiley 2003),
           Chapter 3 (Friis transmission formula).
"""
from dataclasses import dataclass, field
import math


@dataclass
class RFLinkConfig:
    """All configurable RF link parameters with explicit units."""

    # Transmitter (satellite downlink perspective)
    tx_power_dbm: float = 20.0        # dBm  (100 mW)
    tx_antenna_gain_dbi: float = 10.0 # dBi  transmit antenna gain
    tx_pointing_loss_db: float = 2.0  # dB   fixed pointing offset loss

    # Receiver (ground station)
    rx_antenna_gain_dbi: float = 20.0 # dBi  receive antenna gain
    rx_pointing_loss_db: float = 2.0  # dB   fixed pointing offset loss

    # Channel
    frequency_hz: float = 10e9        # Hz   10 GHz (X-band); use ~2.4 GHz for S-band
    bandwidth_hz: float = 10e6        # Hz   10 MHz

    # Noise
    system_noise_figure_db: float = 3.0  # dB  includes LNA + feed losses

    def validate(self):
        if not math.isfinite(self.tx_power_dbm):
            raise ValueError("tx_power_dbm must be finite")
        if self.frequency_hz <= 0 or not math.isfinite(self.frequency_hz):
            raise ValueError("frequency_hz must be positive and finite")
        if self.bandwidth_hz <= 0 or not math.isfinite(self.bandwidth_hz):
            raise ValueError("bandwidth_hz must be positive and finite")
        if self.system_noise_figure_db < 0:
            raise ValueError("noise figure must be nonnegative")
        return self


_SPEED_OF_LIGHT = 299_792_458.0  # m/s


def free_space_path_loss_db(range_m: float, frequency_hz: float) -> float:
    """FSPL = 20 log10(4π R / λ), dB.  Range and wavelength must be positive."""
    if range_m <= 0:
        raise ValueError("range_m must be positive")
    wavelength = _SPEED_OF_LIGHT / frequency_hz
    return 20.0 * math.log10(4.0 * math.pi * range_m / wavelength)


def thermal_noise_floor_dbm(bandwidth_hz: float, noise_figure_db: float) -> float:
    """kTB noise floor in dBm at 290 K plus system noise figure."""
    # k_B = 1.380649e-23 J/K; T = 290 K; 10 log10(kTB) ≈ -174 dBm/Hz at 290 K
    kTB_per_hz_dbm = -173.98  # dBm/Hz at 290 K (= 10*log10(1.38e-23 * 290 * 1000))
    return kTB_per_hz_dbm + 10.0 * math.log10(bandwidth_hz) + noise_figure_db


def shannon_capacity_bps(bandwidth_hz: float, snr_linear: float) -> float:
    """Shannon–Hartley upper bound: C = B log2(1 + SNR)."""
    if snr_linear < 0:
        raise ValueError("SNR must be nonnegative")
    return bandwidth_hz * math.log2(1.0 + snr_linear)


def rf_link_budget(range_m: float, cfg: RFLinkConfig) -> dict:
    """Return RF link metrics for a given slant range.

    Parameters
    ----------
    range_m : float
        Slant range from satellite to ground station, meters. Must be positive.
    cfg : RFLinkConfig
        Link parameters.

    Returns
    -------
    dict with keys (all float unless noted):
        available : bool — True when received power exceeds noise floor
        fspl_db   : free-space path loss, dB
        eirp_dbm  : effective isotropic radiated power, dBm
        Pr_dbm    : received power, dBm
        noise_floor_dbm : thermal noise floor, dBm
        snr_db    : signal-to-noise ratio, dB
        snr_linear : SNR as a linear power ratio (not dB)
        shannon_capacity_bps : Shannon upper-bound throughput, bit/s
        channel_id : 'rf_data'
    """
    cfg.validate()
    fspl = free_space_path_loss_db(range_m, cfg.frequency_hz)
    eirp = cfg.tx_power_dbm + cfg.tx_antenna_gain_dbi - cfg.tx_pointing_loss_db
    Pr = eirp + cfg.rx_antenna_gain_dbi - cfg.rx_pointing_loss_db - fspl
    noise_floor = thermal_noise_floor_dbm(cfg.bandwidth_hz, cfg.system_noise_figure_db)
    snr_db = Pr - noise_floor
    snr_lin = max(10.0 ** (snr_db / 10.0), 0.0)
    capacity = shannon_capacity_bps(cfg.bandwidth_hz, snr_lin)
    return {
        "channel_id": "rf_data",
        "available": snr_db > 0,
        "fspl_db": fspl,
        "eirp_dbm": eirp,
        "Pr_dbm": Pr,
        "noise_floor_dbm": noise_floor,
        "snr_db": snr_db,
        "snr_linear": snr_lin,
        "shannon_capacity_bps": capacity,
    }

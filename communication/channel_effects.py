"""Apply simulation event disturbances to channel configurations.

Translates satellite state modifiers (set by the event engine) into channel-
specific parameter adjustments.  Each function takes a base channel config and
a disturbance magnitude and returns a *new* config instance; the base is never
mutated.

Design rule: only the channel explicitly targeted by an event is modified.
  - JammingAttack  → rf_data    (signal_loss_db applied as interference)
  - LaserDazzle    → quantum_optical (increased background counts)
  - Intercept-resend eavesdropping → quantum_optical (errors on signal photons)
  - GPSSpoofing    → navigation_position_estimate (not a channel config; handled separately)

Channel-to-channel coupling is NOT modelled automatically.  A jamming attack
on the RF channel does not affect the optical QKD channel unless an explicit
cross-channel dependency is defined and documented.

Units
-----
  signal_loss_db      : dB   (positive = more loss, i.e. worse link)
  background_scale    : linear multiplier on sky_background_hz
  intercept_fraction  : fraction of signal photons intercepted and resent (0–1)
"""
from dataclasses import replace
from communication.rf_link import RFLinkConfig
from communication.optical_link import OpticalLinkConfig


def rf_config_with_jamming(base: RFLinkConfig, signal_loss_db: float) -> RFLinkConfig:
    """Return a copy of *base* with jamming interference applied.

    Jamming is modelled as an increase in the effective receive-path loss,
    equivalent to a reduction in received signal power by *signal_loss_db* dB.
    This is added to the existing rx_pointing_loss_db (which already holds all
    fixed receive-path losses) rather than introduced as a separate field, so
    the Friis equation accounts for it correctly without changing its interface.

    Parameters
    ----------
    base : RFLinkConfig
        Unmodified link configuration.
    signal_loss_db : float
        Additional interference loss in dB (non-negative; negative values are
        silently clamped to 0 to preserve invertibility).
    """
    loss = max(0.0, signal_loss_db)
    return replace(base, rx_pointing_loss_db=base.rx_pointing_loss_db + loss)


def optical_config_with_background_increase(
    base: OpticalLinkConfig, background_scale: float
) -> OpticalLinkConfig:
    """Return a copy of *base* with elevated sky background (laser dazzle / interference).

    Parameters
    ----------
    base : OpticalLinkConfig
        Unmodified optical configuration.
    background_scale : float
        Multiplicative scaling factor for sky_background_hz (≥ 1.0;
        values < 1.0 clamped to 1.0 to avoid improving the baseline).
    """
    scale = max(1.0, background_scale)
    return replace(base, sky_background_hz=base.sky_background_hz * scale)


def optical_config_with_extra_loss(
    base: OpticalLinkConfig, extra_loss_db: float
) -> OpticalLinkConfig:
    """Return a copy of *base* with additional optical-path loss (cloud, obstruction, etc.).

    The loss is added to the pointing_loss_db term so it participates in the
    total-loss calculation without changing the geometric or atmospheric models.
    """
    loss = max(0.0, extra_loss_db)
    return replace(base, pointing_loss_db=base.pointing_loss_db + loss)


def optical_config_with_intercept_resend(
    base: OpticalLinkConfig, intercept_fraction: float
) -> OpticalLinkConfig:
    """Return a copy of *base* with an intercept-resend eavesdropper on the quantum channel.

    Eve measures a fraction of the signal photons in a random basis and resends
    her result.  The optical model turns this into a signal error rate of
    (1 − f) e_d + f (1/4 + e_d/2); full interception gives QBER ≈ 25 %.
    """
    fraction = min(1.0, max(0.0, intercept_fraction))
    return replace(base, intercept_resend_fraction=fraction)


def rf_config_from_state(base: RFLinkConfig, state) -> RFLinkConfig:
    """Apply jamming disturbances from a satellite state object.

    Reads ``state.signal_strength``: a negative value means the signal has been
    attenuated by an event.  The baseline signal strength is 0 dB (no modifier),
    so the loss in dB is ``max(0, -state.signal_strength)``.

    If the state has no ``signal_strength`` attribute (e.g. a plain dict), the
    base config is returned unchanged.
    """
    try:
        ss = state.signal_strength if not isinstance(state, dict) else state.get("signal_strength", 0.0)
        signal_loss_db = max(0.0, -float(ss))
    except (AttributeError, TypeError, ValueError):
        signal_loss_db = 0.0
    return rf_config_with_jamming(base, signal_loss_db)


def optical_config_from_state(base: OpticalLinkConfig, state) -> OpticalLinkConfig:
    """Apply optical disturbances from a satellite state object.

    Currently maps ``state.sensor_noise_rad_s`` (set by LaserDazzle) to a
    background-count increase.  The mapping is:
        background_scale = 1 + sensor_noise_rad_s * 1e6
    which is a coarse surrogate until a proper optical-power–to–background
    model is specified.  The resulting config is also marked cloud_blocked if
    the state has a ``cloud_blocked`` attribute set True.
    """
    try:
        noise = state.sensor_noise_rad_s if not isinstance(state, dict) else state.get("sensor_noise_rad_s", 0.0)
        scale = 1.0 + max(0.0, float(noise)) * 1e6
    except (AttributeError, TypeError, ValueError):
        scale = 1.0

    cfg = optical_config_with_background_increase(base, scale)

    try:
        blocked = state.cloud_blocked if not isinstance(state, dict) else state.get("cloud_blocked", False)
        if blocked:
            cfg = replace(cfg, cloud_blocked=True)
    except (AttributeError, TypeError):
        pass

    return cfg

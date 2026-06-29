"""Resample raw, possibly non-uniform power data onto a uniform 1 Hz grid.

A uniform grid keeps the detection algorithm simple (fixed-width windows,
clean changepoint indices) and gives any future ML model consistent inputs.
"""
from typing import Tuple

import numpy as np

SAMPLE_HZ = 1.0


def _fill_nans(values: np.ndarray) -> np.ndarray:
    """Linearly interpolate NaNs so they don't poison downstream interpolation."""
    v = np.asarray(values, dtype=float)
    nan = np.isnan(v)
    if not nan.any():
        return v
    if nan.all():
        return np.zeros_like(v)
    idx = np.arange(len(v))
    v[nan] = np.interp(idx[nan], idx[~nan], v[~nan])
    return v


def resample_to_1hz(time_s: np.ndarray, power: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Resample (time_s, power) onto integer-second grid 0..floor(duration).

    Args:
        time_s: timestamps in seconds from activity start (monotonic, may be
            non-uniform or contain pause gaps).
        power: power samples aligned with ``time_s``.

    Returns:
        ``(grid_s, power_1hz)`` — the integer-second grid and power interpolated
        onto it. Note pause gaps are interpolated across; that is acceptable for
        v0 since structured intervals do not span pauses.
    """
    t = np.asarray(time_s, dtype=float)
    p = _fill_nans(power)
    n = min(len(t), len(p))
    t, p = t[:n], p[:n]

    if n == 0:
        return np.array([]), np.array([])
    if n == 1:
        return np.array([0.0]), np.array([p[0]])

    # Normalise so the grid starts at 0 regardless of the input's first stamp.
    t = t - t[0]
    grid = np.arange(0.0, np.floor(t[-1]) + 1.0)
    power_1hz = np.interp(grid, t, p)
    return grid, power_1hz

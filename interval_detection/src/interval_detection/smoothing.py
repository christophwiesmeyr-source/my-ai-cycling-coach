"""Time-based moving average for denoising power before detection (and display).

Centred and replicate-padded so interval boundaries are neither phase-shifted
nor dragged toward zero at the ends of the ride. The window is derived from the
median sample spacing, so it works on a raw (possibly non-uniform) series or a
1 Hz resampled one alike.
"""

import numpy as np

DEFAULT_WINDOW_S = 20.0


def moving_average(
    t: np.ndarray, values: np.ndarray, window_s: float = DEFAULT_WINDOW_S
) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    if len(values) < 2:
        return values
    dt = float(np.median(np.diff(t)))
    if dt <= 0:
        return values
    window = int(round(window_s / dt))
    if window < 2:
        return values
    pad = window // 2
    padded = np.pad(values, pad, mode="edge")
    averaged = np.convolve(padded, np.ones(window) / window, mode="same")
    return averaged[pad : pad + len(values)]

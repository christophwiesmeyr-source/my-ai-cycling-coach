"""Shared activity-level metrics: time accounting, elevation, and load primitives.

Centralises the logic that several AI tools (and the UI) need so it lives in one
place. Two design decisions worth knowing:

* Sampling is **not** assumed to be uniform. Recordings can be sub-1 Hz, and
  pauses (manual or Garmin Auto-Pause) appear as *gaps* in the time stream — the
  samples simply stop and resume later. We therefore derive per-sample time
  weights from the actual timestamps and clamp gaps so a pause's duration is
  never attributed to the single sample that follows it.

* "Moving" is taken from Strava's own ``moving`` boolean stream when present.
  We do not re-derive it from speed (GPS-only rides drift and would fool a
  threshold). If Strava gives us no moving stream, moving-only stats are simply
  omitted rather than guessed.
"""
from typing import Optional

import numpy as np
import pandas as pd

# A time delta larger than GAP_FACTOR x the median sampling interval (but at
# least MIN_GAP_SECONDS) is treated as a pause gap rather than a real sample.
GAP_FACTOR = 3.0
MIN_GAP_SECONDS = 5.0


def representative_dt(time_array: np.ndarray) -> float:
    """Robust sampling interval (seconds): the median of positive time deltas.

    Use this instead of ``time[1] - time[0]`` — the first delta is not
    representative when the recording is non-uniform or starts with a gap.
    """
    if time_array is None or len(time_array) < 2:
        return 1.0
    diffs = np.diff(np.asarray(time_array, dtype=float))
    diffs = diffs[diffs > 0]
    if len(diffs) == 0:
        return 1.0
    return float(np.median(diffs))


def sample_weights(time_array: np.ndarray, gap_threshold: Optional[float] = None) -> np.ndarray:
    """Per-sample duration weights in seconds, robust to gaps.

    ``w[i]`` is the time the i-th sample represents (the interval preceding it).
    Sample 0 and any pause gap are set to the median interval so a pause's
    wall-clock duration is not charged to the sample that resumes recording.
    """
    n = len(time_array) if time_array is not None else 0
    if n == 0:
        return np.array([])
    if n == 1:
        return np.array([1.0])

    med = representative_dt(time_array)
    if gap_threshold is None:
        gap_threshold = max(GAP_FACTOR * med, MIN_GAP_SECONDS)

    diffs = np.diff(np.asarray(time_array, dtype=float))
    w = np.empty(n)
    w[0] = med
    w[1:] = diffs
    w[(w > gap_threshold) | (w <= 0)] = med
    return w


def moving_mask(activity) -> Optional[np.ndarray]:
    """Strava's per-sample moving flag as a boolean array, or None if absent."""
    series = activity.get_time_series("moving")
    if series is None or len(series) == 0:
        return None
    return np.asarray(series).astype(bool)


# At or above this cadence the rider is considered to be pedalling (below it,
# coasting). Used for both the coasting share and pedalling-only power.
PEDALING_CADENCE_RPM = 3


def pedaling_mask(activity, cadence_threshold: float = PEDALING_CADENCE_RPM) -> Optional[np.ndarray]:
    """Per-sample mask of samples where the rider is pedalling.

    Prefers cadence (>= threshold); falls back to positive power when there is no
    cadence stream. Returns None if neither stream is available.
    """
    cadence = activity.get_time_series("cadence")
    if cadence is not None and len(cadence) > 0:
        return np.nan_to_num(np.asarray(cadence, dtype=float), nan=0.0) >= cadence_threshold
    power = activity.get_time_series("power")
    if power is not None and len(power) > 0:
        return np.nan_to_num(np.asarray(power, dtype=float), nan=0.0) > 0
    return None


def _count_stops(mask: np.ndarray) -> int:
    """Number of contiguous non-moving runs in a moving mask."""
    if mask is None or len(mask) == 0:
        return 0
    not_moving = (~mask).astype(int)
    starts = int(np.sum(np.diff(not_moving) == 1))
    if not_moving[0]:
        starts += 1
    return starts


def time_summary(activity) -> dict:
    """Elapsed / moving / stopped seconds (+ stop count) where derivable.

    Headline times prefer Strava metadata (``total_elapsed_time`` /
    ``total_moving_time``); moving time falls back to summing weighted
    moving-flagged samples. ``moving_s`` / ``stopped_s`` are omitted when moving
    cannot be determined at all.
    """
    time_array = activity.get_time_array()
    elapsed = getattr(activity, "total_elapsed_time", None)
    if not elapsed:
        elapsed = float(time_array[-1] - time_array[0]) if len(time_array) > 1 else 0.0
    elapsed = float(elapsed)

    moving = getattr(activity, "total_moving_time", None)
    mask = moving_mask(activity)
    if moving is None and mask is not None:
        moving = float(np.sum(sample_weights(time_array)[: len(mask)][mask]))

    result = {"elapsed_s": elapsed}
    if moving is not None:
        moving = float(moving)
        result["moving_s"] = moving
        result["stopped_s"] = max(0.0, elapsed - moving)
    if mask is not None:
        result["stops"] = _count_stops(mask)
    return result


def elevation_changes(altitude: np.ndarray, time_array: np.ndarray,
                      smooth_window_s: float = 20.0) -> tuple[float, float]:
    """Total ascent and descent in metres from a (noisy) altitude stream.

    NaNs are interpolated and the signal is smoothed before summing positive /
    negative deltas, which suppresses GPS/barometric jitter that would otherwise
    inflate both figures.
    """
    if altitude is None or len(altitude) < 2:
        return 0.0, 0.0
    alt = np.asarray(altitude, dtype=float)
    valid = ~np.isnan(alt)
    if np.sum(valid) < 2:
        return 0.0, 0.0
    if not valid.all():
        idx = np.arange(len(alt))
        alt = np.interp(idx, idx[valid], alt[valid])

    # Centred rolling mean with min_periods=1 — unlike a zero-padded convolution
    # it introduces no edge bias, which would otherwise fabricate ascent/descent
    # at the start and end of the ride.
    window = max(1, int(round(smooth_window_s / representative_dt(time_array))))
    smoothed = pd.Series(alt).rolling(window, center=True, min_periods=1).mean().to_numpy()
    diffs = np.diff(smoothed)
    ascent = float(np.sum(diffs[diffs > 0]))
    descent = float(-np.sum(diffs[diffs < 0]))
    return ascent, descent


def weighted_average(series: np.ndarray, time_array: np.ndarray,
                     mask: Optional[np.ndarray] = None) -> Optional[float]:
    """Time-weighted mean over valid (and optionally masked) samples."""
    if series is None or len(series) == 0:
        return None
    s = np.asarray(series, dtype=float)
    w = sample_weights(time_array)
    n = min(len(s), len(w))
    s, w = s[:n], w[:n]
    valid = ~np.isnan(s)
    if mask is not None:
        valid = valid & np.asarray(mask, dtype=bool)[:n]
    if not valid.any() or np.sum(w[valid]) == 0:
        return None
    return float(np.sum(s[valid] * w[valid]) / np.sum(w[valid]))


def normalized_power(power: np.ndarray, time_array: np.ndarray) -> Optional[float]:
    """Coggan Normalized Power: 30 s rolling average, 4th-power mean, 4th root."""
    if power is None or len(power) == 0:
        return None
    p = np.nan_to_num(np.asarray(power, dtype=float), nan=0.0)
    window = max(1, int(round(30.0 / representative_dt(time_array))))
    if len(p) < window:
        return None
    rolling = np.convolve(p, np.ones(window) / window, mode="valid")
    return float(np.mean(rolling ** 4) ** 0.25)


def total_work_kj(power: np.ndarray, time_array: np.ndarray) -> Optional[float]:
    """Total mechanical work in kilojoules (integral of power over time)."""
    if power is None or len(power) == 0:
        return None
    p = np.nan_to_num(np.asarray(power, dtype=float), nan=0.0)
    w = sample_weights(time_array)
    n = min(len(p), len(w))
    return float(np.sum(p[:n] * w[:n]) / 1000.0)

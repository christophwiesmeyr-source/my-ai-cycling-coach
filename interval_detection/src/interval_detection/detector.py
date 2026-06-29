"""Structured work-interval detection.

v1 strategy (chosen after looking at real data — changepoint detection
over-segments because rides are full of surges): an interval is a **sustained
period of elevated power**. On the 20 s-averaged signal:

  1. set an intensity threshold: ``0.8 * ftp`` if FTP is known, else
     ``1.2 * mean(power > 0)`` (self-referential fallback for portability);
  2. take maximal runs above the threshold;
  3. bridge runs separated by a gap <= ``min_separation_s`` (so a brief mid-rep
     dip doesn't fragment one interval) — merge *before* the duration filter;
  4. keep merged runs lasting at least ``min_duration_s``.

This does not yet judge the *variability* of power within an interval; that can
be layered on later.
"""
from typing import List, Optional

import numpy as np

from .resample import resample_to_1hz
from .smoothing import moving_average
from .types import Interval

# Operating envelope (see README). Defaults the consuming app can override.
DEFAULT_MIN_DURATION_S = 60.0
DEFAULT_MIN_SEPARATION_S = 30.0

# Intensity threshold relative to FTP, and the fallback multiple of mean power.
FTP_FRACTION = 0.8
NO_FTP_MULTIPLIER = 1.2


def _intensity_threshold(power_1hz: np.ndarray, ftp: Optional[float]) -> float:
    if ftp:
        return FTP_FRACTION * ftp
    active = power_1hz[power_1hz > 0]
    if active.size == 0:
        return float("inf")  # no power -> nothing can clear the bar
    return NO_FTP_MULTIPLIER * float(active.mean())


def _runs(mask: np.ndarray):
    """Maximal runs of True as (start, end) index pairs, end exclusive."""
    if mask.size == 0:
        return []
    edges = np.diff(mask.astype(np.int8))
    starts = list(np.flatnonzero(edges == 1) + 1)
    ends = list(np.flatnonzero(edges == -1) + 1)
    if mask[0]:
        starts.insert(0, 0)
    if mask[-1]:
        ends.append(len(mask))
    return list(zip(starts, ends))


def _merge_close(runs, grid_s: np.ndarray, max_gap_s: float):
    """Merge runs whose time gap is <= max_gap_s."""
    if not runs:
        return []
    merged = [runs[0]]
    for start, end in runs[1:]:
        prev_start, prev_end = merged[-1]
        if grid_s[start] - grid_s[prev_end - 1] <= max_gap_s:
            merged[-1] = (prev_start, end)
        else:
            merged.append((start, end))
    return merged


def detect_intervals(
    time_s: np.ndarray,
    power: np.ndarray,
    *,
    ftp: Optional[float] = None,
    min_duration_s: float = DEFAULT_MIN_DURATION_S,
    min_separation_s: float = DEFAULT_MIN_SEPARATION_S,
) -> List[Interval]:
    """Detect structured work intervals as sustained elevated-power blocks.

    Args:
        time_s: timestamps in seconds from activity start.
        power: power samples aligned with ``time_s``.
        ftp: optional FTP; sets the intensity threshold to ``0.8 * ftp``. When
            absent, a self-referential ``1.2 * mean(power > 0)`` is used.
        min_duration_s: shortest interval to report.
        min_separation_s: runs closer than this are bridged into one interval.

    Returns:
        Detected intervals ordered by start time.
    """
    grid_s, power_1hz = resample_to_1hz(time_s, power)
    if grid_s.size == 0:
        return []

    smoothed = moving_average(grid_s, power_1hz)
    threshold = _intensity_threshold(power_1hz, ftp)

    runs = _runs(smoothed >= threshold)
    runs = _merge_close(runs, grid_s, min_separation_s)

    intervals = []
    for start, end in runs:
        t0, t1 = float(grid_s[start]), float(grid_s[end - 1])
        if t1 - t0 >= min_duration_s:
            intervals.append(Interval(t0, t1))
    return intervals

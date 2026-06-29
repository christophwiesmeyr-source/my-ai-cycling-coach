"""Structured work-interval detection.

The detection algorithm is intentionally **not implemented yet** — the approach
will be chosen after a seed set of activities has been annotated (looking at
real intervals before committing to features). The current leading hypothesis:
a structured interval is a *sustained region of low power variability at an
elevated level* with clear start/end transitions, so the working signal is
likely a rolling variance / coefficient of variation rather than raw power.

For now ``detect_intervals`` resamples the input and returns an empty list, so
the package, the bench, and the evaluation harness can be built and wired
against a stable interface. An empty detector is a legitimate (zero-recall)
baseline for the metric to measure against.
"""
from typing import List, Optional

import numpy as np

from .resample import resample_to_1hz
from .types import Interval

# Operating envelope (see README). Defaults the consuming app can override.
DEFAULT_MIN_DURATION_S = 60.0
DEFAULT_MIN_SEPARATION_S = 30.0


def detect_intervals(
    time_s: np.ndarray,
    power: np.ndarray,
    *,
    ftp: Optional[float] = None,
    min_duration_s: float = DEFAULT_MIN_DURATION_S,
    min_separation_s: float = DEFAULT_MIN_SEPARATION_S,
) -> List[Interval]:
    """Detect structured work intervals in an activity.

    Args:
        time_s: timestamps in seconds from activity start.
        power: power samples aligned with ``time_s``.
        ftp: optional functional threshold power. When provided it is used as a
            *soft* intensity prior (intervals are usually at least sweet spot);
            it never hard-excludes candidates. ``None`` is fully supported.
        min_duration_s: shortest interval to report.
        min_separation_s: reps closer than this are merged into one.

    Returns:
        Detected intervals, ordered by start time. Currently always ``[]``
        pending the algorithm (see module docstring).
    """
    grid_s, power_1hz = resample_to_1hz(time_s, power)
    if grid_s.size == 0:
        return []

    # TODO(algorithm): choose features after annotating a seed set.
    #   - candidate signal: rolling variance / coefficient of variation
    #   - segment via changepoints (e.g. ruptures) on that signal
    #   - apply ftp as a soft elevated-intensity prior
    #   - enforce min_duration_s and merge reps closer than min_separation_s
    return []

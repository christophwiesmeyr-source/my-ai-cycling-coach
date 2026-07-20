"""Tests for the v1 sustained-elevation detector."""

import numpy as np

from interval_detection import detect_intervals
from interval_detection.detector import (
    _intensity_threshold,
    _merge_close,
    _min_duration_for_intensity,
    _runs,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def test_runs_finds_contiguous_true_blocks() -> None:
    mask = np.array([False, True, True, False, True])
    assert _runs(mask) == [(1, 3), (4, 5)]


def test_runs_handles_edges_and_empty() -> None:
    assert _runs(np.array([True, True])) == [(0, 2)]
    assert _runs(np.array([], dtype=bool)) == []


def test_merge_close_bridges_small_gaps_only() -> None:
    grid = np.arange(300.0)
    runs = [(0, 60), (85, 150), (300 - 1, 300)]  # gaps: 25 s, then large
    merged = _merge_close(runs, grid, max_gap_s=30)
    assert merged[0] == (0, 150)  # 25 s gap bridged
    assert merged[-1] == (300 - 1, 300)  # far run kept separate


def test_merge_close_keeps_large_gaps() -> None:
    grid = np.arange(300.0)
    runs = [(0, 60), (120, 180)]  # 60 s gap
    assert _merge_close(runs, grid, max_gap_s=30) == runs


def test_intensity_threshold_uses_ftp() -> None:
    assert _intensity_threshold(np.array([100.0]), ftp=300) == 240.0


def test_intensity_threshold_fallback_on_mean_positive() -> None:
    power = np.array([0.0, 0.0, 100.0, 200.0])  # mean of positives = 150
    assert _intensity_threshold(power, ftp=None) == 180.0  # 1.2 * 150


# --------------------------------------------------------------------------- #
# End to end
# --------------------------------------------------------------------------- #


def _signal(
    blocks: list[tuple[int, int]], total: int, base: float = 100.0, high: float = 250.0
) -> tuple[np.ndarray, np.ndarray]:
    """Power array: `base` everywhere, `high` inside each (start, end) block."""
    t = np.arange(total, dtype=float)
    p = np.full(total, base)
    for s, e in blocks:
        p[s:e] = high
    return t, p


def test_detects_single_sustained_block() -> None:
    t, p = _signal([(600, 1000)], 1600, high=300)  # 400 s at 1.2x FTP
    intervals = detect_intervals(t, p, ftp=250)  # threshold 200
    assert len(intervals) == 1
    iv = intervals[0]
    # boundaries land near the block, within smoothing slop
    assert 585 <= iv.start_s <= 615
    assert 985 <= iv.end_s <= 1015
    assert iv.duration_s >= 380


def test_ignores_short_surge() -> None:
    t, p = _signal([(600, 640)], 1300)  # 40 s surge, under the 60 s floor
    assert detect_intervals(t, p, ftp=250) == []


def test_two_far_blocks_detected_separately() -> None:
    t, p = _signal([(300, 500), (1000, 1200)], 1600, high=300)  # 1.2x FTP, 90 s floor
    assert len(detect_intervals(t, p, ftp=250)) == 2


# --- power-duration rule -------------------------------------------------- #


def test_min_duration_for_intensity_bands() -> None:
    assert _min_duration_for_intensity(0.85) == 420.0  # low sweet spot
    assert _min_duration_for_intensity(0.95) == 255.0  # sweet spot
    assert _min_duration_for_intensity(1.05) == 150.0  # threshold
    assert _min_duration_for_intensity(1.20) == 75.0  # VO2 / anaerobic


def test_short_modest_block_rejected() -> None:
    # 200 s at 85% FTP -> needs >= 8 min -> dropped (this is the FP cluster)
    t, p = _signal([(600, 800)], 1400, base=100.0, high=213.0)  # 213/250 = 0.85
    assert detect_intervals(t, p, ftp=250) == []


def test_short_hard_block_kept() -> None:
    # 150 s at 120% FTP -> needs only >= 90 s -> kept
    t, p = _signal([(600, 750)], 1400, base=100.0, high=300.0)  # 300/250 = 1.2
    assert len(detect_intervals(t, p, ftp=250)) == 1


def test_long_modest_block_kept() -> None:
    # 700 s at 85% FTP -> clears the 8 min floor -> kept
    t, p = _signal([(600, 1300)], 1900, base=100.0, high=213.0)
    assert len(detect_intervals(t, p, ftp=250)) == 1


def test_no_ftp_uses_average_threshold() -> None:
    # mostly easy with one clear block -> mean stays low, block clears 1.2*mean
    t, p = _signal([(600, 900)], 1500, base=120.0, high=300.0)
    assert len(detect_intervals(t, p)) == 1


def test_empty_input() -> None:
    assert detect_intervals(np.array([]), np.array([])) == []

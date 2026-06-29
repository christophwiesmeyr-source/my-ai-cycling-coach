"""Tests for the v1 sustained-elevation detector."""
import numpy as np

from interval_detection import detect_intervals
from interval_detection.detector import (
    _intensity_threshold,
    _merge_close,
    _runs,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def test_runs_finds_contiguous_true_blocks():
    mask = np.array([False, True, True, False, True])
    assert _runs(mask) == [(1, 3), (4, 5)]


def test_runs_handles_edges_and_empty():
    assert _runs(np.array([True, True])) == [(0, 2)]
    assert _runs(np.array([], dtype=bool)) == []


def test_merge_close_bridges_small_gaps_only():
    grid = np.arange(300.0)
    runs = [(0, 60), (85, 150), (300 - 1, 300)]  # gaps: 25 s, then large
    merged = _merge_close(runs, grid, max_gap_s=30)
    assert merged[0] == (0, 150)            # 25 s gap bridged
    assert merged[-1] == (300 - 1, 300)     # far run kept separate


def test_merge_close_keeps_large_gaps():
    grid = np.arange(300.0)
    runs = [(0, 60), (120, 180)]  # 60 s gap
    assert _merge_close(runs, grid, max_gap_s=30) == runs


def test_intensity_threshold_uses_ftp():
    assert _intensity_threshold(np.array([100.0]), ftp=300) == 240.0


def test_intensity_threshold_fallback_on_mean_positive():
    power = np.array([0.0, 0.0, 100.0, 200.0])  # mean of positives = 150
    assert _intensity_threshold(power, ftp=None) == 180.0  # 1.2 * 150


# --------------------------------------------------------------------------- #
# End to end
# --------------------------------------------------------------------------- #

def _signal(blocks, total, base=100.0, high=250.0):
    """Power array: `base` everywhere, `high` inside each (start, end) block."""
    t = np.arange(total, dtype=float)
    p = np.full(total, base)
    for s, e in blocks:
        p[s:e] = high
    return t, p


def test_detects_single_sustained_block():
    t, p = _signal([(600, 900)], 1500)  # 300 s block
    intervals = detect_intervals(t, p, ftp=250)  # threshold 200
    assert len(intervals) == 1
    iv = intervals[0]
    # boundaries land near the block, within smoothing slop
    assert 590 <= iv.start_s <= 620
    assert 880 <= iv.end_s <= 910
    assert iv.duration_s >= 250


def test_ignores_short_surge():
    t, p = _signal([(600, 640)], 1300)  # 40 s surge, under the 60 s floor
    assert detect_intervals(t, p, ftp=250) == []


def test_two_far_blocks_detected_separately():
    t, p = _signal([(300, 500), (1000, 1200)], 1600)  # 500 s apart
    assert len(detect_intervals(t, p, ftp=250)) == 2


def test_no_ftp_uses_average_threshold():
    # mostly easy with one clear block -> mean stays low, block clears 1.2*mean
    t, p = _signal([(600, 900)], 1500, base=120.0, high=300.0)
    assert len(detect_intervals(t, p)) == 1


def test_empty_input():
    assert detect_intervals(np.array([]), np.array([])) == []

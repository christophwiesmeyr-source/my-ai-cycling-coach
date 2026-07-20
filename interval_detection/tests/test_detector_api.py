"""Tests pinning the public detector interface (algorithm still TBD)."""

import numpy as np

from interval_detection import Interval, detect_intervals


def test_returns_list() -> None:
    t = np.arange(600, dtype=float)
    p = np.full(600, 200.0)
    assert isinstance(detect_intervals(t, p), list)


def test_accepts_optional_ftp_and_envelope_kwargs() -> None:
    t = np.arange(600, dtype=float)
    p = np.full(600, 200.0)
    # Should accept the documented signature without error.
    result = detect_intervals(t, p, ftp=325, min_duration_s=60, min_separation_s=30)
    assert isinstance(result, list)


def test_empty_input_returns_empty() -> None:
    assert detect_intervals(np.array([]), np.array([])) == []


def test_interval_duration_property() -> None:
    iv = Interval(100.0, 250.0)
    assert iv.start_s == 100.0
    assert iv.end_s == 250.0
    assert iv.duration_s == 150.0

"""Tests for the shared moving-average smoother."""
import numpy as np

from interval_detection import moving_average
from interval_detection.smoothing import DEFAULT_WINDOW_S


def test_reduces_variance_and_preserves_length():
    t = np.arange(600.0)
    rng = np.random.default_rng(0)
    p = 200 + 80 * np.sin(t / 5) + rng.normal(0, 40, 600)
    sm = moving_average(t, p)
    assert len(sm) == len(p)
    assert np.isfinite(sm).all()
    assert sm.std() < p.std()


def test_edges_stay_in_range_no_zero_dip():
    t = np.arange(600.0)
    p = np.full(600, 250.0)
    sm = moving_average(t, p)
    # replicate padding keeps a constant signal constant (zero-pad would dip)
    assert np.allclose(sm, 250.0)


def test_window_from_median_dt():
    # 2 s sampling, 20 s window -> 10-sample average
    t = np.arange(0, 200, 2, dtype=float)
    p = np.zeros(len(t)); p[len(t) // 2] = 100.0
    sm = moving_average(t, p)
    # the spike is spread over ~10 samples, so its peak drops to ~100/10
    assert sm.max() < 20.0


def test_short_input_returned_unchanged():
    assert np.array_equal(moving_average([0.0], [200.0]), np.array([200.0]))


def test_default_window_is_20s():
    assert DEFAULT_WINDOW_S == 20.0

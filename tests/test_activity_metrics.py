"""Tests for src/analysis/activity_metrics.py"""
import numpy as np
import pandas as pd
import pytest

from src.data.activity import Activity
from src.analysis.activity_metrics import (
    elevation_changes,
    moving_mask,
    normalized_power,
    representative_dt,
    sample_weights,
    time_summary,
    total_work_kj,
    weighted_average,
)


def _activity(streams, dt=1.0, elapsed=None, moving_time=None):
    n = len(next(iter(streams.values())))
    data = {"timestamp": pd.to_datetime(0, unit="s") + pd.to_timedelta(np.arange(n) * dt, unit="s")}
    data.update(streams)
    return Activity(
        sport="Ride",
        total_elapsed_time=elapsed,
        total_moving_time=moving_time,
        data=pd.DataFrame(data),
    )


# ---------------------------------------------------------------------------
# representative_dt
# ---------------------------------------------------------------------------

class TestRepresentativeDt:
    def test_uniform_1hz(self):
        assert representative_dt(np.arange(100, dtype=float)) == 1.0

    def test_uniform_4s(self):
        assert representative_dt(np.arange(0, 400, 4, dtype=float)) == 4.0

    def test_ignores_leading_gap(self):
        # first delta is a 300 s gap; the rest are 1 s — median should be 1
        t = np.concatenate([[0.0, 300.0], 300.0 + np.arange(1, 50)])
        assert representative_dt(t) == 1.0

    def test_too_short_defaults_to_one(self):
        assert representative_dt(np.array([5.0])) == 1.0


# ---------------------------------------------------------------------------
# sample_weights
# ---------------------------------------------------------------------------

class TestSampleWeights:
    def test_uniform_weights_sum_to_span_plus_one_sample(self):
        t = np.arange(10, dtype=float)
        w = sample_weights(t)
        assert np.allclose(w, 1.0)

    def test_gap_clamped_to_median(self):
        # 1 Hz for 5 samples, then a 600 s pause, then 1 Hz again
        t = np.array([0, 1, 2, 3, 4, 604, 605, 606], dtype=float)
        w = sample_weights(t)
        # the post-gap sample must NOT carry the 600 s gap
        assert w[5] == 1.0
        assert w.max() == 1.0

    def test_single_sample(self):
        assert sample_weights(np.array([0.0])).tolist() == [1.0]


# ---------------------------------------------------------------------------
# moving_mask / time_summary
# ---------------------------------------------------------------------------

class TestTimeSummary:
    def test_prefers_metadata_moving_time(self):
        act = _activity({"power": np.full(100, 200.0)}, elapsed=120, moving_time=100)
        s = time_summary(act)
        assert s["elapsed_s"] == 120
        assert s["moving_s"] == 100
        assert s["stopped_s"] == 20

    def test_moving_from_mask_when_no_metadata(self):
        moving = np.array([True] * 60 + [False] * 40)
        act = _activity({"power": np.full(100, 1.0), "moving": moving}, elapsed=99)
        s = time_summary(act)
        # 60 moving samples at 1 s each
        assert s["moving_s"] == pytest.approx(60.0)
        assert s["stops"] == 1

    def test_no_moving_info_omits_moving_keys(self):
        act = _activity({"power": np.full(50, 100.0)}, elapsed=49)
        s = time_summary(act)
        assert "moving_s" not in s
        assert s["elapsed_s"] == 49

    def test_counts_multiple_stops(self):
        moving = np.array([True] * 10 + [False] * 5 + [True] * 10 + [False] * 5 + [True] * 10)
        act = _activity({"moving": moving})
        assert time_summary(act)["stops"] == 2


# ---------------------------------------------------------------------------
# elevation_changes
# ---------------------------------------------------------------------------

class TestElevationChanges:
    def test_pure_climb_then_descent(self):
        alt = np.concatenate([np.linspace(0, 100, 200), np.linspace(100, 0, 200)])
        t = np.arange(len(alt), dtype=float)
        ascent, descent = elevation_changes(alt, t)
        assert ascent == pytest.approx(100, abs=5)
        assert descent == pytest.approx(100, abs=5)

    def test_noise_does_not_explode(self):
        # flat with small jitter → both should stay tiny after smoothing
        rng = np.random.default_rng(0)
        alt = 50 + rng.normal(0, 0.3, 600)
        t = np.arange(len(alt), dtype=float)
        ascent, descent = elevation_changes(alt, t)
        assert ascent < 15
        assert descent < 15

    def test_handles_nan(self):
        alt = np.linspace(0, 50, 100)
        alt[40:50] = np.nan
        t = np.arange(len(alt), dtype=float)
        ascent, _ = elevation_changes(alt, t)
        assert ascent == pytest.approx(50, abs=5)

    def test_empty_returns_zero(self):
        assert elevation_changes(np.array([]), np.array([])) == (0.0, 0.0)


# ---------------------------------------------------------------------------
# normalized_power / total_work_kj / weighted_average
# ---------------------------------------------------------------------------

class TestPowerMetrics:
    def test_np_of_constant_power_equals_power(self):
        t = np.arange(600, dtype=float)
        assert normalized_power(np.full(600, 250.0), t) == pytest.approx(250.0)

    def test_np_none_when_too_short(self):
        t = np.arange(10, dtype=float)
        assert normalized_power(np.full(10, 200.0), t) is None

    def test_work_kj(self):
        # 100 W for 100 s = 10000 J = 10 kJ
        t = np.arange(100, dtype=float)
        assert total_work_kj(np.full(100, 100.0), t) == pytest.approx(10.0, abs=0.2)

    def test_weighted_average_constant(self):
        t = np.arange(100, dtype=float)
        assert weighted_average(np.full(100, 150.0), t) == pytest.approx(150.0)

    def test_weighted_average_with_mask(self):
        t = np.arange(100, dtype=float)
        series = np.concatenate([np.full(50, 100.0), np.full(50, 200.0)])
        mask = np.array([True] * 50 + [False] * 50)
        assert weighted_average(series, t, mask) == pytest.approx(100.0)

    def test_weighted_average_ignores_nan(self):
        t = np.arange(100, dtype=float)
        series = np.full(100, 120.0)
        series[:50] = np.nan
        assert weighted_average(series, t) == pytest.approx(120.0)

    def test_weighted_average_empty_returns_none(self):
        assert weighted_average(np.array([]), np.array([])) is None

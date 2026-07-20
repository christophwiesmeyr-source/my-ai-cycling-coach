"""Tests for resample_to_1hz."""

import numpy as np

from interval_detection.resample import resample_to_1hz


def test_uniform_1hz_passthrough() -> None:
    t = np.arange(10, dtype=float)
    p = np.arange(10, dtype=float)
    grid, power = resample_to_1hz(t, p)
    assert np.array_equal(grid, np.arange(10, dtype=float))
    assert np.allclose(power, p)


def test_grid_starts_at_zero_regardless_of_offset() -> None:
    t = 1000 + np.arange(5, dtype=float)
    p = np.full(5, 200.0)
    grid, power = resample_to_1hz(t, p)
    assert grid[0] == 0.0
    assert np.allclose(power, 200.0)


def test_non_uniform_input_is_interpolated() -> None:
    # samples at 0, 2, 4 s -> grid fills 1, 3 s by interpolation
    t = np.array([0.0, 2.0, 4.0])
    p = np.array([100.0, 200.0, 100.0])
    grid, power = resample_to_1hz(t, p)
    assert np.array_equal(grid, np.arange(5, dtype=float))
    assert power[1] == 150.0  # halfway between 100 and 200


def test_nans_are_filled() -> None:
    t = np.arange(5, dtype=float)
    p = np.array([100.0, np.nan, np.nan, np.nan, 200.0])
    _, power = resample_to_1hz(t, p)
    assert not np.isnan(power).any()
    assert power[0] == 100.0 and power[-1] == 200.0


def test_empty_input() -> None:
    grid, power = resample_to_1hz(np.array([]), np.array([]))
    assert grid.size == 0 and power.size == 0

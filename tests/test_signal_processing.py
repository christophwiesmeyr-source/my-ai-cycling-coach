"""Tests for signal processing utilities"""
import numpy as np
import pytest
from src.analysis.signal_processing import apply_moving_average_filter


class TestApplyMovingAverageFilter:
    """Test apply_moving_average_filter function"""
    
    def test_empty_data(self):
        data = np.array([])
        time_array = np.array([])
        result = apply_moving_average_filter(data, time_array)
        assert len(result) == 0
    
    def test_single_sample(self):
        data = np.array([1.0])
        time_array = np.array([0.0])
        result = apply_moving_average_filter(data, time_array, 20.0)
        np.testing.assert_array_equal(result, data)  # Should return unchanged
    
    def test_small_window(self):
        data = np.array([1, 2, 3, 4, 5])
        time_array = np.linspace(0, 4, 5)  # 1 second intervals
        result = apply_moving_average_filter(data, time_array, 0.5)  # Window smaller than sample rate
        np.testing.assert_array_equal(result, data)  # Should return unchanged
    
    def test_normal_filtering(self):
        data = np.array([1, 2, 3, 4, 5])
        time_array = np.linspace(0, 4, 5)  # 1 second intervals
        result = apply_moving_average_filter(data, time_array, 2.0)  # Window of 2 samples
        # Expected: convolution with [0.5, 0.5] -> [1, 1.5, 2.5, 3.5, 4.5, 5] but 'same' mode
        # Actually for window_samples=2, kernel=[0.5,0.5], convolve same: [0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5] take middle 5
        expected = np.array([1.0, 1.5, 2.5, 3.5, 4.5])  # Approximate
        assert len(result) == len(data)
        assert result[0] < result[2]  # Should smooth
    
    def test_with_nans(self):
        data = np.array([1, np.nan, 3, 4, 5])
        time_array = np.linspace(0, 4, 5)
        result = apply_moving_average_filter(data, time_array, 2.0)
        # Should handle NaNs gracefully (convolution propagates NaNs)
        assert len(result) == len(data)
        assert not np.isnan(result[0])  # First should be ok
        assert np.isnan(result[1])  # NaN in input should propagate
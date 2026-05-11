"""Tests for Activity data class"""
import numpy as np
import pandas as pd
import pytest
from src.data import Activity


class TestActivity:
    """Test Activity class methods"""
    
    def test_get_time_series_normal(self, sample_activity):
        series = sample_activity.get_time_series('power', 10, 20)
        assert len(series) == 10
        assert isinstance(series, np.ndarray)
    
    def test_get_time_series_full_range(self, sample_activity):
        series = sample_activity.get_time_series('power')
        assert len(series) == len(sample_activity.data)
    
    def test_get_time_series_invalid_indices(self, sample_activity):
        # Negative start
        series = sample_activity.get_time_series('power', -1, 10)
        assert len(series) == 0  # iloc handles negative as empty slice
        
        # End beyond length
        series = sample_activity.get_time_series('power', 90, 110)
        assert len(series) == 10  # Last 10
    
    def test_get_time_series_missing_column(self, sample_activity):
        series = sample_activity.get_time_series('nonexistent')
        assert len(series) == 0
    
    def test_get_time_array(self, sample_activity):
        time_array = sample_activity.get_time_array()
        assert len(time_array) == len(sample_activity.data)
        assert time_array[0] == 0.0  # Should start at 0
        assert time_array[-1] > 0  # Should be positive
    
    def test_get_time_array_empty(self, empty_activity):
        time_array = empty_activity.get_time_array()
        assert len(time_array) == 0
    
    def test_available_metrics(self, sample_activity):
        metrics = sample_activity.available_metrics
        assert 'power' in metrics
        assert 'heart_rate' in metrics
        assert 'distance' in metrics
        assert 'timestamp' not in metrics  # Should exclude timestamp
    
    def test_get_data_range(self, sample_activity):
        start, end = sample_activity.get_data_range()
        assert start == 0.0
        time_array = sample_activity.get_time_array()
        assert end == time_array[-1]
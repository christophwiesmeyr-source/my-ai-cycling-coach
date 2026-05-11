"""Tests for statistics calculations"""
import numpy as np
import pytest
from src.analysis.statistics import rolling_max, StatisticsCalculator, ROLLING_WINDOWS
from src.data import Activity


class TestRollingMax:
    """Test rolling_max function"""
    
    def test_empty_array(self):
        assert rolling_max(np.array([]), 10) == 0.0
    
    def test_zero_window(self):
        data = np.array([1, 2, 3])
        assert rolling_max(data, 0) == 0.0
    
    def test_negative_window(self):
        data = np.array([1, 2, 3])
        assert rolling_max(data, -1) == 0.0
    
    def test_window_larger_than_data(self):
        data = np.array([1, 2, 3])
        # Should return max of available data
        assert rolling_max(data, 10) == 3.0
    
    def test_normal_case(self):
        data = np.array([1, 2, 3, 4, 5])
        # Window of 3: averages [2, 3, 4], max is 4
        result = rolling_max(data, 3)
        assert result == 4.0
    
    def test_with_nans(self):
        data = np.array([1, np.nan, 3, 4, 5])
        # Clean data: [1, 3, 4, 5], window 3: averages [8/3, 12/3, 4], max 4
        result = rolling_max(data, 3)
        assert result == 4.0
    
    def test_all_nans(self):
        data = np.array([np.nan, np.nan])
        assert rolling_max(data, 2) == 0.0


class TestStatisticsCalculator:
    """Test StatisticsCalculator.calculate_specific_stats"""
    
    def test_empty_time_array(self, empty_activity):
        result = StatisticsCalculator.calculate_specific_stats(empty_activity, 0, 10)
        assert result == {}
    
    def test_invalid_indices(self, sample_activity):
        # Start >= end
        result = StatisticsCalculator.calculate_specific_stats(sample_activity, 10, 5)
        assert result == {}
        
        # Negative start
        result = StatisticsCalculator.calculate_specific_stats(sample_activity, -1, 10)
        assert result == {}
        
        # End beyond length
        result = StatisticsCalculator.calculate_specific_stats(sample_activity, 0, 1000)
        assert result == {}
    
    def test_single_sample(self, sample_activity):
        # Modify to have single sample
        single_df = sample_activity.data.iloc[:1].copy()
        single_activity = Activity(
            sport='cycling',
            start_time='2023-01-01T00:00:00',
            total_distance=10.0,
            total_elapsed_time=10.0,
            data=single_df
        )
        result = StatisticsCalculator.calculate_specific_stats(single_activity, 0, 1)
        # Should have some basic stats
        assert 'Total Time' in result
    
    def test_normal_calculation(self, sample_activity):
        result = StatisticsCalculator.calculate_specific_stats(sample_activity, 10, 50)
        
        # Check presence of expected keys
        expected_keys = [
            'Distance Total', 'Distance Start', 'Distance End',
            'Power Max', 'Power Avg', 'Power 1min Max', 'Power 10min Max', 'Power 20min Max',
            'HR min', 'HR max', 'HR avg',
            'Total Time'
        ]
        for key in expected_keys:
            assert key in result, f"Missing key: {key}"
        
        # Check types and units
        assert isinstance(result['Power Max'][0], float)
        assert result['Power Max'][1] == 'W'
        assert isinstance(result['Distance Total'][0], float)
        assert result['Distance Total'][1] == 'km'
    
    def test_missing_metrics(self, sample_activity):
        # Remove power column
        no_power_df = sample_activity.data.drop(columns=['power'])
        no_power_activity = Activity(
            sport='cycling',
            start_time='2023-01-01T00:00:00',
            total_distance=1000.0,
            total_elapsed_time=1000.0,
            data=no_power_df
        )
        result = StatisticsCalculator.calculate_specific_stats(no_power_activity, 10, 50)
        
        # Should not have power stats
        assert 'Power Max' not in result
        # But should have others
        assert 'Distance Total' in result
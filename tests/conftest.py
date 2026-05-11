"""Pytest configuration and fixtures"""
import pytest
import pandas as pd
import numpy as np
from src.data import Activity


@pytest.fixture
def sample_activity():
    """Create a sample Activity with test data"""
    # Create sample data with 100 points over 1000 seconds
    time_points = pd.date_range('2023-01-01', periods=100, freq='10s')
    data = {
        'timestamp': time_points,
        'power': np.random.normal(200, 50, 100),  # Watts
        'heart_rate': np.random.normal(150, 10, 100),  # BPM
        'distance': np.cumsum(np.random.normal(10, 2, 100)),  # Cumulative meters
    }
    df = pd.DataFrame(data)
    
    return Activity(
        sport='cycling',
        start_time='2023-01-01T00:00:00',
        total_distance=1000.0,
        total_elapsed_time=1000.0,
        data=df
    )


@pytest.fixture
def empty_activity():
    """Create an empty Activity for edge case testing"""
    df = pd.DataFrame({'timestamp': pd.to_datetime([])})
    return Activity(
        sport='cycling',
        start_time='2023-01-01T00:00:00',
        total_distance=0.0,
        total_elapsed_time=0.0,
        data=df
    )
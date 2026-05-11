"""Signal processing utilities for data analysis"""
import numpy as np


def apply_moving_average_filter(data: np.ndarray, time_array: np.ndarray, window_seconds: float = 20.0) -> np.ndarray:
    """
    Apply moving average filter with time-based window

    Args:
        data: Input data array
        time_array: Time array in seconds
        window_seconds: Window size in seconds

    Returns:
        Filtered data array
    """
    if len(data) == 0 or len(time_array) == 0:
        return data

    # Calculate window size in samples
    # Find the number of samples that fit within the time window
    time_diffs = np.diff(time_array)
    if len(time_diffs) == 0:
        return data

    avg_sample_rate = 1.0 / np.mean(time_diffs)
    window_samples = int(window_seconds * avg_sample_rate)

    if window_samples < 2:
        return data  # Not enough samples for meaningful filtering

    # Apply moving average using convolution
    kernel = np.ones(window_samples) / window_samples
    filtered = np.convolve(data, kernel, mode='same')

    return filtered
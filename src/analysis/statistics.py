"""Statistics calculator for activity data analysis"""
from typing import Optional
import numpy as np
from dataclasses import dataclass


@dataclass
class Statistics:
    """Container for calculated statistics"""
    metric: str
    count: int
    mean: float
    stddev: float
    min: float
    max: float
    duration_seconds: float
    
    def __str__(self) -> str:
        return (
            f"{self.metric.upper()}\n"
            f"  Count: {self.count}\n"
            f"  Mean: {self.mean:.1f}\n"
            f"  StdDev: {self.stddev:.1f}\n"
            f"  Min: {self.min:.1f}\n"
            f"  Max: {self.max:.1f}\n"
            f"  Duration: {self.duration_seconds:.1f}s ({self.duration_seconds/60:.1f}m)"
        )


class StatisticsCalculator:
    """Calculates statistics for activity data selections"""
    
    @staticmethod
    def calculate_stats(data: np.ndarray, duration_seconds: float) -> Optional[Statistics]:
        """
        Calculate statistics for a data array
        
        Args:
            data: NumPy array of values
            duration_seconds: Duration of the selection in seconds
            
        Returns:
            Statistics object or None if data is empty
        """
        if len(data) == 0 or np.all(np.isnan(data)):
            return None
        
        # Filter out NaN values
        valid_data = data[~np.isnan(data)]
        
        if len(valid_data) == 0:
            return None
        
        return Statistics(
            metric='',
            count=len(valid_data),
            mean=float(np.mean(valid_data)),
            stddev=float(np.std(valid_data)),
            min=float(np.min(valid_data)),
            max=float(np.max(valid_data)),
            duration_seconds=duration_seconds
        )
    
    @staticmethod
    def calculate_multiple_stats(activity, start_idx: int = 0, end_idx: int = -1) -> dict[str, Statistics]:
        """
        Calculate statistics for all available metrics in a time range
        
        Args:
            activity: Activity object
            start_idx: Start index (inclusive)
            end_idx: End index (exclusive)
            
        Returns:
            Dictionary mapping metric names to Statistics objects
        """
        stats = {}
        
        # Calculate duration for this selection
        time_array = activity.get_time_array(start_idx, end_idx)
        if len(time_array) > 0:
            duration = time_array[-1] - time_array[0]
        else:
            duration = 0
        
        # Calculate stats for each available metric
        for metric in activity.available_metrics:
            data = activity.get_time_series(metric, start_idx, end_idx)
            metric_stats = StatisticsCalculator.calculate_stats(data, duration)
            if metric_stats:
                metric_stats.metric = metric
                stats[metric] = metric_stats
        
        return stats

"""Analysis layer for computing statistics from activity data"""
from .statistics import StatisticsCalculator
from .signal_processing import apply_moving_average_filter
from .activity_metrics import (
    elevation_changes,
    moving_mask,
    normalized_power,
    representative_dt,
    sample_weights,
    time_summary,
    total_work_kj,
    weighted_average,
)

__all__ = [
    'StatisticsCalculator',
    'apply_moving_average_filter',
    'elevation_changes',
    'moving_mask',
    'normalized_power',
    'representative_dt',
    'sample_weights',
    'time_summary',
    'total_work_kj',
    'weighted_average',
]

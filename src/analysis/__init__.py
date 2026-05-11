"""Analysis layer for computing statistics from activity data"""
from .statistics import StatisticsCalculator
from .signal_processing import apply_moving_average_filter

__all__ = ['StatisticsCalculator', 'apply_moving_average_filter']

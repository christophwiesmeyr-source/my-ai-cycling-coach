"""Detect structured work intervals from cycling power data.

Public API:
    detect_intervals(time_s, power, *, ftp=None, ...) -> list[Interval]
    Interval(start_s, end_s)
"""
from .detector import detect_intervals
from .smoothing import moving_average
from .types import Interval

__all__ = ["detect_intervals", "Interval", "moving_average"]

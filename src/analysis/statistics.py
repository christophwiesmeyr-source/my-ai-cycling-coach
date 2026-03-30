"""Statistics calculator for activity data analysis"""
import datetime
from typing import Optional
import numpy as np
from dataclasses import dataclass


def rolling_max(data: np.ndarray, window: int) -> float:
    """Compute the maximum of rolling averages over a window."""
    if len(data) == 0 or window <= 0:
        return 0.0
    data_clean = data[~np.isnan(data)]
    if window > len(data_clean):
        return np.nan
    cumsum = np.concatenate(([0.0], np.cumsum(data_clean)))
    win_sum = cumsum[window:] - cumsum[:-window]
    rolling_avgs = win_sum / window
    return float(np.max(rolling_avgs))


class StatisticsCalculator:
    """Calculates specific statistics for activity data selections"""
    
    @staticmethod
    def calculate_specific_stats(activity, start_idx: int, end_idx: int) -> dict:
        """
        Calculate specific statistics for DISTANCE, POWER, HEART RATE, Total Time, and Total Moving Time.
        
        Args:
            activity: Activity object
            start_idx: Start index (inclusive)
            end_idx: End index (exclusive)
            
        Returns:
            Dictionary with keys like 'Distance Total', 'Power Max', etc., each as [value, unit]
        """
        out = {}
        time_array = activity.get_time_array()

        if end_idx == -1:
            end_idx = len(time_array)
        
        if len(time_array) == 0 or start_idx < 0 or end_idx > len(time_array) or start_idx >= end_idx:
            return out
        
        # Calculate sampling rate (dt in seconds per sample)
        if len(time_array) < 2:
            dt = 1.0
        else:
            dt = time_array[1] - time_array[0]
        
        for metric in ["distance", "power", "heart_rate"]:
            if metric not in activity.available_metrics:
                continue
            
            data = np.asarray(activity.get_time_series(metric))
            data = data[:len(time_array)]  # Align with time_array
            
            part = data[start_idx:end_idx]
            if len(part) == 0:
                continue
            
            if metric == "distance":
                # Total distance from full data
                out["Distance Total"] = [float(data[-1])/1000 if len(data) > 0 else 0.0, "km"]
                # Start and end distance from slice
                out["Distance Start"] = [float(part[0])/1000, "km"]
                out["Distance End"] = [float(part[-1])/1000, "km"]
            elif metric == "power":
                # Max and avg power from slice
                out["Power Max"] = [float(np.nanmax(part)), "W"]
                out["Power Avg"] = [float(np.nanmean(part)), "W"]
                # Rolling max averages from slice
                for secs in (10, 60, 600, 1200):
                    window_samples = max(1, int(secs / dt))
                    if secs == 60:
                        out[f"Power 1min Max"] = [rolling_max(part, window_samples), "W"]
                    elif secs == 600:
                        out[f"Power 10min Max"] = [rolling_max(part, window_samples), "W"]
                    elif secs == 1200:
                        out[f"Power 20min Max"] = [rolling_max(part, window_samples), "W"]
                    else:
                        out[f"Power {secs}s Max"] = [rolling_max(part, window_samples), "W"]
            elif metric == "heart_rate":
                # Min, max, avg from slice
                out["HR min"] = [float(np.nanmin(part)), "bpm"]
                out["HR max"] = [float(np.nanmax(part)), "bpm"]
                out["HR avg"] = [float(np.nanmean(part)), "bpm"]
        
        # Total Time for the slice
        if len(time_array) > start_idx:
            total_time = time_array[end_idx - 1] - time_array[start_idx]
            duration = datetime.timedelta(seconds=total_time)
            time_text = str(duration) if activity.duration_seconds else "N/A"
            out["Total Time"] = [time_text, ""]
        else:
            out["Total Time"] = [0, "s"]
        
        return out

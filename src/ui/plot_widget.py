"""Plot widget for interactive data visualization"""
from typing import Optional

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import pyqtSignal, QObject
from PyQt6.QtGui import QColor, QPen

from src.data import Activity


class PlotWidget(pg.GraphicsLayoutWidget):
    """Widget for plotting activity data with interactive selection"""
    
    # Signal emitted when a time range is selected
    selection_changed = pyqtSignal(int, int)  # start_idx, end_idx
    
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        
        self.current_activity: Optional[Activity] = None
        self.primary_metric: Optional[str] = None
        self.secondary_metric: Optional[str] = None

        self.setBackground('w')

        # Main plot (primary metric)
        self.plot = self.addPlot(row=0, col=0, title="Metrics")
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        self.plot.setLabel('bottom', 'Time (s)')

        # Secondary y-axis viewbox
        self.plot.showAxis('right')
        self.plot.getAxis('right').setLabel('')
        self.secondary_view = pg.ViewBox()
        self.plot.scene().addItem(self.secondary_view)
        self.plot.getAxis('right').linkToView(self.secondary_view)
        self.secondary_view.setXLink(self.plot)

        # Keep the views aligned when resizing
        self.plot.getViewBox().sigResized.connect(self._update_views)

        # Data lines
        self.line_primary: Optional[pg.PlotDataItem] = None
        self.line_secondary: Optional[pg.PlotDataItem] = None
        
        # Selection region
        self.selection_region = pg.LinearRegionItem()
        self.selection_region.setZValue(10)
        self.plot.addItem(self.selection_region)
        
        # Connect selection change
        self.selection_region.sigRegionChangeFinished.connect(self._on_selection_changed)
    
    def _apply_moving_average_filter(self, data: np.ndarray, time_array: np.ndarray, window_seconds: float = 20.0) -> np.ndarray:
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
    
    def _update_views(self):
        """Keep secondary view geometry and axis sync with primary plot"""
        self.secondary_view.setGeometry(self.plot.getViewBox().sceneBoundingRect())
        self.secondary_view.linkedViewChanged(self.plot.getViewBox(), self.secondary_view.XAxis)
    
    def plot_activity(self, activity: Activity, primary_metric: Optional[str], secondary_metric: Optional[str], 
                     primary_filtered: bool = False, secondary_filtered: bool = False):
        """
        Plot activity data
        
        Args:
            activity: Activity object to plot
            primary_metric: Name of metric for primary plot
            secondary_metric: Name of metric for secondary plot
        """
        self.current_activity = activity
        self.primary_metric = primary_metric
        self.secondary_metric = secondary_metric
        
        # Clear previous plot data
        self.plot.clear()
        self.secondary_view.clear()

        # Re-add selection region to the primary plot
        self.plot.addItem(self.selection_region)

        # Get time array
        time_array = activity.get_time_array()

        if len(time_array) == 0:
            return

        # Plot primary metric on left y-axis
        if primary_metric and primary_metric in activity.available_metrics:
            data = activity.get_time_series(primary_metric)
            if primary_filtered:
                data = self._apply_moving_average_filter(data, time_array, 20.0)
            self.line_primary = self.plot.plot(
                time_array, data,
                pen=pg.mkPen(color=QColor(25, 118, 210), width=2),
                name=primary_metric
            )
            self.plot.setLabel('left', primary_metric.replace('_', ' ').title())
        else:
            self.line_primary = None
            self.plot.setLabel('left', '')

        # Plot secondary metric on right y-axis (optional)
        if secondary_metric and secondary_metric in activity.available_metrics:
            data = activity.get_time_series(secondary_metric)
            if secondary_filtered:
                data = self._apply_moving_average_filter(data, time_array, 20.0)
            self.line_secondary = pg.PlotDataItem(
                time_array, data,
                pen=pg.mkPen(color=QColor(244, 67, 54), width=2),
                name=secondary_metric
            )
            self.secondary_view.addItem(self.line_secondary)
            self.plot.getAxis('right').setLabel(secondary_metric.replace('_', ' ').title())
        else:
            self.line_secondary = None
            self.plot.getAxis('right').setLabel('')

        # Set initial selection region to full range
        self.selection_region.setRegion((time_array[0], time_array[-1]))

        # Auto-scale
        self.plot.autoRange()
        self.secondary_view.autoRange()

    def _on_selection_changed(self):
        """Handle selection region change"""
        if not self.current_activity or len(self.current_activity.data) == 0:
            return
        
        # Get selected time range
        min_time, max_time = self.selection_region.getRegion()
        
        # Convert time values to indices
        time_array = self.current_activity.get_time_array()
        
        if len(time_array) == 0:
            return
        
        # Find closest indices
        start_idx = np.searchsorted(time_array, min_time, side='left')
        end_idx = np.searchsorted(time_array, max_time, side='right')
        
        # Clamp to valid range
        start_idx = max(0, min(start_idx, len(time_array) - 1))
        end_idx = max(start_idx + 1, min(end_idx, len(time_array)))
        
        self.selection_changed.emit(start_idx, end_idx)
    
    def reset_view(self):
        """Reset plot to show all data"""
        if not self.current_activity or len(self.current_activity.data) == 0:
            return

        self.plot.autoRange()
        self.secondary_view.autoRange()

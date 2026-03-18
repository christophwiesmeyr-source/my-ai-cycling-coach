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
        
        # Create plots
        self.plot_primary = self.addPlot(row=0, col=0, title="Primary Metric")
        self.plot_secondary = self.addPlot(row=1, col=0, title="Secondary Metric")
        
        # Link the x-axis between plots for synchronized zooming
        self.plot_secondary.setXLink(self.plot_primary)
        
        # Data lines
        self.line_primary: Optional[pg.PlotDataItem] = None
        self.line_secondary: Optional[pg.PlotDataItem] = None
        
        # Selection region
        self.selection_region = pg.LinearRegionItem()
        self.selection_region.setZValue(10)
        self.plot_primary.addItem(self.selection_region)
        
        # Set colors
        self._setup_colors()
        
        # Connect selection change
        self.selection_region.sigRegionChangeFinished.connect(self._on_selection_changed)
    
    def _setup_colors(self):
        """Setup color scheme"""
        
        # Set grid
        self.plot_primary.showGrid(x=True, y=True, alpha=0.3)
        self.plot_secondary.showGrid(x=True, y=True, alpha=0.3)
    
    def plot_activity(self, activity: Activity, primary_metric: str, secondary_metric: str):
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
        
        # Clear previous plots
        self.plot_primary.clear()
        self.plot_secondary.clear()
        
        # Re-add selection region
        self.plot_primary.addItem(self.selection_region)
        
        # Get time array
        time_array = activity.get_time_array()
        
        if len(time_array) == 0:
            return
        
        # Plot primary metric
        if primary_metric and primary_metric in activity.available_metrics:
            data = activity.get_time_series(primary_metric)
            self.line_primary = self.plot_primary.plot(
                time_array, data,
                pen=pg.mkPen(color=QColor(25, 118, 210), width=2),
                name=primary_metric
            )
            self.plot_primary.setLabel('left', primary_metric.replace('_', ' ').title())
            self.plot_primary.setLabel('bottom', 'Time (s)')
        
        # Plot secondary metric
        if secondary_metric and secondary_metric in activity.available_metrics:
            data = activity.get_time_series(secondary_metric)
            self.line_secondary = self.plot_secondary.plot(
                time_array, data,
                pen=pg.mkPen(color=QColor(244, 67, 54), width=2),
                name=secondary_metric
            )
            self.plot_secondary.setLabel('left', secondary_metric.replace('_', ' ').title())
            self.plot_secondary.setLabel('bottom', 'Time (s)')
        
        # Set initial selection region to full range
        self.selection_region.setRegion((time_array[0], time_array[-1]))
        
        # Auto-scale
        self.plot_primary.autoRange()
        self.plot_secondary.autoRange()
    
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
        
        self.plot_primary.autoRange()
        self.plot_secondary.autoRange()

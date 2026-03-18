"""Main UI window for FIT data visualization"""
import sys
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QFileDialog, QLabel, QComboBox, QTextEdit, QSplitter
)
from PyQt6.QtCore import Qt, QTimer
import pyqtgraph as pg

from src.data import FITParser, Activity
from src.analysis import StatisticsCalculator
from .plot_widget import PlotWidget


class MainWindow(QMainWindow):
    """Main application window"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FIT Data Visualizer - Cycling Analysis")
        self.setGeometry(100, 100, 1400, 800)
        
        self.current_activity: Optional[Activity] = None
        self.current_directory: Optional[Path] = None
        
        self._init_ui()
    
    def _init_ui(self):
        """Initialize UI components"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QHBoxLayout()
        
        # Left panel: Controls
        left_panel = QWidget()
        left_layout = QVBoxLayout()
        
        # File controls
        self._create_file_controls(left_layout)
        
        # Activity selection
        self._create_activity_selection(left_layout)
        
        # Metric selection
        self._create_metric_controls(left_layout)
        
        # Statistics display
        self._create_statistics_display(left_layout)
        
        left_layout.addStretch()
        left_panel.setLayout(left_layout)
        left_panel.setMaximumWidth(350)
        
        # Right panel: Plot
        self.plot_widget = PlotWidget()
        
        # Add to main layout
        main_layout.addWidget(left_panel)
        main_layout.addWidget(self.plot_widget, 1)
        
        central_widget.setLayout(main_layout)
    
    def _create_file_controls(self, layout):
        """Create file loading controls"""
        label = QLabel("File Management")
        label.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(label)
        
        btn_open_dir = QPushButton("Open Folder")
        btn_open_dir.clicked.connect(self._open_directory)
        layout.addWidget(btn_open_dir)
        
        btn_open_file = QPushButton("Open FIT File")
        btn_open_file.clicked.connect(self._open_file)
        layout.addWidget(btn_open_file)
        
        self.label_current_file = QLabel("No file loaded")
        self.label_current_file.setStyleSheet("color: #666; font-size: 10px;")
        self.label_current_file.setWordWrap(True)
        layout.addWidget(self.label_current_file)
    
    def _create_activity_selection(self, layout):
        """Create activity selection dropdown"""
        layout.addSpacing(15)
        label = QLabel("Activity Info")
        label.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(label)
        
        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setMaximumHeight(150)
        layout.addWidget(self.info_text)
    
    def _create_metric_controls(self, layout):
        """Create metric selection controls"""
        layout.addSpacing(15)
        label = QLabel("Metrics")
        label.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(label)
        
        self.combo_primary = QComboBox()
        self.combo_primary.currentTextChanged.connect(self._on_metric_changed)
        layout.addWidget(QLabel("Primary:"))
        layout.addWidget(self.combo_primary)
        
        self.combo_secondary = QComboBox()
        self.combo_secondary.currentTextChanged.connect(self._on_metric_changed)
        layout.addWidget(QLabel("Secondary:"))
        layout.addWidget(self.combo_secondary)
        
        btn_reset = QPushButton("Reset View")
        btn_reset.clicked.connect(self._reset_plot_view)
        layout.addWidget(btn_reset)
    
    def _create_statistics_display(self, layout):
        """Create statistics display area"""
        layout.addSpacing(15)
        label = QLabel("Selection Statistics")
        label.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(label)
        
        self.stats_text = QTextEdit()
        self.stats_text.setReadOnly(True)
        layout.addWidget(self.stats_text)
    
    def _open_directory(self):
        """Open a directory and list FIT files"""
        directory = QFileDialog.getExistingDirectory(
            self, "Select Folder with FIT Files"
        )
        if directory:
            self.current_directory = Path(directory)
            fit_files = FITParser.find_fit_files(directory)
            if fit_files:
                # Load the first file
                self._load_fit_file(fit_files[0])
            else:
                self.label_current_file.setText("No .fit files found in directory")
    
    def _open_file(self):
        """Open a single FIT file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select FIT File", "", "FIT Files (*.fit)"
        )
        if file_path:
            self._load_fit_file(file_path)
    
    def _load_fit_file(self, file_path):
        """Load a FIT file"""
        try:
            self.current_activity = FITParser.parse(file_path)
            self.label_current_file.setText(f"Loaded: {Path(file_path).name}")
            
            # Update UI
            self._update_activity_info()
            self._update_metric_dropdowns()
            self._plot_data()
            
        except Exception as e:
            self.label_current_file.setText(f"Error: {str(e)}")
    
    def _update_activity_info(self):
        """Update activity information display"""
        if not self.current_activity:
            return
        
        info = (
            f"Sport: {self.current_activity.sport}\n"
            f"Duration: {self.current_activity.duration_seconds:.1f}s "
            f"({self.current_activity.duration_seconds/60:.1f}m)\n"
            f"Records: {len(self.current_activity.data)}\n"
            f"Distance: {self.current_activity.total_distance or 'N/A'} m\n"
            f"Start: {self.current_activity.start_time or 'N/A'}"
        )
        self.info_text.setText(info)
    
    def _update_metric_dropdowns(self):
        """Update metric dropdown menus"""
        if not self.current_activity:
            return
        
        metrics = self.current_activity.available_metrics
        
        self.combo_primary.blockSignals(True)
        self.combo_secondary.blockSignals(True)
        
        self.combo_primary.clear()
        self.combo_secondary.clear()
        
        # Add metrics to dropdowns
        for metric in metrics:
            self.combo_primary.addItem(metric)
            self.combo_secondary.addItem(metric)
        
        # Set defaults (prefer power as primary, heart_rate as secondary)
        if 'power' in metrics:
            self.combo_primary.setCurrentText('power')
        if 'heart_rate' in metrics:
            self.combo_secondary.setCurrentText('heart_rate')
        
        self.combo_primary.blockSignals(False)
        self.combo_secondary.blockSignals(False)
    
    def _plot_data(self):
        """Plot the current activity data"""
        if not self.current_activity:
            return
        
        primary_metric = self.combo_primary.currentText()
        secondary_metric = self.combo_secondary.currentText()
        
        self.plot_widget.plot_activity(
            self.current_activity,
            primary_metric,
            secondary_metric
        )
        
        # Connect selection signal
        self.plot_widget.selection_changed.connect(self._on_selection_changed)
    
    def _on_metric_changed(self):
        """Handle metric selection change"""
        self._plot_data()
    
    def _reset_plot_view(self):
        """Reset plot view to show all data"""
        self.plot_widget.reset_view()
    
    def _on_selection_changed(self, start_idx: int, end_idx: int):
        """Handle selection change in plot"""
        if not self.current_activity or start_idx >= end_idx:
            self.stats_text.setText("No selection")
            return
        
        # Calculate statistics
        stats = StatisticsCalculator.calculate_multiple_stats(
            self.current_activity, start_idx, end_idx
        )
        
        # Format output
        output = "SELECTION STATISTICS\n"
        output += f"Range: {start_idx} to {end_idx} ({end_idx - start_idx} points)\n\n"
        
        for metric, stat in stats.items():
            output += str(stat) + "\n\n"
        
        self.stats_text.setText(output)

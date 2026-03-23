"""Main UI window for FIT data visualization"""
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QFileDialog, QLabel, QComboBox, QTextEdit
)
from PyQt6.QtCore import Qt
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
        self.activity_path_map = {}

        self._init_ui()

    def _init_ui(self):
        """Initialize UI components"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout()

        left_panel = QWidget()
        left_layout = QVBoxLayout()

        self._create_file_controls(left_layout)
        self._create_activity_selection(left_layout)
        self._create_metric_controls(left_layout)
        self._create_full_statistics_display(left_layout)
        self._create_selection_statistics_display(left_layout)

        left_layout.addStretch()
        left_panel.setLayout(left_layout)
        left_panel.setMaximumWidth(350)

        self.plot_widget = PlotWidget()

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

    def _create_activity_selection(self, layout):
        layout.addSpacing(15)
        label = QLabel("Activity Selection")
        label.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(label)

        self.combo_activity = QComboBox()
        self.combo_activity.currentTextChanged.connect(self._on_activity_selected)
        layout.addWidget(self.combo_activity)

        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setMaximumHeight(150)
        layout.addWidget(self.info_text)

    def _create_metric_controls(self, layout):
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

    def _create_full_statistics_display(self, layout):
        layout.addSpacing(15)
        label = QLabel("Activity Statistics")
        label.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(label)

        self.full_stats_text = QTextEdit()
        self.full_stats_text.setReadOnly(True)
        layout.addWidget(self.full_stats_text)

    def _create_selection_statistics_display(self, layout):
        layout.addSpacing(15)
        label = QLabel("Selection Statistics")
        label.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(label)

        self.selection_stats_text = QTextEdit()
        self.selection_stats_text.setReadOnly(True)
        layout.addWidget(self.selection_stats_text)

    def _open_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Folder with FIT Files")
        if not directory:
            return

        self.current_directory = Path(directory)
        fit_files = FITParser.find_fit_files(directory)

        self.combo_activity.clear()
        self.activity_path_map.clear()

        if not fit_files:
            self.info_text.setText("No .fit files found in directory")
            return

        for p in sorted(fit_files):
            name = Path(p).name
            self.activity_path_map[name] = p
            self.combo_activity.addItem(name)

        if self.combo_activity.count() > 0:
            self.combo_activity.setCurrentIndex(0)
            self._on_activity_selected(self.combo_activity.currentText())

    def _on_activity_selected(self, file_name):
        if not file_name or file_name not in self.activity_path_map:
            return

        file_path = self.activity_path_map[file_name]
        self._load_fit_file(file_path)

    def _load_fit_file(self, file_path):
        self.current_activity = FITParser.parse(file_path)
        self._update_activity_info()
        self._update_metric_dropdowns()
        self._plot_data()
        self._update_activity_stats()

    def _update_activity_info(self):
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

    def _update_activity_stats(self):
        statistics_string = self._format_stats_output(0, -1)
        self.full_stats_text.setText(statistics_string)

    def _update_metric_dropdowns(self):
        if not self.current_activity:
            return

        metrics = self.current_activity.available_metrics

        self.combo_primary.blockSignals(True)
        self.combo_secondary.blockSignals(True)
        self.combo_primary.clear()
        self.combo_secondary.clear()

        for metric in metrics:
            self.combo_primary.addItem(metric)
            self.combo_secondary.addItem(metric)

        if "power" in metrics:
            self.combo_primary.setCurrentText("power")
        if "heart_rate" in metrics:
            self.combo_secondary.setCurrentText("heart_rate")

        self.combo_primary.blockSignals(False)
        self.combo_secondary.blockSignals(False)

    def _plot_data(self):
        if not self.current_activity:
            return

        primary_metric = self.combo_primary.currentText()
        secondary_metric = self.combo_secondary.currentText()
        self.plot_widget.plot_activity(self.current_activity, primary_metric, secondary_metric)

        try:
            self.plot_widget.selection_changed.disconnect(self._on_selection_changed)
        except TypeError:
            pass
        self.plot_widget.selection_changed.connect(self._on_selection_changed)

    def _on_metric_changed(self):
        self._plot_data()

    def _reset_plot_view(self):
        self.plot_widget.reset_view()

    def _on_selection_changed(self, start_idx: int, end_idx: int):
        if not self.current_activity or start_idx >= end_idx:
            self.stats_text.setText("No selection")
            return

        statistics_string = self._format_stats_output(
            start_idx, end_idx
        )

        self.selection_stats_text.setText(statistics_string)
        
    def _format_stats_output(self, start_idx: int, end_idx: int) -> str:
        stats = StatisticsCalculator.calculate_specific_stats(
            self.current_activity, start_idx, end_idx
        )

        output = ""
        for stat_name, value in stats.items():
            output += f"{stat_name}: {value[0]:0.2f} {value[1]}\n"

        return output

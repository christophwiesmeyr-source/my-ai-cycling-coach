"""Main UI window for FIT data visualization"""
import datetime
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QFileDialog, QLabel, QComboBox, QTableWidget, QTableWidgetItem, QTextEdit
)
from PyQt6.QtCore import Qt
import pyqtgraph as pg

from src.data import FITParser, Activity
from src.analysis import StatisticsCalculator
from .plot_widget import PlotWidget
        

LABEL_STYLE_HEADER = "font-weight: bold; font-size: 14px;"


class MainWindow(QMainWindow):
    """Main application window"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FIT Data Visualizer - Cycling Analysis")
        self.setGeometry(100, 100, 1400, 800)

        self.current_activity: Optional[Activity] = None
        self.current_directory: Optional[Path] = None
        self.activity_path_map = {}
        self.activity_list = []

        self._init_ui()

    def _init_ui(self):
        """Initialize UI components"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout()

        left_panel = QWidget()
        left_layout = QVBoxLayout()
        right_panel = QWidget()
        right_layout = QVBoxLayout()

        self._create_file_controls(left_layout)
        self._create_activity_selection(left_layout)
        self._create_metric_controls(left_layout)

        left_layout.addStretch()
        left_panel.setLayout(left_layout)
        left_panel.setMaximumWidth(500)
        right_panel.setLayout(right_layout)

        self.plot_widget = PlotWidget()

        right_layout.addWidget(self.plot_widget, 1)

        # Stats side by side below the plot
        stats_container = QWidget()
        stats_layout = QHBoxLayout()
        stats_container.setLayout(stats_layout)

        self._create_full_statistics_display(stats_layout)
        self._create_selection_statistics_display(stats_layout)

        right_layout.addWidget(stats_container)

        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel, 1)
        central_widget.setLayout(main_layout)

    def _create_file_controls(self, layout):
        """Create file loading controls"""
        label = QLabel("File Management")
        label.setStyleSheet(LABEL_STYLE_HEADER)
        layout.addWidget(label)

        btn_open_dir = QPushButton("Open Folder")
        btn_open_dir.clicked.connect(self._open_directory)
        layout.addWidget(btn_open_dir)

    def _create_activity_selection(self, layout):
        layout.addSpacing(15)
        label = QLabel("Activity Selection")
        label.setStyleSheet(LABEL_STYLE_HEADER)
        layout.addWidget(label)

        self.table_activities = QTableWidget(0, 3)
        self.table_activities.setMinimumWidth(302)
        self.table_activities.setHorizontalHeaderLabels(["Date", "Distance", "Time"])
        self.table_activities.verticalHeader().setVisible(False)
        self.table_activities.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_activities.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table_activities.cellClicked.connect(self._on_activity_table_selected)
        self.table_activities.setSortingEnabled(False)  # enable after filling
        layout.addWidget(self.table_activities)

        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setMaximumHeight(150)
        layout.addWidget(self.info_text)

    def _create_metric_controls(self, layout):
        layout.addSpacing(15)
        label = QLabel("Metrics")
        label.setStyleSheet(LABEL_STYLE_HEADER)
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
        stats_widget = QWidget()
        stats_layout = QVBoxLayout()
        label = QLabel("Activity Statistics")
        label.setStyleSheet("font-weight: bold; font-size: 14px;")
        stats_layout.addWidget(label)

        self.full_stats_text = QTextEdit()
        self.full_stats_text.setReadOnly(True)
        stats_layout.addWidget(self.full_stats_text)
        stats_widget.setLayout(stats_layout)
        layout.addWidget(stats_widget)

    def _create_selection_statistics_display(self, layout):
        stats_widget = QWidget()
        stats_layout = QVBoxLayout()
        label = QLabel("Selection Statistics")
        label.setStyleSheet(LABEL_STYLE_HEADER)
        stats_layout.addWidget(label)

        self.selection_stats_text = QTextEdit()
        self.selection_stats_text.setReadOnly(True)
        stats_layout.addWidget(self.selection_stats_text)
        stats_widget.setLayout(stats_layout)
        layout.addWidget(stats_widget)

    def _open_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Folder with FIT Files")
        if not directory:
            return

        self.current_directory = Path(directory)
        fit_files = FITParser.find_fit_files(directory)

        self.table_activities.setSortingEnabled(False)
        self.table_activities.setRowCount(0)
        self.activity_path_map.clear()
        self.activity_list = []

        if not fit_files:
            self.info_text.setText("No .fit files found in directory")
            return

        for p in sorted(fit_files):
            activity = FITParser.parse(p)
            row = self.table_activities.rowCount()
            self.table_activities.insertRow(row)

            if len(activity.data) > 0 and 'timestamp' in activity.data.columns:
                date_value = activity.data.timestamp.iloc[0]
                date_text = date_value.strftime("%Y-%m-%d")
            else:
                date_text = Path(p).stem

            distance_text = f"{activity.total_distance/1000:.0f} km" if activity.total_distance else "N/A"
            duration = datetime.timedelta(seconds=activity.duration_seconds)
            time_text = str(duration) if activity.duration_seconds else "N/A"

            date_item = QTableWidgetItem(date_text)
            date_item.setData(Qt.ItemDataRole.UserRole, p)
            self.table_activities.setItem(row, 0, date_item)
            self.table_activities.setItem(row, 1, QTableWidgetItem(distance_text))
            self.table_activities.setItem(row, 2, QTableWidgetItem(time_text))

            self.activity_list.append(p)
            self.activity_path_map[date_text] = p

        self.table_activities.setSortingEnabled(True)
        self.table_activities.sortItems(0, Qt.SortOrder.DescendingOrder)

        if self.table_activities.rowCount() > 0:
            self.table_activities.selectRow(0)
            self._on_activity_table_selected(0, 0)

    def _on_activity_selected(self, file_name):
        # Deprecated when using table-based selection. Keep for API compatibility.
        if not file_name or file_name not in self.activity_path_map:
            return

        file_path = self.activity_path_map[file_name]
        self._load_fit_file(file_path)

    def _on_activity_table_selected(self, row, column):
        if row < 0 or row >= self.table_activities.rowCount():
            return

        date_item = self.table_activities.item(row, 0)
        if not date_item:
            return

        # Use stored file path to keep mapping consistent after sorting
        file_path = date_item.data(Qt.ItemDataRole.UserRole)
        if not file_path:
            return

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

        self.combo_secondary.addItem("None")
        for metric in metrics:
            self.combo_primary.addItem(metric)
            self.combo_secondary.addItem(metric)

        if "power" in metrics:
            self.combo_primary.setCurrentText("power")
        elif metrics:
            self.combo_primary.setCurrentText(metrics[0])

        self.combo_secondary.setCurrentText("None")

        self.combo_primary.blockSignals(False)
        self.combo_secondary.blockSignals(False)

    def _plot_data(self):
        if not self.current_activity:
            return

        primary_metric = self.combo_primary.currentText()
        secondary_metric = self.combo_secondary.currentText()
        if secondary_metric == "None":
            secondary_metric = None

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
            self.selection_stats_text.setText("No selection")
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
            if isinstance(value[0], str):
                output += f"{stat_name}: {value[0]}\n"
            else:
                output += f"{stat_name}: {value[0]:0.2f} {value[1]}\n"

        return output

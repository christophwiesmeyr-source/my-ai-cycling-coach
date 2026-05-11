"""Main UI window for data visualization"""
import datetime
from typing import Optional

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QComboBox, QTableWidget, QTableWidgetItem, QTextEdit, QTabWidget,
    QCheckBox, QMessageBox
)
from PyQt6.QtCore import Qt
import pyqtgraph as pg

from src.data import Activity, StravaClient, StravaClientError
from src.analysis import StatisticsCalculator
from .plot_widget import PlotWidget
        

LABEL_STYLE_HEADER = "font-weight: bold; font-size: 14px;"


class MainWindow(QMainWindow):
    """Main application window"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FIT Data Visualizer")
        self.setGeometry(100, 100, 1400, 800)

        self.current_activity: Optional[Activity] = None
        self.strava_client = StravaClient()
        self.activity_metadatas: list[dict] = []
        self.activity_map: dict[int, dict] = {}
        self.activity_cache: dict[int, Activity] = {}

        self._init_ui()
        self._load_recent_activities()

    def _init_ui(self):
        """Initialize UI components"""
        tab_widget = QTabWidget()
        self.setCentralWidget(tab_widget)

        # Analysis tab
        analysis_widget = QWidget()
        main_layout = QHBoxLayout()

        left_panel = QWidget()
        left_layout = QVBoxLayout()
        right_panel = QWidget()
        right_layout = QVBoxLayout()

        self._create_strava_controls(left_layout)
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
        analysis_widget.setLayout(main_layout)

        # Training tab
        training_widget = QWidget()
        training_layout = QVBoxLayout()
        training_label = QLabel("Training Plan Generation and Feedback")
        training_label.setStyleSheet(LABEL_STYLE_HEADER)
        training_layout.addWidget(training_label)
        training_layout.addStretch()
        training_widget.setLayout(training_layout)

        tab_widget.addTab(analysis_widget, "Analysis")
        tab_widget.addTab(training_widget, "Training")

    def _create_strava_controls(self, layout):
        """Create Strava synchronization controls"""
        label = QLabel("Strava Sync")
        label.setStyleSheet(LABEL_STYLE_HEADER)
        layout.addWidget(label)

        btn_refresh = QPushButton("Refresh Activities")
        btn_refresh.clicked.connect(self._load_recent_activities)
        layout.addWidget(btn_refresh)

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

    def _create_metric_controls(self, layout):
        layout.addSpacing(15)
        label = QLabel("Metrics")
        label.setStyleSheet(LABEL_STYLE_HEADER)
        layout.addWidget(label)

        self.combo_primary = QComboBox()
        self.combo_primary.currentTextChanged.connect(self._on_metric_changed)
        layout.addWidget(QLabel("Primary:"))
        layout.addWidget(self.combo_primary)

        self.checkbox_primary_filter = QCheckBox("Filter (20s)")
        self.checkbox_primary_filter.stateChanged.connect(self._on_metric_changed)
        layout.addWidget(self.checkbox_primary_filter)

        self.combo_secondary = QComboBox()
        self.combo_secondary.currentTextChanged.connect(self._on_metric_changed)
        layout.addWidget(QLabel("Secondary:"))
        layout.addWidget(self.combo_secondary)

        self.checkbox_secondary_filter = QCheckBox("Filter (20s)")
        self.checkbox_secondary_filter.stateChanged.connect(self._on_metric_changed)
        layout.addWidget(self.checkbox_secondary_filter)

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

    def _load_recent_activities(self):
        self.table_activities.setSortingEnabled(False)
        self.table_activities.setRowCount(0)
        self.activity_map.clear()
        self.activity_metadatas = []

        one_year_ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=365)
        activities = self.strava_client.list_activities(one_year_ago)

        self.activity_metadatas = activities

        for activity in activities:
            row = self.table_activities.rowCount()
            self.table_activities.insertRow(row)

            start_date = activity.get('start_date_local') or activity.get('start_date') or ''
            try:
                date_value = datetime.datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                date_text = date_value.strftime('%Y-%m-%d %H:%M')
            except Exception:
                date_text = start_date or 'Unknown'

            distance_text = f"{activity.get('distance', 0) / 1000:.1f} km" if activity.get('distance') else 'N/A'
            duration_text = str(datetime.timedelta(seconds=activity.get('elapsed_time', 0))) if activity.get('elapsed_time') else 'N/A'

            date_item = QTableWidgetItem(date_text)
            activity_id = int(activity.get('id'))
            date_item.setData(Qt.ItemDataRole.UserRole, activity_id)
            self.table_activities.setItem(row, 0, date_item)
            self.table_activities.setItem(row, 1, QTableWidgetItem(distance_text))
            self.table_activities.setItem(row, 2, QTableWidgetItem(duration_text))

            self.activity_map[activity_id] = activity

        self.table_activities.setSortingEnabled(True)
        self.table_activities.sortItems(0, Qt.SortOrder.DescendingOrder)

        if self.table_activities.rowCount() > 0:
            self.table_activities.selectRow(0)
            self._on_activity_table_selected(0, 0)

    def _on_activity_selected(self, activity_id):
        # Deprecated when using table-based selection. Keep for API compatibility.
        if not activity_id:
            return

        try:
            activity_id = int(activity_id)
        except (TypeError, ValueError):
            return

        self._load_activity(activity_id)

    def _on_activity_table_selected(self, row, column):
        if row < 0 or row >= self.table_activities.rowCount():
            return

        date_item = self.table_activities.item(row, 0)
        if not date_item:
            return

        activity_id = date_item.data(Qt.ItemDataRole.UserRole)
        if activity_id is None:
            return

        self._load_activity(activity_id)

    def _load_activity(self, activity_id: int):
        metadata = self.activity_map.get(activity_id)
        if not metadata:
            return

        if activity_id in self.activity_cache:
            self.current_activity = self.activity_cache[activity_id]
        else:
            try:
                self.current_activity = self.strava_client.download_activity(activity_id)
                self.activity_cache[activity_id] = self.current_activity
            except StravaClientError as e:
                QMessageBox.critical(self, "Download Error", f"Failed to download activity: {str(e)}")
                return

        self._update_metric_dropdowns()
        self._plot_data()
        self._update_activity_stats()

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

        # Apply filtering if checkboxes are checked
        primary_filtered = self.checkbox_primary_filter.isChecked()
        secondary_filtered = self.checkbox_secondary_filter.isChecked()

        self.plot_widget.plot_activity(
            self.current_activity, 
            primary_metric, 
            secondary_metric,
            primary_filtered=primary_filtered,
            secondary_filtered=secondary_filtered
        )

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

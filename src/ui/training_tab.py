"""Training tab — AI plan generation, adaptation, and coaching chat"""
import csv
import json
import re
from datetime import date

import markdown as md

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QPushButton, QLabel, QLineEdit, QTextEdit,
    QSpinBox, QComboBox, QFormLayout, QTabWidget,
    QMessageBox, QDateEdit, QTableWidget, QTableWidgetItem, QHeaderView,
)
from PyQt6.QtCore import Qt, QDate

from src.ai import ChatSession, PLAN_ORIGINAL_PATH, PLAN_ADAPTED_PATH
from src.constants import GOALS_PATH, SESSIONS_ORIGINAL_PATH
from .workers import PlanGeneratorWorker, PlanAdaptorWorker, ChatWorker


def _compute_watts(pct_str: str, ftp: int) -> str:
    """Convert a %FTP range string to absolute watts given an FTP value."""
    s = pct_str.strip()
    m = re.match(r'<(\d+)%', s)
    if m:
        return f"<{round(int(m.group(1)) / 100 * ftp)} W"
    m = re.match(r'>(\d+)%', s)
    if m:
        return f">{round(int(m.group(1)) / 100 * ftp)} W"
    m = re.match(r'(\d+)[-–](\d+)%', s)
    if m:
        lo = round(int(m.group(1)) / 100 * ftp)
        hi = round(int(m.group(2)) / 100 * ftp)
        return f"{lo}–{hi} W"
    return ""

LABEL_STYLE_HEADER = "font-weight: bold; font-size: 14px;"
LABEL_STYLE_SUBHEADER = "font-weight: bold;"


class TrainingTab(QWidget):
    def __init__(self, strava_client):
        super().__init__()
        self.strava_client = strava_client
        self.chat_session = ChatSession()
        self._active_worker = None
        self._init_ui()
        self._load_existing_plans()
        self._load_sessions_table()
        self._load_goals()
        self._connect_autosave()

    # ------------------------------------------------------------------ #
    # UI construction                                                      #
    # ------------------------------------------------------------------ #

    def _init_ui(self):
        root = QHBoxLayout(self)

        root.addWidget(self._build_left_panel(), 0)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self._build_plan_viewer())
        splitter.addWidget(self._build_chat_panel())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter, 1)

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(340)
        layout = QVBoxLayout(panel)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        header = QLabel("Training Goals")
        header.setStyleSheet(LABEL_STYLE_HEADER)
        layout.addWidget(header)

        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

        self.input_goal = QTextEdit()
        self.input_goal.setPlaceholderText("e.g. Complete a gran fondo, Improve FTP")
        self.input_goal.setFixedHeight(70)
        form.addRow("Main goal:", self.input_goal)

        self.input_event_name = QLineEdit()
        self.input_event_name.setPlaceholderText("e.g. Ötztaler Radmarathon (optional)")
        form.addRow("Event name:", self.input_event_name)

        self.input_event_date = QDateEdit()
        self.input_event_date.setCalendarPopup(True)
        self.input_event_date.setDisplayFormat("dd MMM yyyy")
        self.input_event_date.setMinimumDate(QDate.currentDate().addDays(1))
        self.input_event_date.setDate(QDate.currentDate().addMonths(4))
        form.addRow("Event date:", self.input_event_date)

        self.spin_hours = QSpinBox()
        self.spin_hours.setRange(1, 30)
        self.spin_hours.setValue(8)
        self.spin_hours.setSuffix(" h/week")
        form.addRow("Available time:", self.spin_hours)

        self.spin_ftp = QSpinBox()
        self.spin_ftp.setRange(0, 600)
        self.spin_ftp.setValue(0)
        self.spin_ftp.setSuffix(" W  (0 = unknown)")
        form.addRow("Current FTP:", self.spin_ftp)

        self.spin_max_hr = QSpinBox()
        self.spin_max_hr.setRange(0, 250)
        self.spin_max_hr.setValue(0)
        self.spin_max_hr.setSuffix(" bpm  (0 = unknown)")
        form.addRow("Max heart rate:", self.spin_max_hr)

        self.combo_level = QComboBox()
        self.combo_level.addItems(["Beginner", "Intermediate", "Advanced"])
        self.combo_level.setCurrentText("Intermediate")
        form.addRow("Experience:", self.combo_level)

        self.input_notes = QTextEdit()
        self.input_notes.setPlaceholderText(
            "Anything else the coach should know (injuries, schedule constraints, …)"
        )
        self.input_notes.setFixedHeight(70)
        form.addRow("Notes:", self.input_notes)

        layout.addLayout(form)
        layout.addSpacing(12)

        self.btn_generate = QPushButton("Generate Plan")
        self.btn_generate.clicked.connect(self._on_generate)
        layout.addWidget(self.btn_generate)

        self.btn_adapt = QPushButton("Adapt Plan from Strava")
        self.btn_adapt.clicked.connect(self._on_adapt)
        layout.addWidget(self.btn_adapt)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: grey; font-style: italic;")
        layout.addSpacing(8)
        layout.addWidget(self.status_label)

        return panel

    def _build_plan_viewer(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        header = QLabel("Training Plan")
        header.setStyleSheet(LABEL_STYLE_HEADER)
        layout.addWidget(header)

        self.plan_tabs = QTabWidget()

        self.original_plan_view = QTextEdit()
        self.original_plan_view.setReadOnly(True)
        self.original_plan_view.setPlaceholderText(
            "No plan yet. Fill in your goals and click Generate Plan."
        )
        self.plan_tabs.addTab(self.original_plan_view, "Original")

        self.adapted_plan_view = QTextEdit()
        self.adapted_plan_view.setReadOnly(True)
        self.adapted_plan_view.setPlaceholderText(
            "No adapted plan yet. Click Adapt Plan from Strava after completing some workouts."
        )
        self.plan_tabs.addTab(self.adapted_plan_view, "Adapted")

        sessions_widget = QWidget()
        sessions_layout = QVBoxLayout(sessions_widget)
        sessions_layout.setContentsMargins(0, 0, 0, 0)
        sessions_splitter = QSplitter(Qt.Orientation.Vertical)

        self.sessions_table = QTableWidget()
        self.sessions_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.sessions_table.setSortingEnabled(True)
        self.sessions_table.setAlternatingRowColors(True)
        self.sessions_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.sessions_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        if (vh := self.sessions_table.verticalHeader()):
            vh.setVisible(False)
        self.sessions_table.itemSelectionChanged.connect(self._on_session_selected)
        sessions_splitter.addWidget(self.sessions_table)

        self.session_detail = QTextEdit()
        self.session_detail.setReadOnly(True)
        self.session_detail.setPlaceholderText("Select a session to see the full protocol.")
        self.session_detail.setMaximumHeight(140)
        sessions_splitter.addWidget(self.session_detail)
        sessions_splitter.setStretchFactor(0, 4)
        sessions_splitter.setStretchFactor(1, 1)

        sessions_layout.addWidget(sessions_splitter)
        self.plan_tabs.addTab(sessions_widget, "Sessions")

        layout.addWidget(self.plan_tabs)
        return widget

    def _build_chat_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        header = QLabel("Chat with your Coach")
        header.setStyleSheet(LABEL_STYLE_HEADER)
        layout.addWidget(header)

        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setPlaceholderText(
            "Ask your coach anything about the plan or your progress."
        )
        layout.addWidget(self.chat_display, 1)

        input_row = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Type a message…")
        self.chat_input.returnPressed.connect(self._on_send)
        input_row.addWidget(self.chat_input, 1)

        self.btn_send = QPushButton("Send")
        self.btn_send.clicked.connect(self._on_send)
        input_row.addWidget(self.btn_send)

        layout.addLayout(input_row)
        return widget

    # ------------------------------------------------------------------ #
    # Plan generation                                                      #
    # ------------------------------------------------------------------ #

    def _on_generate(self):
        goals = self._collect_goals()
        if not goals.get("main_goal"):
            QMessageBox.warning(self, "Missing Goal", "Please enter a main training goal.")
            return

        self._save_goals(goals)
        self._set_busy(True, "Starting…")
        worker = PlanGeneratorWorker(goals)
        worker.status_update.connect(self.status_label.setText)
        worker.finished.connect(self._on_plan_generated)
        worker.error_occurred.connect(self._on_error)
        worker.finished.connect(lambda: self._set_busy(False, ""))
        worker.error_occurred.connect(lambda: self._set_busy(False, ""))
        self._active_worker = worker
        worker.start()

    def _on_plan_generated(self, plan: str):
        self.original_plan_view.setHtml(self._render_markdown(plan))
        self._load_sessions_table()
        self.plan_tabs.setCurrentIndex(0)
        self.chat_session.reload_plans()
        self._append_chat_system("Training plan generated. You can now chat about it.")

    # ------------------------------------------------------------------ #
    # Plan adaptation                                                      #
    # ------------------------------------------------------------------ #

    def _on_adapt(self):
        if not PLAN_ORIGINAL_PATH.exists():
            QMessageBox.warning(
                self, "No Plan", "Generate a training plan first before adapting it."
            )
            return

        self._set_busy(True, "Querying Strava and adapting plan — this may take a minute…")
        worker = PlanAdaptorWorker(self.strava_client)
        worker.finished.connect(self._on_plan_adapted)
        worker.error_occurred.connect(self._on_error)
        worker.finished.connect(lambda: self._set_busy(False, ""))
        worker.error_occurred.connect(lambda: self._set_busy(False, ""))
        self._active_worker = worker
        worker.start()

    def _on_plan_adapted(self, plan: str):
        self.adapted_plan_view.setHtml(self._render_markdown(plan))
        self.plan_tabs.setCurrentIndex(1)
        self.chat_session.reload_plans()
        self._append_chat_system("Adapted plan ready. Ask your coach about the changes.")

    # ------------------------------------------------------------------ #
    # Chat                                                                 #
    # ------------------------------------------------------------------ #

    def _on_send(self):
        text = self.chat_input.text().strip()
        if not text:
            return
        if self._active_worker and self._active_worker.isRunning():
            return

        self.chat_input.clear()
        self._append_chat_user(text)
        self.chat_session.add_user_message(text)

        self._set_chat_input_enabled(False)
        self._append_chat_assistant_start()

        worker = ChatWorker(self.chat_session, self.strava_client)
        worker.chunk_received.connect(self._on_chat_chunk)
        worker.tool_status.connect(self._on_chat_tool_status)
        worker.finished.connect(self._on_chat_finished)
        worker.error_occurred.connect(self._on_chat_error)
        self._active_worker = worker
        worker.start()

    def _on_chat_tool_status(self, message: str):
        self.chat_display.append(f"<i>({message})</i>")

    def _on_chat_chunk(self, chunk: str):
        cursor = self.chat_display.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        if self._stream_text_start is None:
            self._stream_text_start = cursor.position()
        cursor.insertText(chunk)
        self.chat_display.setTextCursor(cursor)
        self.chat_display.ensureCursorVisible()

    def _on_chat_finished(self, full_response: str):
        self.chat_session.add_assistant_message(full_response)
        if self._stream_text_start is not None:
            cursor = self.chat_display.textCursor()
            cursor.setPosition(self._stream_text_start)
            cursor.movePosition(cursor.MoveOperation.End, cursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
            cursor.insertHtml(md.markdown(full_response, extensions=["tables", "fenced_code"]))
            self._stream_text_start = None
        self.chat_display.append("")
        self._set_chat_input_enabled(True)

    def _on_chat_error(self, error: str):
        self._append_chat_system(f"Error: {error}")
        self._set_chat_input_enabled(True)

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _collect_goals(self) -> dict:
        today = date.today()
        event_date = self.input_event_date.date().toPyDate()
        days_until = (event_date - today).days
        weeks_until = max(days_until // 7, 1)
        return {
            "main_goal": self.input_goal.toPlainText().strip(),
            "event_name": self.input_event_name.text().strip(),
            "event_date": event_date.isoformat(),
            "current_date": today.isoformat(),
            "days_until_event": days_until,
            "weeks_until_event": weeks_until,
            "available_hours_per_week": self.spin_hours.value(),
            "current_ftp_watts": self.spin_ftp.value() or None,
            "max_hr_bpm": self.spin_max_hr.value() or None,
            "experience_level": self.combo_level.currentText(),
            "additional_notes": self.input_notes.toPlainText().strip(),
        }

    def _load_sessions_table(self):
        if not SESSIONS_ORIGINAL_PATH.exists():
            return

        ftp = self.spin_ftp.value()
        show_watts = ftp > 0

        with open(SESSIONS_ORIGINAL_PATH, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        if not rows:
            return

        headers = ["Date", "Week", "Phase", "Type", "Duration", "Intensity", "Target %FTP"]
        if show_watts:
            headers.append("Target Watts")

        self.sessions_table.setSortingEnabled(False)
        self.sessions_table.setRowCount(len(rows))
        self.sessions_table.setColumnCount(len(headers))
        self.sessions_table.setHorizontalHeaderLabels(headers)

        for row_idx, row in enumerate(rows):
            pct = row.get("target_power_pct_ftp", "")
            values = [
                row.get("date", ""),
                row.get("week", ""),
                row.get("phase", ""),
                row.get("type", ""),
                f"{row.get('duration_min', '')} min",
                row.get("intensity", ""),
                pct,
            ]
            if show_watts:
                values.append(_compute_watts(pct, ftp))

            for col_idx, val in enumerate(values):
                item = QTableWidgetItem(str(val))
                if col_idx == 0:
                    # store the full row dict on the date item for retrieval on selection
                    item.setData(Qt.ItemDataRole.UserRole, row)
                self.sessions_table.setItem(row_idx, col_idx, item)

        self.sessions_table.setSortingEnabled(True)
        self.sessions_table.resizeColumnsToContents()
        header = self.sessions_table.horizontalHeader()
        if header:
            header.setStretchLastSection(True)

    def _on_session_selected(self):
        row_idx = self.sessions_table.currentRow()
        if row_idx < 0:
            self.session_detail.clear()
            return
        item = self.sessions_table.item(row_idx, 0)
        if item is None:
            return
        row = item.data(Qt.ItemDataRole.UserRole)
        if not row:
            return

        warmup = row.get("warmup", "").strip()
        main_set = row.get("main_set", "").strip()
        cooldown = row.get("cooldown", "").strip()
        description = row.get("description", "").strip()

        parts = []
        if warmup:
            parts.append(f"<b>Warm-up:</b> {warmup}")
        if main_set:
            parts.append(f"<b>Main set:</b> {main_set}")
        if cooldown:
            parts.append(f"<b>Cool-down:</b> {cooldown}")
        if description:
            parts.append(f"<br><i>{description}</i>")

        self.session_detail.setHtml("<br>".join(parts))

    def _load_existing_plans(self):
        if PLAN_ORIGINAL_PATH.exists():
            self.original_plan_view.setHtml(self._render_markdown(PLAN_ORIGINAL_PATH.read_text()))
        if PLAN_ADAPTED_PATH.exists():
            self.adapted_plan_view.setHtml(self._render_markdown(PLAN_ADAPTED_PATH.read_text()))

    def _render_markdown(self, text: str) -> str:
        body = md.markdown(text, extensions=["tables", "fenced_code"])
        return f"""<!DOCTYPE html><html><head><style>
            body {{ font-family: sans-serif; font-size: 13px; margin: 8px; }}
            h1 {{ font-size: 1.4em; margin-top: 12px; }}
            h2 {{ font-size: 1.2em; margin-top: 10px; }}
            h3 {{ font-size: 1.05em; margin-top: 8px; }}
            table {{ border-collapse: collapse; width: 100%; margin: 8px 0; }}
            th, td {{ border: 1px solid #ccc; padding: 4px 8px; text-align: left; }}
            th {{ background-color: #f0f0f0; font-weight: bold; }}
            tr:nth-child(even) {{ background-color: #fafafa; }}
            code {{ background: #f5f5f5; padding: 1px 4px; border-radius: 3px; font-size: 0.9em; }}
            pre {{ background: #f5f5f5; padding: 8px; border-radius: 4px; overflow-x: auto; }}
            ul, ol {{ padding-left: 20px; }}
            li {{ margin: 2px 0; }}
        </style></head><body>{body}</body></html>"""

    def _connect_autosave(self):
        self.input_goal.textChanged.connect(self._autosave_goals)
        self.input_event_name.textChanged.connect(self._autosave_goals)
        self.input_event_date.dateChanged.connect(self._autosave_goals)
        self.spin_hours.valueChanged.connect(self._autosave_goals)
        self.spin_ftp.valueChanged.connect(self._autosave_goals)
        self.spin_max_hr.valueChanged.connect(self._autosave_goals)
        self.combo_level.currentTextChanged.connect(self._autosave_goals)
        self.input_notes.textChanged.connect(self._autosave_goals)

    def _autosave_goals(self):
        self._save_goals(self._collect_goals())

    def _save_goals(self, goals: dict):
        GOALS_PATH.parent.mkdir(parents=True, exist_ok=True)
        GOALS_PATH.write_text(json.dumps(goals, indent=2))

    def _load_goals(self):
        if not GOALS_PATH.exists():
            return
        try:
            goals = json.loads(GOALS_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            return
        self.input_goal.setPlainText(goals.get("main_goal") or "")
        self.input_event_name.setText(goals.get("event_name") or "")
        if goals.get("event_date"):
            q_date = QDate.fromString(goals["event_date"], "yyyy-MM-dd")
            if q_date.isValid() and q_date > QDate.currentDate():
                self.input_event_date.setDate(q_date)
        if goals.get("available_hours_per_week"):
            self.spin_hours.setValue(int(goals["available_hours_per_week"]))
        if goals.get("current_ftp_watts"):
            self.spin_ftp.setValue(int(goals["current_ftp_watts"]))
        if goals.get("max_hr_bpm"):
            self.spin_max_hr.setValue(int(goals["max_hr_bpm"]))
        if goals.get("experience_level"):
            self.combo_level.setCurrentText(goals["experience_level"])
        self.input_notes.setPlainText(goals.get("additional_notes") or "")

    def _set_busy(self, busy: bool, message: str):
        self.btn_generate.setEnabled(not busy)
        self.btn_adapt.setEnabled(not busy)
        self.status_label.setText(message)

    def _set_chat_input_enabled(self, enabled: bool):
        self.chat_input.setEnabled(enabled)
        self.btn_send.setEnabled(enabled)

    def _append_chat_user(self, text: str):
        self.chat_display.append(f"<b>You:</b> {text}\n")

    def _append_chat_assistant_start(self):
        self.chat_display.append("<b>Coach:</b> ")
        self._stream_text_start = None  # set lazily on first chunk

    def _append_chat_system(self, text: str):
        self.chat_display.append(f"<i>{text}</i>\n")

    def _on_error(self, error: str):
        QMessageBox.critical(self, "Error", error)

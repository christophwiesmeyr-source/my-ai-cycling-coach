"""Chat session — maintains conversation history and system context for the coaching chat"""
import csv
import datetime
import json
from io import StringIO

from src.constants import (
    PLAN_ORIGINAL_PATH, PLAN_ADAPTED_PATH,
    SESSIONS_ORIGINAL_PATH, SESSIONS_ADAPTED_PATH, SESSIONS_LOG_PATH,
    STRAVA_HISTORY_WEEKS,
)

_SYSTEM_BASE = (
    "You are an expert cycling coach assistant. Help the athlete understand their training "
    "progress, compare completed workouts against the plan, and provide actionable advice. "
    "Be concise and practical. Reference specific sessions or metrics when relevant. "
    "Use the available tools to fetch Strava activity data whenever it would help you give "
    "a more specific or accurate answer."
)


def _build_session_table() -> str:
    """Merge sessions CSV with the completion log into a markdown table for the system prompt."""
    csv_path = SESSIONS_ADAPTED_PATH if SESSIONS_ADAPTED_PATH.exists() else SESSIONS_ORIGINAL_PATH
    if not csv_path.exists():
        return ""
    try:
        rows = list(csv.DictReader(StringIO(csv_path.read_text())))
    except (OSError, csv.Error):
        return ""
    if not rows:
        return ""

    try:
        log = json.loads(SESSIONS_LOG_PATH.read_text()) if SESSIONS_LOG_PATH.exists() else {}
    except (OSError, json.JSONDecodeError):
        log = {}

    today = datetime.date.today()
    cutoff = today - datetime.timedelta(weeks=STRAVA_HISTORY_WEEKS)

    lines = [
        "## Session log\n",
        "| Planned date | Type | Duration | Intensity | Target power | Completed date | Comment |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        plan_date = row.get("date", "")
        try:
            session_date = datetime.date.fromisoformat(plan_date)
        except ValueError:
            continue
        if session_date > today or session_date < cutoff:
            continue
        entry = log.get(plan_date, {})
        completed = entry.get("completed_date", "") or "—"
        comment = entry.get("comment", "")
        lines.append(
            f"| {plan_date}"
            f" | {row.get('type', '')}"
            f" | {row.get('duration_min', '')} min"
            f" | {row.get('intensity', '')}"
            f" | {row.get('target_power_pct_ftp', '')}"
            f" | {completed}"
            f" | {comment} |"
        )
    if len(lines) == 3:  # only header rows, no data
        return ""
    return "\n".join(lines) + "\n\n"


class ChatSession:
    def __init__(self):
        self.history: list = []
        self.original_plan: str = ""
        self.adapted_plan: str = ""
        self.reload_plans()

    def reload_plans(self):
        """Re-read plan files from disk (call after generating or adapting a plan)."""
        if PLAN_ORIGINAL_PATH.exists():
            self.original_plan = PLAN_ORIGINAL_PATH.read_text()
        if PLAN_ADAPTED_PATH.exists():
            self.adapted_plan = PLAN_ADAPTED_PATH.read_text()

    def add_user_message(self, text: str):
        self.history.append({"role": "user", "content": text})

    def add_assistant_message(self, text: str):
        self.history.append({"role": "assistant", "content": text})

    def build_system(self) -> str:
        parts = [_SYSTEM_BASE]
        if self.original_plan:
            parts.append(f"\n\n## Original Training Plan\n\n{self.original_plan}")
        if self.adapted_plan:
            parts.append(f"\n\n## Adapted Training Plan\n\n{self.adapted_plan}")
        session_table = _build_session_table()
        if session_table:
            parts.append(f"\n\n{session_table}")
        return "\n".join(parts)

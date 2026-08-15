"""Canonical metadata for training goal fields — shared by the UI and plan generator."""

import json
from dataclasses import dataclass
from typing import Any, Callable, Optional

from src.constants import GOALS_PATH


@dataclass
class GoalMeta:
    key: str
    label: str
    fmt: Optional[Callable[[Any], str]] = None

    def format_value(self, v: Any) -> str:
        return self.fmt(v) if self.fmt else str(v)


# Ordered for the plan parameter header (event context → training load → athlete profile).
# Add new fields here; training_tab.py will raise at startup if its registry drifts.
GOAL_FIELDS: list[GoalMeta] = [
    GoalMeta("main_goal", "Goal"),
    GoalMeta("event_name", "Event"),
    GoalMeta("available_hours_per_week", "Hours per week", lambda v: f"{v} h"),
    GoalMeta("sessions_per_week", "Sessions per week"),
    GoalMeta("current_ftp_watts", "FTP", lambda v: f"{v} W"),
    GoalMeta("max_hr_bpm", "Max HR", lambda v: f"{v} bpm"),
    GoalMeta("experience_level", "Experience"),
    GoalMeta("age_years", "Age", lambda v: f"{v} yrs"),
    GoalMeta("weight_kg", "Weight", lambda v: f"{v} kg"),
    GoalMeta("gender", "Gender"),
    GoalMeta("additional_notes", "Notes"),
]


def load_goals() -> dict:
    try:
        return json.loads(GOALS_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def format_goals_table(goals: dict, title: str) -> str:
    if not goals:
        return ""

    rows = []
    for gm in GOAL_FIELDS:
        v = goals.get(gm.key)
        if v:
            rows.append((gm.label, gm.format_value(v)))
        # insert computed event fields directly after event_name
        if gm.key == "event_name":
            if goals.get("event_date"):
                rows.append(("Event date", goals["event_date"]))
            if goals.get("weeks_until_event"):
                rows.append(("Weeks to event", str(goals["weeks_until_event"])))
    if goals.get("current_date"):
        rows.append(("Generated on", goals["current_date"]))

    table_rows = "\n".join(f"| {k} | {v} |" for k, v in rows)
    return f"## {title}\n\n| Parameter | Value |\n|-----------|-------|\n{table_rows}\n\n---"

"""Canonical metadata for training goal fields — shared by the UI and plan generator."""
from dataclasses import dataclass
from typing import Any, Callable, Optional


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
    GoalMeta("main_goal",                "Goal"),
    GoalMeta("event_name",               "Event"),
    GoalMeta("available_hours_per_week", "Hours per week",    lambda v: f"{v} h"),
    GoalMeta("sessions_per_week",        "Sessions per week"),
    GoalMeta("current_ftp_watts",        "FTP",               lambda v: f"{v} W"),
    GoalMeta("max_hr_bpm",               "Max HR",            lambda v: f"{v} bpm"),
    GoalMeta("experience_level",         "Experience"),
    GoalMeta("age_years",                "Age",               lambda v: f"{v} yrs"),
    GoalMeta("weight_kg",                "Weight",            lambda v: f"{v} kg"),
    GoalMeta("gender",                   "Gender"),
    GoalMeta("additional_notes",         "Notes"),
]

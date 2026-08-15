"""Tests for src/goals.py — load_goals() and format_goals_table()"""

import json
from pathlib import Path
from unittest.mock import patch

from src.goals import GOAL_FIELDS, format_goals_table, load_goals


class TestLoadGoals:
    def test_missing_file_returns_empty_dict(self, tmp_path: Path) -> None:
        with patch("src.goals.GOALS_PATH", tmp_path / "missing.json"):
            assert load_goals() == {}

    def test_malformed_json_returns_empty_dict(self, tmp_path: Path) -> None:
        goals_file = tmp_path / "goals.json"
        goals_file.write_text("not valid json{")
        with patch("src.goals.GOALS_PATH", goals_file):
            assert load_goals() == {}

    def test_valid_file_returns_parsed_dict(self, tmp_path: Path) -> None:
        goals_file = tmp_path / "goals.json"
        goals_file.write_text(json.dumps({"current_ftp_watts": 343}))
        with patch("src.goals.GOALS_PATH", goals_file):
            assert load_goals() == {"current_ftp_watts": 343}


class TestFormatGoalsTable:
    def test_empty_goals_returns_empty_string(self) -> None:
        assert format_goals_table({}, "Any title") == ""

    def test_populated_goals_contains_title(self) -> None:
        table = format_goals_table(
            {"main_goal": "Race"}, "Current athlete profile (live)"
        )
        assert "## Current athlete profile (live)" in table

    def test_populated_goals_contains_labels_and_values(self) -> None:
        goals = {"main_goal": "Race", "current_ftp_watts": 343, "max_hr_bpm": 185}
        table = format_goals_table(goals, "Profile")
        assert "| Goal | Race |" in table
        assert "| FTP | 343 W |" in table
        assert "| Max HR | 185 bpm |" in table

    def test_rows_follow_goal_fields_order(self) -> None:
        goals = {"max_hr_bpm": 185, "main_goal": "Race", "current_ftp_watts": 343}
        table = format_goals_table(goals, "Profile")
        assert (
            table.index("| Goal |") < table.index("| FTP |") < table.index("| Max HR |")
        )

    def test_missing_optional_fields_omitted(self) -> None:
        table = format_goals_table({"main_goal": "Race"}, "Profile")
        assert "| Event |" not in table
        assert "| FTP |" not in table

    def test_computed_event_fields_included_after_event_name(self) -> None:
        goals = {
            "main_goal": "Race",
            "event_name": "Oetztaler",
            "event_date": "2025-08-31",
            "weeks_until_event": 20,
        }
        table = format_goals_table(goals, "Profile")
        assert "| Event date | 2025-08-31 |" in table
        assert "| Weeks to event | 20 |" in table

    def test_all_goal_fields_representable(self) -> None:
        # Sanity check that every field in the shared registry renders without error.
        goals = {gm.key: "x" for gm in GOAL_FIELDS}
        table = format_goals_table(goals, "Profile")
        for gm in GOAL_FIELDS:
            assert gm.label in table

"""Tests for src/ai/plan_generator.py — pure helper functions only (no API calls)."""
from src.ai.plan_generator import (
    _build_plan_header,
    _build_plan_prompt,
    _build_sessions_prompt,
    _extract_csv,
)


# ---------------------------------------------------------------------------
# _build_plan_header
# ---------------------------------------------------------------------------

class TestBuildPlanHeader:
    def test_contains_all_provided_fields(self):
        goals = {
            "main_goal": "Complete a gran fondo",
            "event_name": "Oetztaler",
            "event_date": "2025-08-31",
            "weeks_until_event": 20,
            "available_hours_per_week": 10,
            "current_ftp_watts": 280,
            "max_hr_bpm": 185,
            "experience_level": "Intermediate",
            "additional_notes": "No injuries",
            "current_date": "2025-04-01",
        }
        header = _build_plan_header(goals)
        assert "Complete a gran fondo" in header
        assert "Oetztaler" in header
        assert "2025-08-31" in header
        assert "20" in header
        assert "10 h" in header
        assert "280 W" in header
        assert "185 bpm" in header
        assert "Intermediate" in header
        assert "No injuries" in header
        assert "2025-04-01" in header

    def test_omits_missing_optional_fields(self):
        goals = {"main_goal": "Improve FTP"}
        header = _build_plan_header(goals)
        assert "| Event |" not in header
        assert "| FTP |" not in header
        assert "| Max HR |" not in header

    def test_is_valid_markdown_table(self):
        goals = {"main_goal": "Race"}
        header = _build_plan_header(goals)
        assert "| Parameter | Value |" in header
        assert "|-----------|-------|" in header

    def test_ends_with_horizontal_rule(self):
        goals = {"main_goal": "Race"}
        assert _build_plan_header(goals).endswith("---")

    def test_empty_goals_produces_empty_table(self):
        header = _build_plan_header({})
        assert "| Parameter | Value |" in header
        # No data rows beyond the header
        lines = [l for l in header.splitlines() if l.startswith("|") and "Parameter" not in l and "---" not in l]
        assert lines == []


# ---------------------------------------------------------------------------
# _build_plan_prompt
# ---------------------------------------------------------------------------

class TestBuildPlanPrompt:
    BASE_GOALS = {
        "main_goal": "Race",
        "event_name": "Gran Fondo",
        "event_date": "2025-08-31",
        "current_date": "2025-04-01",
        "weeks_until_event": 20,
        "days_until_event": 140,
        "available_hours_per_week": 10,
        "experience_level": "Intermediate",
    }

    def test_contains_event_and_date(self):
        prompt = _build_plan_prompt(self.BASE_GOALS)
        assert "Gran Fondo" in prompt
        assert "2025-08-31" in prompt

    def test_contains_week_and_day_count(self):
        prompt = _build_plan_prompt(self.BASE_GOALS)
        assert "20 weeks" in prompt
        assert "140 days" in prompt

    def test_excludes_meta_keys_from_athlete_profile(self):
        prompt = _build_plan_prompt(self.BASE_GOALS)
        # These keys are rendered separately and must not appear in the profile block
        assert "event_name:" not in prompt
        assert "event_date:" not in prompt
        assert "current_date:" not in prompt
        assert "days_until_event:" not in prompt
        assert "weeks_until_event:" not in prompt

    def test_includes_athlete_profile_fields(self):
        prompt = _build_plan_prompt(self.BASE_GOALS)
        assert "available_hours_per_week" in prompt
        assert "experience_level" in prompt

    def test_fallback_event_name_when_missing(self):
        goals = {**self.BASE_GOALS, "event_name": ""}
        prompt = _build_plan_prompt(goals)
        assert "target event" in prompt

    def test_empty_values_excluded_from_profile(self):
        goals = {**self.BASE_GOALS, "additional_notes": ""}
        prompt = _build_plan_prompt(goals)
        assert "additional_notes" not in prompt


# ---------------------------------------------------------------------------
# _build_sessions_prompt
# ---------------------------------------------------------------------------

class TestBuildSessionsPrompt:
    GOALS = {
        "current_date": "2025-04-01",
        "event_date": "2025-08-31",
        "weeks_until_event": 20,
    }
    PLAN = "Week 1: Base training..."

    def test_contains_plan_text(self):
        prompt = _build_sessions_prompt(self.PLAN, self.GOALS)
        assert "Week 1: Base training..." in prompt

    def test_contains_planning_context(self):
        prompt = _build_sessions_prompt(self.PLAN, self.GOALS)
        assert "2025-04-01" in prompt
        assert "2025-08-31" in prompt
        assert "20" in prompt

    def test_contains_csv_header_requirement(self):
        prompt = _build_sessions_prompt(self.PLAN, self.GOALS)
        assert "date,week,phase,type,duration_min,intensity,target_power_pct_ftp" in prompt


# ---------------------------------------------------------------------------
# _extract_csv
# ---------------------------------------------------------------------------

class TestExtractCsv:
    def test_clean_csv_returned_unchanged(self):
        csv = "date,week,phase\n2025-04-01,1,Base"
        assert _extract_csv(csv) == csv

    def test_strips_preamble_before_header(self):
        raw = "Here is your CSV:\ndate,week,phase\n2025-04-01,1,Base"
        result = _extract_csv(raw)
        assert result.startswith("date,week,phase")
        assert "Here is your CSV" not in result

    def test_strips_markdown_fence_preamble(self):
        raw = "```csv\ndate,week,phase\n2025-04-01,1,Base\n```"
        result = _extract_csv(raw)
        assert result.startswith("date,week,phase")

    def test_preserves_all_data_rows(self):
        raw = "Preamble\ndate,week,phase\nrow1\nrow2\nrow3"
        result = _extract_csv(raw)
        assert "row1" in result
        assert "row2" in result
        assert "row3" in result

    def test_returns_raw_when_no_header_found(self):
        raw = "no csv header here"
        assert _extract_csv(raw) == raw

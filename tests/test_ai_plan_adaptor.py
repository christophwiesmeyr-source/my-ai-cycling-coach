"""Tests for src/ai/plan_adaptor.py — pure helper functions plus adapt_plan() with a fake client."""

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.ai.plan_adaptor import (
    _build_log_section,
    _build_user_prompt,
    _extract_text,
    adapt_plan,
)
from src.data.intervals_api import IntervalsClient
from src.goals import load_goals


class _FakeTextBlock:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeOtherBlock:
    pass


class _FakeUsage:
    def __init__(self, input_tokens: int = 100, output_tokens: int = 50) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _FakeResponse:
    def __init__(
        self, stop_reason: str, content: list, usage: _FakeUsage | None = None
    ) -> None:
        self.stop_reason = stop_reason
        self.content = content
        self.usage = usage or _FakeUsage()


class _FakeStream:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    def __enter__(self) -> "_FakeStream":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def get_final_message(self) -> _FakeResponse:
        return self._response


class _FakeMessages:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    def stream(self, **kwargs: object) -> _FakeStream:
        return _FakeStream(self._response)


class _FakeClient:
    def __init__(self, response: _FakeResponse) -> None:
        self.messages = _FakeMessages(response)


@pytest.fixture
def activity_client(tmp_path: Path) -> IntervalsClient:
    with patch.object(IntervalsClient, "CONFIG_FILE", tmp_path / "missing.json"):
        return IntervalsClient(api_key="testkey", athlete_id="i12345")


class TestExtractText:
    def test_joins_text_from_all_text_blocks(self) -> None:
        blocks = [_FakeTextBlock("Hello"), _FakeTextBlock("World")]
        assert _extract_text(blocks) == "Hello\nWorld"

    def test_skips_blocks_without_text_attr(self) -> None:
        blocks = [_FakeOtherBlock(), _FakeTextBlock("only this")]
        assert _extract_text(blocks) == "only this"

    def test_empty_content_returns_empty_string(self) -> None:
        assert _extract_text([]) == ""

    def test_single_block_no_trailing_newline(self) -> None:
        blocks = [_FakeTextBlock("Just one")]
        assert _extract_text(blocks) == "Just one"


class TestBuildLogSection:
    def test_returns_empty_string_when_file_missing(self, tmp_path: Path) -> None:
        with patch("src.ai.plan_adaptor.SESSIONS_LOG_PATH", tmp_path / "missing.json"):
            assert _build_log_section() == ""

    def test_returns_empty_string_when_file_malformed(self, tmp_path: Path) -> None:
        log_file = tmp_path / "log.json"
        log_file.write_text("not valid json{")
        with patch("src.ai.plan_adaptor.SESSIONS_LOG_PATH", log_file):
            assert _build_log_section() == ""

    def test_returns_empty_string_when_log_empty(self, tmp_path: Path) -> None:
        log_file = tmp_path / "log.json"
        log_file.write_text(json.dumps({}))
        with patch("src.ai.plan_adaptor.SESSIONS_LOG_PATH", log_file):
            assert _build_log_section() == ""

    def test_completed_session_formatted_correctly(self, tmp_path: Path) -> None:
        log = {"2025-04-01": {"completed_date": "2025-04-01", "comment": ""}}
        log_file = tmp_path / "log.json"
        log_file.write_text(json.dumps(log))
        with patch("src.ai.plan_adaptor.SESSIONS_LOG_PATH", log_file):
            result = _build_log_section()
        assert "2025-04-01" in result
        assert "completed 2025-04-01" in result

    def test_incomplete_session_formatted_correctly(self, tmp_path: Path) -> None:
        log = {"2025-04-02": {"completed_date": "", "comment": ""}}
        log_file = tmp_path / "log.json"
        log_file.write_text(json.dumps(log))
        with patch("src.ai.plan_adaptor.SESSIONS_LOG_PATH", log_file):
            result = _build_log_section()
        assert "not yet marked complete" in result

    def test_comment_appended_when_present(self, tmp_path: Path) -> None:
        log = {"2025-04-01": {"completed_date": "2025-04-01", "comment": "felt strong"}}
        log_file = tmp_path / "log.json"
        log_file.write_text(json.dumps(log))
        with patch("src.ai.plan_adaptor.SESSIONS_LOG_PATH", log_file):
            result = _build_log_section()
        assert "felt strong" in result

    def test_entries_sorted_by_date(self, tmp_path: Path) -> None:
        log = {
            "2025-04-03": {"completed_date": "2025-04-03", "comment": ""},
            "2025-04-01": {"completed_date": "2025-04-01", "comment": ""},
        }
        log_file = tmp_path / "log.json"
        log_file.write_text(json.dumps(log))
        with patch("src.ai.plan_adaptor.SESSIONS_LOG_PATH", log_file):
            result = _build_log_section()
        assert result.index("2025-04-01") < result.index("2025-04-03")


class TestBuildUserPrompt:
    _ORIGINAL_PLAN_WITH_STALE_FTP = (
        "## Plan parameters\n\n| Parameter | Value |\n|-----------|-------|\n"
        "| FTP | 325 W |\n\n---\n\nWeek 1: Base training..."
    )

    def test_live_goals_reach_prompt_alongside_stale_original(
        self, tmp_path: Path
    ) -> None:
        goals_file = tmp_path / "goals.json"
        goals_file.write_text(json.dumps({"current_ftp_watts": 343}))
        with (
            patch("src.goals.GOALS_PATH", goals_file),
            patch("src.ai.plan_adaptor.SESSIONS_LOG_PATH", tmp_path / "missing.json"),
        ):
            goals = load_goals()
            prompt = _build_user_prompt(
                original_plan=self._ORIGINAL_PLAN_WITH_STALE_FTP,
                today="2026-08-15",
                goals=goals,
            )
        assert "325 W" in prompt  # historical value from the original plan retained
        assert "343 W" in prompt  # live value reaches the model text
        assert "Current athlete profile (live)" in prompt

    def test_authoritative_wording_present_when_profile_included(
        self, tmp_path: Path
    ) -> None:
        with patch("src.ai.plan_adaptor.SESSIONS_LOG_PATH", tmp_path / "missing.json"):
            prompt = _build_user_prompt(
                original_plan="plan text",
                today="2026-08-15",
                goals={"main_goal": "Race"},
            )
        assert "authoritative" in prompt

    def test_empty_goals_omit_profile_section(self, tmp_path: Path) -> None:
        # The section itself (the rendered table) is omitted; the surrounding
        # conditional instruction ("if a section appears above...") still stands
        # since it's static prompt text, not part of format_goals_table's output.
        with patch("src.ai.plan_adaptor.SESSIONS_LOG_PATH", tmp_path / "missing.json"):
            prompt = _build_user_prompt(
                original_plan="plan text", today="2026-08-15", goals={}
            )
        assert "## Current athlete profile (live)" not in prompt

    def test_today_and_original_plan_included(self, tmp_path: Path) -> None:
        with patch("src.ai.plan_adaptor.SESSIONS_LOG_PATH", tmp_path / "missing.json"):
            prompt = _build_user_prompt(
                original_plan="my special plan text",
                today="2026-08-15",
                goals={},
            )
        assert "2026-08-15" in prompt
        assert "my special plan text" in prompt


class TestAdaptPlanWritesAdaptedFile:
    def _run(self, tmp_path: Path, goals_path: Path) -> tuple[str, Path]:
        original = tmp_path / "plan_original.md"
        original.write_text("Original plan text")
        adapted_path = tmp_path / "plan_adapted.md"

        response = _FakeResponse("end_turn", [_FakeTextBlock("Adapted plan body")])
        with (
            patch("src.ai.plan_adaptor.PLAN_ORIGINAL_PATH", original),
            patch("src.ai.plan_adaptor.PLAN_ADAPTED_PATH", adapted_path),
            patch("src.ai.plan_adaptor.SESSIONS_LOG_PATH", tmp_path / "missing.json"),
            patch("src.ai.plan_adaptor.APP_DIR", tmp_path),
            patch("src.goals.GOALS_PATH", goals_path),
            patch("src.ai.plan_adaptor.get_client", return_value=_FakeClient(response)),
        ):
            result = adapt_plan(Mock())
        return result, adapted_path

    def test_prepends_header_when_goals_present(self, tmp_path: Path) -> None:
        goals_path = tmp_path / "goals.json"
        goals_path.write_text(json.dumps({"current_ftp_watts": 343}))
        result, adapted_path = self._run(tmp_path, goals_path)
        assert result.startswith("## Plan parameters (at adaptation)")
        assert "343 W" in result
        assert adapted_path.read_text() == result

    def test_no_header_when_goals_missing(self, tmp_path: Path) -> None:
        result, adapted_path = self._run(tmp_path, tmp_path / "missing.json")
        assert result == "Adapted plan body"
        assert "Plan parameters (at adaptation)" not in result
        assert adapted_path.read_text() == result


class TestAdaptPlanTruncatedResponse:
    def test_raises_when_stop_reason_is_not_end_turn_or_tool_use(
        self, tmp_path: Path, activity_client: IntervalsClient
    ) -> None:
        original = tmp_path / "plan_original.md"
        original.write_text("# Original Plan")
        adapted_path = tmp_path / "plan_adapted.md"
        response = _FakeResponse("max_tokens", [_FakeTextBlock("partial plan")])
        with (
            patch("src.ai.plan_adaptor.PLAN_ORIGINAL_PATH", original),
            patch("src.ai.plan_adaptor.PLAN_ADAPTED_PATH", adapted_path),
            patch("src.ai.plan_adaptor.SESSIONS_LOG_PATH", tmp_path / "missing.json"),
            patch("src.goals.GOALS_PATH", tmp_path / "missing.json"),
            patch("src.ai.plan_adaptor.get_client", return_value=_FakeClient(response)),
        ):
            with pytest.raises(RuntimeError):
                adapt_plan(activity_client)
        assert not adapted_path.exists()

    def test_exception_message_includes_stop_reason(
        self, tmp_path: Path, activity_client: IntervalsClient
    ) -> None:
        original = tmp_path / "plan_original.md"
        original.write_text("# Original Plan")
        response = _FakeResponse("max_tokens", [_FakeTextBlock("partial plan")])
        with (
            patch("src.ai.plan_adaptor.PLAN_ORIGINAL_PATH", original),
            patch(
                "src.ai.plan_adaptor.PLAN_ADAPTED_PATH", tmp_path / "plan_adapted.md"
            ),
            patch("src.ai.plan_adaptor.SESSIONS_LOG_PATH", tmp_path / "missing.json"),
            patch("src.goals.GOALS_PATH", tmp_path / "missing.json"),
            patch("src.ai.plan_adaptor.get_client", return_value=_FakeClient(response)),
        ):
            with pytest.raises(RuntimeError, match="max_tokens") as exc_info:
                adapt_plan(activity_client)
        assert "max_tokens" in str(exc_info.value)

    def test_does_not_overwrite_existing_adapted_plan(
        self, tmp_path: Path, activity_client: IntervalsClient
    ) -> None:
        original = tmp_path / "plan_original.md"
        original.write_text("# Original Plan")
        adapted_path = tmp_path / "plan_adapted.md"
        adapted_path.write_text("PREVIOUS ADAPTED PLAN")
        response = _FakeResponse("max_tokens", [_FakeTextBlock("partial plan")])
        with (
            patch("src.ai.plan_adaptor.PLAN_ORIGINAL_PATH", original),
            patch("src.ai.plan_adaptor.PLAN_ADAPTED_PATH", adapted_path),
            patch("src.ai.plan_adaptor.SESSIONS_LOG_PATH", tmp_path / "missing.json"),
            patch("src.goals.GOALS_PATH", tmp_path / "missing.json"),
            patch("src.ai.plan_adaptor.get_client", return_value=_FakeClient(response)),
        ):
            with pytest.raises(RuntimeError):
                adapt_plan(activity_client)
        assert adapted_path.read_text() == "PREVIOUS ADAPTED PLAN"

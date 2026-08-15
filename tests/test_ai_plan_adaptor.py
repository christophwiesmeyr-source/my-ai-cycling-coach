"""Tests for src/ai/plan_adaptor.py — pure helper functions plus adapt_plan() with a fake client."""

import copy
import json
import logging
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.ai.plan_adaptor import (
    _build_log_section,
    _build_user_prompt,
    _splice_past_sessions,
    _extract_text,
    adapt_plan,
    adapt_sessions,
)
from src.data.intervals_api import IntervalsClient
from src.goals import load_goals


class _FakeTextBlock:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeOtherBlock:
    pass


class _FakeThinkingBlock:
    def __init__(self, thinking: str = "reasoning...") -> None:
        self.thinking = thinking


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
    def __init__(
        self,
        response: _FakeResponse | None = None,
        responses: list[_FakeResponse] | None = None,
    ) -> None:
        self._response = response
        self._responses = list(responses) if responses is not None else None
        self.stream_calls: list[dict] = []

    def stream(self, **kwargs: object) -> _FakeStream:
        # Deep-copy so later in-place mutation of `messages` (moving the cache
        # breakpoint forward) doesn't retroactively change what earlier calls
        # appear to have been made with.
        self.stream_calls.append(copy.deepcopy(kwargs))
        resp = self._responses.pop(0) if self._responses is not None else self._response
        assert resp is not None
        return _FakeStream(resp)


class _FakeClient:
    def __init__(
        self,
        response: _FakeResponse | None = None,
        responses: list[_FakeResponse] | None = None,
    ) -> None:
        self.messages = _FakeMessages(response=response, responses=responses)


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


class _FakeToolUseBlock:
    def __init__(self, tool_use_id: str = "tool1") -> None:
        self.type = "tool_use"
        self.id = tool_use_id
        self.name = "list_recent_activities"
        self.input: dict = {}


_SESSIONS_HEADER = (
    "date,week,phase,type,duration_min,intensity,target_power_pct_ftp,"
    "warmup,main_set,cooldown,description"
)


def _session_row(date: str, type_: str) -> str:
    return f"{date},1,Base,{type_},60,Zone 2,56-75%,warmup,main set,cooldown,desc"


class TestSplicePastSessions:
    def test_keeps_original_past_row_ignores_generated_rewrite(
        self, tmp_path: Path
    ) -> None:
        original_path = tmp_path / "sessions_original.csv"
        original_path.write_text(
            "\n".join([_SESSIONS_HEADER, _session_row("2000-01-01", "Original Past")])
        )
        generated = "\n".join(
            [
                _SESSIONS_HEADER,
                _session_row("2000-01-01", "Model Rewrote Past"),
                _session_row("2999-01-01", "Model Future"),
            ]
        )
        with patch("src.ai.plan_adaptor.SESSIONS_ORIGINAL_PATH", original_path):
            result, dropped = _splice_past_sessions(generated)
        assert "Original Past" in result
        assert "Model Rewrote Past" not in result
        assert "Model Future" in result
        assert dropped == 0

    def test_drops_row_with_extra_trailing_columns(self, tmp_path: Path) -> None:
        # Regression: an unescaped comma in a free-text field (e.g.
        # description) gives DictReader a row with more values than
        # headers; the overflow used to land under a `None` key that
        # crashed DictWriter with "dict contains fields not in fieldnames".
        # Now the malformed row is dropped rather than written at all.
        original_path = tmp_path / "sessions_original.csv"
        original_path.write_text(
            "\n".join([_SESSIONS_HEADER, _session_row("2000-01-01", "Original Past")])
        )
        malformed_future_row = (
            _session_row("2999-01-01", "Generated Future") + ",unexpected,overflow"
        )
        generated = "\n".join([_SESSIONS_HEADER, malformed_future_row])
        with patch("src.ai.plan_adaptor.SESSIONS_ORIGINAL_PATH", original_path):
            result, dropped = _splice_past_sessions(generated)
        assert "Original Past" in result
        assert "Generated Future" not in result
        assert dropped == 1

    def test_logs_raw_response_when_rows_dropped(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        # The raw model response isn't persisted anywhere else, so the
        # dropped-row warning must carry the exact original text — this is
        # the only place it can be recovered from for diagnosis.
        original_path = tmp_path / "sessions_original.csv"
        original_path.write_text(
            "\n".join([_SESSIONS_HEADER, _session_row("2000-01-01", "Original Past")])
        )
        malformed_future_row = (
            _session_row("2999-01-01", "Generated Future") + ",unexpected,overflow"
        )
        generated = "\n".join([_SESSIONS_HEADER, malformed_future_row])
        with patch("src.ai.plan_adaptor.SESSIONS_ORIGINAL_PATH", original_path):
            with caplog.at_level(logging.WARNING):
                _splice_past_sessions(generated)
        assert "dropped 1 malformed row" in caplog.text
        assert malformed_future_row in caplog.text

    def test_drops_row_with_comma_shifted_fields_instead_of_corrupting(
        self, tmp_path: Path
    ) -> None:
        # An unescaped comma *before* the last column shifts every field
        # after it (e.g. real cooldown/description text ends up in the
        # overflow while cooldown/description hold the wrong values). Such
        # a row must be dropped, not written with misassigned data.
        original_path = tmp_path / "sessions_original.csv"
        original_path.write_text(
            "\n".join([_SESSIONS_HEADER, _session_row("2000-01-01", "Original Past")])
        )
        shifted_row = (
            "2999-01-01,1,Base,Threshold,60,Zone 4,91-105%,warmup,"
            "3x10 min, hard, main set,10 min cooldown,desc text"
        )
        generated = "\n".join([_SESSIONS_HEADER, shifted_row])
        with patch("src.ai.plan_adaptor.SESSIONS_ORIGINAL_PATH", original_path):
            result, dropped = _splice_past_sessions(generated)
        assert "Original Past" in result
        assert " hard" not in result  # would appear in a misassigned cooldown
        assert dropped == 1

    def test_falls_back_to_generated_when_no_original(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        generated = "\n".join(
            [_SESSIONS_HEADER, _session_row("2999-01-01", "Only Future")]
        )
        with patch(
            "src.ai.plan_adaptor.SESSIONS_ORIGINAL_PATH", tmp_path / "missing.csv"
        ):
            with caplog.at_level(logging.WARNING):
                result, dropped = _splice_past_sessions(generated)
        assert result == generated
        assert dropped == 0
        assert "no usable original" in caplog.text

    def test_returns_generated_unchanged_when_unparseable(self, tmp_path: Path) -> None:
        original_path = tmp_path / "sessions_original.csv"
        original_path.write_text(
            "\n".join([_SESSIONS_HEADER, _session_row("2000-01-01", "Original Past")])
        )
        with patch("src.ai.plan_adaptor.SESSIONS_ORIGINAL_PATH", original_path):
            result, dropped = _splice_past_sessions("")
        assert result == ""
        assert dropped == 0


class TestAdaptSessions:
    def test_writes_spliced_csv_to_adapted_path(self, tmp_path: Path) -> None:
        original_path = tmp_path / "sessions_original.csv"
        original_path.write_text(
            "\n".join([_SESSIONS_HEADER, _session_row("2000-01-01", "Original Past")])
        )
        adapted_path = tmp_path / "sessions_adapted.csv"
        generated_csv = "\n".join(
            [_SESSIONS_HEADER, _session_row("2999-01-01", "Generated Future")]
        )
        response = _FakeResponse("end_turn", [_FakeTextBlock(generated_csv)])
        with (
            patch("src.ai.plan_adaptor.SESSIONS_ORIGINAL_PATH", original_path),
            patch("src.ai.plan_adaptor.SESSIONS_ADAPTED_PATH", adapted_path),
            patch("src.ai.plan_adaptor.APP_DIR", tmp_path),
            patch("src.goals.GOALS_PATH", tmp_path / "missing.json"),
            patch(
                "src.ai.plan_adaptor.get_client",
                return_value=_FakeClient(response=response),
            ),
        ):
            result, dropped = adapt_sessions("adapted plan text")
        assert "Original Past" in result
        assert "Generated Future" in result
        assert adapted_path.read_text() == result
        assert dropped == 0

    def test_reports_dropped_row_count(self, tmp_path: Path) -> None:
        original_path = tmp_path / "sessions_original.csv"
        original_path.write_text(
            "\n".join([_SESSIONS_HEADER, _session_row("2000-01-01", "Original Past")])
        )
        adapted_path = tmp_path / "sessions_adapted.csv"
        malformed_row = (
            _session_row("2999-01-01", "Generated Future") + ",unexpected,overflow"
        )
        generated_csv = "\n".join([_SESSIONS_HEADER, malformed_row])
        response = _FakeResponse("end_turn", [_FakeTextBlock(generated_csv)])
        with (
            patch("src.ai.plan_adaptor.SESSIONS_ORIGINAL_PATH", original_path),
            patch("src.ai.plan_adaptor.SESSIONS_ADAPTED_PATH", adapted_path),
            patch("src.ai.plan_adaptor.APP_DIR", tmp_path),
            patch("src.goals.GOALS_PATH", tmp_path / "missing.json"),
            patch(
                "src.ai.plan_adaptor.get_client",
                return_value=_FakeClient(response=response),
            ),
        ):
            result, dropped = adapt_sessions("adapted plan text")
        assert "Original Past" in result
        assert "Generated Future" not in result
        assert dropped == 1

    def test_survives_leading_thinking_block(self, tmp_path: Path) -> None:
        # Regression: a leading ThinkingBlock ahead of the CSV text block
        # previously crashed adapt_sessions() with an AttributeError,
        # silently leaving SESSIONS_ADAPTED_PATH unwritten.
        adapted_path = tmp_path / "sessions_adapted.csv"
        generated_csv = "\n".join(
            [_SESSIONS_HEADER, _session_row("2999-01-01", "Generated Future")]
        )
        response = _FakeResponse(
            "end_turn", [_FakeThinkingBlock(), _FakeTextBlock(generated_csv)]
        )
        with (
            patch(
                "src.ai.plan_adaptor.SESSIONS_ORIGINAL_PATH", tmp_path / "missing.csv"
            ),
            patch("src.ai.plan_adaptor.SESSIONS_ADAPTED_PATH", adapted_path),
            patch("src.ai.plan_adaptor.APP_DIR", tmp_path),
            patch("src.goals.GOALS_PATH", tmp_path / "missing.json"),
            patch(
                "src.ai.plan_adaptor.get_client",
                return_value=_FakeClient(response=response),
            ),
        ):
            result, dropped = adapt_sessions("adapted plan text")
        assert "Generated Future" in result
        assert adapted_path.read_text() == result
        assert dropped == 0

    def test_raises_when_response_truncated(self, tmp_path: Path) -> None:
        # Regression: a real run hit max_tokens partway through a multi-week
        # session list — the response wasn't just missing a row, it was
        # missing entire weeks that were never generated at all. Without a
        # stop_reason check, that silently shipped as a "1 row dropped"
        # warning instead of the loud failure this actually is.
        partial_csv = "\n".join(
            [_SESSIONS_HEADER, _session_row("2026-08-18", "Sweet Spot Intervals")]
        )
        response = _FakeResponse("max_tokens", [_FakeTextBlock(partial_csv)])
        with (
            patch(
                "src.ai.plan_adaptor.SESSIONS_ORIGINAL_PATH", tmp_path / "missing.csv"
            ),
            patch(
                "src.ai.plan_adaptor.SESSIONS_ADAPTED_PATH", tmp_path / "adapted.csv"
            ),
            patch("src.ai.plan_adaptor.APP_DIR", tmp_path),
            patch("src.goals.GOALS_PATH", tmp_path / "missing.json"),
            patch(
                "src.ai.plan_adaptor.get_client",
                return_value=_FakeClient(response=response),
            ),
        ):
            with pytest.raises(RuntimeError, match="max_tokens"):
                adapt_sessions("adapted plan text")
        assert not (tmp_path / "adapted.csv").exists()


class TestAdaptPlanCaching:
    def _run_two_turns(self, tmp_path: Path) -> _FakeMessages:
        original = tmp_path / "plan_original.md"
        original.write_text("Original plan text")
        tool_use_response = _FakeResponse("tool_use", [_FakeToolUseBlock()])
        end_turn_response = _FakeResponse(
            "end_turn", [_FakeTextBlock("Adapted plan body")]
        )
        client = _FakeClient(responses=[tool_use_response, end_turn_response])
        tool_result = [{"type": "tool_result", "tool_use_id": "tool1", "content": "ok"}]
        with (
            patch("src.ai.plan_adaptor.PLAN_ORIGINAL_PATH", original),
            patch(
                "src.ai.plan_adaptor.PLAN_ADAPTED_PATH", tmp_path / "plan_adapted.md"
            ),
            patch("src.ai.plan_adaptor.SESSIONS_LOG_PATH", tmp_path / "missing.json"),
            patch("src.ai.plan_adaptor.APP_DIR", tmp_path),
            patch("src.goals.GOALS_PATH", tmp_path / "missing.json"),
            patch("src.ai.plan_adaptor.get_client", return_value=client),
            patch("src.ai.plan_adaptor.execute_tools", return_value=tool_result),
        ):
            adapt_plan(Mock())
        return client.messages

    def test_system_prompt_carries_cache_control(self, tmp_path: Path) -> None:
        messages = self._run_two_turns(tmp_path)
        system = messages.stream_calls[0]["system"]
        assert system[-1]["cache_control"] == {"type": "ephemeral"}

    def test_breakpoint_moves_forward_across_turns(self, tmp_path: Path) -> None:
        messages = self._run_two_turns(tmp_path)
        first_call_messages = messages.stream_calls[0]["messages"]
        second_call_messages = messages.stream_calls[1]["messages"]

        assert first_call_messages[-1]["content"][-1]["cache_control"] == {
            "type": "ephemeral"
        }
        # The initial user message's breakpoint has been stripped by turn 2,
        # and the newly-appended tool-result message carries it instead.
        assert "cache_control" not in second_call_messages[0]["content"][-1]
        assert second_call_messages[-1]["content"][-1]["cache_control"] == {
            "type": "ephemeral"
        }

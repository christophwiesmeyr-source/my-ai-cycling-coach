"""Tests for src/ai/plan_adaptor.py — pure helper functions only (no API calls)."""
import json
from unittest.mock import patch

from src.ai.plan_adaptor import _build_log_section, _extract_text


class _FakeTextBlock:
    def __init__(self, text):
        self.text = text


class _FakeOtherBlock:
    pass


class TestExtractText:
    def test_joins_text_from_all_text_blocks(self):
        blocks = [_FakeTextBlock("Hello"), _FakeTextBlock("World")]
        assert _extract_text(blocks) == "Hello\nWorld"

    def test_skips_blocks_without_text_attr(self):
        blocks = [_FakeOtherBlock(), _FakeTextBlock("only this")]
        assert _extract_text(blocks) == "only this"

    def test_empty_content_returns_empty_string(self):
        assert _extract_text([]) == ""

    def test_single_block_no_trailing_newline(self):
        blocks = [_FakeTextBlock("Just one")]
        assert _extract_text(blocks) == "Just one"


class TestBuildLogSection:
    def test_returns_empty_string_when_file_missing(self, tmp_path):
        with patch("src.ai.plan_adaptor.SESSIONS_LOG_PATH", tmp_path / "missing.json"):
            assert _build_log_section() == ""

    def test_returns_empty_string_when_file_malformed(self, tmp_path):
        log_file = tmp_path / "log.json"
        log_file.write_text("not valid json{")
        with patch("src.ai.plan_adaptor.SESSIONS_LOG_PATH", log_file):
            assert _build_log_section() == ""

    def test_returns_empty_string_when_log_empty(self, tmp_path):
        log_file = tmp_path / "log.json"
        log_file.write_text(json.dumps({}))
        with patch("src.ai.plan_adaptor.SESSIONS_LOG_PATH", log_file):
            assert _build_log_section() == ""

    def test_completed_session_formatted_correctly(self, tmp_path):
        log = {"2025-04-01": {"completed_date": "2025-04-01", "comment": ""}}
        log_file = tmp_path / "log.json"
        log_file.write_text(json.dumps(log))
        with patch("src.ai.plan_adaptor.SESSIONS_LOG_PATH", log_file):
            result = _build_log_section()
        assert "2025-04-01" in result
        assert "completed 2025-04-01" in result

    def test_incomplete_session_formatted_correctly(self, tmp_path):
        log = {"2025-04-02": {"completed_date": "", "comment": ""}}
        log_file = tmp_path / "log.json"
        log_file.write_text(json.dumps(log))
        with patch("src.ai.plan_adaptor.SESSIONS_LOG_PATH", log_file):
            result = _build_log_section()
        assert "not yet marked complete" in result

    def test_comment_appended_when_present(self, tmp_path):
        log = {"2025-04-01": {"completed_date": "2025-04-01", "comment": "felt strong"}}
        log_file = tmp_path / "log.json"
        log_file.write_text(json.dumps(log))
        with patch("src.ai.plan_adaptor.SESSIONS_LOG_PATH", log_file):
            result = _build_log_section()
        assert "felt strong" in result

    def test_entries_sorted_by_date(self, tmp_path):
        log = {
            "2025-04-03": {"completed_date": "2025-04-03", "comment": ""},
            "2025-04-01": {"completed_date": "2025-04-01", "comment": ""},
        }
        log_file = tmp_path / "log.json"
        log_file.write_text(json.dumps(log))
        with patch("src.ai.plan_adaptor.SESSIONS_LOG_PATH", log_file):
            result = _build_log_section()
        assert result.index("2025-04-01") < result.index("2025-04-03")

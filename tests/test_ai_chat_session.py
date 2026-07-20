"""Tests for src/ai/chat_session.py"""
import json
from contextlib import ExitStack
from datetime import date, timedelta
from pathlib import Path
from typing import Optional
from unittest.mock import patch

from src.ai.chat_session import ChatSession, _SYSTEM_BASE, _build_session_table

_CSV_HEADER = "date,week,phase,type,duration_min,intensity,target_power_pct_ftp,warmup,main_set,cooldown,description"


def _csv_row(plan_date: str, session_type: str = "Z2 Endurance", duration: int = 90,
             intensity: str = "Zone 2", power: str = "56-75%") -> str:
    return f"{plan_date},1,Base,{session_type},{duration},{intensity},{power},10 min warmup,60 min steady,10 min cooldown,Aerobic base"


class TestReloadPlans:
    def test_loads_original_plan_when_present(self, tmp_path: Path) -> None:
        plan_file = tmp_path / "plan.md"
        plan_file.write_text("# My Plan")
        with patch("src.ai.chat_session.PLAN_ORIGINAL_PATH", plan_file), \
             patch("src.ai.chat_session.PLAN_ADAPTED_PATH", tmp_path / "missing.md"):
            session = ChatSession()
        assert session.original_plan == "# My Plan"

    def test_loads_adapted_plan_when_present(self, tmp_path: Path) -> None:
        plan_file = tmp_path / "adapted.md"
        plan_file.write_text("# Adapted Plan")
        with patch("src.ai.chat_session.PLAN_ORIGINAL_PATH", tmp_path / "missing.md"), \
             patch("src.ai.chat_session.PLAN_ADAPTED_PATH", plan_file):
            session = ChatSession()
        assert session.adapted_plan == "# Adapted Plan"

    def test_plans_empty_when_files_missing(self, tmp_path: Path) -> None:
        with patch("src.ai.chat_session.PLAN_ORIGINAL_PATH", tmp_path / "a.md"), \
             patch("src.ai.chat_session.PLAN_ADAPTED_PATH", tmp_path / "b.md"):
            session = ChatSession()
        assert session.original_plan == ""
        assert session.adapted_plan == ""

    def test_reload_updates_plans(self, tmp_path: Path) -> None:
        original = tmp_path / "original.md"
        with patch("src.ai.chat_session.PLAN_ORIGINAL_PATH", original), \
             patch("src.ai.chat_session.PLAN_ADAPTED_PATH", tmp_path / "missing.md"):
            session = ChatSession()
            assert session.original_plan == ""
            original.write_text("# New Plan")
            session.reload_plans()
        assert session.original_plan == "# New Plan"

    def test_reload_clears_deleted_adapted_plan(self, tmp_path: Path) -> None:
        adapted = tmp_path / "adapted.md"
        adapted.write_text("# Adapted")
        with patch("src.ai.chat_session.PLAN_ORIGINAL_PATH", tmp_path / "missing.md"), \
             patch("src.ai.chat_session.PLAN_ADAPTED_PATH", adapted):
            session = ChatSession()
            assert session.adapted_plan == "# Adapted"
            adapted.unlink()              # e.g. a new plan was generated
            session.reload_plans()
        assert session.adapted_plan == ""  # stale plan no longer lingers in memory


class TestHistory:
    def _make_session(self, tmp_path: Path) -> ChatSession:
        with patch("src.ai.chat_session.PLAN_ORIGINAL_PATH", tmp_path / "a.md"), \
             patch("src.ai.chat_session.PLAN_ADAPTED_PATH", tmp_path / "b.md"):
            return ChatSession()

    def test_starts_empty(self, tmp_path: Path) -> None:
        assert self._make_session(tmp_path).history == []

    def test_add_user_message(self, tmp_path: Path) -> None:
        session = self._make_session(tmp_path)
        session.add_user_message("Hello")
        assert session.history == [{"role": "user", "content": "Hello"}]

    def test_add_assistant_message(self, tmp_path: Path) -> None:
        session = self._make_session(tmp_path)
        session.add_assistant_message("Hi there")
        assert session.history == [{"role": "assistant", "content": "Hi there"}]

    def test_messages_accumulate_in_order(self, tmp_path: Path) -> None:
        session = self._make_session(tmp_path)
        session.add_user_message("Question")
        session.add_assistant_message("Answer")
        session.add_user_message("Follow-up")
        assert [m["role"] for m in session.history] == ["user", "assistant", "user"]


class TestBuildSystem:
    def _make_session(self, tmp_path: Path, original: str = "", adapted: str = "") -> ChatSession:
        orig = tmp_path / "original.md"
        adpt = tmp_path / "adapted.md"
        if original:
            orig.write_text(original)
        if adapted:
            adpt.write_text(adapted)
        with patch("src.ai.chat_session.PLAN_ORIGINAL_PATH", orig), \
             patch("src.ai.chat_session.PLAN_ADAPTED_PATH", adpt), \
             patch("src.ai.chat_session.SESSIONS_ORIGINAL_PATH", tmp_path / "sessions.csv"), \
             patch("src.ai.chat_session.SESSIONS_ADAPTED_PATH", tmp_path / "sessions_adapted.csv"):
            return ChatSession()

    @staticmethod
    def _text(session: ChatSession) -> str:
        """Concatenated text of all system blocks (build_system returns blocks)."""
        return "".join(block["text"] for block in session.build_system())

    def test_always_contains_base_prompt(self, tmp_path: Path) -> None:
        session = self._make_session(tmp_path)
        assert _SYSTEM_BASE in self._text(session)

    def test_no_plans_returns_base_only(self, tmp_path: Path) -> None:
        session = self._make_session(tmp_path)
        system = self._text(session)
        assert "Original Training Plan" not in system
        assert "Adapted Training Plan" not in system

    def test_includes_original_plan_when_set(self, tmp_path: Path) -> None:
        session = self._make_session(tmp_path, original="# Week 1")
        system = self._text(session)
        assert "Original Training Plan" in system
        assert "# Week 1" in system

    def test_includes_adapted_plan_when_set(self, tmp_path: Path) -> None:
        session = self._make_session(tmp_path, adapted="# Adapted")
        system = self._text(session)
        assert "Adapted Training Plan" in system
        assert "# Adapted" in system

    def test_includes_both_plans_when_both_set(self, tmp_path: Path) -> None:
        session = self._make_session(tmp_path, original="# Original", adapted="# Adapted")
        system = self._text(session)
        assert "Original Training Plan" in system
        assert "Adapted Training Plan" in system

    def test_original_plan_precedes_adapted_plan(self, tmp_path: Path) -> None:
        session = self._make_session(tmp_path, original="# Original", adapted="# Adapted")
        system = self._text(session)
        assert system.index("Original Training Plan") < system.index("Adapted Training Plan")

    def test_includes_session_table_when_sessions_present(self, tmp_path: Path) -> None:
        recent = (date.today() - timedelta(days=3)).isoformat()
        csv_file = tmp_path / "sessions.csv"
        csv_file.write_text(f"{_CSV_HEADER}\n{_csv_row(recent)}")
        session = self._make_session(tmp_path)
        with patch("src.ai.chat_session.SESSIONS_ORIGINAL_PATH", csv_file), \
             patch("src.ai.chat_session.SESSIONS_ADAPTED_PATH", tmp_path / "missing_adapted.csv"), \
             patch("src.ai.chat_session.SESSIONS_LOG_PATH", tmp_path / "missing.json"):
            blocks = session.build_system()
        text = "".join(b["text"] for b in blocks)
        assert "Session log" in text
        assert recent in text

    def test_stable_prefix_is_cached_session_table_is_not(self, tmp_path: Path) -> None:
        # plans live in the cached prefix block; the volatile session table
        # (today's date + log) is a separate, uncached block after it.
        recent = (date.today() - timedelta(days=3)).isoformat()
        csv_file = tmp_path / "sessions.csv"
        csv_file.write_text(f"{_CSV_HEADER}\n{_csv_row(recent)}")
        session = self._make_session(tmp_path, original="# Original")
        with patch("src.ai.chat_session.SESSIONS_ORIGINAL_PATH", csv_file), \
             patch("src.ai.chat_session.SESSIONS_ADAPTED_PATH", tmp_path / "missing_adapted.csv"), \
             patch("src.ai.chat_session.SESSIONS_LOG_PATH", tmp_path / "missing.json"):
            blocks = session.build_system()
        assert blocks[0]["cache_control"] == {"type": "ephemeral"}
        assert "Original Training Plan" in blocks[0]["text"]
        assert "cache_control" not in blocks[-1]      # session table block
        assert "Session log" in blocks[-1]["text"]

    def test_no_session_table_means_single_cached_block(self, tmp_path: Path) -> None:
        session = self._make_session(tmp_path, original="# Original")
        with patch("src.ai.chat_session.SESSIONS_ORIGINAL_PATH", tmp_path / "missing.csv"), \
             patch("src.ai.chat_session.SESSIONS_ADAPTED_PATH", tmp_path / "missing_adapted.csv"):
            blocks = session.build_system()
        assert len(blocks) == 1
        assert blocks[0]["cache_control"] == {"type": "ephemeral"}


class TestBuildSessionTable:
    def _write_csv(self, path: Path, rows: list[str]) -> None:
        lines = [_CSV_HEADER] + rows
        path.write_text("\n".join(lines))

    def _patches(self, tmp_path: Path, original: Optional[Path] = None,
                 adapted: Optional[Path] = None, log: Optional[Path] = None) -> ExitStack:
        stack = ExitStack()
        stack.enter_context(patch("src.ai.chat_session.SESSIONS_ORIGINAL_PATH",
                                  original or tmp_path / "missing.csv"))
        stack.enter_context(patch("src.ai.chat_session.SESSIONS_ADAPTED_PATH",
                                  adapted or tmp_path / "missing_adapted.csv"))
        stack.enter_context(patch("src.ai.chat_session.SESSIONS_LOG_PATH",
                                  log or tmp_path / "missing.json"))
        return stack

    def test_returns_empty_when_no_csv(self, tmp_path: Path) -> None:
        with self._patches(tmp_path):
            assert _build_session_table() == ""

    def test_returns_empty_when_csv_has_only_header(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "sessions.csv"
        self._write_csv(csv_file, [])
        with self._patches(tmp_path, original=csv_file):
            assert _build_session_table() == ""

    def test_returns_empty_when_all_sessions_outside_window(self, tmp_path: Path) -> None:
        old = (date.today() - timedelta(weeks=9)).isoformat()
        future = (date.today() + timedelta(days=1)).isoformat()
        csv_file = tmp_path / "sessions.csv"
        self._write_csv(csv_file, [_csv_row(old), _csv_row(future)])
        with self._patches(tmp_path, original=csv_file):
            assert _build_session_table() == ""

    def test_excludes_future_sessions(self, tmp_path: Path) -> None:
        future = (date.today() + timedelta(days=1)).isoformat()
        csv_file = tmp_path / "sessions.csv"
        self._write_csv(csv_file, [_csv_row(future)])
        with self._patches(tmp_path, original=csv_file):
            assert _build_session_table() == ""

    def test_excludes_sessions_older_than_cutoff(self, tmp_path: Path) -> None:
        old = (date.today() - timedelta(weeks=9)).isoformat()
        csv_file = tmp_path / "sessions.csv"
        self._write_csv(csv_file, [_csv_row(old)])
        with self._patches(tmp_path, original=csv_file):
            assert _build_session_table() == ""

    def test_includes_session_within_window(self, tmp_path: Path) -> None:
        recent = (date.today() - timedelta(days=3)).isoformat()
        csv_file = tmp_path / "sessions.csv"
        self._write_csv(csv_file, [_csv_row(recent)])
        with self._patches(tmp_path, original=csv_file):
            result = _build_session_table()
        assert recent in result

    def test_shows_dash_when_no_log_entry(self, tmp_path: Path) -> None:
        recent = (date.today() - timedelta(days=3)).isoformat()
        csv_file = tmp_path / "sessions.csv"
        self._write_csv(csv_file, [_csv_row(recent)])
        with self._patches(tmp_path, original=csv_file):
            result = _build_session_table()
        assert "—" in result

    def test_shows_completion_date_from_log(self, tmp_path: Path) -> None:
        recent = (date.today() - timedelta(days=3)).isoformat()
        completed = (date.today() - timedelta(days=2)).isoformat()
        csv_file = tmp_path / "sessions.csv"
        log_file = tmp_path / "log.json"
        self._write_csv(csv_file, [_csv_row(recent)])
        log_file.write_text(json.dumps({recent: {"completed_date": completed, "comment": ""}}))
        with self._patches(tmp_path, original=csv_file, log=log_file):
            result = _build_session_table()
        assert completed in result

    def test_shows_comment_from_log(self, tmp_path: Path) -> None:
        recent = (date.today() - timedelta(days=3)).isoformat()
        csv_file = tmp_path / "sessions.csv"
        log_file = tmp_path / "log.json"
        self._write_csv(csv_file, [_csv_row(recent)])
        log_file.write_text(json.dumps({recent: {"completed_date": recent, "comment": "felt strong"}}))
        with self._patches(tmp_path, original=csv_file, log=log_file):
            result = _build_session_table()
        assert "felt strong" in result

    def test_prefers_adapted_csv_over_original(self, tmp_path: Path) -> None:
        recent = (date.today() - timedelta(days=3)).isoformat()
        original_csv = tmp_path / "sessions.csv"
        adapted_csv = tmp_path / "sessions_adapted.csv"
        self._write_csv(original_csv, [_csv_row(recent, session_type="Z2 Endurance")])
        self._write_csv(adapted_csv, [_csv_row(recent, session_type="Threshold Intervals")])
        with self._patches(tmp_path, original=original_csv, adapted=adapted_csv):
            result = _build_session_table()
        assert "Threshold Intervals" in result
        assert "Z2 Endurance" not in result

    def test_falls_back_to_original_when_no_adapted(self, tmp_path: Path) -> None:
        recent = (date.today() - timedelta(days=3)).isoformat()
        original_csv = tmp_path / "sessions.csv"
        self._write_csv(original_csv, [_csv_row(recent, session_type="Long Ride")])
        with self._patches(tmp_path, original=original_csv):
            result = _build_session_table()
        assert "Long Ride" in result

    def test_handles_missing_log_file_gracefully(self, tmp_path: Path) -> None:
        recent = (date.today() - timedelta(days=3)).isoformat()
        csv_file = tmp_path / "sessions.csv"
        self._write_csv(csv_file, [_csv_row(recent)])
        with self._patches(tmp_path, original=csv_file):
            result = _build_session_table()
        assert "—" in result

    def test_handles_malformed_log_file_gracefully(self, tmp_path: Path) -> None:
        recent = (date.today() - timedelta(days=3)).isoformat()
        csv_file = tmp_path / "sessions.csv"
        log_file = tmp_path / "log.json"
        self._write_csv(csv_file, [_csv_row(recent)])
        log_file.write_text("not valid json{")
        with self._patches(tmp_path, original=csv_file, log=log_file):
            result = _build_session_table()
        assert "—" in result

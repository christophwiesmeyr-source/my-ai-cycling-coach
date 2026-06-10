"""Tests for src/ai/chat_session.py"""
from unittest.mock import patch

from src.ai.chat_session import ChatSession, _SYSTEM_BASE


class TestReloadPlans:
    def test_loads_original_plan_when_present(self, tmp_path):
        plan_file = tmp_path / "plan.md"
        plan_file.write_text("# My Plan")
        with patch("src.ai.chat_session.PLAN_ORIGINAL_PATH", plan_file), \
             patch("src.ai.chat_session.PLAN_ADAPTED_PATH", tmp_path / "missing.md"):
            session = ChatSession()
        assert session.original_plan == "# My Plan"

    def test_loads_adapted_plan_when_present(self, tmp_path):
        plan_file = tmp_path / "adapted.md"
        plan_file.write_text("# Adapted Plan")
        with patch("src.ai.chat_session.PLAN_ORIGINAL_PATH", tmp_path / "missing.md"), \
             patch("src.ai.chat_session.PLAN_ADAPTED_PATH", plan_file):
            session = ChatSession()
        assert session.adapted_plan == "# Adapted Plan"

    def test_plans_empty_when_files_missing(self, tmp_path):
        with patch("src.ai.chat_session.PLAN_ORIGINAL_PATH", tmp_path / "a.md"), \
             patch("src.ai.chat_session.PLAN_ADAPTED_PATH", tmp_path / "b.md"):
            session = ChatSession()
        assert session.original_plan == ""
        assert session.adapted_plan == ""

    def test_reload_updates_plans(self, tmp_path):
        original = tmp_path / "original.md"
        with patch("src.ai.chat_session.PLAN_ORIGINAL_PATH", original), \
             patch("src.ai.chat_session.PLAN_ADAPTED_PATH", tmp_path / "missing.md"):
            session = ChatSession()
            assert session.original_plan == ""
            original.write_text("# New Plan")
            session.reload_plans()
        assert session.original_plan == "# New Plan"


class TestHistory:
    def _make_session(self, tmp_path):
        with patch("src.ai.chat_session.PLAN_ORIGINAL_PATH", tmp_path / "a.md"), \
             patch("src.ai.chat_session.PLAN_ADAPTED_PATH", tmp_path / "b.md"):
            return ChatSession()

    def test_starts_empty(self, tmp_path):
        assert self._make_session(tmp_path).history == []

    def test_add_user_message(self, tmp_path):
        session = self._make_session(tmp_path)
        session.add_user_message("Hello")
        assert session.history == [{"role": "user", "content": "Hello"}]

    def test_add_assistant_message(self, tmp_path):
        session = self._make_session(tmp_path)
        session.add_assistant_message("Hi there")
        assert session.history == [{"role": "assistant", "content": "Hi there"}]

    def test_messages_accumulate_in_order(self, tmp_path):
        session = self._make_session(tmp_path)
        session.add_user_message("Question")
        session.add_assistant_message("Answer")
        session.add_user_message("Follow-up")
        assert [m["role"] for m in session.history] == ["user", "assistant", "user"]


class TestBuildSystem:
    def _make_session(self, tmp_path, original="", adapted=""):
        orig = tmp_path / "original.md"
        adpt = tmp_path / "adapted.md"
        if original:
            orig.write_text(original)
        if adapted:
            adpt.write_text(adapted)
        with patch("src.ai.chat_session.PLAN_ORIGINAL_PATH", orig), \
             patch("src.ai.chat_session.PLAN_ADAPTED_PATH", adpt):
            return ChatSession()

    def test_always_contains_base_prompt(self, tmp_path):
        session = self._make_session(tmp_path)
        assert _SYSTEM_BASE in session.build_system()

    def test_no_plans_returns_base_only(self, tmp_path):
        session = self._make_session(tmp_path)
        system = session.build_system()
        assert "Original Training Plan" not in system
        assert "Adapted Training Plan" not in system

    def test_includes_original_plan_when_set(self, tmp_path):
        session = self._make_session(tmp_path, original="# Week 1")
        system = session.build_system()
        assert "Original Training Plan" in system
        assert "# Week 1" in system

    def test_includes_adapted_plan_when_set(self, tmp_path):
        session = self._make_session(tmp_path, adapted="# Adapted")
        system = session.build_system()
        assert "Adapted Training Plan" in system
        assert "# Adapted" in system

    def test_includes_both_plans_when_both_set(self, tmp_path):
        session = self._make_session(tmp_path, original="# Original", adapted="# Adapted")
        system = session.build_system()
        assert "Original Training Plan" in system
        assert "Adapted Training Plan" in system

    def test_original_plan_precedes_adapted_plan(self, tmp_path):
        session = self._make_session(tmp_path, original="# Original", adapted="# Adapted")
        system = session.build_system()
        assert system.index("Original Training Plan") < system.index("Adapted Training Plan")

"""Tests for src/ui/workers.py — QThread.run() is a plain method, callable directly."""

from unittest.mock import patch

from src.ui.workers import PlanAdaptorWorker


class TestPlanAdaptorWorker:
    def test_session_csv_failure_does_not_prevent_finished_from_firing(self) -> None:
        captured: dict = {}
        worker = PlanAdaptorWorker(activity_client=None)  # type: ignore[arg-type]
        worker.finished.connect(lambda plan: captured.setdefault("finished", plan))
        worker.error_occurred.connect(lambda err: captured.setdefault("error", err))

        with (
            patch("src.ui.workers.adapt_plan", return_value="the adapted plan"),
            patch("src.ui.workers.adapt_sessions", side_effect=RuntimeError("boom")),
        ):
            worker.run()

        assert captured == {"finished": "the adapted plan"}

    def test_session_csv_failure_emits_sessions_failed_after_finished(self) -> None:
        call_order: list[str] = []
        worker = PlanAdaptorWorker(activity_client=None)  # type: ignore[arg-type]
        worker.finished.connect(lambda plan: call_order.append("finished"))
        worker.sessions_failed.connect(lambda: call_order.append("sessions_failed"))

        with (
            patch("src.ui.workers.adapt_plan", return_value="the adapted plan"),
            patch("src.ui.workers.adapt_sessions", side_effect=RuntimeError("boom")),
        ):
            worker.run()

        # finished must fire first so the adapted plan is on screen before
        # the (modal, blocking) sessions_failed warning appears.
        assert call_order == ["finished", "sessions_failed"]

    def test_session_csv_success_does_not_emit_sessions_failed(self) -> None:
        captured: list[str] = []
        worker = PlanAdaptorWorker(activity_client=None)  # type: ignore[arg-type]
        worker.sessions_failed.connect(lambda: captured.append("sessions_failed"))

        with (
            patch("src.ui.workers.adapt_plan", return_value="the adapted plan"),
            patch("src.ui.workers.adapt_sessions", return_value=("csv text", 0)),
        ):
            worker.run()

        assert captured == []

    def test_dropped_rows_emit_sessions_incomplete_after_finished(self) -> None:
        call_order: list[str] = []
        worker = PlanAdaptorWorker(activity_client=None)  # type: ignore[arg-type]
        worker.finished.connect(lambda plan: call_order.append("finished"))
        worker.sessions_incomplete.connect(
            lambda n: call_order.append(f"sessions_incomplete:{n}")
        )

        with (
            patch("src.ui.workers.adapt_plan", return_value="the adapted plan"),
            patch("src.ui.workers.adapt_sessions", return_value=("csv text", 2)),
        ):
            worker.run()

        assert call_order == ["finished", "sessions_incomplete:2"]

    def test_no_dropped_rows_does_not_emit_sessions_incomplete(self) -> None:
        captured: list[int] = []
        worker = PlanAdaptorWorker(activity_client=None)  # type: ignore[arg-type]
        worker.sessions_incomplete.connect(lambda n: captured.append(n))

        with (
            patch("src.ui.workers.adapt_plan", return_value="the adapted plan"),
            patch("src.ui.workers.adapt_sessions", return_value=("csv text", 0)),
        ):
            worker.run()

        assert captured == []

    def test_session_csv_failure_does_not_emit_sessions_incomplete(self) -> None:
        captured: list[int] = []
        worker = PlanAdaptorWorker(activity_client=None)  # type: ignore[arg-type]
        worker.sessions_incomplete.connect(lambda n: captured.append(n))

        with (
            patch("src.ui.workers.adapt_plan", return_value="the adapted plan"),
            patch("src.ui.workers.adapt_sessions", side_effect=RuntimeError("boom")),
        ):
            worker.run()

        assert captured == []

    def test_plan_adaptation_failure_still_reports_error(self) -> None:
        captured: dict = {}
        worker = PlanAdaptorWorker(activity_client=None)  # type: ignore[arg-type]
        worker.finished.connect(lambda plan: captured.setdefault("finished", plan))
        worker.error_occurred.connect(lambda err: captured.setdefault("error", err))

        with (
            patch(
                "src.ui.workers.adapt_plan", side_effect=RuntimeError("adapt failed")
            ),
            patch("src.ui.workers.adapt_sessions") as mock_adapt_sessions,
        ):
            worker.run()

        assert captured == {"error": "adapt failed"}
        mock_adapt_sessions.assert_not_called()

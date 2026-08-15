"""Background QThread workers for AI operations — keeps the UI responsive"""

import logging
from typing import Any

from PyQt6.QtCore import QThread, pyqtSignal

from src.ai.client import get_client
from src.ai.plan_generator import (
    generate_plan,
    generate_sessions,
    clear_derived_plan_data,
)
from src.ai.plan_adaptor import adapt_plan, adapt_sessions
from src.ai.chat_session import ChatSession
from src.ai.tools import TOOLS, TOOL_STATUS_MESSAGES, execute_tools
from src.constants import AI_MODEL
from src.data.intervals_api import IntervalsClient

logger = logging.getLogger(__name__)


class PlanGeneratorWorker(QThread):
    """Generates a training plan then a structured session CSV."""

    status_update = pyqtSignal(str)
    finished = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, goals: dict):
        super().__init__()
        self.goals = goals

    def run(self) -> None:
        try:
            self.status_update.emit("Generating training plan…")
            plan = generate_plan(self.goals)
            self.status_update.emit("Generating session list…")
            generate_sessions(plan, self.goals)
            # The new plan invalidates any adapted plan and completion log.
            clear_derived_plan_data()
            self.finished.emit(plan)
        except Exception as exc:
            self.error_occurred.emit(str(exc))


class PlanAdaptorWorker(QThread):
    """Runs the agentic plan-adaptation loop against recent activity data."""

    finished = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    sessions_failed = pyqtSignal()
    sessions_incomplete = pyqtSignal(int)

    def __init__(self, activity_client: IntervalsClient):
        super().__init__()
        self.activity_client = activity_client

    def run(self) -> None:
        try:
            plan = adapt_plan(self.activity_client)
        except Exception as exc:
            logger.exception("plan adaptor failed")
            self.error_occurred.emit(str(exc))
            return

        sessions_failed = False
        dropped_rows = 0
        try:
            _, dropped_rows = adapt_sessions(plan)
        except Exception:
            logger.exception(
                "session CSV generation failed after successful plan adaptation"
            )
            sessions_failed = True

        # Emit finished first so the adapted plan is on screen before the
        # sessions_failed/sessions_incomplete warning appears — otherwise the
        # modal warning blocks rendering and the user sees a dialog with no
        # context yet.
        self.finished.emit(plan)
        if sessions_failed:
            self.sessions_failed.emit()
        elif dropped_rows:
            self.sessions_incomplete.emit(dropped_rows)


class ChatWorker(QThread):
    """Streams a coaching chat response, executing activity-data tool calls as needed."""

    chunk_received = pyqtSignal(str)
    tool_status = pyqtSignal(str)
    finished = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, session: ChatSession, activity_client: IntervalsClient):
        super().__init__()
        self.session = session
        self.activity_client = activity_client

    def run(self) -> None:
        messages: list[Any] = list(self.session.history)
        client = get_client()
        full_response = ""

        try:
            while True:
                with client.messages.stream(
                    model=AI_MODEL,
                    max_tokens=8192,
                    system=self.session.build_system(),
                    tools=TOOLS,
                    messages=messages,
                ) as stream:
                    for text in stream.text_stream:
                        full_response += text
                        self.chunk_received.emit(text)
                    final = stream.get_final_message()

                usage = final.usage
                logger.info(
                    "chat turn stop_reason=%s input_tokens=%s output_tokens=%s "
                    "cache_creation=%s cache_read=%s",
                    final.stop_reason,
                    usage.input_tokens,
                    usage.output_tokens,
                    getattr(usage, "cache_creation_input_tokens", None),
                    getattr(usage, "cache_read_input_tokens", None),
                )
                logger.debug("chat turn full response so far: %r", full_response)

                if final.stop_reason == "tool_use":
                    messages.append({"role": "assistant", "content": final.content})
                    for block in final.content:
                        if hasattr(block, "type") and block.type == "tool_use":
                            status = TOOL_STATUS_MESSAGES.get(
                                block.name, f"Using tool: {block.name}…"
                            )
                            self.tool_status.emit(status)
                    results = execute_tools(final.content, self.activity_client)
                    messages.append({"role": "user", "content": results})
                    continue

                if final.stop_reason != "end_turn":
                    logger.warning(
                        "chat turn ended on unhandled stop_reason=%s — response may be truncated",
                        final.stop_reason,
                    )
                break

            self.finished.emit(full_response)
        except Exception as exc:
            logger.exception("chat worker failed")
            self.error_occurred.emit(str(exc))

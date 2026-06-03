"""Background QThread workers for AI operations — keeps the UI responsive"""
from typing import Any

from PyQt6.QtCore import QThread, pyqtSignal

from src.ai.client import get_client
from src.ai.plan_generator import generate_plan, generate_sessions
from src.ai.plan_adaptor import adapt_plan
from src.ai.chat_session import ChatSession
from src.ai.tools import TOOLS, TOOL_STATUS_MESSAGES, execute_tools
from src.constants import AI_MODEL


class PlanGeneratorWorker(QThread):
    """Generates a training plan then a structured session CSV."""

    status_update = pyqtSignal(str)
    finished = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, goals: dict):
        super().__init__()
        self.goals = goals

    def run(self):
        try:
            self.status_update.emit("Generating training plan…")
            plan = generate_plan(self.goals)
            self.status_update.emit("Generating session list…")
            generate_sessions(plan, self.goals)
            self.finished.emit(plan)
        except Exception as exc:
            self.error_occurred.emit(str(exc))


class PlanAdaptorWorker(QThread):
    """Runs the agentic plan-adaptation loop against Strava data."""

    finished = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, strava_client):
        super().__init__()
        self.strava_client = strava_client

    def run(self):
        try:
            plan = adapt_plan(self.strava_client)
            self.finished.emit(plan)
        except Exception as exc:
            self.error_occurred.emit(str(exc))


class ChatWorker(QThread):
    """Streams a coaching chat response, executing Strava tool calls as needed."""

    chunk_received = pyqtSignal(str)
    tool_status = pyqtSignal(str)
    finished = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, session: ChatSession, strava_client):
        super().__init__()
        self.session = session
        self.strava_client = strava_client

    def run(self):
        messages: list[Any] = list(self.session.history)
        client = get_client()
        full_response = ""

        try:
            while True:
                with client.messages.stream(
                    model=AI_MODEL,
                    max_tokens=2048,
                    system=self.session.build_system(),
                    tools=TOOLS,
                    messages=messages,
                ) as stream:
                    for text in stream.text_stream:
                        full_response += text
                        self.chunk_received.emit(text)
                    final = stream.get_final_message()

                if final.stop_reason == "end_turn":
                    break

                if final.stop_reason == "tool_use":
                    messages.append({"role": "assistant", "content": final.content})
                    for block in final.content:
                        if hasattr(block, "type") and block.type == "tool_use":
                            status = TOOL_STATUS_MESSAGES.get(
                                block.name, f"Using tool: {block.name}…"
                            )
                            self.tool_status.emit(status)
                    results = execute_tools(final.content, self.strava_client)
                    messages.append({"role": "user", "content": results})
                    continue

                break

            self.finished.emit(full_response)
        except Exception as exc:
            self.error_occurred.emit(str(exc))

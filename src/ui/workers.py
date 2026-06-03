"""Background QThread workers for AI operations — keeps the UI responsive"""
from PyQt6.QtCore import QThread, pyqtSignal

from src.ai.plan_generator import generate_plan, generate_sessions
from src.ai.plan_adaptor import adapt_plan
from src.ai.chat_session import ChatSession


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
    """Streams a chat response chunk by chunk."""

    chunk_received = pyqtSignal(str)
    finished = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, session: ChatSession):
        super().__init__()
        self.session = session

    def run(self):
        full_response = ""
        try:
            for chunk in self.session.stream_response():
                full_response += chunk
                self.chunk_received.emit(chunk)
            self.finished.emit(full_response)
        except Exception as exc:
            self.error_occurred.emit(str(exc))

"""Chat session — maintains conversation history and system context for the coaching chat"""
from src.constants import PLAN_ORIGINAL_PATH, PLAN_ADAPTED_PATH

_SYSTEM_BASE = (
    "You are an expert cycling coach assistant. Help the athlete understand their training "
    "progress, compare completed workouts against the plan, and provide actionable advice. "
    "Be concise and practical. Reference specific sessions or metrics when relevant. "
    "Use the available tools to fetch Strava activity data whenever it would help you give "
    "a more specific or accurate answer."
)


class ChatSession:
    def __init__(self):
        self.history: list = []
        self.original_plan: str = ""
        self.adapted_plan: str = ""
        self.reload_plans()

    def reload_plans(self):
        """Re-read plan files from disk (call after generating or adapting a plan)."""
        if PLAN_ORIGINAL_PATH.exists():
            self.original_plan = PLAN_ORIGINAL_PATH.read_text()
        if PLAN_ADAPTED_PATH.exists():
            self.adapted_plan = PLAN_ADAPTED_PATH.read_text()

    def add_user_message(self, text: str):
        self.history.append({"role": "user", "content": text})

    def add_assistant_message(self, text: str):
        self.history.append({"role": "assistant", "content": text})

    def build_system(self) -> str:
        parts = [_SYSTEM_BASE]
        if self.original_plan:
            parts.append(f"\n\n## Original Training Plan\n\n{self.original_plan}")
        if self.adapted_plan:
            parts.append(f"\n\n## Adapted Training Plan\n\n{self.adapted_plan}")
        return "\n".join(parts)

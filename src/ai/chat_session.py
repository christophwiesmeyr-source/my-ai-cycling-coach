"""Chat session — maintains conversation history and streams coaching responses"""
from pathlib import Path
from typing import Iterator

from .client import get_client, MODEL
from .plan_generator import PLAN_ORIGINAL_PATH
from .plan_adaptor import PLAN_ADAPTED_PATH

_SYSTEM_BASE = (
    "You are an expert cycling coach assistant. Help the athlete understand their training "
    "progress, compare completed workouts against the plan, and provide actionable advice. "
    "Be concise and practical. Reference specific sessions or metrics when relevant."
)


class ChatSession:
    def __init__(self):
        self.history: list[dict] = []
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

    def stream_response(self) -> Iterator[str]:
        """Stream the next assistant response given current history. Yields text chunks."""
        client = get_client()
        with client.messages.stream(
            model=MODEL,
            max_tokens=2048,
            system=self._build_system(),
            messages=self.history,
        ) as stream:
            for chunk in stream.text_stream:
                yield chunk

    def _build_system(self) -> str:
        parts = [_SYSTEM_BASE]
        if self.original_plan:
            parts.append(f"\n\n## Original Training Plan\n\n{self.original_plan}")
        if self.adapted_plan:
            parts.append(f"\n\n## Adapted Training Plan\n\n{self.adapted_plan}")
        return "\n".join(parts)

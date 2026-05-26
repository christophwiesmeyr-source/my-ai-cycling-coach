"""Anthropic API client — key loading and client factory"""
import os
from pathlib import Path

import anthropic

MODEL = "claude-sonnet-4-6"
_KEY_FILE = Path.home() / ".aitrainer" / "claude_api_key"


class AIClientError(Exception):
    pass


def _load_api_key() -> str:
    if key := os.environ.get("ANTHROPIC_API_KEY"):
        return key
    if _KEY_FILE.exists():
        key = _KEY_FILE.read_text().strip()
        if key:
            return key
    raise AIClientError(
        f"Claude API key not found. Set the ANTHROPIC_API_KEY environment variable "
        f"or save your key to {_KEY_FILE}.\n"
        f"See the README for setup instructions."
    )


def get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=_load_api_key())

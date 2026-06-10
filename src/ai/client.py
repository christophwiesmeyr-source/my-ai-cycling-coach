"""Anthropic API client — key loading and client factory"""
import anthropic

from src.constants import CLAUDE_API_KEY_PATH


class AIClientError(Exception):
    pass


def _load_api_key() -> str:
    if CLAUDE_API_KEY_PATH.exists():
        key = CLAUDE_API_KEY_PATH.read_text().strip()
        if key:
            return key
    raise AIClientError(
        f"Claude API key not found. Save your key to {CLAUDE_API_KEY_PATH}.\n"
        f"See the README for setup instructions."
    )


def get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=_load_api_key())

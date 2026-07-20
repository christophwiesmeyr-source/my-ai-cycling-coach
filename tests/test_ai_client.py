"""Tests for src/ai/client.py"""
from pathlib import Path
from unittest.mock import patch

import pytest

from src.ai.client import AIClientError, _load_api_key, get_client


class TestLoadApiKey:
    def test_reads_key_from_file(self, tmp_path: Path) -> None:
        key_file = tmp_path / "key.txt"
        key_file.write_text("my_api_key")
        with patch("src.ai.client.CLAUDE_API_KEY_PATH", key_file):
            assert _load_api_key() == "my_api_key"

    def test_key_is_stripped(self, tmp_path: Path) -> None:
        key_file = tmp_path / "key.txt"
        key_file.write_text("  key_with_whitespace\n")
        with patch("src.ai.client.CLAUDE_API_KEY_PATH", key_file):
            assert _load_api_key() == "key_with_whitespace"

    def test_empty_file_raises(self, tmp_path: Path) -> None:
        key_file = tmp_path / "key.txt"
        key_file.write_text("   ")
        with patch("src.ai.client.CLAUDE_API_KEY_PATH", key_file):
            with pytest.raises(AIClientError):
                _load_api_key()

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with patch("src.ai.client.CLAUDE_API_KEY_PATH", tmp_path / "missing.txt"):
            with pytest.raises(AIClientError):
                _load_api_key()


class TestGetClient:
    def test_returns_anthropic_client(self) -> None:
        import anthropic
        with patch("src.ai.client._load_api_key", return_value="test_key"):
            client = get_client()
        assert isinstance(client, anthropic.Anthropic)

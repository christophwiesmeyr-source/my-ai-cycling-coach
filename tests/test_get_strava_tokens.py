"""Tests for get_strava_tokens helper (OAuthHandler, find_free_port, exchange_code_for_tokens, save_tokens)"""
import json
import socket
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
import requests

from src.data.get_strava_tokens import (
    OAuthHandler,
    exchange_code_for_tokens,
    find_free_port,
    save_tokens,
)


# ---------------------------------------------------------------------------
# OAuthHandler
# ---------------------------------------------------------------------------

def _make_handler(path: str) -> OAuthHandler:
    """Build an OAuthHandler instance without starting a real server."""
    server = MagicMock()
    server.code = None

    request = MagicMock()
    request.makefile.return_value = BytesIO()

    handler = OAuthHandler.__new__(OAuthHandler)
    handler.server = server
    handler.path = path
    handler.wfile = BytesIO()

    # Capture response state
    handler._response_code = None
    handler._headers = {}

    def send_response(code, message=None):
        handler._response_code = code

    def send_header(key, value):
        handler._headers[key] = value

    handler.send_response = send_response
    handler.send_header = send_header
    handler.end_headers = lambda: None

    return handler


class TestOAuthHandler:
    def test_success_stores_code_and_responds_200(self):
        handler = _make_handler("/callback?code=abc123")
        handler.do_GET()

        assert handler._response_code == 200
        assert handler.server.code == "abc123"

    def test_success_triggers_server_shutdown(self):
        handler = _make_handler("/callback?code=abc123")
        with patch("threading.Thread") as mock_thread:
            mock_thread.return_value = MagicMock()
            handler.do_GET()
            mock_thread.assert_called_once()

    def test_error_param_responds_400_and_clears_code(self):
        handler = _make_handler("/callback?error=access_denied")
        handler.do_GET()

        assert handler._response_code == 400
        assert handler.server.code is None

    def test_no_code_no_error_responds_400(self):
        handler = _make_handler("/callback")
        handler.do_GET()

        assert handler._response_code == 400


# ---------------------------------------------------------------------------
# find_free_port
# ---------------------------------------------------------------------------

class TestFindFreePort:
    def test_returns_valid_port(self):
        port = find_free_port()
        assert isinstance(port, int)
        assert 1024 <= port <= 65535

    def test_port_is_available(self):
        port = find_free_port()
        # If the port is truly free we can bind to it
        s = socket.socket()
        try:
            s.bind(("", port))
        finally:
            s.close()


# ---------------------------------------------------------------------------
# exchange_code_for_tokens
# ---------------------------------------------------------------------------

class TestExchangeCodeForTokens:
    def test_success_returns_token_dict(self):
        fake_tokens = {"access_token": "tok", "refresh_token": "ref", "athlete": {}}
        mock_resp = Mock()
        mock_resp.raise_for_status = Mock()
        mock_resp.json.return_value = fake_tokens

        with patch("requests.post", return_value=mock_resp) as mock_post:
            result = exchange_code_for_tokens("cid", "csec", "code42", "http://localhost:5000/callback")

        assert result == fake_tokens
        _, kwargs = mock_post.call_args
        assert kwargs["data"]["code"] == "code42"
        assert kwargs["data"]["grant_type"] == "authorization_code"

    def test_http_error_raises(self):
        mock_resp = Mock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("401 Unauthorized")

        with patch("requests.post", return_value=mock_resp):
            with pytest.raises(requests.HTTPError):
                exchange_code_for_tokens("cid", "csec", "badcode", "http://localhost:5000/callback")

    def test_network_error_propagates(self):
        with patch("requests.post", side_effect=requests.ConnectionError("timeout")):
            with pytest.raises(requests.ConnectionError):
                exchange_code_for_tokens("cid", "csec", "code", "http://localhost:5000/callback")


# ---------------------------------------------------------------------------
# save_tokens
# ---------------------------------------------------------------------------

class TestSaveTokens:
    def test_writes_json_with_credentials(self, tmp_path):
        token_file = tmp_path / "strava_tokens.json"

        with patch("src.constants.STRAVA_TOKENS_PATH", token_file):
            result = save_tokens(
                {"access_token": "tok", "refresh_token": "ref"},
                "my_id",
                "my_secret",
            )

        saved = json.loads(token_file.read_text())
        assert saved["access_token"] == "tok"
        assert saved["strava_client_id"] == "my_id"
        assert saved["strava_client_secret"] == "my_secret"
        assert result == token_file

    def test_creates_parent_directory(self, tmp_path):
        token_file = tmp_path / "nested" / "dir" / "tokens.json"
        assert not token_file.parent.exists()

        with patch("src.constants.STRAVA_TOKENS_PATH", token_file):
            save_tokens({"access_token": "t"}, "id", "sec")

        assert token_file.exists()

    def test_does_not_mutate_input_dict(self, tmp_path):
        token_file = tmp_path / "tokens.json"
        original_tokens = {"access_token": "tok"}

        with patch("src.constants.STRAVA_TOKENS_PATH", token_file):
            save_tokens(original_tokens, "id", "sec")

        assert "strava_client_id" not in original_tokens

"""Tests for StravaClient — gaps not covered by test_strava_client.py.

Covers: _load_tokens, _check_and_refresh_token, _refresh_token, _save_tokens,
        _build_activity, _get_activity_detail, _get_activity_streams, and the
        error path of list_activities.
"""
import json
from datetime import datetime
from unittest.mock import Mock, patch, mock_open

import pandas as pd
import pytest
import requests

from src.data.strava_api import StravaClient, StravaClientError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_TOKENS = {
    "access_token": "acc_tok",
    "refresh_token": "ref_tok",
    "strava_client_id": "cid",
    "strava_client_secret": "csec",
}


def _make_client() -> StravaClient:
    """Return a StravaClient with token I/O and the initial refresh check stubbed out."""
    with patch.object(StravaClient, "_load_tokens", return_value=dict(FAKE_TOKENS)), \
         patch.object(StravaClient, "_check_and_refresh_token"):
        client = StravaClient()
    client._check_and_refresh_token = Mock()
    return client


def _ok(payload) -> Mock:
    m = Mock()
    m.status_code = 200
    m.json.return_value = payload
    return m


def _err(status: int, text: str = "error") -> Mock:
    m = Mock()
    m.status_code = status
    m.text = text
    m.json.return_value = {}
    return m


# ---------------------------------------------------------------------------
# _load_tokens
# ---------------------------------------------------------------------------

class TestLoadTokens:
    def test_loads_from_existing_file(self, tmp_path):
        token_file = tmp_path / "tokens.json"
        token_file.write_text(json.dumps(FAKE_TOKENS))

        with patch.object(StravaClient, "_check_and_refresh_token"), \
             patch("src.data.strava_api.STRAVA_TOKENS_PATH", token_file):
            client = StravaClient.__new__(StravaClient)
            client.TOKEN_FILE = token_file
            tokens = client._load_tokens()

        assert tokens["access_token"] == "acc_tok"

    def test_raises_when_file_missing(self, tmp_path):
        missing = tmp_path / "no_such_file.json"

        client = StravaClient.__new__(StravaClient)
        client.TOKEN_FILE = missing

        with pytest.raises(StravaClientError, match="Unable to find Strava access token"):
            client._load_tokens()


# ---------------------------------------------------------------------------
# _check_and_refresh_token
# ---------------------------------------------------------------------------

class TestCheckAndRefreshToken:
    def test_401_triggers_refresh(self):
        client = _make_client()
        del client._check_and_refresh_token
        client._refresh_token = Mock()

        with patch("requests.get", return_value=_err(401)):
            client._check_and_refresh_token()

        client._refresh_token.assert_called_once()

    def test_200_does_not_trigger_refresh(self):
        client = _make_client()
        del client._check_and_refresh_token
        client._refresh_token = Mock()

        with patch("requests.get", return_value=_ok({})):
            client._check_and_refresh_token()

        client._refresh_token.assert_not_called()

    def test_network_error_is_swallowed(self):
        client = _make_client()
        del client._check_and_refresh_token

        with patch("requests.get", side_effect=requests.RequestException("timeout")):
            client._check_and_refresh_token()  # must not raise


# ---------------------------------------------------------------------------
# _refresh_token
# ---------------------------------------------------------------------------

class TestRefreshToken:
    def test_success_updates_access_token_and_headers(self):
        client = _make_client()
        new_tokens = {"access_token": "new_acc", "refresh_token": "new_ref"}

        with patch("requests.post", return_value=_ok(new_tokens)), \
             patch.object(client, "_save_tokens"):
            client._refresh_token()

        assert client.access_token == "new_acc"
        assert client.headers["Authorization"] == "Bearer new_acc"

    def test_success_persists_tokens(self):
        client = _make_client()
        new_tokens = {"access_token": "new_acc", "refresh_token": "new_ref"}

        with patch("requests.post", return_value=_ok(new_tokens)), \
             patch.object(client, "_save_tokens") as mock_save:
            client._refresh_token()

        mock_save.assert_called_once()

    def test_missing_client_id_raises(self):
        client = _make_client()
        client.tokens = {"access_token": "t", "refresh_token": "r"}  # no client creds

        with pytest.raises(StravaClientError, match="Client ID and Client Secret required"):
            client._refresh_token()

    def test_missing_refresh_token_raises(self):
        client = _make_client()
        client.tokens = {
            "access_token": "t",
            "strava_client_id": "cid",
            "strava_client_secret": "csec",
            # no refresh_token
        }

        with pytest.raises(StravaClientError, match="Refresh token not found"):
            client._refresh_token()

    def test_non_200_response_raises(self):
        client = _make_client()

        with patch("requests.post", return_value=_err(400, "Bad Request")):
            with pytest.raises(StravaClientError, match="Failed to refresh token"):
                client._refresh_token()


# ---------------------------------------------------------------------------
# _save_tokens
# ---------------------------------------------------------------------------

class TestSaveTokens:
    def test_writes_tokens_to_file(self, tmp_path):
        client = _make_client()
        client.TOKEN_FILE = tmp_path / "tokens.json"
        client.tokens = dict(FAKE_TOKENS)

        client._save_tokens()

        saved = json.loads(client.TOKEN_FILE.read_text())
        assert saved["access_token"] == "acc_tok"

    def test_creates_parent_directory(self, tmp_path):
        client = _make_client()
        client.TOKEN_FILE = tmp_path / "nested" / "dir" / "tokens.json"
        client.tokens = dict(FAKE_TOKENS)

        client._save_tokens()

        assert client.TOKEN_FILE.exists()


# ---------------------------------------------------------------------------
# _get_activity_detail
# ---------------------------------------------------------------------------

class TestGetActivityDetail:
    def test_success_returns_json(self):
        client = _make_client()
        payload = {"id": 1, "sport": "Ride"}

        with patch("requests.get", return_value=_ok(payload)):
            result = client._get_activity_detail(1)

        assert result == payload

    def test_non_200_raises(self):
        client = _make_client()

        with patch("requests.get", return_value=_err(404, "Not Found")):
            with pytest.raises(StravaClientError, match="Failed to fetch activity detail"):
                client._get_activity_detail(1)

    def test_network_error_raises(self):
        client = _make_client()

        with patch("requests.get", side_effect=requests.RequestException("timeout")):
            with pytest.raises(StravaClientError, match="Failed to fetch activity detail"):
                client._get_activity_detail(1)


# ---------------------------------------------------------------------------
# _get_activity_streams
# ---------------------------------------------------------------------------

class TestGetActivityStreams:
    def test_success_returns_json(self):
        client = _make_client()
        payload = {"time": {"data": [0, 1, 2]}}

        with patch("requests.get", return_value=_ok(payload)):
            result = client._get_activity_streams(1)

        assert result == payload

    def test_non_200_raises(self):
        client = _make_client()

        with patch("requests.get", return_value=_err(403, "Forbidden")):
            with pytest.raises(StravaClientError, match="Failed to fetch activity streams"):
                client._get_activity_streams(1)

    def test_network_error_raises(self):
        client = _make_client()

        with patch("requests.get", side_effect=requests.RequestException("dns fail")):
            with pytest.raises(StravaClientError, match="Failed to fetch activity streams"):
                client._get_activity_streams(1)


# ---------------------------------------------------------------------------
# list_activities — error path
# ---------------------------------------------------------------------------

class TestListActivitiesErrors:
    def test_non_200_raises(self):
        client = _make_client()

        with patch("requests.get", return_value=_err(500, "Server Error")):
            with pytest.raises(StravaClientError, match="Failed to load Strava activities"):
                client.list_activities(datetime(2023, 1, 1))


# ---------------------------------------------------------------------------
# _build_activity
# ---------------------------------------------------------------------------

MINIMAL_META = {
    "start_date_local": "2023-06-01T10:00:00",
    "distance": 20000.0,
    "elapsed_time": 3600,
    "sport": "Ride",
}

FULL_STREAMS = {
    "time": {"data": [0, 10, 20]},
    "distance": {"data": [0.0, 50.0, 100.0]},
    "altitude": {"data": [100.0, 101.0, 102.0]},
    "heartrate": {"data": [130, 135, 140]},
    "cadence": {"data": [80, 82, 84]},
    "watts": {"data": [200, 210, 220]},
    "velocity_smooth": {"data": [5.0, 5.5, 6.0]},
}


class TestBuildActivity:
    def test_all_streams_mapped_correctly(self):
        client = _make_client()
        activity = client._build_activity(MINIMAL_META, FULL_STREAMS)

        assert set(activity.data.columns) >= {"timestamp", "distance", "altitude", "heart_rate", "cadence", "power", "speed"}
        assert len(activity.data) == 3

    def test_optional_streams_absent(self):
        client = _make_client()
        streams = {"time": {"data": [0, 10]}}

        activity = client._build_activity(MINIMAL_META, streams)

        assert "timestamp" in activity.data.columns
        assert "power" not in activity.data.columns
        assert "heart_rate" not in activity.data.columns

    def test_metadata_fields_propagated(self):
        client = _make_client()
        activity = client._build_activity(MINIMAL_META, FULL_STREAMS)

        assert activity.sport == "Ride"
        assert activity.total_distance == 20000.0
        assert activity.total_elapsed_time == 3600

    def test_sport_fallback_to_type(self):
        client = _make_client()
        meta = {**MINIMAL_META, "sport": None, "type": "Run"}
        activity = client._build_activity(meta, FULL_STREAMS)
        assert activity.sport == "Run"

    def test_sport_fallback_to_cycling(self):
        client = _make_client()
        meta = {**MINIMAL_META, "sport": None, "type": None}
        activity = client._build_activity(meta, FULL_STREAMS)
        assert activity.sport == "cycling"

    def test_timezone_stripped_from_start_time(self):
        client = _make_client()
        meta = {**MINIMAL_META, "start_date_local": "2023-06-01T10:00:00+02:00"}
        activity = client._build_activity(meta, FULL_STREAMS)
        assert activity.data["timestamp"].dt.tz is None

    def test_missing_start_time_raises(self):
        client = _make_client()
        meta = {"distance": 1000, "elapsed_time": 60, "sport": "Ride"}

        with pytest.raises(StravaClientError, match="missing start time"):
            client._build_activity(meta, FULL_STREAMS)

    def test_missing_time_stream_raises(self):
        client = _make_client()

        with pytest.raises(StravaClientError, match="No time stream available"):
            client._build_activity(MINIMAL_META, {})

    def test_empty_time_values_raises(self):
        client = _make_client()
        streams = {"time": {"data": []}}

        with pytest.raises(StravaClientError, match="No time values found"):
            client._build_activity(MINIMAL_META, streams)

    def test_timestamp_derived_from_time_stream(self):
        client = _make_client()
        activity = client._build_activity(MINIMAL_META, {"time": {"data": [0, 30, 60]}})

        timestamps = activity.data["timestamp"]
        assert (timestamps.iloc[1] - timestamps.iloc[0]).total_seconds() == 30
        assert (timestamps.iloc[2] - timestamps.iloc[0]).total_seconds() == 60

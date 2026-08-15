"""Tests for IntervalsClient with mocked HTTP calls.

Field-name mapping (_normalize_activity / _build_activity) is the one thing
NOT independently verified against a live intervals.icu response — the docs
page couldn't be fully introspected offline. These tests pin the mapping we
implemented so a live smoke test has a clear diff to compare against, and so
the mapping doesn't silently drift once it *is* verified.
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.data.intervals_api import IntervalsClient, IntervalsClientError


@pytest.fixture
def mock_client(tmp_path: Path) -> IntervalsClient:
    config = tmp_path / "intervals_config.json"
    with patch.object(IntervalsClient, "CONFIG_FILE", config):
        return IntervalsClient(api_key="testkey", athlete_id="i12345")


class TestInit:
    def test_uses_explicit_credentials(self, tmp_path: Path) -> None:
        with patch.object(IntervalsClient, "CONFIG_FILE", tmp_path / "missing.json"):
            client = IntervalsClient(api_key="k", athlete_id="i1")
        assert client.api_key == "k"
        assert client.athlete_id == "i1"
        assert client.auth == ("API_KEY", "k")

    def test_loads_credentials_from_config_file(self, tmp_path: Path) -> None:
        config = tmp_path / "intervals_config.json"
        config.write_text('{"api_key": "filekey", "athlete_id": "i999"}')
        with patch.object(IntervalsClient, "CONFIG_FILE", config):
            client = IntervalsClient()
        assert client.api_key == "filekey"
        assert client.athlete_id == "i999"

    def test_explicit_args_override_config_file(self, tmp_path: Path) -> None:
        config = tmp_path / "intervals_config.json"
        config.write_text('{"api_key": "filekey", "athlete_id": "i999"}')
        with patch.object(IntervalsClient, "CONFIG_FILE", config):
            client = IntervalsClient(api_key="override")
        assert client.api_key == "override"
        assert client.athlete_id == "i999"  # falls back to config

    def test_missing_credentials_raises_with_setup_hint(self, tmp_path: Path) -> None:
        with patch.object(IntervalsClient, "CONFIG_FILE", tmp_path / "missing.json"):
            with pytest.raises(IntervalsClientError, match="Developer Settings"):
                IntervalsClient()


class TestListActivities:
    def test_success_normalizes_and_uses_basic_auth(
        self, mock_client: IntervalsClient
    ) -> None:
        mock_response = Mock(status_code=200)
        mock_response.json.return_value = [
            {
                "id": "i67890",
                "start_date_local": "2026-06-01T10:00:00",
                "type": "Ride",
                "distance": 40000,
                "elapsed_time": 3600,
                "average_watts": 210,
                "average_heartrate": 145,
                "trainer": False,
            }
        ]
        with patch("requests.get", return_value=mock_response) as mock_get:
            activities = mock_client.list_activities(datetime(2026, 1, 1))

        assert activities == [
            {
                "id": "i67890",
                "start_date_local": "2026-06-01T10:00:00",
                "sport_type": "Ride",
                "distance": 40000,
                "elapsed_time": 3600,
                "average_watts": 210,
                "average_heartrate": 145,
                "trainer": False,
            }
        ]
        _, kwargs = mock_get.call_args
        assert kwargs["auth"] == ("API_KEY", "testkey")
        assert "athlete/i12345/activities" in mock_get.call_args[0][0]
        assert kwargs["params"]["oldest"] == "2026-01-01T00:00:00"

    def test_falls_back_to_icu_prefixed_and_alt_keys(
        self, mock_client: IntervalsClient
    ) -> None:
        mock_response = Mock(status_code=200)
        mock_response.json.return_value = [
            {
                "id": "i1",
                "start_date": "2026-01-02T08:00:00",  # no start_date_local
                "sport_type": "VirtualRide",  # no "type"
                "icu_average_watts": 180,  # no "average_watts"
            }
        ]
        with patch("requests.get", return_value=mock_response):
            activities = mock_client.list_activities(datetime(2026, 1, 1))
        a = activities[0]
        assert a["start_date_local"] == "2026-01-02T08:00:00"
        assert a["sport_type"] == "VirtualRide"
        assert a["average_watts"] == 180

    def test_http_error_raises(self, mock_client: IntervalsClient) -> None:
        mock_response = Mock(status_code=403, text="Forbidden")
        with patch("requests.get", return_value=mock_response):
            with pytest.raises(IntervalsClientError, match="403"):
                mock_client.list_activities(datetime(2026, 1, 1))

    def test_network_error_raises(self, mock_client: IntervalsClient) -> None:
        import requests

        with patch("requests.get", side_effect=requests.RequestException("boom")):
            with pytest.raises(IntervalsClientError, match="boom"):
                mock_client.list_activities(datetime(2026, 1, 1))


class TestDownloadActivity:
    def _streams(self, n: int = 5) -> list[dict]:
        return [
            {"type": "time", "data": list(range(n))},
            {"type": "watts", "data": [200] * n},
            {"type": "heartrate", "data": [140] * n},
            {"type": "cadence", "data": [85] * n},
            {"type": "distance", "data": [i * 10 for i in range(n)]},
            {"type": "altitude", "data": [100] * n},
            {"type": "velocity_smooth", "data": [8.0] * n},
            {"type": "temp", "data": [18.5] * n},
        ]

    def test_builds_activity_with_all_streams(
        self, mock_client: IntervalsClient
    ) -> None:
        metadata = {
            "start_date_local": "2026-06-01T10:00:00",
            "type": "Ride",
            "distance": 50000,
            "elapsed_time": 3600,
            "moving_time": 3500,
        }
        responses = [
            Mock(status_code=200, json=Mock(return_value=metadata)),
            Mock(status_code=200, json=Mock(return_value=self._streams())),
        ]
        with patch("requests.get", side_effect=responses):
            activity = mock_client.download_activity("i67890")

        assert activity.sport == "Ride"
        assert activity.total_distance == 50000
        assert activity.total_elapsed_time == 3600
        assert activity.total_moving_time == 3500
        assert list(activity.get_time_series("power")) == [200] * 5
        assert list(activity.get_time_series("heart_rate")) == [140] * 5
        assert list(activity.get_time_series("cadence")) == [85] * 5
        assert list(activity.get_time_series("speed")) == [8.0] * 5
        assert list(activity.get_time_series("temperature")) == [18.5] * 5
        assert "grade" in activity.data.columns

    def test_no_grade_column_when_altitude_missing(
        self, mock_client: IntervalsClient
    ) -> None:
        metadata = {"start_date_local": "2026-06-01T10:00:00", "type": "Ride"}
        streams = [s for s in self._streams() if s["type"] != "altitude"]
        responses = [
            Mock(status_code=200, json=Mock(return_value=metadata)),
            Mock(status_code=200, json=Mock(return_value=streams)),
        ]
        with patch("requests.get", side_effect=responses):
            activity = mock_client.download_activity("i67890")

        assert "grade" not in activity.data.columns

    def test_no_grade_column_when_distance_missing(
        self, mock_client: IntervalsClient
    ) -> None:
        metadata = {"start_date_local": "2026-06-01T10:00:00", "type": "Ride"}
        streams = [s for s in self._streams() if s["type"] != "distance"]
        responses = [
            Mock(status_code=200, json=Mock(return_value=metadata)),
            Mock(status_code=200, json=Mock(return_value=streams)),
        ]
        with patch("requests.get", side_effect=responses):
            activity = mock_client.download_activity("i67890")

        assert "grade" not in activity.data.columns

    def test_no_temp_stream_leaves_temperature_column_absent(
        self, mock_client: IntervalsClient
    ) -> None:
        metadata = {"start_date_local": "2026-06-01T10:00:00", "type": "Ride"}
        streams = [s for s in self._streams() if s["type"] != "temp"]
        responses = [
            Mock(status_code=200, json=Mock(return_value=metadata)),
            Mock(status_code=200, json=Mock(return_value=streams)),
        ]
        with patch("requests.get", side_effect=responses):
            activity = mock_client.download_activity("i67890")

        assert "temperature" not in activity.data.columns
        assert list(activity.get_time_series("temperature")) == []

    def test_missing_time_stream_raises(self, mock_client: IntervalsClient) -> None:
        metadata = {"start_date_local": "2026-06-01T10:00:00", "type": "Ride"}
        responses = [
            Mock(status_code=200, json=Mock(return_value=metadata)),
            Mock(
                status_code=200,
                json=Mock(return_value=[{"type": "watts", "data": [1, 2]}]),
            ),
        ]
        with patch("requests.get", side_effect=responses):
            with pytest.raises(IntervalsClientError, match="No time stream"):
                mock_client.download_activity("i1")

    def test_missing_start_time_raises(self, mock_client: IntervalsClient) -> None:
        responses = [
            Mock(status_code=200, json=Mock(return_value={})),
            Mock(status_code=200, json=Mock(return_value=self._streams())),
        ]
        with patch("requests.get", side_effect=responses):
            with pytest.raises(IntervalsClientError, match="missing start time"):
                mock_client.download_activity("i1")

    def test_detail_http_error_raises(self, mock_client: IntervalsClient) -> None:
        with patch(
            "requests.get", return_value=Mock(status_code=404, text="not found")
        ):
            with pytest.raises(IntervalsClientError, match="404"):
                mock_client.download_activity("i1")

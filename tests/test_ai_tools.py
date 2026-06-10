"""Tests for src/ai/tools.py"""
import json
from unittest.mock import MagicMock, Mock, patch

import numpy as np
import pytest

from src.ai.tools import (
    _get_activity_details,
    _get_activity_power_curve,
    _get_activity_zones,
    _HR_ZONES,
    _list_activities,
    _POWER_ZONES,
    _zone_breakdown,
    execute_tools,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SIMPLE_ZONES = [
    ("Low",  0,  50),
    ("High", 50, None),
]


def _make_activity(power=None, heart_rate=None, n=100):
    activity = Mock()
    activity.get_time_array.return_value = np.arange(n, dtype=float)

    def _series(metric):
        if metric == "power":
            return power
        if metric == "heart_rate":
            return heart_rate
        return None

    activity.get_time_series.side_effect = _series
    return activity


def _make_block(name, **inputs):
    block = Mock()
    block.type = "tool_use"
    block.id = "block_001"
    block.name = name
    block.input = inputs
    return block


# ---------------------------------------------------------------------------
# execute_tools
# ---------------------------------------------------------------------------

class TestExecuteTools:
    def test_empty_content_returns_empty(self):
        assert execute_tools([], Mock()) == []

    def test_non_tool_block_skipped(self):
        block = Mock()
        block.type = "text"
        assert execute_tools([block], Mock()) == []

    def test_block_without_type_attr_skipped(self):
        assert execute_tools([object()], Mock()) == []

    def test_result_structure(self):
        block = _make_block("list_recent_activities", weeks=4)
        with patch("src.ai.tools._list_activities", return_value="output"):
            results = execute_tools([block], Mock())
        assert results == [{"type": "tool_result", "tool_use_id": "block_001", "content": "output"}]

    def test_routes_list_recent_activities(self):
        block = _make_block("list_recent_activities", weeks=4)
        with patch("src.ai.tools._list_activities", return_value="ok") as fn:
            execute_tools([block], Mock())
        fn.assert_called_once()

    def test_routes_get_activity_details(self):
        block = _make_block("get_activity_details", activity_id=1)
        with patch("src.ai.tools._get_activity_details", return_value="ok") as fn:
            execute_tools([block], Mock())
        fn.assert_called_once()

    def test_routes_get_activity_power_curve(self):
        block = _make_block("get_activity_power_curve", activity_id=1)
        with patch("src.ai.tools._get_activity_power_curve", return_value="ok") as fn:
            execute_tools([block], Mock())
        fn.assert_called_once()

    def test_routes_get_activity_zones(self):
        block = _make_block("get_activity_zones", activity_id=1)
        with patch("src.ai.tools._get_activity_zones", return_value="ok") as fn:
            execute_tools([block], Mock())
        fn.assert_called_once()

    def test_unknown_tool_returns_error_string(self):
        block = _make_block("no_such_tool")
        results = execute_tools([block], Mock())
        assert "Unknown tool" in results[0]["content"]

    def test_multiple_blocks_all_processed(self):
        blocks = [
            _make_block("list_recent_activities", weeks=4),
            _make_block("get_activity_details", activity_id=1),
        ]
        with patch("src.ai.tools._list_activities", return_value="a"), \
             patch("src.ai.tools._get_activity_details", return_value="b"):
            results = execute_tools(blocks, Mock())
        assert len(results) == 2


# ---------------------------------------------------------------------------
# _list_activities
# ---------------------------------------------------------------------------

class TestListActivities:
    def test_empty_returns_no_activities_message(self):
        client = Mock()
        client.list_activities.return_value = []
        assert "No activities found" in _list_activities(client, 4)
        assert "4 weeks" in _list_activities(client, 4)

    def test_weeks_clamped_to_minimum_1(self):
        client = Mock()
        client.list_activities.return_value = []
        result = _list_activities(client, 0)
        assert "1 weeks" in result

    def test_weeks_clamped_to_maximum_52(self):
        client = Mock()
        client.list_activities.return_value = []
        assert "52 weeks" in _list_activities(client, 100)

    def test_basic_activity_format(self):
        client = Mock()
        client.list_activities.return_value = [{
            "id": 123,
            "start_date_local": "2024-01-15T10:00:00Z",
            "sport_type": "Ride",
            "distance": 50000,
            "elapsed_time": 7200,
        }]
        result = _list_activities(client, 4)
        assert "ID 123" in result
        assert "2024-01-15" in result
        assert "Ride" in result
        assert "50.0 km" in result
        assert "2h00m" in result

    def test_optional_power_and_hr_included_when_present(self):
        client = Mock()
        client.list_activities.return_value = [{
            "id": 1, "start_date_local": "", "sport_type": "Ride",
            "distance": 0, "elapsed_time": 0,
            "average_watts": 245.6, "average_heartrate": 152.3,
        }]
        result = _list_activities(client, 4)
        assert "246 W avg" in result
        assert "152 bpm avg" in result

    def test_optional_power_and_hr_absent_when_missing(self):
        client = Mock()
        client.list_activities.return_value = [{
            "id": 1, "start_date_local": "", "sport_type": "Run",
            "distance": 10000, "elapsed_time": 3600,
        }]
        result = _list_activities(client, 4)
        assert "W avg" not in result
        assert "bpm avg" not in result


# ---------------------------------------------------------------------------
# _get_activity_details
# ---------------------------------------------------------------------------

class TestGetActivityDetails:
    def test_success_formats_stats(self):
        client = Mock()
        activity = MagicMock()
        client.download_activity.return_value = activity
        fake_stats = {"Avg Power": (200.5, "W"), "Avg HR": (145, "bpm")}

        with patch("src.ai.tools.StatisticsCalculator.calculate_specific_stats", return_value=fake_stats):
            result = _get_activity_details(client, 42)

        assert "Activity 42 details:" in result
        assert "Avg Power: 200.5 W" in result
        assert "Avg HR: 145 bpm" in result

    def test_skips_distance_start_and_end(self):
        client = Mock()
        activity = MagicMock()
        client.download_activity.return_value = activity
        fake_stats = {
            "Distance Start": (0.0, "km"),
            "Distance End": (50.0, "km"),
            "Avg Power": (200.0, "W"),
        }

        with patch("src.ai.tools.StatisticsCalculator.calculate_specific_stats", return_value=fake_stats):
            result = _get_activity_details(client, 42)

        assert "Distance Start" not in result
        assert "Distance End" not in result
        assert "Avg Power" in result

    def test_download_error_returns_error_message(self):
        client = Mock()
        client.download_activity.side_effect = Exception("timeout")
        result = _get_activity_details(client, 42)
        assert "Failed to download activity 42" in result
        assert "timeout" in result


# ---------------------------------------------------------------------------
# _get_activity_power_curve
# ---------------------------------------------------------------------------

class TestGetActivityPowerCurve:
    def test_success_contains_header_and_values(self):
        power = np.full(500, 250.0)
        client = Mock()
        client.download_activity.return_value = _make_activity(power=power, n=500)
        result = _get_activity_power_curve(client, 42)
        assert "Activity 42 power curve:" in result
        assert "5s:" in result
        assert "250 W" in result

    def test_no_power_data_returns_message(self):
        client = Mock()
        client.download_activity.return_value = _make_activity(power=np.array([]))
        result = _get_activity_power_curve(client, 42)
        assert "No power data available for activity 42" in result

    def test_download_error_returns_error_message(self):
        client = Mock()
        client.download_activity.side_effect = Exception("timeout")
        result = _get_activity_power_curve(client, 42)
        assert "Failed to download activity 42" in result


# ---------------------------------------------------------------------------
# _zone_breakdown
# ---------------------------------------------------------------------------

class TestZoneBreakdown:
    def test_returns_one_line_per_zone(self):
        series = np.full(60, 100.0)
        lines = _zone_breakdown(series, _SIMPLE_ZONES, 200, 1.0)
        assert len(lines) == len(_SIMPLE_ZONES)

    def test_all_samples_in_low_zone(self):
        series = np.full(60, 50.0)  # 25% of reference 200 → Low
        lines = _zone_breakdown(series, _SIMPLE_ZONES, 200, 1.0)
        assert "100.0%" in lines[0]
        assert "0.0%" in lines[1]

    def test_all_samples_in_open_ended_top_zone(self):
        series = np.full(60, 150.0)  # 75% of reference 200 → High (no upper bound)
        lines = _zone_breakdown(series, _SIMPLE_ZONES, 200, 1.0)
        assert "0.0%" in lines[0]
        assert "100.0%" in lines[1]

    def test_nan_values_excluded_from_total(self):
        series = np.array([50.0] * 30 + [np.nan] * 30)
        lines = _zone_breakdown(series, _SIMPLE_ZONES, 200, 1.0)
        # 30 valid samples all in Low → 100%, not 50%
        assert "100.0%" in lines[0]

    def test_dt_scaling(self):
        series = np.full(30, 50.0)  # 30 samples × dt=2.0 → 60 s
        lines = _zone_breakdown(series, _SIMPLE_ZONES, 200, 2.0)
        assert "1m00s" in lines[0]

    def test_sub_hour_time_format(self):
        series = np.full(90, 50.0)  # 90 s → 1m30s
        lines = _zone_breakdown(series, _SIMPLE_ZONES, 200, 1.0)
        assert "1m30s" in lines[0]

    def test_over_hour_time_format(self):
        series = np.full(3661, 50.0)  # 3661 s → 1h01m01s
        lines = _zone_breakdown(series, _SIMPLE_ZONES, 200, 1.0)
        assert "1h01m01s" in lines[0]

    def test_zero_valid_samples_all_zero_percent(self):
        series = np.full(10, np.nan)
        lines = _zone_breakdown(series, _SIMPLE_ZONES, 200, 1.0)
        for line in lines:
            assert "0.0%" in line


# ---------------------------------------------------------------------------
# _get_activity_zones
# ---------------------------------------------------------------------------

class TestGetActivityZones:
    def test_goals_unreadable_returns_error(self, tmp_path):
        with patch("src.ai.tools.GOALS_PATH", tmp_path / "missing.json"):
            result = _get_activity_zones(Mock(), 42)
        assert "Training goals not available" in result

    def test_neither_ftp_nor_max_hr_returns_error(self, tmp_path):
        goals = tmp_path / "goals.json"
        goals.write_text(json.dumps({}))
        with patch("src.ai.tools.GOALS_PATH", goals):
            result = _get_activity_zones(Mock(), 42)
        assert "Neither FTP nor max heart rate" in result

    def test_download_error_returns_error(self, tmp_path):
        goals = tmp_path / "goals.json"
        goals.write_text(json.dumps({"current_ftp_watts": 280}))
        client = Mock()
        client.download_activity.side_effect = Exception("timeout")
        with patch("src.ai.tools.GOALS_PATH", goals):
            result = _get_activity_zones(client, 42)
        assert "Failed to download activity 42" in result

    def test_only_ftp_power_zones_computed_hr_skipped(self, tmp_path):
        goals = tmp_path / "goals.json"
        goals.write_text(json.dumps({"current_ftp_watts": 280}))
        client = Mock()
        client.download_activity.return_value = _make_activity(power=np.full(100, 200.0))
        with patch("src.ai.tools.GOALS_PATH", goals):
            result = _get_activity_zones(client, 42)
        assert "Power zones (Coggan, FTP = 280 W):" in result
        assert "set max heart rate in Training Goals" in result

    def test_only_max_hr_hr_zones_computed_power_skipped(self, tmp_path):
        goals = tmp_path / "goals.json"
        goals.write_text(json.dumps({"max_hr_bpm": 185}))
        client = Mock()
        client.download_activity.return_value = _make_activity(heart_rate=np.full(100, 150.0))
        with patch("src.ai.tools.GOALS_PATH", goals):
            result = _get_activity_zones(client, 42)
        assert "set FTP in Training Goals" in result
        assert "HR zones (max HR = 185 bpm):" in result

    def test_both_set_both_sections_present(self, tmp_path):
        goals = tmp_path / "goals.json"
        goals.write_text(json.dumps({"current_ftp_watts": 280, "max_hr_bpm": 185}))
        client = Mock()
        client.download_activity.return_value = _make_activity(
            power=np.full(100, 200.0), heart_rate=np.full(100, 150.0)
        )
        with patch("src.ai.tools.GOALS_PATH", goals):
            result = _get_activity_zones(client, 42)
        assert "Power zones (Coggan, FTP = 280 W):" in result
        assert "HR zones (max HR = 185 bpm):" in result

    def test_ftp_set_but_no_power_data(self, tmp_path):
        goals = tmp_path / "goals.json"
        goals.write_text(json.dumps({"current_ftp_watts": 280}))
        client = Mock()
        client.download_activity.return_value = _make_activity(power=np.array([]))
        with patch("src.ai.tools.GOALS_PATH", goals):
            result = _get_activity_zones(client, 42)
        assert "Power zones: no power data" in result

    def test_max_hr_set_but_no_hr_data(self, tmp_path):
        goals = tmp_path / "goals.json"
        goals.write_text(json.dumps({"max_hr_bpm": 185}))
        client = Mock()
        client.download_activity.return_value = _make_activity(heart_rate=np.array([]))
        with patch("src.ai.tools.GOALS_PATH", goals):
            result = _get_activity_zones(client, 42)
        assert "HR zones: no heart rate data" in result

    def test_reference_values_visible_in_headers(self, tmp_path):
        goals = tmp_path / "goals.json"
        goals.write_text(json.dumps({"current_ftp_watts": 300, "max_hr_bpm": 190}))
        client = Mock()
        client.download_activity.return_value = _make_activity(
            power=np.full(100, 200.0), heart_rate=np.full(100, 150.0)
        )
        with patch("src.ai.tools.GOALS_PATH", goals):
            result = _get_activity_zones(client, 42)
        assert "FTP = 300 W" in result
        assert "max HR = 190 bpm" in result

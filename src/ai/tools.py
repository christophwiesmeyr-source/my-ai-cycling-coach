"""Tool schema definitions and execution for Strava data access"""
import datetime
import json

import numpy as np

from src.constants import STRAVA_HISTORY_WEEKS, GOALS_PATH
from src.analysis.statistics import rolling_max, StatisticsCalculator

TOOLS = [
    {
        "name": "list_recent_activities",
        "description": (
            "List recent Strava activities with summary metadata: date, sport type, "
            "distance, duration, average heart rate, and average power where available. "
            "Use this to get a broad overview of completed workouts before drilling into specifics."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "weeks": {
                    "type": "integer",
                    "description": "Number of weeks to look back. Defaults to 8, maximum 52.",
                    "default": STRAVA_HISTORY_WEEKS,
                }
            },
            "required": [],
        },
    },
    {
        "name": "get_activity_details",
        "description": (
            "Download detailed metrics for a specific activity: duration, distance, "
            "average and max power, best rolling power efforts (1 min, 10 min, 20 min), "
            "and average/max heart rate. Use the activity ID returned by list_recent_activities."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "activity_id": {
                    "type": "integer",
                    "description": "The Strava activity ID.",
                }
            },
            "required": ["activity_id"],
        },
    },
    {
        "name": "get_activity_power_curve",
        "description": (
            "Get the best average power for standard durations (5 s, 30 s, 1 min, 5 min, "
            "10 min, 20 min, 60 min) for a specific activity. Use this to assess peak efforts "
            "and compare them to FTP or training targets."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "activity_id": {
                    "type": "integer",
                    "description": "The Strava activity ID.",
                }
            },
            "required": ["activity_id"],
        },
    },
    {
        "name": "get_activity_zones",
        "description": (
            "Break down a specific activity by time spent in each power zone (Z1–Z6, "
            "Coggan, relative to FTP) and, if max heart rate is set in the athlete's goals, "
            "each HR zone (Z1–Z5, relative to max HR). FTP and max HR are loaded automatically "
            "from stored goals. Use this to check whether the athlete trained at the intended intensity."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "activity_id": {
                    "type": "integer",
                    "description": "The Strava activity ID.",
                },
            },
            "required": ["activity_id"],
        },
    },
]

# Human-readable status messages shown in the UI while a tool call is in flight
TOOL_STATUS_MESSAGES = {
    "list_recent_activities": "Fetching your recent Strava activities…",
    "get_activity_details": "Loading activity details from Strava…",
    "get_activity_power_curve": "Computing power curve…",
    "get_activity_zones": "Analysing training zones…",
}

# Best-effort durations for the power curve (seconds)
_POWER_CURVE_WINDOWS = [5, 30, 60, 300, 600, 1200, 3600]
_POWER_CURVE_LABELS = {
    5: "5s", 30: "30s", 60: "1min", 300: "5min",
    600: "10min", 1200: "20min", 3600: "60min",
}

# Coggan 6-zone model: (label, lower % FTP inclusive, upper % FTP exclusive or None)
_POWER_ZONES = [
    ("Z1 Active Recovery",  0,   55),
    ("Z2 Endurance",       55,   75),
    ("Z3 Tempo",           75,   90),
    ("Z4 Threshold",       90,  105),
    ("Z5 VO2max",         105,  121),
    ("Z6 Anaerobic",      121, None),
]

# 5-zone HR model: (label, lower % max HR inclusive, upper % max HR exclusive or None)
_HR_ZONES = [
    ("Z1 Recovery",   0,   60),
    ("Z2 Endurance",  60,  70),
    ("Z3 Tempo",      70,  80),
    ("Z4 Threshold",  80,  90),
    ("Z5 VO2max",     90, None),
]


def execute_tools(content: list, strava_client) -> list:
    """Execute all tool-use blocks in an assistant response and return tool results."""
    results = []
    for block in content:
        if not hasattr(block, "type") or block.type != "tool_use":
            continue
        output = _execute_tool(block, strava_client)
        results.append({"type": "tool_result", "tool_use_id": block.id, "content": output})
    return results


def _execute_tool(block, strava_client) -> str:
    if block.name == "list_recent_activities":
        weeks = block.input.get("weeks", STRAVA_HISTORY_WEEKS)
        return _list_activities(strava_client, weeks)
    if block.name == "get_activity_details":
        return _get_activity_details(strava_client, int(block.input["activity_id"]))
    if block.name == "get_activity_power_curve":
        return _get_activity_power_curve(strava_client, int(block.input["activity_id"]))
    if block.name == "get_activity_zones":
        return _get_activity_zones(strava_client, int(block.input["activity_id"]))
    return f"Unknown tool: {block.name}"


def _list_activities(strava_client, weeks: int) -> str:
    weeks = min(max(weeks, 1), 52)
    after = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(weeks=weeks)
    activities = strava_client.list_activities(after)

    if not activities:
        return f"No activities found in the last {weeks} weeks."

    lines = [f"Found {len(activities)} activities in the last {weeks} weeks:\n"]
    for a in activities:
        date = (a.get("start_date_local") or "")[:10]
        sport = a.get("sport_type") or a.get("type") or "Unknown"
        dist_km = (a.get("distance") or 0) / 1000
        elapsed = a.get("elapsed_time") or 0
        h, rem = divmod(int(elapsed), 3600)
        m = rem // 60
        line = f"- ID {a['id']} | {date} | {sport} | {dist_km:.1f} km | {h}h{m:02d}m"
        if a.get("average_watts"):
            line += f" | {a['average_watts']:.0f} W avg"
        if a.get("average_heartrate"):
            line += f" | {a['average_heartrate']:.0f} bpm avg"
        lines.append(line)

    return "\n".join(lines)


def _get_activity_details(strava_client, activity_id: int) -> str:
    try:
        activity = strava_client.download_activity(activity_id)
    except Exception as exc:
        return f"Failed to download activity {activity_id}: {exc}"

    n = len(activity.data)
    stats = StatisticsCalculator.calculate_specific_stats(activity, 0, n)

    skip = {"Distance Start", "Distance End"}
    lines = [f"Activity {activity_id} details:"]
    for key, (value, unit) in stats.items():
        if key in skip:
            continue
        formatted = f"{value:.1f}" if isinstance(value, float) else str(value)
        lines.append(f"  {key}: {formatted} {unit}".rstrip())

    return "\n".join(lines)


def _get_activity_power_curve(strava_client, activity_id: int) -> str:
    try:
        activity = strava_client.download_activity(activity_id)
    except Exception as exc:
        return f"Failed to download activity {activity_id}: {exc}"

    power = activity.get_time_series("power")
    if power is None or len(power) == 0:
        return f"No power data available for activity {activity_id}."

    time_array = activity.get_time_array()
    dt = float(time_array[1] - time_array[0]) if len(time_array) > 1 else 1.0

    lines = [f"Activity {activity_id} power curve:"]
    for secs in _POWER_CURVE_WINDOWS:
        window_samples = max(1, int(secs / dt))
        best = rolling_max(power, window_samples)
        if best > 0:
            lines.append(f"  {_POWER_CURVE_LABELS[secs]}: {best:.0f} W")

    return "\n".join(lines)


def _zone_breakdown(series, zones, reference, dt: float) -> list:
    valid = ~np.isnan(series)
    total_sec = int(np.sum(valid) * dt)
    lines = []
    for name, lo_pct, hi_pct in zones:
        lo = reference * lo_pct / 100
        if hi_pct is None:
            in_zone = valid & (series >= lo)
        else:
            hi = reference * hi_pct / 100
            in_zone = valid & (series >= lo) & (series < hi)
        secs = int(np.sum(in_zone) * dt)
        pct = 100 * secs / total_sec if total_sec > 0 else 0
        h, rem = divmod(secs, 3600)
        m, s = divmod(rem, 60)
        time_str = f"{h}h{m:02d}m{s:02d}s" if h > 0 else f"{m}m{s:02d}s"
        lines.append(f"  {name}: {time_str} ({pct:.1f}%)")
    return lines


def _get_activity_zones(strava_client, activity_id: int) -> str:
    try:
        goals = json.loads(GOALS_PATH.read_text())
    except Exception:
        return "Training goals not available. Set your FTP and max heart rate in Training Goals."

    ftp_watts = int(goals.get("current_ftp_watts") or 0)
    max_hr_bpm = int(goals.get("max_hr_bpm") or 0) or None

    if not ftp_watts and not max_hr_bpm:
        return "Neither FTP nor max heart rate is set in Training Goals. At least one is required."

    try:
        activity = strava_client.download_activity(activity_id)
    except Exception as exc:
        return f"Failed to download activity {activity_id}: {exc}"

    time_array = activity.get_time_array()
    dt = float(time_array[1] - time_array[0]) if len(time_array) > 1 else 1.0

    lines = [f"Activity {activity_id} zones:"]

    if ftp_watts:
        power = activity.get_time_series("power")
        if power is not None and len(power) > 0:
            lines.append(f"Power zones (Coggan, FTP = {ftp_watts} W):")
            lines += _zone_breakdown(power, _POWER_ZONES, ftp_watts, dt)
        else:
            lines.append("Power zones: no power data for this activity.")
    else:
        lines.append("Power zones: set FTP in Training Goals to see power zone breakdown.")

    if max_hr_bpm:
        hr = activity.get_time_series("heart_rate")
        if hr is not None and len(hr) > 0:
            lines.append(f"HR zones (max HR = {max_hr_bpm} bpm):")
            lines += _zone_breakdown(hr, _HR_ZONES, max_hr_bpm, dt)
        else:
            lines.append("HR zones: no heart rate data for this activity.")
    else:
        lines.append("HR zones: set max heart rate in Training Goals to see HR zone breakdown.")

    return "\n".join(lines)

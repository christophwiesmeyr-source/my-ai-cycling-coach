"""Tool schema definitions and execution for Strava data access"""
import datetime

import numpy as np

from src.constants import STRAVA_HISTORY_WEEKS

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
        "name": "get_activity_power_data",
        "description": (
            "Download detailed power and heart rate data for a specific activity. "
            "Returns average power, max power, average heart rate, max heart rate, "
            "duration, and distance. Use the activity ID returned by list_recent_activities."
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
]

# Human-readable status messages shown in the UI while a tool call is in flight
TOOL_STATUS_MESSAGES = {
    "list_recent_activities": "Fetching your recent Strava activities…",
    "get_activity_power_data": "Loading activity details from Strava…",
}


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
    if block.name == "get_activity_power_data":
        return _get_power_data(strava_client, int(block.input["activity_id"]))
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


def _get_power_data(strava_client, activity_id: int) -> str:
    try:
        activity = strava_client.download_activity(activity_id)
    except Exception as exc:
        return f"Failed to download activity {activity_id}: {exc}"

    lines = [f"Activity {activity_id} details:"]
    lines.append(f"  duration: {activity.duration_seconds / 3600:.2f} h")
    if activity.total_distance:
        lines.append(f"  distance: {activity.total_distance / 1000:.1f} km")

    power = activity.get_time_series("power")
    if power is not None and len(power) > 0:
        valid = power[~np.isnan(power)]
        if len(valid) > 0:
            lines.append(f"  avg power: {valid.mean():.0f} W")
            lines.append(f"  max power: {valid.max():.0f} W")

    hr = activity.get_time_series("heart_rate")
    if hr is not None and len(hr) > 0:
        valid = hr[~np.isnan(hr)]
        if len(valid) > 0:
            lines.append(f"  avg heart rate: {valid.mean():.0f} bpm")
            lines.append(f"  max heart rate: {valid.max():.0f} bpm")

    return "\n".join(lines)

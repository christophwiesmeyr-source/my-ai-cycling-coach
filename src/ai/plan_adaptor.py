"""Plan adaptor agent — compares original plan to Strava activities and produces an adapted plan"""
import datetime

import numpy as np

from src.constants import APP_DIR, PLAN_ORIGINAL_PATH, PLAN_ADAPTED_PATH, AI_MODEL, STRAVA_HISTORY_WEEKS
from .client import get_client
from .tools import TOOLS

_SYSTEM = (
    "You are an expert cycling coach. You will analyse a training plan against the athlete's "
    "actual completed workouts retrieved from Strava, identify gaps and achievements, and "
    "produce an adapted plan that accounts for their real progress. "
    "Use the provided tools to query Strava data before drawing conclusions."
)

_USER_PROMPT = """\
Here is the original training plan:

{original_plan}

Please:
1. Use the tools to retrieve recent Strava activities (start with the last {weeks} weeks).
2. Compare completed workouts against the planned sessions — what was done, what was skipped, \
and what the current fitness trajectory looks like.
3. Identify 3-5 key observations about adherence and progress.
4. Produce a complete adapted training plan in Markdown format that retains the original goals \
but adjusts timing, intensity, and session structure based on what was actually completed.

Begin the adapted plan with a short "Adaptation Notes" section summarising your findings before \
the full plan."""


def adapt_plan(strava_client) -> str:
    """Run the agentic loop to adapt the original plan using Strava data."""
    if not PLAN_ORIGINAL_PATH.exists():
        raise FileNotFoundError(
            "No original plan found. Generate a plan first using the Training tab."
        )

    original_plan = PLAN_ORIGINAL_PATH.read_text()
    client = get_client()
    prompt = _USER_PROMPT.format(original_plan=original_plan, weeks=STRAVA_HISTORY_WEEKS)
    messages = [{"role": "user", "content": prompt}]

    while True:
        response = client.messages.create(
            model=AI_MODEL,
            max_tokens=4096,
            system=_SYSTEM,
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            adapted = _extract_text(response.content)
            APP_DIR.mkdir(parents=True, exist_ok=True)
            PLAN_ADAPTED_PATH.write_text(adapted)
            return adapted

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            results = _execute_tools(response.content, strava_client)
            messages.append({"role": "user", "content": results})
            continue

        # Unexpected stop reason — return whatever text we have
        return _extract_text(response.content)


def _extract_text(content: list) -> str:
    return "\n".join(block.text for block in content if hasattr(block, "text"))


def _execute_tools(content: list, strava_client) -> list:
    results = []
    for block in content:
        if block.type != "tool_use":
            continue
        if block.name == "list_recent_activities":
            weeks = block.input.get("weeks", STRAVA_HISTORY_WEEKS)
            output = _list_activities(strava_client, weeks)
        elif block.name == "get_activity_power_data":
            output = _get_power_data(strava_client, int(block.input["activity_id"]))
        else:
            output = f"Unknown tool: {block.name}"
        results.append({"type": "tool_result", "tool_use_id": block.id, "content": output})
    return results


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

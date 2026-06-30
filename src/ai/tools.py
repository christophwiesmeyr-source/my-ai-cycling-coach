"""Tool schema definitions and execution for Strava data access"""
import datetime
import json

import numpy as np

from src.constants import STRAVA_HISTORY_WEEKS, GOALS_PATH
from src.analysis.statistics import rolling_max
from src.analysis.activity_metrics import (
    elevation_changes,
    moving_mask,
    normalized_power,
    pedaling_mask,
    representative_dt,
    sample_weights,
    time_summary,
    total_work_kj,
    weighted_average,
)
from interval_detection import detect_intervals

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
        "name": "get_activity_training_load",
        "description": (
            "Compute training-load and work metrics for a specific activity: Normalized "
            "Power, Intensity Factor, Training Stress Score (TSS), Variability Index, total "
            "work (kJ), a rough calorie estimate, Efficiency Factor (NP per heartbeat), and "
            "power-to-weight (W/kg). FTP, max HR, and weight are loaded automatically from "
            "stored goals; metrics needing a missing value are reported as unavailable. Use "
            "this to quantify how hard and how taxing a session was."
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
        "name": "get_activity_efficiency",
        "description": (
            "Assess pacing and aerobic durability for a specific activity: aerobic "
            "decoupling (Pw:Hr drift between the first and second half of moving time) and "
            "first-half vs second-half power and speed splits. Use this to judge whether the "
            "athlete faded, paced evenly, or negative-split the effort."
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
        "name": "get_activity_intervals",
        "description": (
            "Detect the structured work intervals (reps) in an activity and report how each "
            "was executed: time range, duration, average power and %FTP, Normalized Power, "
            "average/max heart rate with start→end drift, and cadence. Use this to check "
            "whether prescribed intervals were completed and how they were paced — controlled "
            "and even, fading, or near-maximal. FTP and max HR are loaded from stored goals; "
            "needs power data. Only structured efforts ≥1 min are reported (not surges/climbs)."
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
    "get_activity_training_load": "Computing training load…",
    "get_activity_efficiency": "Analysing pacing and efficiency…",
    "get_activity_intervals": "Detecting work intervals…",
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
    if block.name == "get_activity_training_load":
        return _get_activity_training_load(strava_client, int(block.input["activity_id"]))
    if block.name == "get_activity_efficiency":
        return _get_activity_efficiency(strava_client, int(block.input["activity_id"]))
    if block.name == "get_activity_intervals":
        return _get_activity_intervals(strava_client, int(block.input["activity_id"]))
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


def _fmt_duration(seconds: float) -> str:
    """Format a duration as H?h MM m SS s, dropping the hour part when zero."""
    secs = int(round(seconds))
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h{m:02d}m{s:02d}s" if h > 0 else f"{m}m{s:02d}s"


def _load_goals() -> dict:
    """Load stored training goals (FTP, max HR, weight). Empty dict on failure."""
    try:
        return json.loads(GOALS_PATH.read_text())
    except Exception:
        return {}


def _get_activity_details(strava_client, activity_id: int) -> str:
    try:
        activity = strava_client.download_activity(activity_id)
    except Exception as exc:
        return f"Failed to download activity {activity_id}: {exc}"

    time_array = activity.get_time_array()
    mask = moving_mask(activity)
    times = time_summary(activity)

    lines = [f"Activity {activity_id} details:"]
    lines.append(f"Sport: {activity.sport}")

    distance = activity.get_time_series("distance")
    if distance is not None and len(distance) > 0:
        lines.append(f"Distance: {float(distance[-1]) / 1000:.1f} km")

    # Time accounting
    lines.append("Time:")
    lines.append(f"  Elapsed: {_fmt_duration(times['elapsed_s'])}")
    if "moving_s" in times:
        stops = times.get("stops")
        stop_note = f" ({stops} stop{'s' if stops != 1 else ''})" if stops else ""
        lines.append(f"  Moving: {_fmt_duration(times['moving_s'])}")
        lines.append(f"  Stopped: {_fmt_duration(times['stopped_s'])}{stop_note}")
    else:
        lines.append("  Moving: unavailable (no moving stream from Strava)")

    # Elevation
    ascent, descent = elevation_changes(activity.get_time_series("altitude"), time_array)
    if ascent or descent:
        lines.append("Elevation:")
        lines.append(f"  Ascent: {ascent:.0f} m")
        lines.append(f"  Descent: {descent:.0f} m")

    # Averages: moving vs full where a moving mask is available
    dual = mask is not None
    header = "Averages (moving | full):" if dual else "Averages:"
    avg_lines = []

    def _avg_line(label, series, unit, scale=1.0, fmt="{:.0f}"):
        full = weighted_average(series, time_array)
        if full is None:
            return
        if dual:
            mv = weighted_average(series, time_array, mask)
            mv_str = fmt.format(mv * scale) if mv is not None else "—"
            avg_lines.append(f"  {label}: {mv_str} | {fmt.format(full * scale)} {unit}".rstrip())
        else:
            avg_lines.append(f"  {label}: {fmt.format(full * scale)} {unit}".rstrip())

    _avg_line("Power", activity.get_time_series("power"), "W")
    _avg_line("Heart rate", activity.get_time_series("heart_rate"), "bpm")
    _avg_line("Speed", activity.get_time_series("speed"), "km/h", scale=3.6, fmt="{:.1f}")
    _avg_line("Cadence", activity.get_time_series("cadence"), "rpm")

    if avg_lines:
        lines.append(header)
        lines += avg_lines

    # Pedalling: power while actually driving the pedals (excludes coasting),
    # plus the coasting share — far more telling than average power on hilly rides.
    power = activity.get_time_series("power")
    pedaling = pedaling_mask(activity)
    if pedaling is not None:
        active = mask if mask is not None else np.ones(len(time_array), dtype=bool)
        n = min(len(pedaling), len(active))
        ped_active = pedaling[:n] & active[:n]
        ped_lines = []

        ped_power = weighted_average(power, time_array, ped_active)
        if ped_power is not None:
            ped_lines.append(f"  Power (pedalling): {ped_power:.0f} W")

        w = sample_weights(time_array)[:n]
        active_total = float(np.sum(w * active[:n]))
        if active_total > 0:
            coasting = float(np.sum(w * (active[:n] & ~pedaling[:n])))
            of = "moving time" if mask is not None else "activity"
            ped_lines.append(f"  Coasting: {100 * coasting / active_total:.0f}% of {of}")

        if ped_lines:
            lines.append("Pedalling:")
            lines += ped_lines

    # Peaks
    hr = activity.get_time_series("heart_rate")
    hr = activity.get_time_series("heart_rate")
    peaks = []
    if power is not None and len(power) > 0 and not np.all(np.isnan(power)):
        peaks.append(f"  Max power: {np.nanmax(power):.0f} W")
    if hr is not None and len(hr) > 0 and not np.all(np.isnan(hr)):
        peaks.append(f"  Max HR: {np.nanmax(hr):.0f} bpm")
    if peaks:
        lines.append("Peaks:")
        lines += peaks

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
    dt = representative_dt(time_array)

    lines = [f"Activity {activity_id} power curve:"]
    for secs in _POWER_CURVE_WINDOWS:
        window_samples = max(1, int(secs / dt))
        best = rolling_max(power, window_samples)
        if best > 0:
            lines.append(f"  {_POWER_CURVE_LABELS[secs]}: {best:.0f} W")

    return "\n".join(lines)


def _get_activity_training_load(strava_client, activity_id: int) -> str:
    try:
        activity = strava_client.download_activity(activity_id)
    except Exception as exc:
        return f"Failed to download activity {activity_id}: {exc}"

    power = activity.get_time_series("power")
    if power is None or len(power) == 0:
        return f"No power data available for activity {activity_id}; training load needs power."

    time_array = activity.get_time_array()
    mask = moving_mask(activity)
    times = time_summary(activity)
    goals = _load_goals()
    ftp = int(goals.get("current_ftp_watts") or 0)
    weight = float(goals.get("weight_kg") or 0)

    np_watts = normalized_power(power, time_array)
    avg_power = weighted_average(power, time_array, mask)
    work_kj = total_work_kj(power, time_array)

    lines = [f"Activity {activity_id} training load:"]

    if np_watts is not None:
        lines.append(f"  Normalized Power: {np_watts:.0f} W")
    if np_watts is not None and avg_power and avg_power > 0:
        lines.append(f"  Variability Index: {np_watts / avg_power:.2f}")

    if np_watts is not None and ftp:
        intensity = np_watts / ftp
        lines.append(f"  Intensity Factor: {intensity:.2f} (FTP {ftp} W)")
        duration_s = times.get("moving_s", times["elapsed_s"])
        tss = duration_s * np_watts * intensity / (ftp * 3600) * 100
        lines.append(f"  TSS: {tss:.0f}")
    else:
        lines.append("  Intensity Factor / TSS: set FTP in Training Goals.")

    if work_kj is not None:
        lines.append(f"  Work: {work_kj:.0f} kJ")
        # For cycling, kJ ≈ kcal (the ~24% human efficiency and the J→cal
        # factor roughly cancel), so the work figure doubles as a rough estimate.
        lines.append(f"  Calories: ~{work_kj:.0f} kcal (rough estimate)")

    avg_hr = weighted_average(activity.get_time_series("heart_rate"), time_array, mask)
    if np_watts is not None and avg_hr and avg_hr > 0:
        lines.append(f"  Efficiency Factor: {np_watts / avg_hr:.2f} W/beat")

    if avg_power is not None and weight:
        lines.append(f"  Avg power-to-weight: {avg_power / weight:.2f} W/kg (weight {weight:.0f} kg)")
    elif avg_power is not None:
        lines.append("  Power-to-weight: set weight in Training Goals.")

    return "\n".join(lines)


def _moving_halves(time_array, mask):
    """Boolean masks splitting the moving (or, absent a mask, full) duration in half."""
    w = sample_weights(time_array)
    n = len(w)
    active = np.asarray(mask, dtype=bool)[:n] if mask is not None else np.ones(n, dtype=bool)
    aw = w * active
    total = float(np.sum(aw))
    if total <= 0:
        return None, None
    cum = np.cumsum(aw)
    half = total / 2
    return active & (cum <= half), active & (cum > half)


def _get_activity_efficiency(strava_client, activity_id: int) -> str:
    try:
        activity = strava_client.download_activity(activity_id)
    except Exception as exc:
        return f"Failed to download activity {activity_id}: {exc}"

    time_array = activity.get_time_array()
    mask = moving_mask(activity)
    h1, h2 = _moving_halves(time_array, mask)
    if h1 is None:
        return f"Activity {activity_id}: not enough data to split into halves."

    power = activity.get_time_series("power")
    hr = activity.get_time_series("heart_rate")
    speed = activity.get_time_series("speed")

    lines = [f"Activity {activity_id} efficiency:"]

    # Aerobic decoupling (Pw:Hr drift)
    if power is not None and len(power) > 0 and hr is not None and len(hr) > 0:
        p1 = weighted_average(power, time_array, h1)
        p2 = weighted_average(power, time_array, h2)
        hr1 = weighted_average(hr, time_array, h1)
        hr2 = weighted_average(hr, time_array, h2)
        if all(v is not None and v > 0 for v in (p1, p2, hr1, hr2)):
            r1, r2 = p1 / hr1, p2 / hr2
            drift = (r1 - r2) / r1 * 100
            lines.append(
                f"  Aerobic decoupling (Pw:Hr): {drift:+.1f}% "
                f"(first half {r1:.2f} → second half {r2:.2f} W/bpm)"
            )
    else:
        lines.append("  Aerobic decoupling: needs both power and heart rate.")

    # First/second-half splits
    split_lines = []
    p1 = weighted_average(power, time_array, h1)
    p2 = weighted_average(power, time_array, h2)
    if p1 is not None and p2 is not None:
        split_lines.append(f"    Power: {p1:.0f} W | {p2:.0f} W")
    s1 = weighted_average(speed, time_array, h1)
    s2 = weighted_average(speed, time_array, h2)
    if s1 is not None and s2 is not None:
        split_lines.append(f"    Speed: {s1 * 3.6:.1f} km/h | {s2 * 3.6:.1f} km/h")
    if split_lines:
        lines.append("  Splits (first half | second half):")
        lines += split_lines

    return "\n".join(lines)


def _get_activity_intervals(strava_client, activity_id: int) -> str:
    try:
        activity = strava_client.download_activity(activity_id)
    except Exception as exc:
        return f"Failed to download activity {activity_id}: {exc}"

    power = activity.get_time_series("power")
    if power is None or len(power) == 0:
        return f"No power data for activity {activity_id}; interval detection needs power."

    time_array = activity.get_time_array()
    n = min(len(time_array), len(power))
    time_array = np.asarray(time_array, dtype=float)[:n]
    power = np.asarray(power, dtype=float)[:n]

    goals = _load_goals()
    ftp = int(goals.get("current_ftp_watts") or 0) or None

    intervals = detect_intervals(time_array, power, ftp=ftp)
    if not intervals:
        return f"No structured work intervals (≥1 min) detected in activity {activity_id}."

    hr = activity.get_time_series("heart_rate")
    hr = np.asarray(hr, dtype=float)[:n] if hr is not None and len(hr) > 0 else None
    cadence = activity.get_time_series("cadence")
    cadence = np.asarray(cadence, dtype=float)[:n] if cadence is not None and len(cadence) > 0 else None

    header = f"Activity {activity_id}: {len(intervals)} structured work interval(s) detected"
    header += f" (FTP {ftp} W):" if ftp else " (no FTP set — %FTP omitted):"
    lines = [header]

    for i, iv in enumerate(intervals, 1):
        s_idx = int(np.searchsorted(time_array, iv.start_s, side="left"))
        e_idx = max(s_idx + 1, int(np.searchsorted(time_array, iv.end_s, side="right")))
        t_slice = time_array[s_idx:e_idx]
        p_slice = power[s_idx:e_idx]

        parts = [f"Interval {i}: {_fmt_duration(iv.start_s)}–{_fmt_duration(iv.end_s)} "
                 f"({_fmt_duration(iv.duration_s)})"]

        avg_p = weighted_average(p_slice, t_slice)
        if avg_p is not None:
            seg = f"{avg_p:.0f} W avg"
            if ftp:
                seg += f" ({100 * avg_p / ftp:.0f}% FTP)"
            parts.append(seg)
        np_p = normalized_power(p_slice, t_slice)
        if np_p is not None:
            parts.append(f"NP {np_p:.0f} W")

        if hr is not None:
            h_slice = hr[s_idx:e_idx]
            valid = h_slice[~np.isnan(h_slice)]
            if len(valid) > 0:
                third = max(1, len(valid) // 3)
                start_hr, end_hr = np.mean(valid[:third]), np.mean(valid[-third:])
                parts.append(f"HR {start_hr:.0f}→{end_hr:.0f} (avg {np.mean(valid):.0f}, "
                             f"max {np.max(valid):.0f})")

        if cadence is not None:
            avg_cad = weighted_average(cadence[s_idx:e_idx], t_slice)
            if avg_cad is not None:
                parts.append(f"{avg_cad:.0f} rpm")

        lines.append("  " + " | ".join(parts))

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
    dt = representative_dt(time_array)

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

---
title: Add temperature readings to coach tooling
status: ready   # see tasks/WORKFLOW.md for the lifecycle
release: v4     # see tasks/WORKFLOW.md; can be set before status: ready
---

## Problem / Context

Currently the coach does not have access to the temperature readings of the head unit. This would be meaningful information to explain decoupling and other factors.

intervals.icu's activity streams endpoint supports a `temp` stream type (mirroring Strava's stream taxonomy), populated from the FIT file's per-record temperature field when the recording device provides one. The app's `IntervalsClient` (`src/data/intervals_api.py`) currently does not request it — `STREAM_TYPES` only lists `time,watts,heartrate,cadence,distance,altitude,velocity_smooth`, and no `temp` -> column mapping exists.

## Acceptance Criteria

- [ ] intervals.icu's `temp` stream is fetched and mapped to a `temperature` column on `Activity.data`.
- [ ] Temperature is selectable in the existing primary/secondary metric plot dropdowns (main window), the same way heart rate/cadence/etc. are today — no dedicated UI code needed since dropdowns and plotting already derive from `Activity.available_metrics`.
- [ ] The AI coach's `get_activity_details` tool reports average temperature (moving | full, matching the existing dual-average pattern used for power/HR/speed/cadence) when temperature data is present for the activity.
- [ ] Activities without a temperature stream (e.g. indoor trainer rides, or outdoor rides recorded on a device/sensor without a thermometer) continue to work unchanged: no temperature column, no temperature line in AI output, no errors.
- [ ] The `temp` -> `temperature` field-name mapping has been verified against a real intervals.icu API response for an activity known to have recorded temperature, per the note in `intervals_api.py`'s module docstring that stream field names were never independently confirmed live.
- [ ] A standalone CLI script exists that downloads one real activity by id via `IntervalsClient` and dumps (a) the raw stream summary (`available_metrics` plus per-metric count/min/max/mean) and (b) the output of every read-only AI coach tool (`get_activity_details`, `get_activity_power_curve`, `get_activity_training_load`, `get_activity_efficiency`, `get_activity_intervals`, `get_activity_zones`) for that activity — used to do the field-mapping verification above, and kept as a reusable dev tool for verifying future data/tool changes against a live activity.

## Technical Decisions

- Add `"temp"` to `IntervalsClient.STREAM_TYPES` (`src/data/intervals_api.py:41`).
- Add `"temp": "temperature"` to the `field_mapping` dict in `_build_activity` (`src/data/intervals_api.py:153-160`).
- No `Activity` dataclass changes needed: `temperature` becomes a plain DataFrame column, and is automatically picked up by `available_metrics` (`src/data/activity.py:77-81`) and the metric dropdowns in `main_window.py`, which already populate from `available_metrics`.
- Units: assume Celsius (intervals.icu/FIT convention, consistent with the app's other metric units e.g. altitude in meters). Confirm against the live verification call in Acceptance Criteria; adjust the label if the API returns something else.
- Extend `_get_activity_details` (`src/ai/tools.py:296`) with an `_avg_line("Temperature", activity.get_time_series("temperature"), "°C")` call alongside the existing Power/Heart rate/Speed/Cadence lines (`src/ai/tools.py:357-362`). `_avg_line` already no-ops when a series is absent, so no extra guarding is needed for activities without temperature data.
- `get_activity_efficiency`/decoupling tool output (`src/ai/tools.py:511`) is explicitly not touched by this story — see Out of Scope.
- No FIT-file-direct ingestion path exists in this app; intervals.icu is the sole activity data source (per `intervals_api.py`'s module docstring), so no other ingestion code needs updating.
- New verification script: `src/data/inspect_activity.py`, `python -m src.data.inspect_activity <activity_id>` — follows the existing `export_for_bench.py` precedent (standalone script, `IntervalsClient()` default-constructed, `if __name__ == "__main__"` entry point). It downloads the activity once, prints `activity.available_metrics` with basic stats per column (via `activity.data.describe()` or equivalent), then constructs a `ToolUseBlock` for each read-only tool in `src/ai/tools.py` and prints `_execute_tool`'s output for each — exercising the exact dispatch path the AI coach uses in production, not a reimplementation of it. Read-only only (no write/mutating tools exist today, but exclude any if added later). Requires a configured `intervals.icu` API key/athlete id (same config as the rest of the app) and live network access, so it stays a manual dev tool — not wired into `pytest`.

## Test Plan

- Manual: run `python -m src.data.inspect_activity <id>` against a real activity known to have temperature data; confirm `temperature` shows up in the stream summary with plausible values, and use its output to confirm/correct the `temp` field-name assumption in Technical Decisions.
- Manual: from that same script run, confirm `get_activity_details`'s output includes a plausible Temperature line.
- Manual: run the script against an activity with no temperature data (e.g. an indoor trainer ride); confirm it completes without error and shows no `temperature` metric / no Temperature line.
- Manual: sync an outdoor ride known to have temperature data via the Training tab; confirm "temperature" appears in the primary/secondary metric dropdowns and plots with plausible values.
- Automated: unit test in `tests/test_intervals_api.py` covering `_build_activity` mapping a fake `temp` stream to a `temperature` column, and confirming its absence is handled when no `temp` stream is returned.
- Automated: unit test in `tests/test_ai_tools.py` covering `_get_activity_details` including a Temperature line when the series is present, and omitting it when absent.

## Out of Scope

- Feeding temperature into `get_activity_efficiency`/aerobic decoupling analysis (e.g. correlating a first-half vs second-half temperature split with Pw:Hr drift). The coach can still reason about temperature and decoupling together itself, using separate tool calls, if asked.
- Unit conversion / user-configurable °C vs °F display.
- Any FIT-file-direct temperature ingestion path (not applicable — see Technical Decisions).

## Implementation Notes

<!-- Filled in during/after implementation, not during drafting. What was
     actually built, especially where it deviates from Technical
     Decisions and why, plus any concrete results worth recording. -->

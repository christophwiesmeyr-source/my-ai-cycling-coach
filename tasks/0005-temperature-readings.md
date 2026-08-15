---
title: Add temperature readings to coach tooling
status: done   # see tasks/WORKFLOW.md for the lifecycle
release: v4     # see tasks/WORKFLOW.md; can be set before status: ready
---

## Problem / Context

Currently the coach does not have access to the temperature readings of the head unit. This would be meaningful information to explain decoupling and other factors.

intervals.icu's activity streams endpoint supports a `temp` stream type (mirroring Strava's stream taxonomy), populated from the FIT file's per-record temperature field when the recording device provides one. The app's `IntervalsClient` (`src/data/intervals_api.py`) currently does not request it — `STREAM_TYPES` only lists `time,watts,heartrate,cadence,distance,altitude,velocity_smooth`, and no `temp` -> column mapping exists.

## Acceptance Criteria

- [x] intervals.icu's `temp` stream is fetched and mapped to a `temperature` column on `Activity.data`.
- [x] Temperature is selectable in the existing primary/secondary metric plot dropdowns (main window), the same way heart rate/cadence/etc. are today — no dedicated UI code needed since dropdowns and plotting already derive from `Activity.available_metrics`.
- [x] The AI coach's `get_activity_details` tool reports average temperature (moving | full, matching the existing dual-average pattern used for power/HR/speed/cadence) when temperature data is present for the activity.
- [x] Activities without a temperature stream (e.g. indoor trainer rides, or outdoor rides recorded on a device/sensor without a thermometer) continue to work unchanged: no temperature column, no temperature line in AI output, no errors.
- [x] The `temp` -> `temperature` field-name mapping has been verified against a real intervals.icu API response for an activity known to have recorded temperature, per the note in `intervals_api.py`'s module docstring that stream field names were never independently confirmed live.
- [x] A standalone CLI script exists that downloads one real activity by id via `IntervalsClient` and dumps (a) the raw stream summary (`available_metrics` plus per-metric count/min/max/mean) and (b) the output of every read-only AI coach tool (`get_activity_details`, `get_activity_power_curve`, `get_activity_training_load`, `get_activity_efficiency`, `get_activity_intervals`, `get_activity_zones`) for that activity — used to do the field-mapping verification above, and kept as a reusable dev tool for verifying future data/tool changes against a live activity.

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

Implemented exactly as drafted in Technical Decisions, no deviations:

- `src/data/intervals_api.py`: added `"temp"` to `STREAM_TYPES` and
  `"temp": "temperature"` to `field_mapping` in `_build_activity`. Module
  docstring's "not independently verified" list updated to include `temp`
  (superseded below — it *has* now been verified live) and points to the
  new `inspect_activity.py` script for future verification needs.
- `src/ai/tools.py`: added
  `_avg_line("Temperature", activity.get_time_series("temperature"), "°C")`
  in `_get_activity_details`, immediately after the Cadence line. No other
  tool touched (efficiency/decoupling intentionally out of scope).
- New `src/data/inspect_activity.py`: `python -m src.data.inspect_activity
  <activity_id>`, following the `export_for_bench.py` precedent exactly —
  standalone script, default-constructed `IntervalsClient()`, typed defs
  throughout, `print()` for output (CLAUDE.md's standalone-script
  exception). Prints `activity.available_metrics` plus
  `activity.data[metrics].describe()` (count/mean/std/min/25/50/75/max —
  a superset of the required count/min/max/mean), then builds one
  `ToolUseBlock` per read-only tool and prints `_execute_tool`'s output for
  each, exercising the real production dispatch path. Not wired into
  pytest (needs live credentials/network).
- Tests: `tests/test_intervals_api.py` — added a `temp` stream to the
  shared `_streams()` fixture (asserted in
  `test_builds_activity_with_all_streams`) plus a new
  `test_no_temp_stream_leaves_temperature_column_absent`.
  `tests/test_ai_tools.py` — added a `temperature` parameter to the
  `_real_activity` test helper and two new tests in
  `TestGetActivityDetails` (`test_temperature_line_present_when_series_available`,
  `test_temperature_line_absent_when_series_missing`).

**Live verification** (this environment had a working intervals.icu API
key and network access, so the manual/live Test Plan items were actually
run, not just read through):

- `python -m src.data.inspect_activity i175720350` (a real outdoor "Ride",
  2026-08-14) confirmed the `temp` stream is real and non-empty:
  `temperature` appeared in `available_metrics` with plausible values
  (24–31°C, mean 27°C — a hot summer ride), and `get_activity_details`
  printed `Temperature: 27 °C` in the Averages section. This confirms both
  the `temp` field name and the Celsius unit assumption — no label change
  needed.
- Note: live-downloaded activities never populate a `moving` column
  (intervals.icu doesn't expose one — see the existing comment in
  `_build_activity`), so `get_activity_details`'s Averages header is always
  singular ("Averages:"), not the dual "(moving | full)" form, for real
  data. This is pre-existing behavior of the dual-average pattern itself,
  not something this story changed — Temperature follows the exact same
  mechanism as Power/HR/Speed/Cadence and would show the dual form too if
  the data source ever provided a moving stream.
- `python -m src.data.inspect_activity i161860195` (a real outdoor "Ride"
  from a device/sensor without a thermometer — no `temp` stream) completed
  with exit code 0, no errors: `temperature` absent from
  `available_metrics`, no `Temperature` line in `get_activity_details`
  output, and every other tool call still worked normally. Also spot
  checked a `VirtualRide` (indoor trainer, `i161860693`) and found it
  *did* have a `temp` stream (13–20°C, plausibly a room/garage sensor) —
  worth noting that "indoor trainer" and "no temperature data" aren't
  reliably the same thing in real data, though several other real outdoor
  rides (`i161860186`, `i161860213`, `i161860246`, `i161860250`,
  `i161860253`, `i161860424`, `i161860444`) also lacked a `temp` stream and
  confirm the no-data path works regardless of sport type.
- The primary/secondary metric dropdown Test Plan item (syncing via the
  Training tab and visually confirming "temperature" appears and plots)
  was **NOT independently verified live** — this is a background/headless
  execution environment with no display to run the Qt GUI. What was
  confirmed instead: `main_window.py`'s `_update_metric_dropdowns` reads
  directly from `activity.available_metrics` with no filtering, and the
  live download of `i175720350` above produced
  `available_metrics == ['distance', 'altitude', 'heart_rate', 'cadence',
  'power', 'speed', 'temperature']` — i.e. the exact data the dropdown
  would populate from does include `temperature` for a real synced
  activity. The GUI-level visual check is left for the user to confirm.

All of `pytest` (268 tests, all passing), `ruff check .`, `ruff format .`,
and `mypy ./` (53 source files, no issues) pass with no failures.

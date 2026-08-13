---
title: Add elevation metrics to tooling
status: ready   # see tasks/WORKFLOW.md for the lifecycle
release: v4       # see tasks/WORKFLOW.md; can be set before status: ready
---

## Problem / Context

Currently the coach lacks the following information:
* elevation gain
* grade
* climbing time

Investigation found that elevation gain is already implemented: the
`altitude` stream is fetched from intervals.icu (`IntervalsClient.STREAM_TYPES`,
`src/data/intervals_api.py:41`) and mapped to an `altitude` column on
`Activity.data`. `elevation_changes()` (`src/analysis/activity_metrics.py:126`)
computes smoothed ascent/descent, and `_get_activity_details`
(`src/ai/tools.py:325-331`) already reports "Ascent"/"Descent" to the AI
coach but the tool description is lacking this information. No UI or further work is needed there.

Grade (%) and climbing time are genuinely unimplemented — a repo-wide
search turns up nothing. This story adds those two.

Depends on [0005-temperature-readings.md](0005-temperature-readings.md)'s
`src/data/inspect_activity.py` verification script (`python -m
src.data.inspect_activity <activity_id>`, dumps stream stats + every
read-only AI tool's output for one real activity) landing first — this
story's manual verification reuses it rather than re-deriving the same
ad hoc checks. If 0005 hasn't been implemented yet when 0004 starts,
implement 0005 first (or bring just that script forward) rather than
duplicating a one-off verification script here.

## Acceptance Criteria

- [ ] A per-sample `grade` column (instantaneous % slope, smoothed) is
      added to `Activity.data` whenever both `altitude` and `distance`
      streams are present, so it is automatically selectable in the main
      window's primary/secondary metric plot dropdowns — no dedicated UI
      code needed, matching how `altitude` already appears there today.
- [ ] `get_activity_details` reports, inside the existing `Elevation:`
      block (alongside Ascent/Descent), the activity's max grade, average
      grade while climbing, total climbing time, and ascent per km — a
      hilliness indicator that (unlike a global/net average grade) stays
      meaningful for loop rides, where ascents and descents cancel out to
      near-zero regardless of how hilly the route actually was.
- [ ] "Climbing" is defined as: moving time where the smoothed grade
      exceeds a fixed threshold (3%). This is a single aggregate number,
      not per-climb segments (start/end of individual climbs is out of
      scope — see below).
- [ ] Activities missing `altitude` and/or `distance` data (e.g. indoor
      trainer rides without GPS) continue to work unchanged: no `grade`
      column, no grade/climbing lines in AI output, no errors.
- [ ] Periods where the rider is stationary (near-zero horizontal distance
      over the smoothing window) do not produce spurious extreme grade
      values — grade is `NaN` there rather than a divide-by-near-zero
      spike, matching how `elevation_changes` already avoids GPS/barometric
      jitter artifacts.
- [ ] `get_activity_details`'s tool description (`src/ai/tools.py:49-53`)
      is rewritten to accurately list everything the tool currently
      returns, not just the new grade/climbing-time fields. It's
      currently both stale and wrong: it claims "best rolling power
      efforts (1 min, 10 min, 20 min)", which this tool doesn't compute
      at all (that's `get_activity_power_curve`'s job — a different
      tool), and it omits several sections the function actually emits —
      elapsed/moving/stopped time, ascent/descent, moving-vs-full
      averages for speed and cadence, pedalling power / coasting %, and
      max power / max HR ("Peaks"). This was flagged directly by the AI
      coach itself in a chat session — it under- and mis-reports its own
      capabilities to the user because the description the LLM sees
      doesn't match what the tool actually does.

## Technical Decisions

- New pure function in `src/analysis/activity_metrics.py`, matching the
  existing style of `elevation_changes`/`weighted_average` (pure
  functions over arrays + `time_array`):
  ```
  def grade_series(
      altitude: np.ndarray,
      distance: np.ndarray,
      time_array: np.ndarray,
      smooth_window_s: float = 20.0,
  ) -> np.ndarray
  ```
  Returns an array the same length as `altitude`, in % grade
  (`rise / run * 100`), `NaN` where undefined (see below). Altitude is
  smoothed the same way as in `elevation_changes` (NaN-interpolated,
  centred rolling mean, same `smooth_window_s` default) — factor the
  shared interpolate+smooth logic out of `elevation_changes` into a
  private `_smoothed_altitude(altitude, time_array, smooth_window_s)`
  helper used by both, rather than duplicating it.
- Grade is computed from `np.diff` of the smoothed altitude divided by
  `np.diff` of raw distance (distance is cumulative and comparatively
  low-noise; it is not smoothed). The result has one fewer element than
  the input; pad with a leading `NaN` (grade undefined for the first
  sample) to keep the array aligned 1:1 with `time_array`/other columns.
- Divide-by-near-zero guard: a new constant `MIN_GRADE_RUN_M = 1.0`; where
  the distance delta between consecutive smoothing-window points is below
  this, that sample's grade is `NaN` instead of computed. This is what
  keeps stationary/near-stationary periods (traffic lights, GPS distance
  jitter while stopped) from producing spurious spikes.
- New constant `CLIMBING_GRADE_THRESHOLD_PCT = 3.0` (module-level, next to
  the new function) — the grade above which a sample counts as
  "climbing." Not user-configurable in this story.
- New pure function, also in `activity_metrics.py`:
  ```
  def climbing_time_s(
      grade: np.ndarray,
      time_array: np.ndarray,
      threshold_pct: float = CLIMBING_GRADE_THRESHOLD_PCT,
  ) -> float
  ```
  Sums `sample_weights(time_array)` over samples where
  `grade > threshold_pct`. `NaN` grade samples are naturally excluded
  (comparison with `NaN` is `False`), which is also why no separate
  `moving_mask` intersection is needed: distance not advancing (stopped)
  already yields `NaN` grade via the `MIN_GRADE_RUN_M` guard above.
- **Where the `grade` column gets added** — `IntervalsClient._build_activity`
  (`src/data/intervals_api.py:129`), right after the existing
  `field_mapping` loop: if both `"altitude"` and `"distance"` ended up in
  `data`, compute `time_array` from the timestamps already assembled and
  call `grade_series`, adding the result as `data["grade"]`. This is a
  data-layer function calling into the analysis layer
  (`src.analysis.activity_metrics`) — a new dependency direction (today
  `activity_metrics.py` depends on `src.data.activity.Activity`, not the
  other way, and `intervals_api.py` depends on neither). No import cycle
  results (analysis layer doesn't import `intervals_api`), and this is
  the only way to guarantee `grade` is always present as a real
  DataFrame column without every call site that builds/consumes an
  `Activity` needing to remember to derive it separately (the UI dropdown
  and the AI tool would otherwise need two different derivation paths).
  Flagging this trade-off explicitly since it doesn't strictly match the
  `src/` structure's `data/`→`analysis/` separation described in
  CLAUDE.md.
- Wiring in `_get_activity_details` (`src/ai/tools.py`): read the
  already-computed `grade` column via
  `activity.get_time_series("grade")` (no recomputation — it was set once
  at `Activity`-build time). Inside the existing
  `if ascent or descent:` block, after the Ascent/Descent lines, append
  (only when computable, i.e. at least one non-`NaN` grade sample exists):
  ```
  Max grade: {np.nanmax(grade):.0f}%
  Avg grade (climbing): {avg:.0f}%
  Climbing time: {_fmt_duration(climbing_s)} (grade > 3%)
  ```
  where `avg` is `weighted_average(grade, time_array, mask=grade > CLIMBING_GRADE_THRESHOLD_PCT)`
  (reusing the existing helper — the mask/NaN-exclusion logic doesn't need
  reimplementing) and `climbing_s` is `climbing_time_s(grade, time_array)`.
  "Avg grade (climbing)" and "Climbing time" lines are only appended when
  `avg is not None` (i.e. at least one sample was above threshold) —
  otherwise the ride had no meaningful climbing and those two lines would
  be noise. "Max grade" is still shown whenever any valid grade sample
  exists, independent of the threshold.
- No global/net average grade line — deliberately rejected. For a loop
  ride (start elevation ≈ end elevation), ascents and descents cancel out
  to a near-zero average regardless of how hilly the route actually was,
  making it actively misleading rather than merely uninformative. For a
  point-to-point ride it's just `net elevation change / distance`, which
  the coach can already derive from the existing Ascent/Descent + Distance
  lines if it wants that number.
- Instead, add an "ascent per km" figure to the existing Ascent line —
  `Ascent: {ascent:.0f} m ({ascent / (distance_km):.0f} m/km)` — computed
  from `ascent` (already available from `elevation_changes`) and the
  activity's total distance in km (already computed at
  `src/ai/tools.py:311`, needs hoisting slightly earlier so it's in scope
  at the Elevation block, or recomputed from `distance[-1] / 1000`).
  Ascent is a magnitude (not signed), so unlike net average grade it
  doesn't suffer the loop-cancellation problem — a hilly loop still shows
  a large m/km figure. Only shown when distance is available and nonzero
  (division guard); Descent is left as-is (no per-km figure needed there
  — ascent/km is the standard "how hilly was this route" proxy riders
  and tools like Strava/RideWithGPS already use, descent/km would be
  redundant for a loop and less standard for point-to-point).
- `get_activity_details`'s tool description (`src/ai/tools.py:49-53`) is
  rewritten from scratch to match what `_get_activity_details` actually
  emits: duration/distance, time accounting (elapsed/moving/stopped),
  elevation (ascent/descent + ascent per km, max grade, avg climbing
  grade, climbing time), moving-vs-full averages (power/HR/speed/cadence),
  pedalling power and coasting %, and peaks (max power/HR). The incorrect
  "best rolling power efforts" claim is removed — that capability belongs
  to `get_activity_power_curve`'s own description, which already covers
  it and is left untouched.
- No changes to `elevation_changes`'s existing return value (still just
  `(ascent, descent)`) — only the *rendering* of the Ascent line in
  `_get_activity_details` changes (appending the m/km figure); the
  Descent line and the underlying computation are untouched.
- No changes to the `interval_detection` package — grade/climbing-time
  are computed as plain aggregate/per-sample metrics, not as detected
  segments (see Out of Scope).

## Test Plan

- Unit tests in `tests/test_activity_metrics.py`:
  - `grade_series`: a synthetic steady climb (known altitude/distance
    ratio) returns the expected constant % grade; a flat-then-climb
    profile returns ~0% on the flat section and the expected % on the
    climb; a stationary section (distance not advancing) returns `NaN`
    instead of a spike; NaN altitude is interpolated the same way
    `elevation_changes` already is (reusing `_smoothed_altitude`, so this
    can largely mirror `TestElevationChanges::test_handles_nan`).
  - `climbing_time_s`: a grade array with known above/below-threshold
    segments returns the expected total seconds; an all-`NaN` or
    all-below-threshold grade array returns `0.0`.
- Unit tests in `tests/test_intervals_api.py::TestDownloadActivity`: fake
  streams with both `altitude` and `distance` produce a `grade` column on
  the built `Activity`; fake streams missing either one produce no
  `grade` column (no error).
- Unit tests in `tests/test_ai_tools.py::TestGetActivityDetails`: an
  activity with a clear climb reports "Max grade", "Avg grade (climbing)",
  "Climbing time", and an m/km figure on the Ascent line, all with
  plausible values; an activity with altitude but no meaningful climb
  (all grade below 3%) still reports "Max grade" and the Ascent m/km
  figure but omits the climbing-specific lines; a synthetic loop
  (start/end altitude equal, real intermediate hills) confirms Ascent/km
  stays a large nonzero figure even though net elevation change is ~0 —
  the case this metric was chosen to handle correctly; an activity with
  no altitude/distance data omits the whole extension unchanged (existing
  `test_elevation_reported_when_altitude_present`-style coverage extended
  or a sibling test added).
- Manual: run `python -m src.data.inspect_activity <id>` (from 0005)
  against a real activity with known hills; use its stream-summary dump
  to confirm the new `grade` column has plausible min/max/mean values,
  and its `get_activity_details` output dump to sanity-check max grade /
  avg climbing grade / climbing time / ascent per km all in one pass,
  cross-checked against what's visible when that same activity is opened
  in the app.
- Manual: run the app, select "grade" in the primary/secondary metric
  dropdown for that same real ride; confirm the plotted values are
  plausible against the known climbs (visual cross-check against the
  `inspect_activity.py` dump from the previous step).
- Manual: from the same `inspect_activity.py` run, confirm the rewritten
  tool description matches reality — every section it now claims (time,
  elevation, averages, pedalling, peaks) actually appears in the dumped
  `get_activity_details` output, and nothing it claims is absent.

## Out of Scope

- Per-climb segmentation (individual climb start/end, distance, elevation
  gain, duration, avg grade per climb) — this story reports one
  aggregate climbing-time number for the whole activity, not detected
  climb segments. A future story could add this as a form of interval
  detection if wanted.
- A user-configurable climbing-grade threshold — `CLIMBING_GRADE_THRESHOLD_PCT`
  is a fixed constant.
- Any UI surface for climbing time/grade summary stats beyond the plot
  dropdown (e.g. a dedicated stats panel) — the main window doesn't
  currently show derived summary stats anywhere (only plots), and this
  story doesn't add that. Climbing time/max/avg grade are AI-tool-only.
- Imperial units — grade is reported in %, consistent with how the rest
  of the app already handles units (metric only, no user-facing unit
  conversion).
- Changes to `elevation_changes`'s existing ascent/descent computation or
  output — already implemented, untouched by this story.
- A global/net average grade figure — deliberately rejected as
  misleading for loop rides (see Technical Decisions); ascent per km is
  used instead.

## Implementation Notes

<!-- Filled in during/after implementation, not during drafting. What was
     actually built, especially where it deviates from Technical
     Decisions and why, plus any concrete results worth recording. -->

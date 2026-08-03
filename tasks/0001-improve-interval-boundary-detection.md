---
title: Improve interval boundary detection
status: ready
release: v3
---

## Problem / Context

I have seen the detection of intervals being slightly off (i.e. not the whole interval is covered). A few seconds are missing.

Context: Probably the 20s averaging window used for interval detection takes a longer time to raise above the threshold / drop below the threshold.

Potential solutions: Adapt the boundary of the interval through a different criterion (e.g. when the unfiltered version of the signal first crosses a threshold close to the current detection).

## Acceptance Criteria

<!-- Checklist of concrete, verifiable outcomes. -->

Baseline, current `main` on the bench (`interval_detection/bench/evaluate.py`,
24 labelled activities, 65 matched intervals): P 91.5%, R 81.2%, F1 86.1%;
end boundary early (clipped tail) in 44/65 matches (mean -5.4s), start
boundary late (clipped head) in 28/65 (mean +8.4s).

- [ ] Count of matched intervals with an early end boundary (pred end < GT
      end - `BOUNDARY_TOL_S`) is lower than the 44/65 baseline.
- [ ] Count of matched intervals with a late start boundary (pred start > GT
      start + `BOUNDARY_TOL_S`) is lower than the 28/65 baseline.
- [ ] Refinement does not overshoot past the true edge by more than 3s: for
      matched intervals, start-early (pred before GT start) and end-late
      (pred after GT end) deltas stay within 3s of zero.
- [ ] Overall precision/recall/F1 on the bench does not regress below the
      baseline (P 91.5%, R 81.2%, F1 86.1%) — no previously-correct match
      turns into a false negative/positive as a side effect of the shift.
- [ ] Mean boundary error across matched intervals (bench `Overall` ->
      `boundary error: mean`) decreases from the 19.0s baseline — a
      holistic check that the fix reduces accumulated boundary error, not
      just the directional counts above.
- [ ] Unit tests cover: a sharp step edge gets tightened close to the true
      edge; boundary refinement is bounded (does not search past the max
      shift); a boundary that's already accurate is left alone (no
      spurious shift from noise).

## Technical Decisions

<!-- Code-related decisions made during drafting, with rationale. -->

- Add a `_refine_boundaries` step in `detector.py`, run once per merged run
  (`_merge_close` output) on its outer `start`/`end` only — internal
  sub-run edges bridged by the gap-merge are not part of the output
  contract and stay untouched.
- Refinement signal: a short secondary moving average (new constant
  `REFINE_WINDOW_S = 4.0`, reusing `smoothing.moving_average` with this
  window instead of the 20s detection window) — short enough to track the
  true power step, long enough to not flip on a single noisy sample
  (pedal stroke / cadence dropout).
- Refinement threshold: the *same* intensity threshold used for detection
  (`_intensity_threshold` result) — no second threshold to tune.
- Search bound: `REFINE_MAX_SHIFT_S = smoothing.DEFAULT_WINDOW_S / 2` (10s)
  either side of the original boundary — matches the scale of the 20s
  window's smoothing lag; large enough to correct it, small enough to not
  wander into an unrelated surge or the warm-up/cooldown.
- Search method, symmetric (handles both the clipping and the overshoot
  case with one rule): within `[boundary - bound, boundary + bound]` on the
  short-smoothed signal, find the threshold crossing nearest to the
  original boundary and snap to it. If no crossing exists in that window
  (short-smoothed signal doesn't change sign relative to threshold — e.g.
  a very short bound relative to sampling), keep the original boundary.
- Order: refine immediately after `_merge_close`, before the duration-floor
  filter — the floor check's duration and median-intensity calculation use
  the *refined* start/end, since those are the more accurate boundaries.
- Both boundaries of a run are refined independently; since the search
  bound (10s) is well under `min_separation_s` (30s default) between
  distinct (non-merged) runs, refinement of one run's boundary cannot
  cross into a neighbouring run.

## Test Plan

<!-- How to verify the implementation once done: manual steps and/or
     specific automated tests to add/run. -->

- Automated: new unit tests in `interval_detection/tests/test_detector.py`
  for `_refine_boundaries` (or equivalent), covering the cases listed in
  Acceptance Criteria (step-edge tightening, bounded search, stable
  no-op on an already-accurate boundary). Full `pytest` suite still green.
- Bench: run `python interval_detection/bench/evaluate.py` before and
  after, compare the `Boundary direction` section (early-end / late-start
  counts, means) and the `Overall` P/R/F1 line against the baseline
  numbers captured above and add to Implementation Notes.
- Manual spot-check: use `interval_detection/bench/view_results.py` (or
  `label_tool.py`) on 1-2 activities that were previously clipped (e.g. a
  `sweet_spot` one, the type with the worst 31.6s mean boundary error) to
  visually confirm the detected interval now hugs the real power step.

## Out of Scope

Do not completely re-open the algorithms used for interval detection unless absolutely necessary.

## Implementation Notes

<!-- Filled in during/after implementation, not during drafting. What was
     actually built, especially where it deviates from Technical
     Decisions and why, plus any concrete results worth recording. -->

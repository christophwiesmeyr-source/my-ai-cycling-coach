---
title: Improve interval boundary detection
status: done
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

- [x] Count of matched intervals with an early end boundary (pred end < GT
      end - `BOUNDARY_TOL_S`) is lower than the 44/65 baseline. **17/69.**
- [x] Count of matched intervals with a late start boundary (pred start > GT
      start + `BOUNDARY_TOL_S`) is lower than the 28/65 baseline. **7/69.**
- [x] **Revised during implementation** (see Implementation Notes) — original
      wording: "refinement does not overshoot past the true edge by more
      than 3s". That was written for the originally-planned bounded
      -refinement design, where a small search window made large overshoot
      structurally impossible. The approach actually implemented (see
      Technical Decisions) has no such per-case bound. Revised criterion:
      overshoot is judged in aggregate, not per case — mean/median boundary
      error must clearly improve on baseline (see below), and every
      individual matched interval with unusually large error must be
      identified and listed in Implementation Notes for manual review, not
      silently accepted.
- [x] Overall precision/recall/F1 on the bench does not regress below the
      baseline (P 91.5%, R 81.2%, F1 86.1%) — no previously-correct match
      turns into a false negative/positive as a side effect of the shift.
      **P 93.2%, R 86.2%, F1 89.6%.**
- [x] Mean boundary error across matched intervals (bench `Overall` ->
      `boundary error: mean`) decreases from the 19.0s baseline — a
      holistic check that the fix reduces accumulated boundary error, not
      just the directional counts above. **11.3s (median 3.6s).**
- [x] Unit tests reflect the actual implementation (see Technical
      Decisions): the changed default constants are pinned by a test, and
      a test that derives window size from sample spacing is decoupled
      from whatever the default happens to be.

## Technical Decisions

<!-- Code-related decisions made during drafting, with rationale. -->

**As implemented** (see Implementation Notes for how this superseded the
plan below): two existing tunable constants changed, no new code path.

- `smoothing.DEFAULT_WINDOW_S`: `20.0` -> `6.0`. A shorter primary smoothing
  window tracks a real power step more closely, directly reducing boundary
  lag at the source instead of correcting it after the fact.
- `detector.DEFAULT_MIN_SEPARATION_S`: `30.0` -> `45.0`. A shorter window
  makes run *detection* (not just boundary placement) sensitive to a real
  mid-effort power dip on long, variable-power efforts — if the dip exceeds
  `min_separation_s`, `_merge_close` can't bridge it and the run fragments.
  Raising the bridge-gap tolerance compensates.
- Both constants were tuned together against the real 24-activity bench (a
  5x5 grid of window ∈ {4-8s} x separation ∈ {35-55s}) rather than picked
  analytically — `window=6s, sep=45s` was a stable local optimum, not a
  single lucky point.

**Originally planned, drafted before implementation began** (kept here for
context, not implemented):

- A secondary `_refine_boundaries` step in `detector.py`, run once per
  merged run on its outer `start`/`end` only: a short secondary moving
  average (`REFINE_WINDOW_S = 4.0`) computed alongside the primary 20s one,
  searching within `REFINE_MAX_SHIFT_S = 10s` of each boundary for the
  nearest same-threshold crossing and snapping to it, symmetric (could
  correct clipping or overshoot with one rule), applied before the
  duration-floor filter.
- Superseded because, once prototyped and bench-tested alongside the
  simpler alternative below, it was strictly dominated on every metric by
  just changing the two primary-detection constants — see Implementation
  Notes for the numbers. Not used in the shipped code, but the reasoning
  and the bench comparison are recorded here since the story was originally
  drafted around this approach.

**Alternative tried and rejected**: shrinking only `DEFAULT_WINDOW_S`
(leaving `min_separation_s` at its original 30s default) — regresses mean
boundary error despite better P/R/F1, because run fragmentation on long
outdoor `sweet_spot` efforts produces a few catastrophic (400s+) errors that
the lenient coverage-based bench matching doesn't otherwise penalize. Fixed
by raising `min_separation_s` alongside the window (the chosen approach
above). See Implementation Notes for the specific failing case.

## Test Plan

<!-- How to verify the implementation once done: manual steps and/or
     specific automated tests to add/run. -->

- Automated: `interval_detection/tests/test_smoothing.py` updated for the
  new default window (pinned-value test + a test decoupled from the
  default so it doesn't need updating again next time the default moves).
  Full `interval_detection` and root `pytest` suites still green with no
  other changes needed — `test_detects_single_sustained_block` in
  particular still passes with its existing (now conservative) slop bounds.
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

**What shipped**: two constant changes, no new code —
`smoothing.DEFAULT_WINDOW_S` 20.0 -> 6.0, `detector.DEFAULT_MIN_SEPARATION_S`
30.0 -> 45.0 — plus the module docstring, related comments, and
`bench/view_results.py`'s previously-hardcoded "20 s" plot label/docstring
updated to match (the label now reads the constant dynamically so it can't
drift again). `test_smoothing.py`'s pinned-default test and its
window-from-sample-spacing test (decoupled from the default) were updated;
no other test changes were needed.

**Why this deviates from the drafted Technical Decisions**: the story was
drafted around a secondary bounded-refinement pass. During plan-confirmation
the user asked to first check a simpler alternative (shrink the primary
window directly) against the real bench before building it. That check, and
the follow-up investigation it triggered, changed the final approach twice:

1. Shrinking `DEFAULT_WINDOW_S` alone (still 30s separation) tightens the
   common case but *regresses* mean boundary error (19.0s -> 25.7s at
   window=4s) — a short window makes run *detection* fragile to a real
   mid-effort power dip on long outdoor `sweet_spot` efforts; if the dip
   exceeds `min_separation_s`, the run silently fragments. One activity
   (`18027845542`) went from fine at baseline to a 547s error this way,
   still scored a "true positive" by the bench's lenient 50%-coverage match.
2. Raising `min_separation_s` alongside the smaller window fixes that
   fragmentation and, swept on the real bench (window ∈ {4-8s} x
   separation ∈ {35-55s}, 25 combinations), `window=6s, sep=45s` beat both
   the 20s/30s baseline and a fully-prototyped version of the originally
   -planned refinement pass on every metric:

   | | baseline (20s/30s) | drafted refine (prototype) | **shipped (6s/45s)** |
   |---|---|---|---|
   | P / R / F1 | 91.5% / 81.2% / 86.1% | 91.7% / 82.5% / 86.8% | **93.2% / 86.2% / 89.6%** |
   | mean boundary error | 19.0s | 17.8s | **11.3s** |
   | median boundary error | 5.7s | 4.0s | **3.6s** |
   | FP | 6 | 6 | **5** |

   The refinement pass was fully prototyped and bench-verified (not just
   estimated) before being set aside — it worked, but was strictly
   dominated by the simpler change while requiring three new functions.
3. This surfaced a real gap in the original Acceptance Criteria: raising
   `min_separation_s` occasionally bridges a genuinely separate preceding
   effort into the same run as the labelled interval, producing large
   one-sided boundary error on a handful of matches — something the
   drafted AC ("overshoot ≤3s") assumed couldn't happen because it was
   written for the bounded-refinement design specifically. Confirmed some
   of this already existed in the *original* baseline too (e.g.
   `18555538951` had a pre-existing -126.5s error at 20s/30s); some is
   newly introduced by the larger bridge gap (e.g. `18107328654`,
   `17793371241` — previously detected as several separate, accurate
   sub-intervals, now merged into one with a large one-sided error). Per
   the user's decision, the AC was revised to judge overshoot in aggregate
   rather than per-case, on condition that every notable individual case is
   listed here for manual review (below).

**Activities with matched-interval boundary error >= 15s, final (6s/45s)
config** — all ten are `sweet_spot` type (the longest, lowest-intensity,
most terrain/pacing-variable efforts), nine of ten outdoor:

| activity | pred | GT | Δstart | Δend | total err |
|---|---|---|---|---|---|
| 19058385210 | (4147, 4540) | (4267, 4545) | -119.8s | -5.0s | 124.8s |
| 18107328654 | (4406, 5604) | (4529, 5603) | -122.9s | +1.4s | 124.3s |
| 17878972679 | (584, 1782) | (640, 1786) | -56.5s | -3.8s | 60.3s |
| 17520183984 | (5335, 5858) | (5346, 5823) | -10.7s | +34.8s | 45.5s |
| 17793371241 | (1852, 2688) | (1895, 2690) | -43.1s | -1.8s | 44.9s |
| 17520183984 | (4630, 5151) | (4629, 5109) | +0.9s | +42.3s | 43.2s |
| 18555538951 | (3425, 4324) | (3430, 4288) | -4.9s | +36.3s | 41.2s |
| 17603018706 | (3682, 4857) | (3689, 4883) | -6.9s | -25.6s | 32.5s |
| 18424073756 | (10710, 11822) | (10709, 11845) | +1.3s | -23.2s | 24.5s |
| 18107328654 | (1158, 2291) | (1152, 2301) | +6.1s | -9.6s | 15.7s |

Visually confirmed via `bench/view_results.py --save`: `18424073756`'s
previously-worst-case interval (485s error at baseline) now hugs the GT bar
closely; `18107328654`'s second interval visibly shows the over-merge —
detection starts well before the labelled GT bar because a preceding
distinct effort within 45s gets bridged in.

**Caveat**: both the shipped constants and the rejected alternatives were
tuned against the same 24-activity bench — some risk of overfitting to this
specific dataset either way. Worth keeping in mind if boundary quality is
revisited with more labelled data later; not a blocker for this story.

**Verification**: `pytest` (root, 254 tests) and `pytest interval_detection/tests`
(64 tests) both green; `ruff check .`, `ruff format --check .`, `mypy ./`
all clean.

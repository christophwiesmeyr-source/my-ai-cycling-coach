---
title: Add HRR60 to the numbers computed for intervals
status: ready
release: v3
---

## Problem / Context

For the coach to judge the quality of intervals the Heart Rate Recovery in 60 seconds is a relevant number. Therefore it should be given to the coach when they request intervals through the corresponding tool.

Note: This requires a fairly accurate interval boundary detection (see 0001).

## Acceptance Criteria

<!-- Checklist of concrete, verifiable outcomes. -->

- [ ] `get_activity_intervals` (`src/ai/tools.py`) reports an HRR60 value per
      interval — bpm dropped between end-of-effort HR and HR 60s later —
      alongside the existing power/HR/cadence metrics.
- [ ] HRR60 uses short-window averages, not single noisy samples: end HR is
      the average over the last ~5s of the interval; the +60s HR is a short
      window centred on `end_s + 60`.
- [ ] If another detected interval starts before `end_s + 60`, HRR60 is
      omitted for that interval (window is contaminated by the next
      effort) rather than reporting a misleading number.
- [ ] If fewer than 60s of trailing data exist after the interval ends
      (recording stops too soon), HRR60 is omitted.
- [ ] If HR data is missing/insufficient (NaNs) in either the end-of-effort
      or +60s window, HRR60 is omitted — consistent with how the existing
      HR segment already no-ops when HR is unavailable.
- [ ] If the rider kept working during the recovery window (mean power over
      the full 60s exceeds the backoff threshold), HRR60 is omitted — an
      HR decay under continued load is active, not passive, recovery and
      would misrepresent fitness if reported as HRR60.
- [ ] The `get_activity_intervals` tool description (`tools.py:124-131`) is
      updated so the LLM coach knows HRR60 is reported and what it means.
- [ ] Unit tests cover: normal recovery case, contamination-by-next-interval
      case, insufficient-trailing-data case, missing/NaN HR case, and the
      didn't-back-off (power-too-high) case.

## Technical Decisions

<!-- Code-related decisions made during drafting, with rationale. -->

- New pure function in `src/analysis/activity_metrics.py`, matching the
  existing style of `weighted_average`/`normalized_power` (pure functions
  over arrays + `time_array`, returning `Optional[float]`):
  ```
  def heart_rate_recovery_60s(
      hr: np.ndarray,
      power: np.ndarray,
      time_array: np.ndarray,
      end_s: float,
      next_start_s: Optional[float] = None,
      ftp: Optional[float] = None,
      interval_avg_power: Optional[float] = None,
  ) -> Optional[float]
  ```
  Returns bpm dropped (positive = recovered) or `None` if not computable.
- Backoff guard: mean power (`weighted_average`) over the *full* `[end_s,
  end_s + 60]` window must stay below a threshold or HRR60 is `None`.
  Threshold is `RECOVERY_MAX_FTP_FRAC * ftp` (constant `0.55`, matching the
  existing Z1 Active-Recovery/Z2 boundary in `_POWER_ZONES`,
  `tools.py:189`) when FTP is known. Without FTP, fall back to
  `RECOVERY_MAX_INTERVAL_FRAC * interval_avg_power` (constant `0.5`) —
  mirrors this codebase's existing self-referential no-FTP fallback
  pattern (`interval_detection`'s `NO_FTP_MULTIPLIER`). Caller passes the
  interval's own already-computed `avg_p` as `interval_avg_power`.
  Checked before the HR windows are computed (cheap short-circuit).
- End-of-effort HR: `weighted_average` of `hr` over `[end_s - 5, end_s]`
  (trailing window, still within/at the effort — matches "how hard was HR
  when the rep stopped").
- +60s HR: `weighted_average` of `hr` over `[end_s + 60 - 2.5, end_s + 60 +
  2.5]` (centred window — by this point HR is just recovering, no reason
  to bias trailing/leading).
- Reuse `weighted_average`'s existing NaN handling; if either window's
  `weighted_average` returns `None` (no valid samples), HRR60 is `None`.
- Contamination guard: caller passes `next_start_s` (the start of the
  *next* detected interval, if any); if `next_start_s < end_s + 60`,
  return `None` before computing anything — the recovery window would
  otherwise include the next effort's power/HR rise.
- Insufficient trailing data: if `time_array[-1] < end_s + 60`, return
  `None` — a truncated window isn't a standard HRR60 reading.
- Wiring in `_get_activity_intervals`: pass `intervals[i + 1].start_s if i +
  1 < len(intervals) else None` as `next_start_s`, and the interval's own
  `avg_p` as `interval_avg_power`, for interval `i`. Append `f"HRR60
  {hrr:.0f} bpm"` to `parts` only when not `None`, following the existing
  pattern (`if avg_p is not None: parts.append(...)`) — no explicit "n/a"
  text, consistent with how other metrics already conditionally omit.
- No changes to the `interval_detection` package or the `Interval`
  contract — this story only consumes already-detected intervals.

## Test Plan

<!-- How to verify the implementation once done: manual steps and/or
     specific automated tests to add/run. -->

- Unit tests in `tests/test_activity_metrics.py` for
  `heart_rate_recovery_60s` directly: clear recovery (HR drops after
  `end_s`, power drops off too) returns the expected bpm delta;
  `next_start_s` inside the 60s window returns `None`; trailing data
  shorter than 60s returns `None`; all-NaN HR in a window returns `None`;
  power staying above the FTP-based (and no-FTP fallback) threshold
  through the recovery window returns `None` even when HR itself drops.
- Unit tests in `tests/test_ai_tools.py::TestGetActivityIntervals`: an
  activity with a clear post-interval HR decay (and low recovery-window
  power) reports `"HRR60"` in the output; a second synthetic interval
  starting soon after the first suppresses HRR60 for the first; an
  interval placed near the end of the synthetic recording (< 60s of
  trailing data) omits HRR60; a recovery window with sustained high power
  omits HRR60 despite a dropping HR.
- Manual: run the app, ask the AI coach about a real activity with known
  recovery behaviour via `get_activity_intervals`, sanity-check the
  reported HRR60 against what's visible in the HR trace.

## Out of Scope

<!-- Explicit non-goals, to prevent scope creep during implementation. -->

- No changes to the `interval_detection` package or boundary detection
  (see 0001) — this story only adds a metric computed from already
  -detected interval boundaries.
- No UI changes — intervals aren't currently displayed with computed
  metrics in the Qt UI (only plotted/marked); this story is scoped to the
  AI tool's text output.
- No truncated/best-effort HRR60 for the contamination or insufficient
  -data cases — both are omitted outright rather than approximated.

## Implementation Notes

<!-- Filled in during/after implementation, not during drafting. What was
     actually built, especially where it deviates from Technical
     Decisions and why, plus any concrete results worth recording. -->

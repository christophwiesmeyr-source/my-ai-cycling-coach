---
title: Fix silent plan-adaptation failure on truncated Claude responses
status: ready   # see tasks/WORKFLOW.md for the lifecycle
release: v4
---

## Problem / Context

During manual testing of story 0006 in `--test` mode, clicking **Adapt Plan**
ran the full agentic tool-use loop successfully (three tool-use rounds
against intervals.icu data, all logged as `200 OK`), and the final call to
the Claude API also returned `200 OK` after ~51s. Despite that, no adapted
plan was ever written to `plan_adapted.md`, no error was shown, and nothing
was logged as a failure — the run looked like a silent no-op.

Root cause, in `src/ai/plan_adaptor.py`'s `adapt_plan()`:

- The request is capped at `max_tokens=4096`, well below the `max_tokens=8192`
  `plan_generator.py` uses to generate a plan of comparable size. Adaptation
  has to reproduce most of the original plan's structure, so it needs at
  least as much headroom as generation — 4096 is undersized and a real plan
  (confirmed with a 13-week, ~26KB original plan) can truncate mid-response.
- The loop only handles two `stop_reason` values explicitly: `"end_turn"`
  (writes `PLAN_ADAPTED_PATH` and returns) and `"tool_use"` (continues the
  loop). Any other value — e.g. `"max_tokens"` on truncation — falls through
  to a bare `return _extract_text(response.content)`. This hands whatever
  text came back to the UI for display via `_on_plan_adapted` (which is why
  something briefly rendered) but never persists it, and never logs a
  warning. There's no diagnostic trail pointing at what happened.

## Acceptance Criteria

- [ ] `adapt_plan()`'s `max_tokens` is raised from 4096 to 8192, matching
      `plan_generator.py`'s generation calls.
- [ ] When `response.stop_reason` is not `"end_turn"` or `"tool_use"`,
      `adapt_plan()` raises an exception instead of silently returning
      display-only text — so `PlanAdaptorWorker.run()`'s existing
      `except Exception` handler emits `error_occurred` and the user sees a
      visible error instead of a result that quietly fails to save.
- [ ] The exception message includes the actual `stop_reason` value, so the
      failure is diagnosable directly from the error shown to the user (or
      the log), without re-deriving it from raw HTTP debug logs.
- [ ] `PLAN_ADAPTED_PATH` is left untouched (not overwritten with partial or
      empty content) when this failure path is hit.

## Technical Decisions

- **Raise on the fallback path rather than best-effort-saving partial text.**
  Truncated markdown can look like a plausible plan while silently dropping
  or corrupting later weeks. An athlete following a corrupted plan is worse
  than a visible error asking them to retry. Failing loudly is the safer
  default for this code path.
- **Match `plan_generator.py`'s existing `max_tokens=8192` rather than
  introducing a new/dynamic limit.** Keeps the two AI call sites consistent
  and avoids adding configuration for what should now be a rare edge case
  once it fails clearly instead of silently.

## Test Plan

- Unit test in `tests/test_ai_plan_adaptor.py`: mock a Claude response with
  `stop_reason="max_tokens"` (or any value other than `"end_turn"` /
  `"tool_use"`) and assert `adapt_plan()` raises, and that
  `PLAN_ADAPTED_PATH` is not created/modified by the call.
- Unit test confirming the exception message contains the `stop_reason`
  value used in the mock.
- Existing `TestAdaptPlanWritesAdaptedFile` tests continue to pass unchanged
  for the `end_turn` happy path.
- Manual retest: reproduce the original repro (Adapt Plan against a
  multi-week plan in `--test` mode) and confirm either a full adapted plan
  is saved, or a visible error dialog appears — never a silent no-op.

## Out of Scope

- Streaming responses or incrementally persisting partial output.
- Retrying automatically on truncation.
- Any changes to `plan_generator.py` itself (already uses 8192).
- Making `max_tokens` user-configurable.

## Implementation Notes

<!-- Filled in during/after implementation, not during drafting. What was
     actually built, especially where it deviates from Technical
     Decisions and why, plus any concrete results worth recording. -->

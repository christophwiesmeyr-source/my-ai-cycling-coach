---
title: Fix silent plan-adaptation failure on truncated Claude responses
status: done   # see tasks/WORKFLOW.md for the lifecycle
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
- Separately, `adapt_plan()` never logs token usage anywhere — unlike
  `ChatWorker.run()` in `src/ui/workers.py`, which logs
  `stop_reason`/`input_tokens`/`output_tokens`/cache stats on every turn.
  This made the original bug harder to diagnose (no way to tell from the
  log whether/how close to the cap the response landed) and is worth fixing
  alongside the `max_tokens` bump for the same reason.

**Retested during implementation, twice:**
1. Even after raising `max_tokens` to 8192 (matching `plan_generator.py`),
   the user hit the same truncation on a real adaptation run against the
   Istria 300 plan — 8192 was still undersized for this workload. Raised
   further to 32768 (see Technical Decisions).
2. At `max_tokens=32768`, the Anthropic Python SDK itself refused the
   non-streaming `client.messages.create()` call: *"Streaming is required
   for operations that may take longer than 10 minutes."* The SDK estimates
   worst-case generation time from `max_tokens` alone and raises client-side
   before sending the request once that estimate crosses ~10 minutes — 8192
   was under that threshold, 32768 isn't. Fixed by switching to
   `client.messages.stream()` (see Technical Decisions).

## Acceptance Criteria

- [x] `adapt_plan()`'s `max_tokens` is raised from 4096 to 32768 (see
      Technical Decisions for why 32768 rather than matching
      `plan_generator.py`'s 8192).
- [x] `adapt_plan()` logs token usage (`stop_reason`, `input_tokens`,
      `output_tokens`, cache stats) on every turn, mirroring
      `ChatWorker.run()`'s existing `logger.info` pattern in
      `src/ui/workers.py` — so a future truncation (or any other stop
      reason) is diagnosable from `app.log` without re-deriving it from
      raw HTTP debug output.
- [x] When `response.stop_reason` is not `"end_turn"` or `"tool_use"`,
      `adapt_plan()` raises an exception instead of silently returning
      display-only text — so `PlanAdaptorWorker.run()`'s existing
      `except Exception` handler emits `error_occurred` and the user sees a
      visible error instead of a result that quietly fails to save.
- [x] The exception message includes the actual `stop_reason` value, so the
      failure is diagnosable directly from the error shown to the user (or
      the log), without re-deriving it from raw HTTP debug logs.
- [x] `PLAN_ADAPTED_PATH` is left untouched (not overwritten with partial or
      empty content) when this failure path is hit.

## Technical Decisions

- **Raise on the fallback path rather than best-effort-saving partial text.**
  Truncated markdown can look like a plausible plan while silently dropping
  or corrupting later weeks. An athlete following a corrupted plan is worse
  than a visible error asking them to retry. Failing loudly is the safer
  default for this code path.
- **`max_tokens=32768`, not `plan_generator.py`'s 8192.** Originally planned
  to match `plan_generator.py`, but a real adaptation run against the
  Istria 300 plan still truncated at 8192 during manual testing — the
  workload needs materially more headroom than initial generation (an
  "Adaptation Notes" section on top of reproducing most of the original
  plan's structure). Left as a static constant rather than a
  computed/dynamic limit — avoid adding configuration for what should now
  fail loudly instead of silently if it's still ever undersized.
- **Switch `adapt_plan()`'s API call from `client.messages.create()` to
  `client.messages.stream()` + `.get_final_message()`.** At `max_tokens=
  32768` the non-streaming call is rejected client-side by the SDK itself
  (see Problem / Context, retest 2) — the SDK estimates worst-case
  generation time from `max_tokens` and requires streaming above ~10
  minutes' worth. `client.messages.stream()` used as a context manager,
  calling `.get_final_message()` once the stream completes, gets back the
  exact same `Message` object (`stop_reason`, `content`, `usage` all
  populated) that `create()` returned — so nothing downstream of the call
  changes, only how the response is obtained. This is a transport-level
  fix, not incremental UI streaming — `ChatWorker` already streams to the
  UI via `chunk_received`, but `PlanAdaptorWorker`/`adapt_plan()` has no
  such callback and doesn't need one; see Out of Scope.
- **Add usage logging alongside the `max_tokens` bump, not as a follow-up.**
  The lack of a log line for token usage is exactly what made both rounds
  of truncation (4096, then 8192) hard to diagnose — there was no way to
  see how close to the cap a response landed without re-deriving it from
  raw HTTP debug logs. Mirrors `ChatWorker.run()`'s existing
  `logger.info("chat turn stop_reason=... input_tokens=... ...")` pattern
  exactly, just renamed to "plan adaptation turn" and logged once per
  `while True` iteration (covers both `tool_use` continuations and the
  final turn).

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
- Usage logging isn't independently unit-tested (it's a log line with no
  externally observable behavior change); covered indirectly by the fake
  response needing a `usage` object for the existing tests to keep passing.
  Verify manually by checking `app.log` for a `plan adaptation turn
  stop_reason=... input_tokens=... output_tokens=...` line after an Adapt
  Plan run.

## Out of Scope

- Incrementally displaying or persisting partial output as it streams (no
  `chunk_received`-style callback for `adapt_plan()`/`PlanAdaptorWorker`,
  unlike `ChatWorker`). Note: switching the API call itself to
  `client.messages.stream()` transport turned out to be **required**, not
  optional — see Technical Decisions — but the response is still assembled
  into one complete `Message` via `.get_final_message()` before any of the
  existing logic runs; the UI still only sees the final result, same as
  before.
- Retrying automatically on truncation.
- Any changes to `plan_generator.py` itself (already uses 8192, and its
  requests are small enough to stay under the SDK's non-streaming
  threshold).
- Making `max_tokens` user-configurable.

## Implementation Notes

Built in three passes, each triggered by the user retesting from this
branch and hitting the next problem in sequence:

1. Matched `plan_generator.py`'s `max_tokens=8192`, per the Technical
   Decisions as originally drafted.
2. Still truncated on a real adaptation run against the Istria 300 plan.
   Raised `max_tokens` to 32768 and added usage logging in the same pass.
3. At 32768, `client.messages.create()` (non-streaming) started raising
   the Anthropic SDK's own `ValueError` — *"Streaming is required for
   operations that may take longer than 10 minutes"* — before any request
   even reached the network. Switched the call to
   `client.messages.stream()` + `.get_final_message()`.

- `src/ai/plan_adaptor.py`: `max_tokens` 4096 → 32768. The API call is now
  `with client.messages.stream(...) as stream: response =
  stream.get_final_message()` instead of `client.messages.create(...)` —
  everything downstream (the `stop_reason`/`tool_use`/fallback branching,
  usage logging) is unchanged, since `get_final_message()` returns the same
  `Message` shape `create()` did. The trailing `return
  _extract_text(response.content)` fallback (hit when `stop_reason` is
  neither `"end_turn"` nor `"tool_use"`) now raises `RuntimeError(f"Plan
  adaptation stopped unexpectedly (stop_reason={response.stop_reason!r}); no
  adapted plan was saved. This usually means the response was truncated —
  try again.")`. Used a plain builtin exception rather than a new class, to
  match this module's existing convention (`FileNotFoundError` a few lines
  above for the missing-original-plan case). Added `logger =
  logging.getLogger(__name__)` and a `logger.info("plan adaptation turn
  stop_reason=... input_tokens=... output_tokens=... cache_creation=...
  cache_read=...")` call right after every turn's response is obtained,
  before branching on `stop_reason` — so it fires on every loop iteration
  (tool-use rounds and the final turn alike), matching `ChatWorker.run()`'s
  existing per-turn logging.
- `src/ui/workers.py`: added `logger.exception("plan adaptor failed")` to
  `PlanAdaptorWorker.run()`'s `except` block, mirroring `ChatWorker.run()`'s
  existing pattern. Not literally named in the Acceptance Criteria, but
  required to actually deliver AC #3's "diagnosable ... from the error
  dialog or **the log**" — without it, the new exception's message reaches
  the UI dialog but leaves no trace in `app.log`, same diagnosability gap
  as before for anyone checking logs instead of catching the dialog live.

**Test coverage note:** this branch was forked from `release/v4` before
story 0006 merged, so none of story 0006's `adapt_plan()`-level tests exist
here yet — only `_extract_text` and `_build_log_section` had coverage.
Added a fake Claude client/response chain to `tests/test_ai_plan_adaptor.py`:
`_FakeResponse` (plus `_FakeUsage`, defaulted so `response.usage` is
satisfied without every test constructing one explicitly), `_FakeStream` (a
context manager whose `get_final_message()` returns the fake response —
mirrors the real `client.messages.stream(...)` context-manager shape), and
`_FakeMessages`/`_FakeClient` wiring `.stream()` to it (renamed from an
earlier `.create()`-based version once the implementation switched to
streaming). Also added an `activity_client` fixture (real `IntervalsClient`,
`CONFIG_FILE` patched to a missing tmp path — needed only to satisfy
`adapt_plan`'s type signature, never exercised since the fallback path
makes no tool calls). Then:
- `TestAdaptPlanWritesAdaptedFile` — one happy-path (`end_turn`) test,
  since this is otherwise the first direct test of `adapt_plan()` and the
  change touches its core control flow. (The story's Test Plan expected
  this class to already exist from story 0006; it didn't on this branch.)
- `TestAdaptPlanTruncatedResponse` — three tests per the Test Plan: raises
  and leaves no file on a `"max_tokens"` stop reason, exception message
  contains `"max_tokens"`, and an existing `plan_adapted.md` is left
  byte-for-byte unchanged when the failure path is hit.

All four project checks (`ruff check`, `ruff format --check`, `mypy`,
`pytest`) pass — 274 tests, including the 4 new ones.

**Manual retest — confirmed by the user.** Run from this branch in
`--test` mode against the Istria 300 plan that originally triggered the
bug: Adapt Plan completed and produced a full adapted plan (no truncation,
no silent no-op). `app.log` confirms the usage-logging AC too — the
successful run logged 4 `plan adaptation turn` lines (3 `tool_use` + 1
`end_turn`), totalling 75,254 input / 17,130 output tokens with
`cache_creation=0`/`cache_read=0` throughout (no prompt caching yet — that
gap, along with the discovery below, is now tracked separately).

**Follow-up gap found during this retest, deliberately left out of
scope:** the Sessions table in the Training tab does not update after
Adapt Plan — `adapt_plan()` only ever wrote the adapted plan's Markdown,
never a structured `sessions_adapted.csv`, and nothing in `training_tab.py`
reloads the sessions table after adaptation regardless. Pre-existing gap,
unrelated to this story's truncation fix; filed as story 0010 (also
covers adding prompt caching to `adapt_plan()`'s loop, since the same
retest's log data showed zero cache activity across all 4 turns).

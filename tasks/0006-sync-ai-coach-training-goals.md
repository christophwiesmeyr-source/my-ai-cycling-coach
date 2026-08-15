---
title: Sync AI coach context with live training goals
status: done
release: v4
---

## Problem / Context

The user asked the AI coach directly which capabilities/tools were missing, and it reported that it has no direct way to assess the athlete's training goals. Investigation confirmed the coach's context can go stale relative to `goals.json`.

The chat coach's system prompt is built in `ChatSession.build_system()`
(`src/ai/chat_session.py`). It includes the original/adapted training plan
markdown verbatim, plus a session log table. The plan markdown has a "Plan
parameters" table baked in at generation time (`main_goal`, `event_name`,
`current_ftp_watts`, `weight_kg`, `max_hr_bpm`, `additional_notes`, etc.,
rendered by `_build_plan_prompt()` in `src/ai/plan_generator.py`). This
table is a snapshot: it reflects whatever `goals.json` (`GOALS_PATH` in
`src/constants.py`) contained the moment the plan was generated.

Static fields (goal, event, notes, experience level) rarely change after
the plan is created, so the snapshot is fine for those. But numeric fields
— most notably `current_ftp_watts` — are expected to change over the
course of training (e.g. after an FTP retest via the Training Goals form,
which calls `_save_goals()` in `src/ui/training_tab.py` and overwrites
`goals.json`). That update is never reflected back into the plan text.

Confirmed concretely on the user's live app data (`~/.my-ai-cycling-coach/`):
`goals.json` has `current_ftp_watts: 343`, while `plan_original.md`'s
parameter table still shows `FTP | 325 W`, the value at generation time
(2026-06-28). `plan_adaptor.py` has the same gap — when it regenerates the
adapted plan, it never re-reads `goals.json`; it only sees whatever
snapshot survived into `original_plan`'s text.

The coach's only access to live `goals.json` values today is incidental:
specific tools in `src/ai/tools.py` (`_load_goals()`, used inside
zone/training-load/efficiency calculations) read the file directly, but
there is no general-purpose way for the coach to see the athlete's current
goals in chat.

Related but distinct: [0003-track-ftp-over-time.md](0003-track-ftp-over-time.md)
is about FTP drift affecting interval-detection accuracy in the analysis
pipeline, not the AI coach's context — different subsystem, not a
duplicate of this story.

## Acceptance Criteria

- [x] `src/goals.py` exposes a public `load_goals() -> dict` that reads
      `GOALS_PATH`, returning `{}` on a missing file or invalid JSON.
- [x] `src/goals.py` exposes a `format_goals_table(goals: dict, title: str) -> str`,
      extracted from `plan_generator._build_plan_header`'s table-rendering
      logic, returning `""` when `goals` is empty.
- [x] `tools.py`'s private `_load_goals()` is removed in favour of
      `src.goals.load_goals()`, so goal-loading logic exists in exactly one
      place.
- [x] `plan_adaptor.adapt_plan()`'s prompt includes a "Current athlete
      profile" section built fresh from `load_goals()` at adaptation time
      (not from the original plan's baked-in snapshot), with explicit
      wording that this live section is authoritative over the original
      plan's "Plan parameters" table where the two disagree (e.g. FTP).
- [x] The adapted plan written to `PLAN_ADAPTED_PATH` has a "Plan
      parameters (at adaptation)" table prepended, built from the same
      live `goals.json` snapshot used in the prompt — so the Training tab
      shows the FTP/hours/etc. that were actually used for the adaptation.
      Skipped (no prepend) when `load_goals()` returns `{}`.
- [x] `chat_session.ChatSession.build_system()` includes the same live
      "Current athlete profile" section, placed in the volatile (uncached)
      block and read fresh on every call — a goal edited mid-session is
      visible on the next message with no reload/restart needed.
- [x] Missing/empty/unparseable `goals.json` degrades gracefully at all
      three call sites: no crash, section/prepend simply omitted.

## Technical Decisions

- **Shared home:** `load_goals()` and `format_goals_table()` live in
  `src/goals.py`, next to `GOAL_FIELDS`/`GoalMeta` — it's already the
  canonical module for goal shape/metadata. `tools.py`, `plan_adaptor.py`,
  and `chat_session.py` all import from there instead of each reading
  `GOALS_PATH` themselves.
- **Error handling:** `load_goals()` catches `(OSError, json.JSONDecodeError)`
  and returns `{}`, matching the narrower, already-typed pattern used by
  `plan_adaptor._build_log_section()` — tightens `tools._load_goals()`'s
  current bare `except Exception`.
- **`format_goals_table(goals, title)`:** returns a full
  `## {title}\n\n| Parameter | Value |...` block using the same
  `GOAL_FIELDS`-driven row logic `_build_plan_header` has today (including
  the computed event-date/weeks-until-event rows, since `goals.json`
  already stores those as of the last autosave). `plan_generator._build_plan_header`
  is refactored to call this helper instead of duplicating it; its output
  for the original-plan flow is unchanged.
- **`plan_adaptor` prompt:** `_USER_PROMPT` gets a new
  `{current_profile_section}` slot, positioned after `{original_plan}` and
  before `{log_section}`, built via `format_goals_table(load_goals(),
  "Current athlete profile (live)")`. Surrounding prompt text tells the
  model to prefer these live values over the original plan's baked-in
  parameters when they conflict.
- **`plan_adaptor` extraction for testability:** `adapt_plan()` currently
  builds its prompt inline via `_USER_PROMPT.format(...)`. Pull that into a
  small pure helper (e.g. `_build_user_prompt(original_plan, today, goals)
  -> str`), mirroring how `_build_log_section` is already isolated, so the
  live-goals wiring is unit-testable without mocking the Anthropic client.
- **Adapted plan file:** after `adapted = _extract_text(...)`, prepend
  `format_goals_table(current_goals, "Plan parameters (at adaptation)")`
  before the `PLAN_ADAPTED_PATH.write_text(...)` call, mirroring the
  header-prepend pattern already used in `plan_generator.generate_plan()`.
- **`chat_session.build_system()`:** `load_goals()` is called inside
  `build_system()` itself (not cached on the instance, not read in
  `__init__`/`reload_plans()`), and the formatted section is appended as
  an additional block in the volatile part, after the session-table block,
  using the same "Current athlete profile (live)" title as the adaptor for
  consistency.

## Test Plan

- Unit tests for `src.goals.load_goals()`: missing file → `{}`; malformed
  JSON → `{}`; valid file → parsed dict (tmp_path + patch `GOALS_PATH`,
  following the pattern already used in `test_ai_plan_adaptor.py`).
- Unit tests for `src.goals.format_goals_table()`: empty goals → `""`;
  populated goals → contains expected labels/values, in `GOAL_FIELDS`
  order.
- Unit tests (`test_ai_plan_adaptor.py`) for the new `_build_user_prompt()`
  helper: a patched `GOALS_PATH` with FTP 343 and a fake `original_plan`
  string containing a baked-in FTP of 325 both appear in the built prompt,
  proving the live value reaches the model text without replacing the
  historical one.
- Unit tests confirming `PLAN_ADAPTED_PATH` content: with a mocked API
  response, the saved file starts with the "Plan parameters (at
  adaptation)" table when `goals.json` has data, and has no such table
  when `goals.json` is empty/missing.
- Unit tests (`test_ai_chat_session.py`): `build_system()` includes the
  "Current athlete profile" section with values from a patched
  `GOALS_PATH`; the section is part of the volatile (uncached) block per
  the existing cache-boundary tests; editing `GOALS_PATH` between two
  `build_system()` calls on the same `ChatSession` (no `reload_plans()` in
  between) is reflected in the second call's output.
- Manual verification: generate a plan, edit FTP in the Training Goals
  form (autosaves to `goals.json`), click "Adapt Plan" — confirm the
  adapted plan's parameters table shows the new FTP. Then ask the chat
  coach "what's my current FTP?" and confirm it reports the updated value
  without restarting the app.

## Out of Scope

- Backfilling or rewriting already-generated `plan_original.md` /
  `plan_adapted.md` files that predate this change.
- Diffing which fields changed since plan generation and calling them out
  specifically — the live section is a full current snapshot, not a diff.
- Any change to how goals are collected or saved in `training_tab.py`
  (`_collect_goals`/`_save_goals`) — this story only changes how
  already-saved goals are consumed downstream.
- Automatically re-triggering plan adaptation when `goals.json` changes
  (e.g. a background watcher) — adaptation stays user-initiated via the
  existing "Adapt Plan" action.

## Implementation Notes

Built as specified in Technical Decisions, with two deliberate deviations:

- **`tools.py` scope narrowed to what the AC actually names.** Only the private
  `_load_goals()` function was removed and routed through `src.goals.load_goals()`
  (its two call sites: `_get_activity_training_load`, `_get_activity_intervals`).
  `_get_activity_zones` has its own separate, pre-existing inline
  `json.loads(GOALS_PATH.read_text())` that was *not* touched — it isn't
  `_load_goals()`, and its `except Exception` branch produces a distinct,
  test-verified message ("Training goals not available…") for an unreadable
  file versus "Neither FTP nor max heart rate is set…" for a valid-but-empty
  one. `load_goals()` collapses both cases to `{}`, so routing this call site
  through it too would have silently changed that message. Judged the AC's
  precise wording ("`_load_goals()` is removed") as intentionally scoped to
  just that function, not a mandate to touch every direct `GOALS_PATH` read in
  the file.
- **`_build_plan_header({})` now returns `""` instead of a header-with-no-rows
  table.** `format_goals_table`'s AC-mandated contract is to return `""` for
  empty goals (AC #2), and `_build_plan_header` is now a one-line delegate to
  it, so this edge case's output changed. Updated the one existing test
  (`test_ai_plan_generator.py::TestBuildPlanHeader`) that asserted the old
  behavior; this path is never hit in practice since the Training Goals form
  always sets `main_goal` before `generate_plan()` is called.

Everything else matches the story as written: `src/goals.py` gained
`load_goals()`/`format_goals_table()`; `plan_adaptor._build_user_prompt()` is a
new pure helper taking `(original_plan, today, goals)`, with `_USER_PROMPT`'s
`{current_profile_section}` slot placed after `{original_plan}` and before
`{log_section}`, plus wording telling the model to prefer live values over the
original plan's baked-in table; `adapt_plan()` loads goals once and reuses that
same snapshot for both the prompt and the `PLAN_ADAPTED_PATH` prepend (skipped
when empty), mirroring `generate_plan()`'s return-what-was-written pattern;
`chat_session.build_system()` calls `load_goals()` fresh on every call and
appends the profile section after the session-table block, in the volatile
(uncached) part.

**Necessary test-isolation fixes (not explicitly in the Test Plan, but required
to keep the suite deterministic):** since `load_goals()` resolves `GOALS_PATH`
from `src.goals`'s own module globals, tests exercising code paths that now go
through it must patch `src.goals.GOALS_PATH`, not the caller module's name.
Updated: the `_get_activity_training_load`/`_get_activity_intervals` patches in
`test_ai_tools.py` (12 occurrences), and all of `TestBuildSystem` in
`test_ai_chat_session.py`, which previously never patched goals at all — before
this story, `build_system()` didn't touch `goals.json`, so those tests were
silently safe; now that it does, leaving them unpatched would have made them
read the developer's real `~/.my-ai-cycling-coach/goals.json` (confirmed
non-empty per this story's Problem/Context) on every run.

**Files touched:** `src/goals.py`, `src/ai/plan_generator.py`,
`src/ai/tools.py`, `src/ai/plan_adaptor.py`, `src/ai/chat_session.py`,
`tests/test_goals.py` (new), `tests/test_ai_plan_generator.py`,
`tests/test_ai_tools.py`, `tests/test_ai_plan_adaptor.py`,
`tests/test_ai_chat_session.py`.

**Test Plan verification:**

- `load_goals()` unit tests — verified (`tests/test_goals.py::TestLoadGoals`).
- `format_goals_table()` unit tests — verified
  (`tests/test_goals.py::TestFormatGoalsTable`).
- `_build_user_prompt()` unit tests — verified
  (`tests/test_ai_plan_adaptor.py::TestBuildUserPrompt`): a patched-in FTP of
  343 and the original plan's baked-in FTP of 325 both appear in the built
  prompt.
- `PLAN_ADAPTED_PATH` content unit tests — verified
  (`tests/test_ai_plan_adaptor.py::TestAdaptPlanWritesAdaptedFile`, mocked
  Anthropic client): saved file starts with the "Plan parameters (at
  adaptation)" table when goals are present, has no such table when
  goals.json is empty/missing.
- `build_system()` live-goals unit tests — verified
  (`tests/test_ai_chat_session.py::TestBuildSystemLiveGoals`): section present
  with patched-goals values, section is in the uncached trailing block, and
  editing `GOALS_PATH` between two `build_system()` calls on the same session
  (no `reload_plans()`) changes the second call's output.
- Manual end-to-end verification (generate plan → edit FTP in Training Goals
  form → Adapt Plan → ask chat coach for current FTP) — **verified live by
  the user**, in two passes:
  1. At implementation time, this environment had no display and no
     configured Anthropic/intervals.icu credentials to run the real Qt app,
     so the flow was verified by tracing the code path instead:
     `training_tab.py`'s autosave writes the new FTP to `goals.json`
     unchanged (out of scope); `PlanAdaptorWorker.run()` calls the
     now-updated `adapt_plan()`, which reads that file fresh via
     `load_goals()` and both feeds it into the prompt and prepends it to
     the adapted plan text rendered in the "Adapted" tab; `ChatWorker.run()`
     calls `session.build_system()` fresh on every send (not cached), so
     the coach's system prompt picks up the new FTP on the very next
     message with no reload or restart.
  2. The user then ran the actual flow against the real app in `--test`
     mode. This surfaced an unrelated pre-existing bug in `adapt_plan()`
     (silent truncation on a real-sized plan — `max_tokens` too low, and a
     fallback path that dropped the result without saving or erroring),
     fixed separately in story 0009. With that fix merged into this
     branch, the user completed the full sequence — generate plan, edit
     FTP, Adapt Plan, ask the chat coach for current FTP — and confirmed
     the live FTP value reached both the adapted plan and the chat coach's
     answer, matching the code-path trace above.

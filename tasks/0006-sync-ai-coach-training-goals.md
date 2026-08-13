---
title: Sync AI coach context with live training goals
status: ready
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

- [ ] `src/goals.py` exposes a public `load_goals() -> dict` that reads
      `GOALS_PATH`, returning `{}` on a missing file or invalid JSON.
- [ ] `src/goals.py` exposes a `format_goals_table(goals: dict, title: str) -> str`,
      extracted from `plan_generator._build_plan_header`'s table-rendering
      logic, returning `""` when `goals` is empty.
- [ ] `tools.py`'s private `_load_goals()` is removed in favour of
      `src.goals.load_goals()`, so goal-loading logic exists in exactly one
      place.
- [ ] `plan_adaptor.adapt_plan()`'s prompt includes a "Current athlete
      profile" section built fresh from `load_goals()` at adaptation time
      (not from the original plan's baked-in snapshot), with explicit
      wording that this live section is authoritative over the original
      plan's "Plan parameters" table where the two disagree (e.g. FTP).
- [ ] The adapted plan written to `PLAN_ADAPTED_PATH` has a "Plan
      parameters (at adaptation)" table prepended, built from the same
      live `goals.json` snapshot used in the prompt — so the Training tab
      shows the FTP/hours/etc. that were actually used for the adaptation.
      Skipped (no prepend) when `load_goals()` returns `{}`.
- [ ] `chat_session.ChatSession.build_system()` includes the same live
      "Current athlete profile" section, placed in the volatile (uncached)
      block and read fresh on every call — a goal edited mid-session is
      visible on the next message with no reload/restart needed.
- [ ] Missing/empty/unparseable `goals.json` degrades gracefully at all
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

<!-- Filled in during/after implementation, not during drafting. What was
     actually built, especially where it deviates from Technical
     Decisions and why, plus any concrete results worth recording. -->

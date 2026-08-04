---
title: Sync AI coach context with live training goals
status: draft
release:
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

<!-- Checklist of concrete, verifiable outcomes. -->

- [ ]

## Technical Decisions

<!-- Code-related decisions made during drafting, with rationale. -->

## Test Plan

<!-- How to verify the implementation once done: manual steps and/or
     specific automated tests to add/run. -->

## Out of Scope

<!-- Explicit non-goals, to prevent scope creep during implementation. -->

## Implementation Notes

<!-- Filled in during/after implementation, not during drafting. What was
     actually built, especially where it deviates from Technical
     Decisions and why, plus any concrete results worth recording. -->

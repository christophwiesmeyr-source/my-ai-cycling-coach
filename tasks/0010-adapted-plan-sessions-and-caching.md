---
title: Generate sessions from the adapted plan, refresh the Sessions table, and cache the adaptation loop's repeated context
status: ready   # see tasks/WORKFLOW.md for the lifecycle
release: v4
---

## Problem / Context

Discovered during manual testing of story 0009 (plan-adaptation truncation
fix), after the fix confirmed a full adapted plan now saves correctly:

**1. Sessions never update after adaptation.** `adapt_plan()` in
`src/ai/plan_adaptor.py` only writes the adapted plan as Markdown to
`PLAN_ADAPTED_PATH`. Unlike plan *generation* — where
`PlanGeneratorWorker.run()` calls `generate_plan()` and then immediately
`generate_sessions()` to build a structured `sessions_original.csv` — there
is no equivalent step for adaptation. `SESSIONS_ADAPTED_PATH` (defined in
`src/constants.py`) is never written anywhere in the codebase; it's only
ever *deleted* by `plan_generator.clear_derived_plan_data()` when a new
plan is generated. `chat_session._build_session_table()` already prefers
`SESSIONS_ADAPTED_PATH` over `SESSIONS_ORIGINAL_PATH` when it exists
([chat_session.py:26-31](src/ai/chat_session.py#L26-L31)) — the read side
was built for this and has just been sitting unused. On top of that,
`training_tab.py`'s `_load_sessions_table()` is hardwired to
`SESSIONS_ORIGINAL_PATH` regardless, and `_on_plan_adapted()` never calls
`_load_sessions_table()` after an adaptation completes. Net effect: the
Sessions table and completion-tracking UI stay pinned to the original plan
forever, even after a successful adaptation.

**2. The adaptation loop re-pays for the same content every turn.**
`adapt_plan()`'s multi-turn tool-use loop resends the full growing
conversation history on every turn with no prompt caching. A real run
(logged 2026-08-15, `app.log`) took 4 turns:

| Turn | stop_reason | input_tokens | output_tokens |
|---|---|---|---|
| 1 | tool_use | 14,355 | 78 |
| 2 | tool_use | 15,513 | 974 |
| 3 | tool_use | 19,157 | 5,969 |
| 4 | end_turn | 26,229 | 10,109 |

`cache_creation`/`cache_read` were `0` on every turn — each turn re-billed
the entire prior prefix (original plan text, system prompt, earlier tool
results) at full price instead of reading it from cache. Total: 75,254
input + 17,130 output tokens, ≈$0.48 at standard Sonnet 5 rates ($0.32 at
the introductory rate) for one Adapt Plan click. Bundled into this story
rather than filed separately because it touches the exact same
`adapt_plan()` code the sessions work also modifies.

**3. Past-session safety is prompt-only, with no code-level enforcement.**
Identified during drafting of this story. `adapt_plan()`'s `_USER_PROMPT`
tells Claude "Only modify sessions scheduled for {today} or later... do
not change their prescriptions," but the tool-use loop hands Claude the
entire plan text and lets it regenerate all of it freely in a single
`end_turn` response — nothing diffs, validates, or guards against the
model silently rewriting history despite the instruction. This matters
more for the CSV `adapt_sessions()` introduces than for the Markdown plan:
`sessions_log.json` completion tracking (`training_tab.py`,
`chat_session.py`) is keyed purely by the CSV's `date` column, so if the
generated adapted CSV drifts on a past-dated row — a different value, a
missing row, a shifted date — completion history for that session silently
orphans or mismatches. The fix belongs in `adapt_sessions()` itself, the
function this story is already adding.

## Acceptance Criteria

- [ ] A new function generates a structured session CSV from the adapted
      plan text (mirroring `plan_generator._build_sessions_prompt()` /
      `_extract_csv()` / the single-call structure of
      `generate_sessions()`) and writes it to `SESSIONS_ADAPTED_PATH`.
- [ ] `adapt_sessions()` never trusts the LLM-generated CSV for past
      sessions: after generating the new CSV, rows with `date < today` are
      taken verbatim from `SESSIONS_ORIGINAL_PATH`, and only rows with
      `date >= today` come from the freshly generated CSV — regardless of
      what the model produced for historical dates.
- [ ] `PlanAdaptorWorker.run()` calls this after `adapt_plan()` succeeds,
      before emitting `finished` — mirroring `PlanGeneratorWorker.run()`'s
      `generate_plan()` → `generate_sessions()` sequence.
- [ ] If session-CSV generation fails after a successful plan adaptation,
      the adapted plan itself is still saved and `finished` still fires
      with it — a CSV-generation bug must never make a successful
      adaptation report as failed (would regress story 0009's fix into a
      different flavor of "silent/confusing failure").
- [ ] `training_tab.py`'s `_load_sessions_table()` prefers
      `SESSIONS_ADAPTED_PATH` over `SESSIONS_ORIGINAL_PATH` when the former
      exists — mirroring `chat_session._build_session_table()`'s existing
      preference.
- [ ] `training_tab.py`'s `_on_plan_adapted()` calls `_load_sessions_table()`
      after rendering the adapted plan, so the Sessions table visibly
      refreshes without an app restart or tab switch.
- [ ] `adapt_plan()`'s Claude API calls use prompt caching
      (`cache_control: {"type": "ephemeral"}`) so turn *N+1* reads turn
      *N*'s shared prefix (system prompt, original plan, earlier tool
      results) from cache instead of re-billing it at full price.

## Technical Decisions

- **New `adapt_sessions()` function in `plan_adaptor.py`, reusing
  `plan_generator`'s CSV helpers directly.** Import and reuse
  `_build_sessions_prompt()` and `_extract_csv()` from `plan_generator.py`
  rather than duplicating the CSV prompt/extraction logic — the adapted
  plan's CSV needs the identical column schema and output-format rules as
  the original.
- **Deterministic splice, not a better prompt, for past-session safety in
  the CSV.** `adapt_plan()`'s existing "don't touch past sessions"
  instruction is prompt-only and unenforced (confirmed during drafting —
  the tool-use loop lets Claude regenerate the whole plan text with no
  diffing or validation against the original). Rather than leaning on a
  similar instruction for `adapt_sessions()`'s CSV, splice deterministically
  after generation: parse both the freshly generated CSV and
  `SESSIONS_ORIGINAL_PATH` by `date`, keep the original's rows for every
  `date < today`, take only `date >= today` rows from the generated CSV,
  and write the merged result to `SESSIONS_ADAPTED_PATH`. `today` uses the
  same `datetime.date.today().isoformat()` reference `adapt_plan()` already
  passes into its prompt, so the cutoff is consistent between the Markdown
  plan and the CSV. This guarantees `sessions_log.json` completion
  correlation (keyed by `date`, see `chat_session.py` /
  `training_tab.py`) can never orphan or mismatch a historical session,
  independent of model behavior. If `SESSIONS_ORIGINAL_PATH` doesn't exist
  or fails to parse (shouldn't happen in practice — sessions are always
  generated before a plan can be adapted — but guard for it), fall back to
  writing the generated CSV as-is and `logger.warning` the fallback, rather
  than failing the whole adaptation over a missing safety net.
- **Goals context for the sessions prompt.** `_build_sessions_prompt(plan_text,
  goals)` needs `current_date`/`event_date`/`weeks_until_event`. This
  branch doesn't yet have `src.goals.load_goals()` (added in the
  not-yet-merged story 0006) — read `GOALS_PATH` directly with the same
  defensive `try/except (OSError, json.JSONDecodeError): return {}` pattern
  `tools.py`'s private `_load_goals()` already uses, rather than importing
  a private helper across module boundaries. **If story 0006 has merged by
  implementation time, use `src.goals.load_goals()` instead** — confirm
  which applies when this story moves to implementation.
- **CSV-generation failure must not roll back the plan.** Call
  `adapt_sessions()` from `PlanAdaptorWorker.run()`, wrapped in its own
  `try/except` separate from the one around `adapt_plan()` — log the
  failure (`logger.exception`) but still emit `finished` with the already-
  successful adapted plan text. A partial success (plan saved, sessions
  CSV not) must surface as a working plan with stale sessions, not as a
  failed run.
- **Prompt caching placement.** `cache_control: {"type": "ephemeral"}` on
  the system prompt (as a single list-wrapped text block — per Anthropic's
  render order `tools → system → messages`, a breakpoint on the last system
  block caches the `tools` array too), and on the last content block of
  `messages[-1]` before each `client.messages.stream()` call in the loop —
  not on every historical message; a later breakpoint's cache read doesn't
  require every earlier position to carry its own marker (see
  `shared/prompt-caching.md` § Multi-turn conversations in the `claude-api`
  skill). Default 5-minute ephemeral TTL is sufficient — the observed
  4-turn run completed in under 4 minutes end to end.
- **Caching is scoped to `adapt_plan()`'s tool-use loop only, not the new
  `adapt_sessions()` call.** Caching only pays off across ≥2 requests
  sharing a prefix within the TTL; `adapt_sessions()` is a single request,
  so there's nothing for a breakpoint there to be read back by.

## Test Plan

- Unit tests for the new session-generation function: mock a Claude
  response returning CSV text, assert it's written to
  `SESSIONS_ADAPTED_PATH` and returned, following the same fake-client
  pattern already in `tests/test_ai_plan_adaptor.py`.
- Unit test for the splice safeguard: given a fake `SESSIONS_ORIGINAL_PATH`
  CSV with rows spanning past/today/future dates and a mocked Claude
  response returning a generated CSV with *different* values for the same
  dates, assert the merged output written to `SESSIONS_ADAPTED_PATH` uses
  the original's rows verbatim for `date < today` and the generated rows
  for `date >= today`. Also test the fallback path: no
  `SESSIONS_ORIGINAL_PATH` present, assert the generated CSV is written
  as-is and a warning is logged.
- Unit test: a session-CSV-generation failure (raised exception from the
  mocked call) does not prevent the overall adaptation flow from reporting
  the adapted plan as successful — test at whatever level the
  `try/except` boundary lands (the new function, or a thin wrapper called
  from `PlanAdaptorWorker`).
- Manual verification (no existing test coverage for `training_tab.py` —
  this file is UI-only and tested manually project-wide): in `--test`
  mode, click Adapt Plan, confirm the Sessions table updates to reflect the
  adapted schedule without restarting the app or switching tabs, and that
  completion tracking (`sessions_log.json` entries) still lines up with the
  matching rows.
- Manual verification of caching: after an Adapt Plan run, check `app.log`
  for `plan adaptation turn ...` lines (added in story 0009) and confirm
  `cache_read` is non-zero on turns after the first, and/or that total
  reported cost trends down relative to the story's baseline log (75,254
  input / 17,130 output tokens, 4 turns, zero cache activity).

## Out of Scope

- Prompt caching for `plan_generator.py` or `chat_session.py` — scoped to
  `adapt_plan()` only, since that's the code this story is already
  touching and the code with the demonstrated repeated-resend pattern.
- Making the Sessions table adapted/original toggle a user-visible choice
  in the UI — adapted always wins when present, matching the existing
  `chat_session.py` read-side precedent.
- Retroactively backfilling `sessions_adapted.csv` for plans that were
  already adapted before this story ships (under the pre-fix silent-no-op
  behavior, no adapted plan was ever actually saved in practice, so there's
  nothing to backfill from).
- Applying an equivalent splice to `adapt_plan()`'s Markdown plan text —
  the model's existing past/future instruction remains prompt-only for the
  Markdown path. Splicing free-form Markdown by date isn't well-defined the
  way splicing a dated CSV is; this story only closes the enforcement gap
  for the structured CSV it adds.

## Implementation Notes

<!-- Filled in during/after implementation, not during drafting. What was
     actually built, especially where it deviates from Technical
     Decisions and why, plus any concrete results worth recording. -->

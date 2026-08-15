---
title: Generate sessions from the adapted plan, refresh the Sessions table, and cache the adaptation loop's repeated context
status: done   # see tasks/WORKFLOW.md for the lifecycle
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

- [x] A new function generates a structured session CSV from the adapted
      plan text (mirroring `plan_generator._build_sessions_prompt()` /
      `_extract_csv()` / the single-call structure of
      `generate_sessions()`) and writes it to `SESSIONS_ADAPTED_PATH`.
- [x] `adapt_sessions()` never trusts the LLM-generated CSV for past
      sessions: after generating the new CSV, rows with `date < today` are
      taken verbatim from `SESSIONS_ORIGINAL_PATH`, and only rows with
      `date >= today` come from the freshly generated CSV — regardless of
      what the model produced for historical dates.
- [x] `PlanAdaptorWorker.run()` calls this after `adapt_plan()` succeeds,
      before emitting `finished` — mirroring `PlanGeneratorWorker.run()`'s
      `generate_plan()` → `generate_sessions()` sequence.
- [x] If session-CSV generation fails after a successful plan adaptation,
      the adapted plan itself is still saved and `finished` still fires
      with it — a CSV-generation bug must never make a successful
      adaptation report as failed (would regress story 0009's fix into a
      different flavor of "silent/confusing failure").
- [x] `training_tab.py`'s `_load_sessions_table()` prefers
      `SESSIONS_ADAPTED_PATH` over `SESSIONS_ORIGINAL_PATH` when the former
      exists — mirroring `chat_session._build_session_table()`'s existing
      preference.
- [x] `training_tab.py`'s `_on_plan_adapted()` calls `_load_sessions_table()`
      after rendering the adapted plan, so the Sessions table visibly
      refreshes without an app restart or tab switch.
- [x] `adapt_plan()`'s Claude API calls use prompt caching
      (`cache_control: {"type": "ephemeral"}`) so turn *N+1* reads turn
      *N*'s shared prefix (system prompt, original plan, earlier tool
      results) from cache instead of re-billing it at full price.
- [x] Every single-shot Claude call in `plan_generator.py` and
      `plan_adaptor.py` (`generate_plan()`, `generate_sessions()`,
      `adapt_sessions()`) checks `stop_reason` and raises a clear error if
      the response wasn't `end_turn`, mirroring the truncation detection
      `adapt_plan()`'s streaming loop already has — a truncated response
      must never be silently accepted as complete (see Technical Decisions
      for why this was pulled into scope, and for why these ended up as
      `client.messages.stream()` calls rather than `.create()`).

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
- **Truncation detection extended to `generate_plan()` and
  `generate_sessions()`, not just the new `adapt_sessions()`.** Discovered
  during manual verification, not drafting: a real Adapt Plan run silently
  produced a `sessions_adapted.csv` missing an entire tail of weeks (all of
  September) because `adapt_sessions()`'s single `client.messages.create()`
  call hit `max_tokens=8192` and nothing checked `stop_reason` — the
  drop-and-warn safeguard only caught the one obviously-truncated row at
  the cut point, understating the real damage as "1 session dropped" when
  actually a third of the plan was silently missing. `adapt_plan()`'s
  streaming loop already guards against exactly this (raises clearly on a
  non-`end_turn` stop), but that check was never applied to any of the
  three plain `.create()` calls — `generate_plan()` and `generate_sessions()`
  in `plan_generator.py` have the identical unchecked gap and the identical
  risk (an original plan spanning many weeks is at least as likely to hit
  the cap as an adapted one). Fixing only `adapt_sessions()` would leave two
  call sites with the same latent bug, one number away from resurfacing as
  a fresh "story" of its own — pulled into this story's scope instead of
  filed separately, since it's the same root cause the story is already
  elbow-deep in. Added a shared `_raise_if_truncated(stop_reason, what)` in
  `plan_generator.py`, raising `RuntimeError` if `stop_reason != "end_turn"`
  — reused by `adapt_sessions()` in `plan_adaptor.py`. Also bumped
  `max_tokens` from `8192` to `32768` on all three calls, matching
  `adapt_plan()`'s existing loop — `max_tokens` is a cap, not a spend, so
  raising it has no cost impact on responses that don't need it, only
  headroom for the ones that do.
- **`max_tokens=32768` on a plain `create()` call requires switching to
  `stream()`.** The very next real run broke immediately and deterministically
  with `ValueError: Streaming is required for operations that may take
  longer than 10 minutes` — the anthropic SDK's own
  `_calculate_nonstreaming_timeout()` rejects any non-streaming call whose
  `max_tokens` implies more than ~10 minutes of generation
  (`3600 * max_tokens / 128_000 > 600`, i.e. `max_tokens > ~21,333`), before
  the request is even sent. `8192` was safely under that; `32768` wasn't.
  Rather than hand-tune `max_tokens` down to just under a threshold that
  could shift with future SDK/model changes, switched all three calls
  (`generate_plan()`, `generate_sessions()`, `adapt_sessions()`) from
  `client.messages.create()` to `client.messages.stream() as stream: ...
  stream.get_final_message()` — the exact pattern `adapt_plan()`'s loop
  already uses successfully, with no ceiling on `max_tokens` and identical
  `message.content` / `.stop_reason` / `.usage` shape, so no other code
  needed to change. Updated the fake-client test fixtures in
  `tests/test_ai_plan_adaptor.py` to drop the now-dead `.create()` fake path
  (`_FakeCreateResponse`/`create_response=`) and exercise `adapt_sessions()`
  through the same `_FakeResponse`/`.stream()` fakes `adapt_plan()`'s tests
  already used — no `generate_plan()`/`generate_sessions()` fake-client
  tests exist yet either way (pre-existing gap, not introduced here).

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
- Unit tests for `_raise_if_truncated()`: no-op on `end_turn`, raises
  `RuntimeError` mentioning both the `stop_reason` and the given context on
  anything else. Unit test: `adapt_sessions()` with a mocked `stop_reason`
  of `"max_tokens"` raises rather than writing a truncated
  `SESSIONS_ADAPTED_PATH`.
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

Built essentially as drafted, on branch `story/0010-adapted-plan-sessions-and-caching`
off `release/v4`:

- `adapt_sessions(plan_text)` added to `src/ai/plan_adaptor.py`, reusing
  `plan_generator._build_sessions_prompt()` / `_extract_csv()` directly, plus
  a new `_SESSIONS_SYSTEM` constant extracted from `plan_generator.py`'s
  `generate_sessions()` (was previously an inline string) so the two call
  sites share the identical system prompt instead of duplicating it.
- `_splice_past_sessions()` implements the deterministic splice: parses the
  generated CSV and `SESSIONS_ORIGINAL_PATH` with `csv.DictReader`, keeps
  `date < today` rows from the original, `date >= today` rows from the
  generated CSV, merges and re-sorts by `date`. Uses plain ISO-8601 string
  comparison rather than `date.fromisoformat` — lexical ordering is correct
  for `YYYY-MM-DD` and avoids per-row exception handling. Falls back to the
  generated CSV as-is (with a `logger.warning`) if the original is missing
  or fails to parse.
- **Goals-loading Technical Decision resolved to the "story 0006 merged"
  branch**: `adapt_sessions()` calls `src.goals.load_goals()` directly (no
  `GOALS_PATH` fallback) — confirmed during planning that 0006 was already
  merged into `release/v4` and `plan_adaptor.py` already imports
  `load_goals()` for other use.
- `PlanAdaptorWorker.run()` (`src/ui/workers.py`) now calls `adapt_sessions()`
  in its own `try/except` after `adapt_plan()` succeeds; a CSV-generation
  failure is logged but `finished` still fires with the adapted plan text.
- `training_tab.py`'s `_load_sessions_table()` now prefers
  `SESSIONS_ADAPTED_PATH` when present (same pattern as
  `chat_session._build_session_table()`), and `_on_plan_adapted()` calls it
  after rendering so the table refreshes without a restart/tab switch.
- Prompt caching in `adapt_plan()`'s loop: system prompt is a single
  `cache_control`-tagged block; the first user message is tagged too; on
  each `tool_use` turn the breakpoint is explicitly moved forward (stripped
  from the previous last message, added to the new tool-result message)
  rather than left stacked on every historical message — keeps the request
  under the API's 4-`cache_control`-block cap regardless of loop length.
- Test coverage: extended `tests/test_ai_plan_adaptor.py` with splice tests,
  `adapt_sessions()` end-to-end tests (fake client), and caching tests
  asserting the breakpoint moves rather than stacks. Added
  `tests/test_ui_workers.py` (first test file for `workers.py` — confirmed
  `QThread.run()` is callable directly without a `QApplication`/real thread)
  covering the CSV-failure-doesn't-roll-back-the-plan behavior.
- **Bug found and fixed during the user's manual verification pass**: the
  first real Adapt Plan run in `--test` mode produced no
  `sessions_adapted.csv`. `app.log` showed
  `AttributeError: 'ThinkingBlock' object has no attribute 'text'` inside
  `adapt_sessions()` — the model returned a `ThinkingBlock` ahead of the CSV
  text block, and `message.content[0]` isn't always the text block. The
  new CSV-failure `try/except` in `PlanAdaptorWorker.run()` worked exactly
  as designed (caught it, still saved the adapted plan, still emitted
  `finished`), but the CSV genuinely never got written — a real bug, not a
  false alarm. The identical `content[0]` assumption was already present
  in `plan_generator.py`'s `generate_plan()` and `generate_sessions()`
  (pre-existing, not introduced by this story, but sharing the exact same
  fragile pattern `adapt_sessions()` was written to mirror). Fixed all three
  call sites by adding `_extract_text_content()` to `plan_generator.py` —
  scans `message.content` for the first block(s) with a `.text` attribute
  instead of indexing `content[0]` directly (same technique
  `plan_adaptor._extract_text()` already used for the multi-turn loop, just
  not applied to the single-call sites). Added regression tests: an
  `_extract_text_content` unit test with a leading fake `ThinkingBlock` in
  `tests/test_ai_plan_generator.py`, and an `adapt_sessions()` end-to-end
  test with the same in `tests/test_ai_plan_adaptor.py`.
- **Second bug found on the next manual retry**: with the `ThinkingBlock`
  fix in place, `adapt_sessions()` got further but then raised
  `ValueError: dict contains fields not in fieldnames: None` inside
  `_splice_past_sessions()`. Root cause: the freshly model-generated CSV had
  a row with more comma-separated values than declared header columns (an
  unescaped comma in a free-text field like `description`, despite the
  prompt asking for none) — `csv.DictReader` stashes that overflow under a
  `None` restkey, and `csv.DictWriter.writerows()` rejects any key not in
  its declared `fieldnames`. `SESSIONS_ORIGINAL_PATH` itself was fine; the
  malformed row came from the model's fresh output. Initial fix was
  `extrasaction="ignore"` on the writer, but investigating further showed
  this doesn't just drop trailing overflow — when the stray comma lands
  *before* the last column, every field after it silently shifts (e.g. real
  cooldown/description text ends up discarded in the overflow while
  cooldown/description are written holding what should've been main_set's
  content). That's worse than a clean failure: plausible-looking but wrong
  data with no indication anything was off. Replaced with
  `_drop_malformed_rows()`: any row containing DictReader's `None` overflow
  key *or* a `None` value (too few fields) is dropped outright rather than
  written, and `_splice_past_sessions()`/`adapt_sessions()` now return
  `tuple[str, int]` (csv text, dropped-row count) instead of a bare `str`.
  `fieldnames` for the writer comes from `DictReader.fieldnames` (the actual
  header), not a data row's `.keys()`, so a malformed row 0 can't corrupt
  the column list either. The no-original fallback path also runs the same
  malformed-row filter (previously it returned the raw generated CSV
  untouched) but does *not* apply the past/future date split in that case —
  with nothing to splice against, there's nothing to protect for past
  dates, so date-filtering there would have silently dropped legitimate
  past-dated rows instead of preserving them. Added regression tests for
  both the trailing-overflow case and the earlier-comma shift case
  (`test_drops_row_with_comma_shifted_fields_instead_of_corrupting`,
  asserting the misassigned value never appears in the output).
- **UX addition beyond the original draft, requested after the bugs above
  made the failure mode's silence obvious in practice**: a CSV-generation
  failure previously only surfaced in `app.log` — the user had no on-screen
  indication the Sessions table hadn't updated, and dropped rows (the fix
  above) had no visibility at all. Added two signals on `PlanAdaptorWorker`
  (`src/ui/workers.py`): `sessions_failed = pyqtSignal()` for a full
  `adapt_sessions()` exception, and `sessions_incomplete = pyqtSignal(int)`
  carrying the dropped-row count for a partial success. Both are emitted
  *after* `finished` (not instead of, deliberately ordered after) so the
  adapted plan is already rendered on-screen before the modal warning
  appears — emitting first would block plan rendering behind a dialog with
  no context yet. Wired to new `_on_sessions_failed()` /
  `_on_sessions_incomplete()` slots in `training_tab.py`, each showing a
  `QMessageBox.warning` with wording specific to which case occurred. No
  change to `_load_sessions_table()`'s fallback logic was needed — since
  `SESSIONS_ADAPTED_PATH` is only ever written after `_splice_past_sessions`
  returns (whether or not rows were dropped), a full failure naturally
  leaves it untouched (absent → `SESSIONS_ORIGINAL_PATH` shown, or holding
  the last successful adaptation, correct to keep either way), while a
  partial success (some rows dropped) still writes the file normally with
  just those rows missing. Added tests in `tests/test_ui_workers.py` for
  both signals' emission order relative to `finished`, and for the
  no-emission cases (clean success, full failure).
- **Root cause of the dropped row, and a targeted prompt fix**: the user
  found the actual malformed row in their real `sessions_adapted.csv` — an
  unquoted `main_set` field containing a natural-language comma ("...NP
  target, fuel 60-80g carbs/hr and electrolytes from hour 1"). The sessions
  prompt already told the model the quoting rule ("do not wrap a field in
  quotes unless it contains a comma") but gave no worked example, and models
  follow a concrete example far more reliably than an abstract rule —
  especially for a free-text field like `main_set`/`description`, which is
  exactly where a model reaches for a natural comma. Added a worked example
  row to `_build_sessions_prompt()` in `plan_generator.py` (shared by both
  `generate_sessions()` and `adapt_sessions()`) showing a comma-containing
  field correctly wrapped in double quotes. This is a lower-risk, more
  targeted fix than switching the CSV delimiter (considered and set aside —
  that would touch `_extract_csv()`'s header check and every
  `csv.DictReader`/`DictWriter` call across four source files plus every
  test fixture, and would only narrow the failure window rather than close
  it, since the drop-and-warn safety net above still has to be the real
  backstop either way). Added `test_contains_worked_comma_quoting_example`
  to `tests/test_ai_plan_generator.py`. If malformed rows keep recurring
  after this, the delimiter change is still on the table as a second line
  of defense.
- **The prompt fix alone was not sufficient**: the very next real Adapt Plan
  run (with the prompt fix already active — confirmed from `app.log`'s
  request-body dump, which showed the new quoting instruction) still
  dropped 4 rows. Investigating turned up a separate, more fundamental gap:
  the raw model response for the sessions call is never persisted anywhere.
  The Anthropic SDK's DEBUG logging captures outgoing *requests* in full
  (`json_data`) but never response bodies (`receive_response_body.complete`
  logs no content) — confirmed by grepping `app.log`. So the 4 dropped rows
  from that run are unrecoverable; there was no way to know what they were.
  Fixed the diagnosability gap regardless of the root cause: `logger.warning`
  in `_splice_past_sessions()` now includes the full raw `generated_csv`
  text whenever any row is dropped (and a separate warning with just the
  count if the on-disk *original* CSV had a malformed row, a rarer/defensive
  case). This is the only place in the codebase the exact malformed text is
  ever visible — the CSV is parsed into rows and the source text discarded
  immediately after in the normal path. Added
  `test_logs_raw_response_when_rows_dropped` asserting the warning contains
  both the count and the exact malformed row text. Given the prompt fix
  didn't hold up under real use, the delimiter change (tab, most likely,
  since it's the least probable character in generated prose) is now a live
  option rather than a fallback — deferred pending the next real run's log,
  which will finally show the exact malformed row(s) instead of just a count.
- **The real culprit, found via the new raw-response logging: silent
  truncation, not a delimiter/quoting problem at all.** The next real run's
  `app.log` showed the actual dropped row was the *last line of the entire
  response*, cut off mid-sentence with no `cooldown`/`description` fields —
  `"...170 min steady @ Zone 2 (192-257W) with a few short Zone 3"`, then
  nothing. September wasn't parsed-and-dropped, it was never generated:
  `adapt_sessions()`'s `client.messages.create()` call had `max_tokens=8192`
  and nothing checked `stop_reason`, so a response cut off by the token cap
  midway through Week 2 was silently accepted as if complete. The "1 session
  dropped" warning was accurate but wildly understated the damage — it
  only knows about rows it can see, not about the weeks that were never
  attempted. This is the identical failure class story 0009 already fixed
  for `adapt_plan()`'s streaming loop (which does check `stop_reason` and
  raises clearly), just never applied to the plain `.create()` calls. Per
  explicit user direction, extended the fix to every call site with the
  same gap rather than just `adapt_sessions()`: added
  `_raise_if_truncated(stop_reason, what)` to `plan_generator.py` (raises
  `RuntimeError` on any non-`end_turn` stop) and applied it to
  `generate_plan()`, `generate_sessions()`, and `adapt_sessions()` — the
  first two had the identical unchecked pattern and, if anything, a higher
  truncation risk (an original plan can span far more weeks than what's
  left to adapt). Bumped `max_tokens` from `8192` to `32768` on all three,
  matching `adapt_plan()`'s existing loop; since `max_tokens` is a cap on
  cost, not a floor, this has no cost impact on runs that don't need the
  headroom. A truncated `adapt_sessions()` response now surfaces through
  the *existing* `sessions_failed` warning ("previous schedule retained")
  instead of a misleading partial-row-count — the honest signal for what
  is, in fact, a full failure of that call. Added
  `TestRaiseIfTruncated` (`tests/test_ai_plan_generator.py`) and
  `test_raises_when_response_truncated` (`tests/test_ai_plan_adaptor.py`).
  On the also-reported "Sweet Spot marked as Recovery" observation: the raw
  logged response shows `type`/`intensity` correctly say "Sweet Spot
  Intervals"/"Sweet Spot" — it's the `phase` column that says "Recovery"
  for that week, reflecting the model's own week-level framing (a deload
  week that still includes a touch of intensity) rather than a splice/parse
  defect on the code side; left as-is pending user follow-up on whether
  it's worth a prompt-level nudge.
- **The `max_tokens=32768` bump broke every `adapt_sessions()` call
  outright** on the very next real run: `ValueError: Streaming is required
  for operations that may take longer than 10 minutes`, raised by the
  anthropic SDK's `_calculate_nonstreaming_timeout()` before the request
  was even sent (`3600 * max_tokens / 128_000 > 600` at `max_tokens=32768`).
  Fixed by switching `generate_plan()`, `generate_sessions()`, and
  `adapt_sessions()` from `client.messages.create()` to
  `client.messages.stream() as stream: stream.get_final_message()` — the
  same pattern `adapt_plan()`'s loop already used, which has no such
  ceiling and returns an identically-shaped `Message`, so
  `_raise_if_truncated()`/`_extract_text_content()` needed no changes.
  Updated `tests/test_ai_plan_adaptor.py`'s fake-client fixtures to drop
  the now-unused `.create()`/`_FakeCreateResponse` path and exercise
  `adapt_sessions()` through the same `_FakeResponse`/`.stream()` fakes
  already used for `adapt_plan()`.
- Verification: `pytest` (319 passed after all fixes above), `ruff check .`
  / `ruff format .` (clean), `mypy ./` (clean, 57 files). Manual verification
  (Sessions table refresh, `sessions_log.json` alignment, `cache_read` in
  `app.log`, and now also the new failure/incomplete warning dialogs) was
  deferred to
  the user running `python main.py --test` themselves, since it requires a
  real, billed Anthropic API call plus a live intervals.icu sync against
  their real training data — not run as part of this session.
- Manual verification: Plan adaption ran on real data executed successfully.
  Logs show successful use of cache reads.

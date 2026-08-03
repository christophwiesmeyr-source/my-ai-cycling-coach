# Story Workflow

Describes the two-phase process for planning and implementing work in this
project. Written to be followed by any coding agent or by a human — it does
not assume a specific tool.

## Story Lifecycle

Stories live in `tasks/*.md`, one file per story, named `NNNN-kebab-title.md`
with a global, never-reused running number (template: `tasks/TEMPLATE.md`).

Two frontmatter fields track a story independently:

- `status` tracks definition completeness and execution: `draft -> ready ->
  in-progress -> done`. `cancelled` is a separate terminal status, reachable
  from `draft`, `ready`, or `in-progress` when a story is dropped from the
  plan — not from `done`, since reverting delivered work is a different
  kind of change. When cancelling, add a one-line reason at the top of
  Problem / Context (e.g. `Cancelled: superseded by 0007`) rather than a
  new section. Keep the story's number and `release` field as-is; numbers
  are never reused and `release` still records what it was targeted for.
  Reviving a cancelled story means setting `status` back to `draft`.
- `release` (e.g. `v3`) tracks which release the story is planned for. It
  can be set at any time, including while a story is still `draft` — that's
  the normal way to assign a batch of not-yet-fully-defined stories to an
  upcoming release during planning.

A story is "staged" once both are true: `release` is set and `status` is
`ready`. That combination — not a status value of its own — is what
`/implement-story` looks for. This lets you assign stories to a release
early and keep refining them individually until each one is ready,
without implementation ever starting on an underspecified story.
`cancelled` stories are terminal: both `/draft-story` and `/implement-story`
should refuse to act on one unless the user explicitly revives it first.

## Drafting a story

Goal: turn an idea into a story file precise enough that implementation
needs no further guessing.

1. Resolve whether this continues an existing file in `tasks/` or starts a
   new one (next running number, `tasks/TEMPLATE.md` as the starting point).
2. Work through each section collaboratively with the user, asking
   questions rather than assuming answers:
   - Problem / Context
   - Acceptance Criteria (concrete, verifiable checklist)
   - Technical Decisions (resolve code-related decisions, grounded in the
     current codebase — read source, don't guess)
   - Test Plan (how the user will verify the implementation)
   - Out of Scope
   Leave Implementation Notes empty — it's filled in during implementation,
   not drafting.
3. Update the file after each round of discussion. Keep `status: draft`
   throughout.
4. Only set `status: ready` once every section (Acceptance Criteria,
   Technical Decisions, Test Plan) has real content — no placeholders, no
   empty checklists.
5. Never write application code during drafting, and never set status
   beyond `ready`.

## Implementing a story

Goal: implement a staged story (`status: ready` and `release` set) and
prove it meets its own Test Plan.

1. Refuse to proceed unless `release` is set AND `status` is `ready`. A
   `draft` story with a `release` assigned is not yet implementable — it
   still needs to be drafted to `ready` first.
2. Confirm the branch this work will happen on was forked from the
   release branch named in the story's `release` field. Check the
   branch's fork point via its reflog (oldest entry, e.g. `branch:
   Created from release/v3`). If that information isn't available
   (expired reflog, fresh clone, etc.), stop and ask the user to confirm
   which release branch this work is based on rather than guessing from
   commit ancestry.
3. Produce a concrete step-by-step implementation plan from Acceptance
   Criteria and Technical Decisions, and get it confirmed before writing
   code. If a Technical Decision conflicts with the current codebase,
   surface the conflict rather than silently overriding either the story
   or the decision.
4. Once confirmed, set `status: in-progress` and implement, following this
   project's CLAUDE.md conventions.
5. Run the project's checks (see CLAUDE.md Commands) and fix failures
   before proceeding.
6. Walk through every Test Plan item and verify it against the actual
   implementation; report anything that couldn't be verified.
7. Write the Implementation Notes section: what was actually built,
   especially where it deviates from the drafted Technical Decisions and
   why, plus any concrete results worth recording (e.g. a measured
   improvement). This is not optional — treat it as part of the
   deliverable, not an afterthought.
8. Only set `status: done` once all Acceptance Criteria are met, the Test
   Plan is verified, and Implementation Notes is filled in. Don't commit
   the changes — leave that for the user to review and commit.

If a story is underspecified enough that a code-related decision isn't
covered by Technical Decisions, stop and ask rather than guessing.

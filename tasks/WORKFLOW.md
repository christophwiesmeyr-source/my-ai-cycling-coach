# Story Workflow

Describes the two-phase process for planning and implementing work in this
project. Written to be followed by any coding agent or by a human — it does
not assume a specific tool.

## Story Lifecycle

Stories live in `tasks/*.md`, one file per story, named `NNNN-kebab-title.md`
with a global, never-reused running number (template: `tasks/TEMPLATE.md`).
Status lives in frontmatter and moves through:

```
draft -> ready -> staged -> in-progress -> done
```

`release` is set once a story is staged (e.g. `v3`).

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
3. Update the file after each round of discussion. Keep `status: draft`
   throughout.
4. Only set `status: ready` once every section (Acceptance Criteria,
   Technical Decisions, Test Plan) has real content — no placeholders, no
   empty checklists.
5. Never write application code during drafting, and never set status
   beyond `ready`.

## Implementing a story

Goal: implement a `staged` story and prove it meets its own Test Plan.

1. Refuse to proceed if status is not `staged` (a `ready` story is well-
   defined but not yet committed to a release, and therefore has no
   branch to implement on).
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
7. Only set `status: done` once all Acceptance Criteria are met and the
   Test Plan is verified. Don't commit the changes — leave that for the
   user to review and commit.

If a story is underspecified enough that a code-related decision isn't
covered by Technical Decisions, stop and ask rather than guessing.

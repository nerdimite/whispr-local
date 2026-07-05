---
name: to-plan
description: Turn a grill-me, brainstorm, or design discussion into a granular, TDD-structured Cursor `.plan.md` — tracer-bullet vertical slices with red/green tests, design pseudocode, a dependency DAG, and subagent dispatch guidance — written to `.cursor/plans/`. Use when the user wants to convert the current discussion, a spec, or an ADR into an executable plan file.
---

# To Plan

Convert the current discussion into a **Cursor-consumable `.plan.md`**: an ordered set of
tracer-bullet build slices, each with its failing test (🔴), the minimal code to pass it (🟢),
design/algorithm pseudocode, and parallelization metadata.

This is the bridge between a **grill-me / brainstorm** (decisions crystallised) and **execution**
(in Cursor, or by dispatching slices to subagents). It does not write production code — it writes
the plan that drives it.

## Operating principles

- **Tracer-bullet vertical slices**: each slice cuts end-to-end through every layer (schema → logic
  → public entrypoint → test) and is independently verifiable/demoable. Prefer many thin slices over
  few thick ones. The first slice is a tracer bullet that proves the whole path works end-to-end.
  Tag each `AFK` (an agent can finish and verify it alone) or `HITL` (needs a human decision or
  review); prefer AFK.
- **Red→green, one behavior at a time**: every slice names ONE failing test (🔴) then the minimal
  code to green it (🟢). Never list all tests up front across slices — that "horizontal slicing"
  produces tests of imagined behavior. Tests assert observable behavior through the public
  interface, not implementation, so they survive refactors.
- **Domain vocabulary**: slice titles, test names, and interfaces use the project's `CONTEXT.md`
  glossary and respect ADRs in the area being touched.

## Process (draft-and-write, one-shot)

1. **Gather context.** Work from the current conversation. If the user passes a reference (issue
   ID/URL, ADR, file path), read it. Skim `CONTEXT.md` and relevant `docs/adr/*` so vocabulary and
   decisions are honoured. **If a design doc exists for this work (`docs/design/*.design.md`), read
   it — it is the authoritative technical design — and link it at the top of the plan and in the
   `design:` frontmatter field.**
2. **Decompose into slices.** Break the work into tracer-bullet slices in dependency order. For
   each, decide its red test, minimal green, design notes, `AFK`/`HITL`, `blocked-by`, and parallel
   `group`. Identify a tracer-bullet first slice that proves the whole path end-to-end.
3. **Write the file** directly to `.cursor/plans/` using [PLAN-FORMAT.md](./PLAN-FORMAT.md). No
   pre-write quiz — write it, then iterate with the user on the file. The written plan must tell the
   implementer to use the `/tdd` skill (if available) for the red→green build loop.
4. **Report**: print the path and a one-line summary of the slice count + parallel groups. Invite
   edits.

## Output location & filename

- Default directory: **`.cursor/plans/`** (create if missing). Honour an explicit path if the user
  gives one.
- **If a plan for this topic already exists** in `.cursor/plans/`, update it in place (keep its
  filename so Cursor keeps tracking it).
- Otherwise create `<kebab-name>_<8hexchars>.plan.md` (e.g. `pdf_decondenser_module_b9c6fed0.plan.md`)
  — the hex suffix matches Cursor's convention; generate it from a hash of the name/timestamp.

## Frontmatter is the todo list

The YAML frontmatter `todos` array **is** the build order — one todo per slice, `id` matching the
slice heading in the body. Cursor renders these as tracked checkboxes; the body holds the granular
detail per `id`. Keep `content` to a single line; never put detail only in the body without a
matching todo, and never add a todo without a body slice.

See [PLAN-FORMAT.md](./PLAN-FORMAT.md) for the full template and conventions.

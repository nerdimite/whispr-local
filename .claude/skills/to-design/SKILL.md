---
name: to-design
description: Turn a grill-me or brainstorm discussion into a concise, self-contained technical design doc at docs/design/<slug>.design.md — data-flow mermaid, module/file-role map, crystallized decisions, and pseudo-snippets — as the review gate before implementation planning. Typically invoked manually. Use for a technical/architecture artifact to review before writing a plan; for end-user/product framing use to-prd, for executable build slices use to-plan.
---

# To Design

Synthesize the current discussion into a **self-contained technical design doc** — the review gate
between **grill-me** (decisions crystallised) and **to-plan** (execution slices). It renders what
was already decided into a reviewable architecture artifact. It does not re-interview, and it does
not write code.

## Operating principles

- **One-shot synthesis, no interview.** This is a follow-up to a grill-me / brainstorm — work from
  the conversation, do not re-litigate decisions. Genuine gaps go into the doc's "Open questions for
  the reviewer" section, never blocking prompts. If the decisions are still fuzzy, that is a signal
  to run grill-me first, not to interview here.
- **Self-contained on decisions, terse in form, silent on execution.** Every technical decision
  taken in the session must be ingrained in the doc so it stands alone as the architecture — none
  dropped for brevity. Express each in its tersest faithful form (a table row, a bullet, a
  decision-encoding pseudo-snippet), never a paragraph of justification; add one clause of rationale
  only when non-obvious. Never enumerate build steps, test cases, or slice ordering — that is
  to-plan's job, and the moment the doc starts sequencing work it has leaked into plan territory.
- **The mirror image of a PRD.** to-prd forbids file paths and snippets and frames user stories;
  to-design REQUIRES the module/file-role map and uses pseudo-snippets, and never writes a user
  story. PRD = features from the end-user perspective; design = technical artifact from the
  implementation standpoint. If you are drawing the directory tree and the data flow, it is a design
  doc.
- **Reference decisions, do not author them.** Use the CONTEXT.md glossary vocabulary and link
  relevant ADRs; never write CONTEXT.md or ADRs here (that is grill-me's job). If a decision looks
  ADR-worthy but was not captured, flag it under Open questions.
- **Domain vocabulary.** Titles, terms, and interfaces use the project's CONTEXT.md glossary and
  respect the ADRs in the area being touched.

## Process (one-shot, write-then-iterate)

1. **Gather context.** Work from the current conversation. Read any referenced material (issue, ADR,
   PRD, files). Explore the repo to ground the file/module map in reality, and skim CONTEXT.md plus
   the relevant docs/adr/* so vocabulary and decisions are honoured.

2. **Inventory the decisions.** Before writing, list every technical decision the session settled —
   completeness is the bar (the doc must be self-contained). Anything still open becomes an Open
   question rather than an invented answer.

3. **Write the doc** to `docs/design/<slug>.design.md` (create the directory lazily) using
   [DESIGN-FORMAT.md](./DESIGN-FORMAT.md). Keep it review-optimised — a human should be able to
   approve the shape in one sitting. The mermaid data-flow and the file/module-role map are the two
   signature-required sections.

4. **Stop for review.** It is a gate: present the doc for the user to read and iterate on the file.
   Once approved, point at /to-plan (which references this design doc at the top of the plan).

## Chaining

grill-me (decisions) → [to-prd if user-facing] → **to-design** (technical shape) → to-plan (slices).
Stands alone for internal refactors (skip to-prd). to-plan reads and links the design doc when one
exists.

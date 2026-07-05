# Design Doc Format

A `<slug>.design.md` is a concise, **self-contained** technical design — the review gate before a
plan. Optimise for "a human can approve the shape in one sitting." Complete on **decisions**, terse
in **form**, silent on **execution** (no build steps, test lists, or slice ordering — that is the
plan's job).

## Header

```md
# Design — <subject>

> Design note for review. Decisions are recorded in the linked ADRs; this renders the technical
> shape. Links: ADR-00XX (decisions), PRD <id> (if user-facing).
```

## Sections

Two are **signature-required** — without them it is a spec, not a design doc:

- **Mermaid — data / control flow** (required). The moving parts and how a request or data travels
  end to end. Sequence or flowchart, whichever reads cleaner.
- **File / module map with roles** (required). The directory tree (or a table) of files to
  create/change, each with a one-line role. This is the mirror-image-of-PRD signature — the thing a
  PRD is forbidden to contain.

Always include:

- **Goals** — 3–5 bullets framing the review.
- **Decisions** — the crystallised choices, one terse row or bullet each. This is the self-contained
  core: every technical decision the session settled must appear here.
- **Non-goals** — the scope fence; link the ADR that owns it.
- **Open questions for the reviewer** — where one-shot gaps surface, plus any "this looks
  ADR-worthy, capture via grill-me" flags.

Include when they earn their place:

- **Component / layering mermaid** — when import-direction or dependency rules matter (e.g. "service
  must not import api/schema").
- **Type / schema placement table** — for refactors that move things ("X today → lands in Y, why").
- **Pseudo-snippets** — only when a snippet encodes a decision better than prose can (a client
  signature, a state/reducer shape, a key seam). Trim to the decision-rich bits; not working code.

## Style

- Tables and bullets over paragraphs; mermaid over prose for any flow.
- Every decision from the session is present, each in its tersest faithful form.
- Rationale only when non-obvious, and then one clause.
- Use the CONTEXT.md glossary terms; link ADRs rather than restating them.
- No sequencing language ("first… then…", "step 1"), no test enumeration — that signals leakage into
  to-plan territory; cut it.

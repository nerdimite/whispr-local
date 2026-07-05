# Plan Format

A `.plan.md` has two parts: **Cursor YAML frontmatter** (kept verbatim so Cursor renders todos) and
a **markdown body** whose slices are keyed to the frontmatter `todos` by `id`.

## Frontmatter

```yaml
---
name: <plan name>                 # short, human title
design: docs/design/<slug>.design.md   # link to the design doc if one exists (omit if none)
overview: >                       # one self-contained paragraph: what we're building & why
  ...
todos:                            # THE build order — one entry per body slice
  - id: <kebab-slug>              # must match a "### Slice — …  {#id}" heading below
    content: <one-line summary>   # what this slice delivers; keep to one line
    status: pending               # pending | in-progress | completed | error
isProject: false                  # true only for large multi-phase plans
---
```

Rules:
- Every todo `id` has exactly one body slice, and every body slice has exactly one todo. No orphans.
- Todos are in **dependency / build order** (tracer-bullet slice first).
- `content` is a single line; the richness lives in the body slice.

## Body

```md
# <Title>

<One-liner.> Design: <docs/design/...design.md, if any> · Issue: <ID/URL> · ADRs: <list> · Glossary: <CONTEXT.md terms touched>

> **Implementation:** build with the `/tdd` skill if available — work one slice at a time,
> 🔴 red → 🟢 green → refactor, asserting behavior through the public interface.

## Invariants & decisions
- The non-negotiables carried out of the grill-me/brainstorm (so the plan stands alone).
- Each: a crisp rule, not a discussion.

## Architecture
- Module / file map (what each file owns).
- Seams (interfaces/protocols that make slices testable, e.g. an injected fake).
- Optional mermaid data-flow.

## Build order

### Slice 1 — <title>   `AFK` · group A · blocked-by: none   {#slice-1}
🔴 **Red** — `path::test_name`: <the behavior the test pins, through the public interface>.
🟢 **Green** — <the minimal code that passes it>.
**Design**
- algorithm bullets / pseudocode (decision-rich, not a full impl)
**Done when** — <observable acceptance bullets>; prior slices still green.

### Slice 2 — <title>   `AFK` · group A · blocked-by: slice-1   {#slice-2}
...

## Parallelization
- **DAG**: `slice-1 → {slice-2, slice-3}` (mermaid or arrows). Slices sharing a `group` with no
  edge between them run concurrently.
- Mark the critical path.

## Parallel execution (subagent dispatch)
For each parallel group, how to fan out:
- **Group A** (after slice-1): dispatch `slice-2`, `slice-3` to separate subagents.
  - **model**: default each subagent to **`composer-2.5-fast`**. Escalate a slice to **`gpt-5.4`
    (medium effort)** only when it is genuinely complex (intricate algorithm, cross-cutting design
    judgement, gnarly debugging) — note the chosen model per slice and why if escalated.
  - each subagent gets: the slice's Red/Green/Design block + the Invariants section + the seam it
    codes against; it returns a diff + its test passing.
  - integration: merge order, who owns shared files (avoid two agents editing the same file).
- Note any slice that must stay on the main thread (HITL, or touches a shared scaffold).

## Dependencies / setup
- New deps (`uv add ...`), env/config, fixtures to build.
```

## Conventions

- **🔴 / 🟢** mark the red→green pair. Exactly one primary behavior per slice. Never list all red
  tests up front across slices — that "horizontal slicing" tests imagined behavior and is forbidden.
- **`AFK` / `HITL`** — AFK = an agent can finish & verify it alone; HITL = needs a human decision or
  review. Prefer AFK.
- **`blocked-by`** — slice ids (or `none`). **`group`** — a label; same group + no blocking edge =
  parallelizable.
- **Vertical, not horizontal** — a slice drives behavior through the public entrypoint (e.g.
  `normalize()`), not "implement layer X". A completed slice is demoable.
- **Deterministic vs probabilistic** — when a plan spans both (per the project's testing split),
  say which slices are **unit-tested** and which are **eval-tested**, and put the deterministic
  tracer bullet first (it needs no live API).
- Keep design blocks decision-rich (state shapes, geometry, guards) but avoid full code dumps —
  detail that goes stale belongs in the code, not the plan.

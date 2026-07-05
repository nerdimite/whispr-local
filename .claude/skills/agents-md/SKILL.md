---
name: agents-md
description: Scaffold a new AGENTS.md file or audit an existing one against research-backed best practices. Use when the user asks to create, write, review, improve, or scaffold an AGENTS.md (or CLAUDE.md) file, or when setting up a new project's agent configuration.
---

# AGENTS.md Scaffolding & Audit

Write or audit the highest-leverage configuration file for coding agents. Every line goes into every session — make each one count.

**Announce at start:** "I'm using the agents-md skill to [scaffold / audit] the AGENTS.md file."

## Decide Mode

- **AGENTS.md exists and is non-empty** → run Audit workflow
- **AGENTS.md is empty or missing** → run Scaffold workflow
- User can request either mode explicitly

---

## Scaffold Workflow

### Phase 1: Gather Context

Explore the project before asking questions:

1. Read `package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, or equivalent
2. Check top-level directory structure (one level deep only)
3. Look for existing docs, READMEs, CI configs
4. Check for monorepo indicators (workspaces, multiple service dirs)

### Phase 2: Ask the Three Questions

Ask the user **one question at a time**. Prefer multiple choice when possible.

**WHAT** — Tech stack, project structure, what each part does:
- "What's the tech stack?" (often inferrable from Phase 1 — confirm rather than ask)
- For monorepos: "What are the apps/packages and what does each one do?"
- "Any non-obvious project structure the agent should know about?"

**WHY** — Purpose and intent:
- "In one sentence, what does this project do?"
- "What are the key domain concepts an agent needs to understand?"

**HOW** — Build, test, verify:
- "How do you build and run this project?"
- "How do you run tests?"
- "Any non-standard tooling?" (e.g., `uv` not `pip`, `bun` not `npm`, `just` not `make`)
- "Any critical gotchas an agent should know?" (e.g., "never modify migrations directly")

### Phase 3: Draft AGENTS.md

Write the file following the Content Rules below. Present it to the user for review before saving.

### Phase 4: Progressive Disclosure via Nested AGENTS.md

Keep the root file lean and push layer-specific guidance into **nested AGENTS.md files colocated
with each top-level layer** (e.g. `src/api/AGENTS.md`, `src/dao/AGENTS.md`). A colocated AGENTS.md is
auto-discovered by the harness when an agent works in that subtree, so the right context loads on
demand without the agent needing to know to go read it.

1. Identify the top-level layers worth documenting (one level deep — the dirs an agent actually edits
   within: api, services, dao/data, types, migrations, tests, etc.). Only layers with non-obvious,
   layer-specific rules need a file.
2. Add a **Layer Index** table at the **end** of the root AGENTS.md pointing at them:

```markdown
## Layer Index — nested AGENTS.md

Each layer has a colocated AGENTS.md; read the one for the code you're changing.

| File | When to read |
|------|--------------|
| `src/api/AGENTS.md` | Adding/altering a route or DI wiring |
| `src/dao/AGENTS.md` | Changing persistence, ORM models, or migrations |
| `src/types/AGENTS.md` | Adding or changing DTOs |
```

3. Create a nested `AGENTS.md` stub only where there is real layer-specific guidance to capture —
   lazily, not for every empty directory.

### Phase 5: Save & Commit

1. Write AGENTS.md to the project root (including the Layer Index table)
2. Create the nested layer AGENTS.md files you identified (only where there is real guidance)
3. Offer to commit using the **commit** skill

---

## Audit Workflow

### Step 1: Read the existing AGENTS.md

### Step 2: Check against each rule

Run through the Audit Checklist below. For each issue found, note:
- **Line(s)** affected
- **Issue** — what's wrong
- **Fix** — specific suggestion

### Step 3: Present findings

Group by severity:
- **Remove** — content that actively hurts (auto-generated fluff, code style rules, stale snippets)
- **Move** — layer-specific instructions that belong in a nested layer AGENTS.md (e.g. `src/dao/AGENTS.md`), not bloating the root
- **Revise** — content that should stay but needs tightening
- **Missing** — required sections (Tech Stack & Architecture, Project Purpose, Development Workflow, Dos and Don'ts) that are absent

### Step 4: Offer to apply fixes

After user approves, edit the file and offer to commit.

---

## Content Rules

These rules govern what goes into AGENTS.md. For the research behind them, see [references/best-practices.md](references/best-practices.md).

### Target: Under 300 lines, ideally under 100

Every line goes into every session. Ruthlessly cut anything that isn't universally applicable.

### Five Required Sections

**WHAT** — Stack, structure, key components:
```markdown
## Tech Stack & Architecture

- Python 3.12 / FastAPI / PostgreSQL / Redis
- Monorepo: `services/api`, `services/worker`, `packages/shared`
- `services/api` — REST API serving the frontend
- `services/worker` — Background job processor
- `packages/shared` — Shared types and utilities
```

**WHY** — Purpose and domain context:
```markdown
## Project Purpose

Invoice processing platform. Extracts line items from uploaded PDFs,
matches them against purchase orders, flags discrepancies for review.

Key domain terms: invoice, line item, purchase order, discrepancy, review queue.
```

**HOW** — Build, test, verify:
```markdown
## Development Workflow

- Build: `uv sync` (NOT pip install)
- Run: `docker compose up`
- Test: `pytest` from repo root
- Lint: `ruff check . --fix && ruff format .`
- Type check: `pyright`
```

**DOS AND DON'TS** — Human-curated project rules and constraints:

These are known project rules written by the team — things agents should always do or never do. Unlike Agent Memory (which is auto-maintained by hooks), this section is manually curated.

When scaffolding, seed it with a placeholder:
```markdown
## Dos and Don'ts

<!-- Add project-specific rules here. Each entry should be a short, direct instruction. -->

(none yet — add rules as you establish project conventions)
```

When populated, it looks like:
```markdown
## Dos and Don'ts

- Use `uv`, not pip — all dependency management goes through uv
- Run all commands from `backend/`, not the repo root
- Use `BaseServiceException` subclasses for service errors, not raw HTTPException
- Put new API routes in the router file, not in `main.py`
- Name migration files descriptively (`add_user_email_column`), not auto-generated
- Never modify migrations directly after they've been applied
```

**AGENT MEMORY** — Living section for learned preferences and workspace facts:

This is a living section maintained both by humans and by automated hooks (like the continual-learning hook). It has two subsections:

- `### Learned User Preferences` — Short "do X, not Y" corrections from actual usage. Grows as the human observes agent behavior that doesn't match their preferences.
- `### Learned Workspace Facts` — Durable facts about the workspace that agents need to know (key files, team names, project relationships).

When scaffolding, seed it with a placeholder:
```markdown
## Agent Memory

### Learned User Preferences

<!-- Add rules here as you notice agents doing things the wrong way.
     Each rule should be a short, direct correction: "do X, not Y."
     This section is also auto-maintained by the continual-learning hook. -->

(none yet — update this section as you work with agents on this codebase)

### Learned Workspace Facts

<!-- Durable facts about the workspace. Auto-maintained by the continual-learning hook. -->

(none yet — facts are added as agents learn about the codebase)
```

When populated, it looks like:
```markdown
## Agent Memory

### Learned User Preferences

- When creating Linear issues, put status, priority, assignee, and labels in Linear MCP fields; do not add a Metadata section in the issue body.
- Use `raise HTTPException` with `detail=`, not custom exception classes
- Put new API routes in the router file, not in `main.py`

### Learned Workspace Facts

- `docs/issues-rd.md` defines the backend PRD and issue requirements for the Cursor Fleet Dashboard.
- Internal Utilities is the Linear team for agent-fleet backend work.
```

These entries are short, authoritative, and universally applicable — exactly the kind of instruction agents follow well. They stay in the root AGENTS.md (not in a nested layer AGENTS.md) because they apply to every session.

### Do Include

- Non-obvious tooling choices (tools mentioned get used **160x** more)
- Critical constraints and gotchas ("never modify migrations directly")
- Dos and Don'ts — human-curated project rules and constraints
- Agent Memory — learned preferences ("do X, not Y") and durable workspace facts
- A Layer Index pointing to nested per-layer AGENTS.md files for layer-specific guidance
- Environment setup steps if non-trivial

### Do NOT Include

- **Codebase overviews or directory trees** — agents discover structure themselves
- **Code style guidelines** — use linters/formatters instead (faster, cheaper, deterministic)
- **Layer-specific instructions** — move to that layer's nested AGENTS.md
- **Code snippets** — they go stale; use `file:line` pointers instead
- **Auto-generated content** — reduces success rate ~3%, increases cost 20%+

### Use Progressive Disclosure

Push layer-specific guidance into nested AGENTS.md colocated with each layer, and index them from
root rather than embedding everything:

```markdown
## Layer Index — nested AGENTS.md

| File | When to read |
|------|-------------|
| `src/tests/AGENTS.md` | Before writing or modifying tests |
| `src/migrations/AGENTS.md` | Before creating database migrations |
```

A nested AGENTS.md is auto-loaded when an agent works in that subtree, so the deeper context arrives
on demand. If a layer needs a long-form doc, link it from that layer's AGENTS.md rather than the root.

### Use Pointers Over Copies

```markdown
# Good — points to the source of truth
See auth middleware implementation: `src/middleware/auth.ts:15-45`

# Bad — will go stale
Here's how auth works:
\`\`\`typescript
// 50 lines of code that will drift from reality
\`\`\`
```

---

## Audit Checklist

| # | Check | Pass criteria |
|---|-------|---------------|
| 1 | Line count | < 300 lines (ideally < 100) |
| 2 | Has Tech Stack & Architecture section | Stack + structure + component purposes |
| 3 | Has Project Purpose section | Project purpose + domain terms |
| 4 | Has Development Workflow section | Build + test + lint commands |
| 5 | Has Dos and Don'ts section | Present (even if empty placeholder) for human-curated rules |
| 6 | Has Agent Memory section | Present (even if empty placeholder) with Learned User Preferences and Learned Workspace Facts subsections |
| 7 | No code style rules | Style enforcement belongs in linters |
| 8 | No directory trees | Agents discover structure themselves |
| 9 | No embedded code | Uses `file:line` pointers instead |
| 10 | No layer-specific instructions in root | Moved to the relevant nested layer AGENTS.md |
| 11 | No auto-generated fluff | Every line is deliberate and useful |
| 12 | Agent Memory entries are concise | Each preference is "do X, not Y" — short and direct; each fact is a single sentence |
| 13 | Non-obvious tools mentioned | e.g., `uv`, `bun`, `just` — these get used 160x more |
| 14 | Progressive disclosure | Has a Layer Index pointing to nested per-layer AGENTS.md; doesn't embed their detail in root |
| 15 | Critical gotchas present | Things that would waste an agent's time if unknown |

---

## Anti-Patterns

- **"Kitchen sink" files** — stuffing everything in AGENTS.md degrades instruction-following uniformly across all instructions
- **Auto-generating the file** — LLM-generated files are redundant with existing docs and hurt performance
- **Detailed codebase tours** — agents navigate fine without them; these just consume tokens
- **Embedded code** — drifts from reality; use pointers
- **Style guides** — use `pyright`, `ruff`, `eslint`, `prettier`, `biome` instead

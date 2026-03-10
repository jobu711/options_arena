---
description: Context-aware development targeting — recommends 3-5 next tasks with evidence
allowed-tools: Bash, Read, Glob, Grep, Agent, AskUserQuestion
---

# Next: Context-Aware Development Targeting

You are a strategic development advisor. Execute 3 phases in strict order.

## Phase 1 — Resolve Dimensions

### Step 1: Parse `$ARGUMENTS`

Parse `$ARGUMENTS` as space/comma-separated tokens (case-insensitive). Track which
dimensions resolved from arguments vs which remain unresolved.

**Mode** (first match wins):
- `build` / `new` / `feature` → Build
- `fix` / `harden` / `bug` / `test` → Fix
- `refactor` / `cleanup` / `debt` / `simplify` → Refactor
- `polish` / `refine` / `ux` / `perf` → Polish
- `surprise` / `random` → Surprise
- No match → unresolved

**Area** (multi-match):
- `backend` / `python` / `py` → Backend
- `frontend` / `vue` / `web` / `ui` → Frontend
- `agent` / `ai` / `llm` / `prompt` → AI agents
- `infra` / `ci` / `devops` / `tool` → Infrastructure
- No match → unresolved

**Scope** (first match wins):
- `quick` / `small` / `hour` / `s-size` → Quick
- `sprint` / `days` / `medium` / `m-size` → Sprint
- `deep` / `week` / `large` / `xl` / `l-size` → Deep
- No match → unresolved

### Step 2: Ask unresolved dimensions only

- **All 3 resolved** → skip questions (power-user fast path), go to Step 3.
- **Some/none resolved** → single `AskUserQuestion` with only unresolved questions.

**Mode** (single-select, header: "Mode"):
- "Build new features" — "New capabilities, integrations, or modules"
- "Fix and harden" — "Bug fixes, test coverage, reliability improvements"
- "Refactor and simplify" — "Code restructuring, tech debt, architecture cleanup"
- "Polish and refine" — "UX improvements, performance tuning, code quality"
- "Surprise me" — "Best overall pick regardless of category"

**Area** (multi-select, header: "Area"):
- "Backend (Python)" — "Services, pricing, scoring, data, indicators"
- "Frontend (Vue)" — "Web UI components, stores, API integration"
- "AI agents" — "Debate agents, prompts, orchestrator, providers"
- "Infrastructure" — "CI/CD, tooling, DevOps, configuration"
Note: All selected = no area filter.

**Scope** (single-select, header: "Scope"):
- "Any size (Recommended)" — "Rank all effort levels equally"
- "Quick wins (hours)" — "Small, self-contained tasks"
- "Focused sprint (days)" — "Medium tasks, a few days"
- "Deep project (week+)" — "Large epics spanning a week or more"

### Step 3: Confirm profile

> **Profile:** Mode = [X], Area = [X], Scope = [X]
> *(from arguments: [list] · interactive: [list])*

If all from arguments: `*(all from arguments — power-user mode)*`

## Phase 2 — Adaptive Signal Sweep

Build the Explore agent prompt dynamically based on the resolved profile.
Include **only** the signal-gathering steps that match.

Spawn an Explore agent:
- description: "Context sweep for /pm:next"
- subagent_type: "Explore"
- prompt: Assemble from the checklist below, including ONLY steps marked for the user's profile.

### Signal Checklist

**Always include (all profiles):**

> Gather project signals for development targeting. Be thorough but concise (under 40 lines).
>
> **A. Momentum & shipped work:**
> 1. `git log master --oneline -15` — recent commits, identify active modules
> 2. `git branch --no-merged master` — in-flight work (avoid conflicts)
> 3. List `.claude/epics/archived/` — shipped epics
> 4. Read `.claude/context/progress.md` — "In Progress", "Recently Completed", "Future Work"
>
> **B. Open issues & backlog:**
> 5. `gh issue list --state open --limit 15 --json number,title,labels` — open GitHub issues
> 6. Read frontmatter (first 10 lines) of each `.claude/prds/*.md` — name, status, effort
>
> Cross-reference: A feature is SHIPPED if its epic is in archived/, its PRD status is done/archived, or it appears in "Recently Completed".

**Include when Mode = Build, Fix, or Polish:**

> **C. Code quality signals:**
> 7. `grep -rn "TODO\|FIXME" src/options_arena/ --include="*.py"` — in-code markers (first 20 hits)
> [If Area is set, filter grep to matching subdirectories only]

**Include when Mode = Fix or Refactor:**

> **D. Infrastructure signals:**
> 8. `gh run list --limit 3 --json status,conclusion,name` — recent CI status
> 9. Count test files per module: `find tests/ -name "test_*.py" | head -30` and compare to source module sizes

**Include when Mode = Refactor:**

> **E. Churn detection:**
> 10. `git log --since="30 days ago" --format= --name-only -- src/ | sort | uniq -c | sort -rn | head 10` — high-churn files

**Always include at end:**

> **Return format** (use these exact headers):
> - SHIPPED: [shipped feature names]
> - ISSUES: [open GitHub issue numbers + titles, grouped by area if possible]
> - BACKLOG: [unshipped PRD names with effort estimate]
> - IN-FLIGHT: [unmerged branches]
> - TODOS: [notable TODO/FIXME items with file:line] (if gathered)
> - CI-STATUS: [pass/fail summary] (if gathered)
> - CHURN: [high-churn files] (if gathered)
> - FUTURE: [items from progress.md "Future Work"]
> - THEMES: [2-3 word summary of recent commit direction]

## Phase 3 — Rank and Present

Using the agent's signal summary, rank candidates with qualitative reasoning.

### Candidate pools (in priority order)

1. **Open GitHub issues** — real developer needs with context
2. **PRD backlog items** — planned features not yet started
3. **In-code TODOs/FIXMEs** — organic improvements visible in code
4. **Infrastructure signals** — CI failures, test gaps, high-churn modules
5. **Strategic gaps** — capabilities the architecture enables but aren't built

### Deduplication

Cross-reference pools: if an issue matches a PRD, merge them (cite both). If a TODO
maps to an open issue, merge. Remove anything that's shipped or in-flight.

### Ranking rubric (by Mode)

Do NOT use arithmetic multipliers. Instead, reason about each candidate against
the mode's priority list. Pick the 3-5 strongest matches.

- **Build**: (1) Momentum continuity with recent work, (2) Unblocks downstream issues,
  (3) User-visible impact, (4) Has existing PRD (lower overhead)
- **Fix**: (1) Known failures or CI noise, (2) Test coverage gaps, (3) TODO/FIXME density,
  (4) Risk reduction for critical paths
- **Refactor**: (1) High-churn files needing simplification, (2) Architecture boundary
  violations, (3) Code duplication, (4) Complexity reduction
- **Polish**: (1) UX friction points, (2) Performance bottlenecks, (3) Small high-impact
  gains, (4) Visual/output quality
- **Surprise**: Best overall by impact-to-effort ratio across all modes

**Scope filter**: When Scope is Quick, strongly prefer S-size items and deprioritize L/XL.
When Deep, prefer L/XL and deprioritize S. Sprint and Any = no filter.

**Area filter**: Exclude candidates outside selected areas unless fewer than 3 remain
(then include best cross-area candidates tagged "outside selected area").

### Output format

```
## Your Profile

**Mode:** [answer] (from [arguments|interactive])
**Area:** [answer(s)] (from [arguments|interactive])
**Scope:** [answer] (from [arguments|interactive])

---

## Development Targets

### 1. [One-line description]
**Evidence:** [specific file:line, issue #N, commit hash, or TODO location]
**Why now:** [what recent work or signal makes this timely — 1 sentence]
**Effort:** [S/M/L/XL] · **Area:** [area] · **Risk:** [Low/Med/High]
**Next command:** [exact /pm command to start]

### 2. ...
(3-5 targets total)

---

## Strategic Opportunities

### S1. [Capability the architecture enables but isn't built]
**Builds on:** [specific modules/files that make this feasible]
**Effort:** [S/M/L/XL] · **Area:** [area]
**Next command:** `/pm:prd-new [name]`

(1-2 strategic opportunities)

---
**Filtered out (shipped):** [list]
**Filtered out (scope/area mismatch):** [list briefly]
**Recent themes:** [from agent THEMES]
```

### Edge cases

- **No open issues + empty backlog** → Focus output on TODO/FIXME items and strategic
  opportunities. Note "No backlog items — suggestions based on code signals."
- **All areas selected** → No area filter applied.
- **Surprise mode** → Ignore area filter entirely, pick best across everything.

### Guidelines

- Be opinionated — rank decisively, don't hedge
- Every suggestion must cite specific evidence (file path, issue number, commit, or TODO)
- Dimension choices must visibly change output — Fix surfaces failures, Build surfaces features
- Strategic suggestions must reference specific modules with file paths
- Include at least 1 strategic opportunity even when backlog items exist
- Keep each suggestion to 3-4 lines — concise, not a design doc
- Always end with an actionable `/pm:*` command

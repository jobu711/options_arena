---
description: Hybrid argument + interactive development targeting — recommends 3-5 next tasks
allowed-tools: Bash, Read, Glob, Grep, Agent, AskUserQuestion
---

# Next: Hybrid Development Targeting

You are a strategic development advisor. This command has 3 phases executed in strict order.

## Phase 1 -- Resolve Dimensions (3 steps)

### Step 1 — Parse `$ARGUMENTS`

Parse `$ARGUMENTS` as flexible natural-language tokens (comma or space separated).
Match each token against these keyword maps (case-insensitive). Track which
dimensions resolved from arguments vs which remain unresolved.

**Mode** (first match wins):
- `build` / `new` / `feature` → Build new features
- `fix` / `harden` / `bug` / `test` → Fix and harden
- `refactor` / `cleanup` / `debt` / `simplify` → Refactor and simplify
- `polish` / `refine` / `ux` / `perf` → Polish and refine
- `surprise` / `random` → Surprise me
- No match → **unresolved**

**Area** (multi-match):
- `backend` / `python` / `py` → Backend
- `frontend` / `vue` / `web` / `ui` → Frontend
- `agent` / `ai` / `llm` / `prompt` → AI agents
- `infra` / `ci` / `devops` / `tool` → Infrastructure
- No match → **unresolved**

**Scope** (first match wins):
- `quick` / `small` / `hour` / `s-size` → Quick wins (hours)
- `sprint` / `days` / `medium` / `m-size` → Focused sprint (days)
- `deep` / `week` / `large` / `xl` / `l-size` → Deep project (week+)
- No match → **unresolved**

### Step 2 — Ask for unresolved dimensions only

- **All 3 resolved** → skip questions entirely (power-user fast path). Go to Step 3.
- **Some resolved** → single `AskUserQuestion` call with only the unresolved questions.
- **None resolved** (empty args or no matches) → single `AskUserQuestion` call with all 3 questions.

Use these question definitions for each unresolved dimension:

**Mode** (single-select, header: "Mode"):
- "Build new features" — description: "New capabilities, integrations, or modules"
- "Fix and harden" — description: "Bug fixes, test coverage, reliability improvements"
- "Refactor and simplify" — description: "Code restructuring, tech debt reduction, architecture cleanup"
- "Polish and refine" — description: "UX improvements, performance tuning, code quality"
- "Surprise me" — description: "Best overall pick regardless of category"

**Area** (multi-select, header: "Area"):
- "Backend (Python)" — description: "Services, pricing, scoring, data, indicators"
- "Frontend (Vue)" — description: "Web UI components, stores, API integration"
- "AI agents" — description: "Debate agents, prompts, orchestrator, providers"
- "Infrastructure" — description: "CI/CD, tooling, DevOps, configuration"
Note: If the user selects all options, treat as "all areas" (no filter).

**Scope** (single-select, header: "Scope"):
- "Any size" — description: "No preference — rank all effort levels equally"
- "Quick wins (hours)" — description: "Small, self-contained tasks completable in hours"
- "Focused sprint (days)" — description: "Medium tasks requiring a few days of work"
- "Deep project (week+)" — description: "Large epics spanning a week or more"

### Step 3 — Confirm profile

Report the resolved profile with source attribution:

> **Profile:** Mode = [X], Area = [X], Scope = [X]
> *(from arguments: [list] · interactive: [list])*

If all 3 came from arguments: `*(all from arguments — power-user mode)*`
If all 3 came from interactive: `*(all from interactive)*`

Map interactive answers back to ranking values:
- "Any size" → no scope boost (all sizes 1x)
- "Surprise me" → Surprise me multipliers
- All areas selected → no area filter

## Phase 2 -- Context Sweep + Ranking (after dimensions resolved)

Use the user's answers from Phase 1 (Mode, Area, Scope) to filter and rank below.

Spawn an Explore agent to gather project state silently. Pass the user's Mode, Area, and Scope answers in the prompt so the agent can tag candidates.

Use the Agent tool with these parameters:
- description: "Context sweep for /pm:next"
- subagent_type: "Explore"
- prompt: Include ALL of the instructions below verbatim, plus the user's interview answers.

Agent instructions (include in prompt):

> Gather project state for development targeting. Return a compact summary under 30 lines.
>
> 1. Run: `git log master --oneline -10` (recent commits)
> 2. Run: `git branch --no-merged master` (in-flight work)
> 3. Read first 10 lines of each file in `.claude/prds/` (frontmatter only — name, status)
> 4. Read `.claude/context/progress.md` — extract "Recently Completed" and "Future Work" sections
> 5. List directories in `.claude/epics/archived/` (shipped epics)
> 6. For each PRD candidate not yet shipped: glob/grep to check if the feature already exists in the codebase (check `src/options_arena/`, `web/src/views/`, `web/src/components/`)
>
> Cross-reference rule — a feature is SHIPPED if ANY of these is true:
> - Its epic name appears in `.claude/epics/archived/`
> - It appears in progress.md "Recently Completed"
> - Its PRD frontmatter has `status: done` or `status: archived`
> - Its key components already exist in the codebase (confirmed by glob/grep)
>
> Return your summary in this exact format:
> - SHIPPED: [list of shipped feature names]
> - BACKLOG: [list of unshipped PRD names with effort estimate]
> - IN-FLIGHT: [unmerged branches, if any]
> - FUTURE IDEAS: [items from progress.md "Future Work"]
> - RECENT THEMES: [2-3 word summary of last 2 weeks of commits]

After the agent returns its summary, apply ranking in the main context.

**Tag each candidate** with: Area (Backend/Frontend/AI agents/Infrastructure), Effort (S/M/L/XL), Momentum signal (yes/no + which recent work).

**Apply weighted ranking using interview answers:**

Base criteria: Momentum, Unblocking potential, Impact/Effort ratio, Freshness, Risk reduction, User-facing value.

Mode multipliers:

| Criterion | Build | Fix/Harden | Polish | Refactor | Surprise me |
|-----------|-------|------------|--------|----------|-------------|
| Momentum | 2x | 1x | 1x | 1x | 1x |
| Unblocking | 2x | 1x | 0.5x | 1.5x | 1x |
| Impact/Effort | 1x | 1x | 1.5x | 1.5x | 1x |
| Freshness | 1x | 1.5x | 1x | 1x | 1x |
| Risk reduction | 0.5x | 2x | 1x | 2x | 1x |
| User-facing value | 1x | 0.5x | 2x | 0.5x | 1x |

Area filter: Exclude candidates outside selected areas unless fewer than 3 remain (then include highest-ranked cross-area candidates tagged "(outside selected area)").

Scope multipliers:
- Quick wins → S: 2x, M: 1x, L/XL: 0.5x
- Focused sprint → S: 0.5x, M: 2x, L/XL: 1x
- Deep project → S: 0.5x, M: 1x, L/XL: 2x

Additional rules:
- Avoid duplicating or conflicting with in-progress efforts
- Prefer targets with existing PRDs (less overhead). Flag if a target needs a PRD first.
- If the user provided free text instead of selecting a preset, interpret their intent and apply closest matching multipliers.

## Phase 3 -- Tailored Output

For strategic opportunities, analyze:
1. **Capability extension**: What existing infrastructure enables new features? (e.g., "WebSocket pipeline exists — could power real-time price alerts")
2. **Module maturity gaps**: Which modules are feature-rich vs underdeveloped?
3. **Industry patterns**: What do comparable options analytics tools have that this lacks?

Always ground strategic suggestions in specific codebase evidence — reference actual modules, services, or infrastructure that enable the opportunity.

Present results in this exact format:

```
## Your Profile

**Mode:** [their answer] → [which criteria got boosted]
**Area:** [their answer(s)] → [filter applied]
**Scope:** [their answer] → [effort sizes boosted]

---

## Development Targets (ranked for your profile)

### 1. [One-line description]
**Alignment:** [Why this matches their mode + area + scope — 1 sentence]
**Why now:** [What recent work makes this timely — reference specific commits/PRs/epics]
**Effort:** [S / M / L / XL] · **Area:** [Backend / Frontend / AI agents / Infrastructure]
**Unblocks:** [What downstream work this enables]
**Reference:** [PRD/epic link if exists, or "Needs PRD"]
**Next command:** [e.g., `/pm:prd-new feature-name` or `/pm:epic-start feature-name`]

### 2. [One-line description]
...

---

## Strategic Opportunities

### S1. [Novel idea based on codebase capabilities]
**Opportunity:** [What the architecture enables that isn't built yet — 1-2 sentences]
**Builds on:** [Which existing modules/infrastructure this leverages]
**Effort:** [S / M / L / XL] · **Area:** [Backend / Frontend / AI agents / Infrastructure]
**Next command:** `/pm:prd-new [feature-name]`

---
**Filtered out (already shipped):** [list from subagent SHIPPED section]
**Filtered out (outside your profile):** [list briefly]
**Recent themes:** [from subagent RECENT THEMES]
**Suggested focus:** [1 sentence strategic direction]
```

If no backlog items match the user's profile, show "No backlog items match your profile" under Development Targets and let Strategic Opportunities be the primary output.

## Guidelines

- Be opinionated — rank decisively, don't hedge
- Ground every suggestion in concrete evidence from git history
- Dimension choices must visibly change the output — each mode produces visibly different targets ("Refactor" surfaces tech debt, "Build" surfaces features)
- Strategic suggestions must reference specific modules, services, or infrastructure — no vague ideas
- Include at least 1 strategic opportunity even when backlog items exist
- Keep each suggestion to 3-5 lines — brainstorm, not design doc
- Always suggest actionable next commands

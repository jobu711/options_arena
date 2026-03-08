---
description: Interview-driven development targeting — recommends 3-5 next tasks
allowed-tools: Bash, Read, Glob, Grep, AskUserQuestion, Agent
---

# Next: Interview-Driven Development Targeting

You are a strategic development advisor. This command has 3 phases executed in strict order.

## Phase 1 -- Interview (MANDATORY FIRST ACTION)

Your first action is to call AskUserQuestion with these 3 questions:

- Question 1 (header: "Mode", single-select): "What kind of work fits your headspace right now?"
  - "Build new features" — New capabilities, endpoints, or UI
  - "Fix and harden" — Bugs, edge cases, test coverage
  - "Polish and refine" — UX, performance, code quality
  - "Surprise me" — Rank purely on project impact

- Question 2 (header: "Area", multi-select): "Which parts of the codebase do you want to work in?"
  - "Backend (Python)" — Models, services, scoring, pricing
  - "Frontend (Vue)" — Components, views, stores, styling
  - "AI agents" — Prompts, orchestration, LLM providers
  - "Infrastructure" — CI/CD, config, tooling, DevOps

- Question 3 (header: "Scope", single-select): "How much time do you want to invest?"
  - "Quick wins (hours)" — S-sized: a focused session or two
  - "Focused sprint (days)" — M-sized: a few days of work
  - "Deep project (week+)" — L/XL-sized: multi-day epics

Phase 2 begins AFTER the user answers all questions.

## Phase 2 -- Context Sweep + Ranking (after interview answers received)

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
> - Its key components already exist in the codebase (confirmed by glob/grep)
>
> Also identify 1-2 strategic opportunities:
> - What does the current architecture enable that isn't built yet?
> - What capabilities exist that could be extended to new use cases?
> - What do comparable options analytics tools have that this project lacks?
>
> Return your summary in this exact format:
> - SHIPPED: [list of shipped feature names]
> - BACKLOG: [list of unshipped PRD names with effort estimate]
> - IN-FLIGHT: [unmerged branches, if any]
> - FUTURE IDEAS: [items from progress.md "Future Work"]
> - STRATEGIC: [1-2 novel opportunities grounded in specific codebase capabilities]
> - RECENT THEMES: [2-3 word summary of last 2 weeks of commits]

After the agent returns its summary, apply ranking in the main context.

**Tag each candidate** with: Area (Backend/Frontend/AI agents/Infrastructure), Effort (S/M/L/XL), Momentum signal (yes/no + which recent work).

**Apply weighted ranking using interview answers:**

Base criteria: Momentum, Unblocking potential, Impact/Effort ratio, Freshness, Risk reduction, User-facing value.

Mode multipliers:

| Criterion | Build | Fix/Harden | Polish | Surprise me |
|-----------|-------|------------|--------|-------------|
| Momentum | 2x | 1x | 1x | 1x |
| Unblocking | 2x | 1x | 0.5x | 1x |
| Impact/Effort | 1x | 1x | 1.5x | 1x |
| Freshness | 1x | 1.5x | 1x | 1x |
| Risk reduction | 0.5x | 2x | 1x | 1x |
| User-facing value | 1x | 0.5x | 2x | 1x |

Area filter: Exclude candidates outside selected areas unless fewer than 3 remain (then include highest-ranked cross-area candidates tagged "(outside selected area)").

Scope multipliers:
- Quick wins → S: 2x, M: 1x, L/XL: 0.5x
- Focused sprint → S: 0.5x, M: 2x, L/XL: 1x
- Deep project → S: 0.5x, M: 1x, L/XL: 2x

Additional rules:
- Avoid duplicating or conflicting with in-progress efforts
- Prefer targets with existing PRDs (less overhead). Flag if a target needs a PRD first.
- If user answered "Other", interpret their free text and apply closest matching multipliers.

## Phase 3 -- Tailored Output

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
**Filtered out (already shipped/in-flight):** [list briefly]
**Filtered out (outside your profile):** [list briefly]
**Recent themes:** [2-3 word summary of last 2 weeks]
**Suggested focus:** [1 sentence strategic direction]
```

## Guidelines

- Be opinionated — rank decisively, don't hedge
- Ground every suggestion in concrete evidence from git history
- Interview answers must visibly change the output — "Fix and harden" produces different targets than "Build new features"
- If the backlog is empty or all PRDs are done, suggest genuinely new directions based on what the codebase enables
- Keep each suggestion to 3-5 lines — brainstorm, not design doc
- Always suggest actionable next commands

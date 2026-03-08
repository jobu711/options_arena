---
description: Interview-driven development targeting — recommends 3-5 next tasks
allowed-tools: Bash, Read, Glob, Grep, AskUserQuestion, Agent
---

# Next: Interview-Driven Development Targeting

You are a strategic development advisor. This command has 3 phases executed in strict order.

## Phase 1 -- Interview (MANDATORY FIRST ACTION)

IMMEDIATELY call AskUserQuestion with all 3 questions below in a single tool call.

Question 1 — header: "Mode", multiSelect: false
  question: "What kind of work fits your headspace right now?"
  options:
    label: "Build new features" → description: "New capabilities, endpoints, or UI"
    label: "Fix and harden" → description: "Bugs, edge cases, test coverage"
    label: "Polish and refine" → description: "UX, performance, code quality"
    label: "Surprise me" → description: "Rank purely on project impact"

Question 2 — header: "Area", multiSelect: true
  question: "Which parts of the codebase do you want to work in?"
  options:
    label: "Backend (Python)" → description: "Models, services, scoring, pricing"
    label: "Frontend (Vue)" → description: "Components, views, stores, styling"
    label: "AI agents" → description: "Prompts, orchestration, LLM providers"
    label: "Infrastructure" → description: "CI/CD, config, tooling, DevOps"

Question 3 — header: "Scope", multiSelect: false
  question: "How much time do you want to invest?"
  options:
    label: "Quick wins (hours)" → description: "S-sized: a focused session or two"
    label: "Focused sprint (days)" → description: "M-sized: a few days of work"
    label: "Deep project (week+)" → description: "L/XL-sized: multi-day epics"

WAIT for the user's actual responses. Phase 2 uses answers from Phase 1.

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
- Interview answers must visibly change the output — "Fix and harden" produces different targets than "Build new features"
- Strategic suggestions must reference specific modules, services, or infrastructure — no vague ideas
- Include at least 1 strategic opportunity even when backlog items exist
- Keep each suggestion to 3-5 lines — brainstorm, not design doc
- Always suggest actionable next commands

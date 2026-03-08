---
description: Interview-driven development targeting — recommends 3-5 next tasks
allowed-tools: Bash, Read, Glob, Grep, AskUserQuestion, Agent
---

# Next: Interview-Driven Development Targeting

You are a strategic development advisor. This command has 3 phases executed in strict order.

## Phase 1 -- Interview (MANDATORY FIRST ACTION)

Before doing ANYTHING else, you must:

1. Output this exact text to the user: "Let me ask a few quick questions to tailor recommendations to your current headspace."
2. Immediately call AskUserQuestion with the 3 questions below.
3. Do NOT run any bash commands, read any files, or gather any context before OR alongside this call.
4. After the user answers, proceed to Phase 2.

Ask all 3 questions in ONE AskUserQuestion call. Use this exact structure:

```json
{
  "questions": [
    {
      "question": "What kind of work fits your headspace right now?",
      "header": "Mode",
      "multiSelect": false,
      "options": [
        {"label": "Build new features", "description": "New capabilities, endpoints, or UI"},
        {"label": "Fix and harden", "description": "Bugs, edge cases, test coverage"},
        {"label": "Polish and refine", "description": "UX, performance, code quality"},
        {"label": "Surprise me", "description": "Rank purely on project impact"}
      ]
    },
    {
      "question": "Which parts of the codebase do you want to work in?",
      "header": "Area",
      "multiSelect": true,
      "options": [
        {"label": "Backend (Python)", "description": "Models, services, scoring, pricing"},
        {"label": "Frontend (Vue)", "description": "Components, views, stores, styling"},
        {"label": "AI agents", "description": "Prompts, orchestration, LLM providers"},
        {"label": "Infrastructure", "description": "CI/CD, config, tooling, DevOps"}
      ]
    },
    {
      "question": "How much time do you want to invest?",
      "header": "Scope",
      "multiSelect": false,
      "options": [
        {"label": "Quick wins (hours)", "description": "S-sized: a focused session or two"},
        {"label": "Focused sprint (days)", "description": "M-sized: a few days of work"},
        {"label": "Deep project (week+)", "description": "L/XL-sized: multi-day epics"}
      ]
    }
  ]
}
```

Do NOT include any other tool calls alongside AskUserQuestion.

## Phase 2 -- Context Sweep + Ranking (after interview answers received)

Use the user's answers from Phase 1 (Mode, Area, Scope) to filter and rank below.

Silently gather project state — no progress updates to the user.

Run in parallel:
```bash
git log master --oneline --merges -15
git log master --oneline -20 --no-merges
git branch -a --no-merged master
git log master --oneline --since="14 days ago" --no-merges
```

For each unmerged branch: `git log master..<branch> --oneline`

**Backlog discovery** (cross-reference against git ground truth):
1. Scan `.claude/prds/` frontmatter (first 10-15 lines). A PRD is **done** if its epic appears in the merge log or `.claude/epics/archived/`.
2. Read `progress.md` "Future Work" section ONLY for idea discovery. Derive actual state from git.
3. For unmerged epics, check branch commit content (not task file statuses).
4. Check `web/src/views/` and glob/grep to confirm whether suggested capabilities already exist.

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

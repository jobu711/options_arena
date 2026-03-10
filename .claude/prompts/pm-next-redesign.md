<role>
You are a developer tooling architect specializing in intelligent task recommendation systems.
Your goal is to redesign the `/pm:next` command so it produces genuinely useful, context-aware
development suggestions — not just dependency-resolved task lists. The quality of suggestions
directly determines developer velocity and project momentum.
</role>

<context>
## Current Implementation

The `/pm:next` command exists in two layers:

### Shell Script (`.claude/scripts/pm/next.sh`)
A simple dependency resolver that scans `.claude/epics/*/` for open tasks with no unmet
`depends_on:` entries. Returns a flat list with no ranking or intelligence.

### Command Spec (`.claude/commands/pm/next.md`)
A 3-phase design with interactive dimension selection (Mode/Area/Scope), an Explore agent
context sweep, and weighted ranking with hardcoded multiplier tables. This is more sophisticated
but has significant blind spots.

### Known Weaknesses in Current Design

1. **No GitHub issue awareness** — ignores the 6+ open issues that represent real backlog items
2. **No code quality signals** — doesn't scan for TODO/FIXME comments, test coverage gaps, or lint warnings
3. **Rigid ranking** — hardcoded multiplier tables can't adapt to project phase or recent patterns
4. **No velocity awareness** — doesn't track what the user worked on recently or their typical task size
5. **Shallow "strategic opportunities"** — tells Claude to "analyze capability extension" but gives no concrete analysis framework
6. **No technical debt detection** — doesn't identify modules with high churn, low test coverage, or stale dependencies
7. **PRD-centric tunnel vision** — only considers items with PRDs; misses organic improvements visible in code
8. **No risk-aware prioritization** — doesn't factor in breaking changes, dependency updates, or security advisories

## Project State Signals Available

These data sources exist and can be queried:

| Signal | Source | What It Reveals |
|--------|--------|----------------|
| Recent commits | `git log --oneline -20` | Momentum direction, active modules |
| File churn | `git log --format= --name-only` | Hot spots needing attention |
| Open GH issues | `gh issue list --state open` | Community/user-reported needs |
| PRD backlog | `.claude/prds/*.md` frontmatter | Planned but unstarted features |
| Archived epics | `.claude/epics/archived/` | What's already shipped |
| Progress file | `.claude/context/progress.md` | Current state + future work |
| TODO/FIXME | `grep -r "TODO\|FIXME" src/` | In-code improvement markers |
| Test coverage | Module-level test counts | Under-tested areas |
| Dependencies | `pyproject.toml`, `package.json` | Outdated or vulnerable packages |
| CI status | `gh run list --limit 5` | Recent failures or flaky tests |

## Architecture Constraints

- Command lives in `.claude/commands/pm/next.md`
- Backing logic can use: Bash, Read, Glob, Grep, Agent (Explore subagent), AskUserQuestion
- Output displayed in terminal via Claude Code
- Must complete in under 60 seconds (user-facing latency)
- The command's `$ARGUMENTS` variable receives any text after `/pm:next`
</context>

<task>
Redesign the `/pm:next` command specification to produce smarter, more contextual development
suggestions. The redesign should replace the current `.claude/commands/pm/next.md` file.

Deliver:
1. A diagnostic of what the current design gets right vs wrong (keep what works)
2. A new 3-phase architecture that addresses the blind spots listed above
3. The complete replacement command file content, ready to write to `.claude/commands/pm/next.md`
</task>

<instructions>
Approach this in three phases:

## Phase A — Assess the Current Design

Read the current command spec (`.claude/commands/pm/next.md`) and shell script
(`.claude/scripts/pm/next.sh`). Identify:
- Which elements to preserve (the interactive dimension selection is good UX)
- Which elements to rethink (the ranking system, context sweep scope, output format)
- What new signal sources to incorporate

## Phase B — Design the New Architecture

Redesign with these principles:

**Signal diversity over rigidity**: Instead of hardcoded multiplier tables, define
signal categories that the ranking phase evaluates qualitatively. The LLM is better
at weighing nuanced factors than following arithmetic formulas.

**Evidence-grounded suggestions**: Every suggestion must cite specific evidence
(a commit hash, a file path, an issue number, a TODO comment). No vague recommendations.

**Adaptive context budget**: The Explore agent should gather only signals relevant to
the user's Mode/Area/Scope — not everything every time. Quick-win mode doesn't need
dependency audits; deep-project mode doesn't need TODO scanning.

**Layered candidate sources**: Combine multiple pools:
- Pool 1: Open GitHub issues (highest signal — real user/developer needs)
- Pool 2: PRD backlog items not yet started
- Pool 3: In-code signals (TODO/FIXME, under-tested modules, high-churn files)
- Pool 4: Infrastructure signals (outdated deps, CI failures, config drift)
- Pool 5: Strategic gaps (capability extensions inferred from architecture)

**Smart deduplication**: Cross-reference pools to merge duplicates (an issue that
matches a PRD, a TODO that maps to an open issue).

## Phase C — Write the Command Spec

Write the complete `.claude/commands/pm/next.md` replacement. Preserve:
- YAML frontmatter format
- 3-phase structure (Resolve → Sweep → Output)
- Interactive dimension selection UX
- Power-user fast path (`/pm:next build backend quick`)
- Actionable next-command suggestions

Improve:
- Context sweep scope and adaptive signal gathering
- Ranking logic (qualitative LLM reasoning over rigid multipliers)
- Output format (evidence citations, confidence indicators, risk flags)
- Strategic opportunities (grounded in code analysis, not hand-waving)

Before finalizing, verify that:
- Every suggestion in the output format includes a concrete evidence citation
- The Explore agent prompt is scoped to Mode/Area/Scope (not gathering everything)
- The command handles edge cases: empty backlog, no open issues, all areas selected
- The design respects the 60-second latency budget
- The YAML frontmatter `allowed-tools` list covers all tools used in the spec
</instructions>

<constraints>
1. Preserve the interactive dimension selection (Mode/Area/Scope) — it's good UX that users already know
2. Use qualitative LLM ranking instead of hardcoded multiplier arithmetic tables
3. Every suggestion must cite specific evidence (commit, file, issue, TODO)
4. The Explore agent prompt must be adaptive — gather only signals matching user's profile
5. Keep the command spec under 250 lines — conciseness aids reliable execution
6. Output format must include a "Next command" for each suggestion (actionable, not informational)
7. Strategic opportunities must reference specific modules or infrastructure, with file paths
8. Handle the empty-state gracefully (no backlog, no issues → focus on strategic opportunities)
9. The redesign must be a drop-in replacement for `.claude/commands/pm/next.md`
10. Use moderate language in agent prompts — "gather signals" not "YOU MUST EXHAUSTIVELY SCAN"
</constraints>

<examples>
<example>
<input>User runs: `/pm:next build backend quick`</input>
<thinking>
All 3 dimensions resolved from arguments — power-user fast path.
Mode=Build → prioritize new capabilities, momentum, unblocking.
Area=Backend → filter to Python modules (services, pricing, scoring, data, indicators).
Scope=Quick → favor S-size tasks, deprioritize L/XL.

Adaptive signal gathering for this profile:
- GitHub issues tagged backend or unlabeled (skip frontend issues)
- Recent backend commits for momentum detection
- TODO/FIXME in src/options_arena/ only (skip web/)
- Skip dependency audit (that's infrastructure, not backend build work)
- Skip CI status (quick wins don't need pipeline context)

Candidate pool after filtering:
1. Issue #394 "Add fundamental data enrichment" — M-size, has PRD, momentum (recent FinancialDatasets work)
2. TODO in services/options_data.py:142 "cache chain results" — S-size, quick win
3. Progress.md "Future Work": real-time streaming — XL-size, deprioritized by scope

Final ranking: #2 (quick, backend, build-aligned), #1 (medium but high momentum)
</thinking>
<output>
## Your Profile

**Mode:** Build new features (from arguments)
**Area:** Backend (from arguments)
**Scope:** Quick wins (from arguments)
*(all from arguments — power-user mode)*

---

## Development Targets

### 1. Cache option chain results in OptionsDataService
**Evidence:** `src/options_arena/services/options_data.py:142` — TODO: "add chain caching"
**Why now:** Chain fetching is the #1 latency bottleneck in scan pipeline (recent Phase 3 work)
**Effort:** S · **Area:** Backend · **Risk:** Low
**Next command:** `/pm:prd-new chain-caching`

### 2. Integrate FinancialDatasets fundamental data (#394)
**Evidence:** GitHub issue #394, PRD exists at `.claude/prds/financialdatasets-ai.md`
**Why now:** MCP server already configured; 5 related issues (#395-#399) blocked on this
**Effort:** M · **Area:** Backend · **Unblocks:** 5 issues
**Next command:** `/pm:epic-start financialdatasets-ai`

---

## Strategic Opportunities

### S1. WebSocket-powered live chain refresh
**Builds on:** `api/websocket.py` bridge pattern + `services/options_data.py` chain fetching
**Effort:** L · **Area:** Backend
**Next command:** `/pm:prd-new live-chain-refresh`

---
**Filtered out (shipped):** backtesting engine, pipeline decomposition, repository decomposition
**Filtered out (scope mismatch):** real-time streaming (XL), frontend unit tests (frontend)
</output>
</example>

<example>
<input>User runs: `/pm:next` (no arguments)</input>
<thinking>
No dimensions resolved — ask all 3 interactively.
After user selects: Mode=Fix, Area=[Backend, Frontend], Scope=Any size.

Adaptive signal gathering for this profile:
- GitHub issues (all, since fix mode wants bugs/hardening)
- Recent CI failures (fix mode cares about reliability)
- TODO/FIXME across both src/ and web/
- Test coverage gaps (which modules have fewest tests relative to code size?)
- Skip strategic opportunity analysis (fix mode, not build mode)

Key signals found:
- CI: last 2 runs green, no flaky tests
- 3 TODO items in scoring/, 2 FIXME in web/src/stores/
- test_expanded_context.py has 2 known failures (NaN/Inf validators)
</thinking>
<output>
[Interactive questions shown first, then output after user responds]

## Development Targets

### 1. Fix NaN/Inf validator edge cases in expanded context
**Evidence:** `tests/test_expanded_context.py` — 2 pre-existing failures on master
**Why now:** These failures mask real regressions in CI; fixing removes noise
**Effort:** S · **Area:** Backend · **Risk:** Low
**Next command:** Start directly — `uv run pytest tests/test_expanded_context.py -v`

### 2. ...
</output>
</example>
</examples>

<output_format>
Structure your response in three sections:

## 1. Current Design Diagnostic
A table with columns: Element | Verdict (Keep/Rethink/Remove) | Rationale
Cover: dimension selection, context sweep, ranking system, output format, strategic opportunities.

## 2. Redesign Architecture
Prose description of the new 3-phase architecture. For each phase, explain:
- What changed from current design and why
- New signal sources incorporated
- How it adapts to Mode/Area/Scope

## 3. Command Spec
The complete replacement content for `.claude/commands/pm/next.md`, including YAML frontmatter.
Present in a single fenced code block, ready to write to disk.
</output_format>

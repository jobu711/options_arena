# Agent Coordination & Orchestration

Comprehensive guide for orchestrating Claude Code's multi-agent system. Covers agent
selection, quality sweeps, parallel execution, context budget management, and workflow
templates for all task types.

Load this guide when: planning multi-agent work, designing quality gates, coordinating
parallel execution, or choosing between agents.

## Agent Tiers

### T1 — Auditors (6 agents, all read-only, all parallelizable)

These agents have **non-overlapping scopes** by design. Run any combination in parallel.

| Agent | IN Scope | OUT of Scope | Model |
|-------|----------|-------------|-------|
| `architect-reviewer` | Module boundaries, coupling, API design, data model changes, dependency direction | Bugs, security, performance, DB | opus |
| `code-reviewer` | Style, patterns, types, NaN defense, clean code, interface misuse | Security, async races, DB queries, deps | opus |
| `security-auditor` | OWASP Top 10, injection, secrets, env vars, WebSocket security, input validation | Code quality, async, DB, deps | opus |
| `bug-auditor` | Async races, resource leaks, timeouts, error handling, concurrency, floating tasks | Security, style, DB, deps | opus |
| `db-auditor` | SQL injection, commit discipline, migrations, serialization, connection lifecycle | API logic, async, security, deps | opus |
| `dep-auditor` | CVEs, unused deps, licenses, optional import guards, version constraints | App code, async, security, DB | sonnet |

**Non-overlap guarantee**: Each auditor's IN scope is every other auditor's OUT scope. No
two auditors will flag the same issue type. This makes parallel execution safe and
non-redundant.

### T2 — Analysts (3 agents, read-only)

| Agent | Use When | Model |
|-------|----------|-------|
| `research-analyst` | Pre-implementation research, API evaluation, data source assessment | opus |
| `code-analyzer` | Deep logic tracing, bug investigation, change impact analysis | opus |
| `file-analyzer` | Summarizing verbose output (logs, test results) to save parent context | haiku |

### T3 — Domain Specialists (3 agents, write-capable)

| Agent | Domain | Model |
|-------|--------|-------|
| `quant-analyst` | `pricing/`, `scoring/`, `indicators/` — derivatives pricing, volatility, statistics | opus |
| `risk-manager` | VaR, stress testing, position sizing, hedging, portfolio risk | opus |
| `prompt-engineer` | `agents/prompts/` — debate agent prompts, template design, token optimization | opus |

### T4 — Execution Engines (4 agents)

| Agent | Purpose | Model |
|-------|---------|-------|
| `tdd-orchestrator` | Red-green-refactor TDD cycles (pytest + pytest-asyncio) | opus |
| `parallel-worker` | Worktree-isolated parallel write streams | inherit |
| `test-runner` | Test execution + log analysis + failure diagnosis | inherit |
| `multi-agent-coordinator` | Dependency graphs, workflow design, parallel execution planning | opus |

### T5 — General (3 built-in agents)

| Agent | Purpose | Model |
|-------|---------|-------|
| `Explore` | Fast codebase search, file patterns, structure understanding | inherit |
| `Plan` | Architecture design, implementation strategy | inherit |
| `general-purpose` | Fallback for tasks that don't fit any specialist | inherit |

## Module-to-Agent Mapping

Every project directory has a primary agent for implementation and required auditors for
validation. This table aligns with CLAUDE.md's module boundary table.

| Module | Primary Agent | Required Auditors | Notes |
|--------|--------------|-------------------|-------|
| `models/` | Main thread | `code-reviewer` | Data shapes only — no logic |
| `services/` | Main thread | `bug-auditor`, `security-auditor` | External API access, async patterns |
| `indicators/` | `quant-analyst` | `code-reviewer` | Pure math, pandas in/out |
| `pricing/` | `quant-analyst` | `code-reviewer` | BSM + BAW, scipy |
| `scoring/` | `quant-analyst` | `code-reviewer` | Normalization, composite scoring |
| `data/` | Main thread | `db-auditor` | SQLite persistence |
| `data/migrations/` | Main thread | `db-auditor` | Sequential SQL migration files |
| `scan/` | Main thread | `bug-auditor`, `architect-reviewer` | 4-phase async pipeline |
| `agents/` | Main thread | `bug-auditor`, `architect-reviewer` | PydanticAI debate orchestration |
| `agents/prompts/` | `prompt-engineer` | `bug-auditor` | Prompt templates & versioning |
| `api/` | Main thread | `security-auditor`, `bug-auditor` | FastAPI REST + WebSocket |
| `cli/` | Main thread | `code-reviewer` | Typer + Rich entry point |
| `reporting/` | Main thread | `code-reviewer` | Export generation |
| `utils/` | Main thread | `code-reviewer` | Exception hierarchy |
| `web/` | Main thread | `security-auditor` | Vue 3 SPA |

## Quality Sweeps

### Full Sweep — All 6 T1 Auditors

When: Epic merges, releases, major refactors, or any change touching 4+ modules.

```
Launch in parallel (all BG):
  architect-reviewer  → boundary violations, coupling
  code-reviewer       → style, patterns, types, NaN
  security-auditor    → OWASP, secrets, injection
  bug-auditor         → async, leaks, timeouts
  db-auditor          → queries, commits, migrations
  dep-auditor         → CVEs, unused deps, licenses
```

All 6 run simultaneously. Non-overlapping scopes mean no duplicated findings.
Expect ~2-4 minutes for full sweep across the codebase.

### Targeted Sweep — 2-4 Auditors by Module

When: Multi-module commits, feature additions, most PRs.

Select auditors from the module-to-auditor matrix. Examples:

| Modules Changed | Auditors |
|----------------|----------|
| `services/` + `api/` | `bug-auditor`, `security-auditor` |
| `pricing/` + `scoring/` | `code-reviewer`, `architect-reviewer` |
| `data/` + `scan/` | `db-auditor`, `bug-auditor`, `architect-reviewer` |
| `agents/prompts/` | `bug-auditor` |
| `models/` + `services/` + `api/` | `code-reviewer`, `security-auditor`, `bug-auditor` |

### Spot Check — Single Auditor

When: Small changes in a single module, focused validation.

Pick the single most relevant auditor for the change type:
- Changed async code → `bug-auditor`
- Changed API endpoint → `security-auditor`
- Changed query/migration → `db-auditor`
- Changed model/types → `code-reviewer`
- Changed module imports → `architect-reviewer`
- Added dependency → `dep-auditor`

## Foreground vs Background vs Worktree

### Foreground (default)

Use when the agent's result determines your next step.

- Research phase (need findings before designing)
- Architecture review (need approval before implementing)
- Test execution when debugging (need results to fix)
- Any blocking decision point

### Background

Use when the agent validates independently while you continue.

- All T1 auditors during quality sweeps
- Regression test suite after implementation
- Documentation generation
- Any non-blocking validation

### Worktree Isolation

Use when 3+ independent write streams touch different modules.

- Epic with parallel implementation issues
- Multi-module refactor with independent extraction tasks
- Different agents writing to different module directories

**Rule**: Never use worktree for read-only work. Worktrees have overhead — only justified
when multiple agents need to write simultaneously.

## Context Budget Management

The main thread's context window is the scarcest resource. Protect it.

### Delegation Thresholds

| Situation | Threshold | Delegate To |
|-----------|-----------|-------------|
| File to read | >200 lines | `file-analyzer` (returns summary) |
| Test output to analyze | >100 lines | `test-runner` (returns diagnosis) |
| Codebase search | >3 queries likely | `Explore` or `code-analyzer` |
| Web/API research | >2 searches needed | `research-analyst` |
| Log file analysis | Any size | `file-analyzer` |

### What Stays on Main Thread

- Direct Glob/Grep for targeted, single-query lookups
- Reading files you're about to edit (need exact content)
- Writing/editing code (main thread is the primary implementer)
- Decision-making between alternatives
- Coordinating wave transitions

### What Gets Delegated

- Open-ended codebase exploration
- Test execution and result analysis
- Quality sweeps (always delegated to auditors)
- Research that might require multiple web searches
- Verbose output processing (logs, large test suites)

## Model Tier Selection

Choose the cheapest model that can do the job well.

| Tier | Cost | Speed | Use For |
|------|------|-------|---------|
| **Opus** | High | Slow | Architecture decisions, security audits, complex bug analysis, quant modeling, multi-module coordination, any task requiring deep reasoning |
| **Sonnet** | Medium | Fast | Dependency checks, structured checklists with explicit criteria |
| **Inherit** | Lowest | Fastest | Test execution, file summarization, parallel workers, command-running tasks that don't need deep reasoning |

**Default rule**: If the agent mostly runs commands and summarizes output → inherit.
If it follows a checklist → sonnet. If it reasons about architecture, correctness, or
security → opus.

## Workflow Templates

### Bug Fix (2-3 waves)

```
Wave 0 — Investigate (FG)
  Direct Glob/Grep for the bug location
  Direct Read of affected files
  [If complex] code-analyzer to trace logic flow

Wave 1 — Fix + Validate (mixed)
  Main thread implements fix
  test-runner: run affected test file (FG)
  Targeted sweep: 1-2 auditors from module matrix (BG)
```

### New Feature (4-5 waves)

```
Wave 0 — Research (parallel, FG)
  research-analyst: evaluate external APIs/approaches
  Explore: find existing patterns to follow
  architect-reviewer: validate proposed boundaries

Wave 1 — Foundation (main thread)
  Add models, config, types
  /pm:epic-checkpoint

Wave 2 — Implementation (main thread or domain specialist)
  Build core logic
  test-runner: run new tests (BG)

Wave 3 — Integration (main thread)
  Wire into orchestrator/CLI/API
  test-runner: full suite (FG)

Wave 4 — Quality Sweep (parallel, BG)
  Full or targeted sweep based on module count
```

### Refactor (3 waves)

```
Wave 0 — Analyze (parallel, FG)
  Explore: map current structure
  architect-reviewer: validate target design

Wave 1 — Execute (main thread)
  Implement refactoring
  test-runner: verify no regressions (FG)

Wave 2 — Triple Audit (parallel, BG)
  architect-reviewer: boundaries post-refactor
  code-reviewer: extraction quality
  bug-auditor: no async/resource regressions
```

### Epic (5+ waves)

```
Wave 0 — Research (parallel, FG)
  research-analyst + Explore + architect-reviewer

Wave 1 — Foundation (main thread)
  Models, config, types (low risk)
  /pm:epic-checkpoint

Waves 2-N — Per-issue implementation
  /pm:issue-start per issue
  Main thread or domain specialist
  test-runner after each issue (BG)
  /pm:epic-checkpoint between waves

Wave N+1 — Full Quality Sweep (parallel, BG)
  All 6 T1 auditors
  Full test suite
```

### Investigation (2 waves)

```
Wave 0 — Search (parallel, FG)
  Explore: find relevant code
  code-analyzer: trace execution flow

Wave 1 — Deep Dive (FG)
  bug-auditor or domain specialist for targeted analysis

Output: Report with findings. No code changes without user approval.
```

## The Elegant Solution Principle

When encountering diverging methods — multiple agents proposing conflicting approaches,
competing implementation patterns, or escalating complexity from layered workarounds —
**stop and find the elegant solution**.

1. **Step back**: Don't patch conflicts between approaches. Identify the root constraint
   causing divergence.
2. **Simplify**: Reframe what you're actually trying to achieve. Often 2 diverging
   50-line approaches share a 10-line core that solves both.
3. **Prefer deletion**: When two methods conflict, the one that removes complexity is
   almost always correct.
4. **One clean path**: If agents disagree on approach, don't merge both — pick the one
   that's simpler to reason about, even if the other has marginal advantages.
5. **Escalate early**: If you've spent 2+ attempts reconciling divergent approaches,
   stop and ask the user. The elegant solution often requires domain knowledge the
   agents don't have.

This applies at every level: agent selection (don't stack when one suffices),
implementation (don't layer abstractions when a direct solution exists), and debugging
(don't add workarounds when the root cause is fixable).

## Anti-Patterns

### 1. Agent Bloat
**Wrong**: Spawning 6 agents for a 3-file change.
**Right**: Use module-to-agent mapping. If one agent covers it, use one agent.

### 2. Auditor Overlap
**Wrong**: Running `code-reviewer` + `security-auditor` for a style issue.
**Right**: Each auditor has defined scope. Pick by issue type, not "more is safer."

### 3. Premature Sweep
**Wrong**: Full sweep after every small commit.
**Right**: Spot check for small changes. Full sweep only at epic merge / release.

### 4. Opus for Execution
**Wrong**: Using opus model for `test-runner` or `file-analyzer`.
**Right**: Inherit for command execution. Opus for reasoning tasks.

### 5. Foreground for Validation
**Wrong**: Blocking on auditors while you could be implementing the next wave.
**Right**: Auditors run BG unless their finding would change your approach.

### 6. Skipping Architect Review
**Wrong**: Implementing multi-module changes and reviewing architecture after.
**Right**: `architect-reviewer` in Wave 0, before any code is written.

### 7. Main Thread File Reads
**Wrong**: Reading 500-line files on the main thread "just to check."
**Right**: Delegate to `file-analyzer` for summary, or use targeted Read with offset/limit.

### 8. General-Purpose Default
**Wrong**: Using `general-purpose` because you're not sure which specialist to pick.
**Right**: Check the module-to-agent map. If truly nothing fits, then `general-purpose`.

### 9. Brute-Forcing Divergence
**Wrong**: Stacking workarounds when two approaches conflict. Adding more agents to
resolve disagreement. Merging both approaches "to be safe."
**Right**: Apply the elegant solution principle. Step back, simplify, pick one clean path.
Escalate to user after 2 failed attempts.

## Parallel Execution Rules

1. **T1 auditors always parallelize** — non-overlapping scopes by design.
2. **Read-only agents (T1 + T2) parallelize freely** with any other agent.
3. **Write agents serialize by file** — two agents writing the same file will conflict.
4. **Write agents in different modules parallelize safely** — module boundaries prevent overlap.
5. **Worktree for 3+ write streams** — overhead only justified at scale.
6. **One scan/debate at a time** — the application's `asyncio.Lock` enforces this.

## File Ownership Protocol

When multiple agents write code in the same wave:

1. Assign each agent explicit file patterns (e.g., Agent A owns `services/*.py`, Agent B owns `api/*.py`).
2. Shared files (e.g., `__init__.py` re-exports) are owned by the main thread — no agent writes to them.
3. If agents discover they need to modify the same file, serialize: one completes first, the other follows.
4. Never have two agents edit the same file in parallel — even in worktrees, merge conflicts are expensive.

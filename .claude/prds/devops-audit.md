---
name: devops-audit
description: Slash command that audits CI/CD, build config, hooks, agent coordination, external services, and identifies devops gaps
status: planned
created: 2026-03-13T23:52:28Z
---

# PRD: devops-audit

## Executive Summary

Create a `/devops-audit` slash command that comprehensively audits the project's devops
environment — CI/CD pipeline health, build configuration, hook integrity, external service
readiness, and (most importantly) agent coordination and parallel execution safety. The
command runs checks directly (no dedicated agent), outputs to `.claude/audits/AUDIT_DEVOPS.md`
in the standard YAML preamble + P1-P4 findings format, and includes proactive recommendations
for missing devops practices.

## Problem Statement

### What problem are we solving?

Options Arena has a robust code-quality audit system (6 auditor agents + `/full-audit`
orchestration), but **no audit coverage for the devops infrastructure itself**. When agents
are added/removed, skills created, CI workflows modified, or hooks changed, there's no
automated way to verify:

- Agent scopes remain non-overlapping and all modules have coverage
- Skills reference valid agents and don't create redundant checks
- CI gates are correctly configured and passing
- Build config (pyproject.toml, ruff, mypy) hasn't drifted from CLAUDE.md standards
- Hooks are syntactically valid and properly registered
- External services are reachable and health checks are complete

### Why is this important now?

The agent-coordination guide lists 7 T1 auditors (including the recently added
`oa-python-reviewer`), but `/full-audit` still launches only 6 — exactly the kind of
discrepancy this command would catch. The project has dozens of slash commands, a 4-gate
CI pipeline, and agent coordination complexity that increases non-linearly with count.
Automated validation of the agent ecosystem itself is overdue.

## User Stories

### US1: Agent coordination health
**As a** developer adding a new agent,
**I want** `/devops-audit` to verify the new agent doesn't overlap existing scopes,
**So that** parallel execution remains safe and non-redundant.

**Acceptance criteria**:
- Detects scope overlap between any two agents
- Flags modules with no agent coverage
- Detects orphaned agents (defined but never referenced by commands)
- Detects phantom references (commands referencing nonexistent agents)

### US2: CI/config drift detection
**As a** developer modifying build configuration,
**I want** `/devops-audit` to verify config matches CLAUDE.md standards,
**So that** configuration drift doesn't silently break conventions.

**Acceptance criteria**:
- Validates ruff rules, target-version, line-length match CLAUDE.md
- Validates mypy strict mode and override list
- Validates test markers and asyncio config
- Checks version sync across pyproject.toml, package.json, progress.md

### US3: Gap analysis and recommendations
**As a** tech lead reviewing infrastructure,
**I want** proactive recommendations for missing devops practices,
**So that** I can prioritize infrastructure improvements.

**Acceptance criteria**:
- Flags missing Dependabot/Renovate, SAST, Docker, release automation
- Reports stale audit reports (>7 days since last full audit)
- Identifies broken guide references in CLAUDE.md

## Architecture & Design

### Chosen Approach

**Phased Checker with Parallel Probes** — A single `.claude/commands/devops-audit.md`
organized into 3 execution phases. Phase 1 runs fast static checks (file reads/greps).
Phase 2 launches slower dynamic probes in parallel (background Bash). Phase 3 synthesizes
findings and generates recommendations. No dedicated agent — the command script runs
checks directly using built-in tools.

### Module Changes

| Change | File | Type |
|--------|------|------|
| New command | `.claude/commands/devops-audit.md` | Create |

No changes to existing modules, agents, or application code.

### Data Models

No new Pydantic models — this is a Claude Code command, not Python application code.

Output follows the existing audit report schema:
```yaml
---
agent: devops-audit
status: COMPLETE | PARTIAL | ERROR
timestamp: <ISO 8601 UTC>
scope: agents, commands, CI, config, hooks, services, gaps
findings:
  critical: <count>
  high: <count>
  medium: <count>
  low: <count>
---
```

### Core Logic

#### Phase 1: Static Analysis (Sequential, Fast)

**Agent Coordination Checks (Primary Focus — 29 checks across 6 categories)**:

**A. Agent Registry & Inventory**
1. Agent census — Glob `.claude/agents/*.md`, build inventory (name, tools, model, tier)
2. Skill census — Glob `.claude/commands/*.md`, build inventory of all slash commands
3. Orphan detection — Agents defined but never referenced by any command
4. Phantom references — Commands referencing agents not in `.claude/agents/`
5. New agent validation — Compare agent list against last audit, flag added/removed

**B. Scope Boundaries & Overlap**
6. Scope extraction — Parse each agent's scope description (IN/OUT columns)
7. Overlap matrix — Cross-compare all agent scopes pairwise, flag overlapping responsibilities
8. Module coverage map — Map every `src/options_arena/` module to owning agent(s), flag 0 or 2+ agents on same concern
9. Boundary table sync — Compare agent scopes against CLAUDE.md boundary table
10. Concern deduplication — Detect two agents checking the same thing

**C. Parallel Execution Safety**
11. Read-only enforcement — Verify T1 auditors have only read-only tools (no Write, Edit)
12. Write-agent isolation — Writers never run parallel with other writers on same files
13. Fan-out pattern — Verify `/full-audit` launches all agents in ONE message
14. Gather pattern — Commands using multiple agents handle failures independently
15. Resource contention — Flag agents that could conflict on temp files or ports

**D. Output Format Consistency**
16. YAML preamble schema — Every auditor outputs same fields (agent, status, timestamp, scope, findings)
17. Severity alignment — All agents use same severity levels (critical/high/medium/low)
18. Finding format — Findings follow `[category] file:line — Description. Impact. Fix.` pattern
19. Deduplication readiness — Each agent includes file:line references for `/full-audit` deduplication

**E. Coordination Efficiency**
20. Redundant checks — Agent and command both perform same validation
21. Agent-to-module mapping completeness — Cross-reference guide vs actual definitions
22. Tier classification — Every agent has clear tier (T1-T5) matching actual tool access
23. Model cost optimization — Expensive models on simple tasks
24. Skill-agent coupling — Which skills invoke which agents, unnecessary spawns
25. Coverage gaps — Project concerns with no agent or command coverage

**F. Change Detection**
26. Agent diff — git history shows added/removed/modified agents since last audit
27. Skill diff — git history shows added/removed/modified commands since last audit
28. Scope drift — Modified agents expanded into another agent's territory
29. New module coverage — New `src/options_arena/*/` modules without agent coverage

**CI/Config/Hook Checks**:
30. CI workflow gates — ci.yml has all 4 gates (lint, typecheck, test, frontend)
31. Nightly workflow — nightly.yml exists and runs exhaustive tests
32. Ruff config drift — Rules match CLAUDE.md spec (E,F,I,UP,B,SIM,ANN, line-length 99, py313)
33. Mypy config drift — strict=true, override list reasonable
34. Test config — asyncio_mode=auto, timeout=60, markers defined
35. Hook integrity — All hooks exist, registered in settings.json, valid Python syntax
36. Version sync — pyproject.toml, web/package.json, progress.md versions match
37. Entry point — options-arena script entry in pyproject.toml
38. Build system — hatchling backend, requires-python >=3.13
39. Context budget — CLAUDE.md + context files line counts within limits

#### Phase 2: Dynamic Probes (Parallel Background Bash)

40. CI run status — `gh run list --limit 5` — recent CI passing?
41. Dependency freshness — `uv lock --check` — lockfile in sync?
42. Dependency security — `uv run pip-audit` — known CVEs?
43. External service health — `uv run options-arena health` — services reachable?
44. Test tier coverage — Count tests by marker (critical, exhaustive, integration, db, unmarked)

#### Phase 3: Gap Analysis & Report (Sequential Synthesis)

45. Missing practices — Flag absent: Dependabot, SAST, Docker, release automation, monitoring
46. Stale audit reports — `.claude/audits/` timestamps >7 days old
47. Broken references — Guides referenced in CLAUDE.md exist in `.claude/guides/`
48. Health check completeness — Services used in code vs services in health.py
49. Consolidate all findings into `AUDIT_DEVOPS.md` with YAML preamble + P1-P4

### Priority Mapping

- **P1 (Critical)**: Write tools on T1 auditors, phantom agent references, parallel writers
  on same files, CI gates broken/missing, security CVEs, version mismatch, broken hooks
- **P2 (High)**: Scope overlap (two agents claiming same concern), unmapped modules, orphaned
  agents, agents defined but not launched by `/full-audit`, broken fan-out, config drift from
  CLAUDE.md, stale lockfile, failing health checks
- **P3 (Medium)**: Inconsistent output formats, stale agent-coordination guide, redundant
  checks, missing devops practices, context budget overruns, stale audit reports
- **P4 (Low)**: Suboptimal model selection, missing tier classification, documentation drift,
  cost optimization suggestions, recommendations for new practices

## Requirements

### Functional Requirements

1. Command runs without arguments — always performs full devops audit
2. Output written to `.claude/audits/AUDIT_DEVOPS.md` in standard format
3. YAML preamble with finding counts is machine-parseable
4. Agent coordination checks cover all 6 categories (A-F) with 29 individual checks
5. CI/config/hook checks cover 10 items
6. Dynamic probes run in parallel via background Bash
7. Gap analysis provides actionable recommendations
8. Each finding includes: category, location, description, impact, and fix

### Non-Functional Requirements

1. Phase 1 completes in <30 seconds (file reads only)
2. Phase 2 completes in <2 minutes (parallel I/O probes)
3. Phase 3 completes in <15 seconds (synthesis)
4. Total execution: <3 minutes typical (each Phase 2 probe has 30s timeout)
5. No modifications to application source code — read-only audit
6. Compatible with existing `/full-audit` report format for potential integration

## API / CLI Surface

**Invocation**: `/devops-audit`

No arguments in v1. Future: `--quick` to skip Phase 2 for fast config-only checks.

**Output**: `.claude/audits/AUDIT_DEVOPS.md`

**User-facing summary**: After writing the report, display:
- Summary table with finding counts by severity
- P1 count with recommendation to run `/fix-loop` if >0
- Path to full report

## Testing Strategy

Since this is a Claude Code command file (`.md`), not Python source:

1. **Smoke test**: Run `/devops-audit` on current repo, verify report written to correct path
2. **Format validation**: Verify YAML preamble is parseable and finding counts are accurate
3. **Drift detection**: Intentionally change ruff target-version in pyproject.toml, verify it's caught
4. **Agent overlap**: Create a temporary agent with overlapping scope, verify detected
5. **Parallel safety**: Verify Phase 2 probes all launch as background tasks
6. **Idempotency**: Run twice in a row, verify report is replaced (not appended)

## Success Criteria

1. Running `/devops-audit` produces a complete report in <3 minutes
2. Report catches at least one real finding on first run (e.g., `oa-python-reviewer` defined
   in `agent-coordination.md` but not launched by `/full-audit`, stale audit reports, etc.)
3. Agent coordination section correctly identifies all agents and their scope relationships
4. Format is compatible with existing audit reports (could be added to `/full-audit` later)
5. Recommendations section identifies genuine missing practices

## Constraints & Assumptions

- Assumes `gh` CLI is available for CI run status checks (graceful degradation if missing)
- Assumes `pip-audit` is installed as a dev dependency (graceful degradation if missing)
- Assumes `uv` is the package manager (hardcoded, not configurable)
- Assumes agent definitions are in `.claude/agents/*.md` with consistent frontmatter
- Assumes command definitions are in `.claude/commands/*.md`
- Git history must be available for change detection checks
- Phase 2 probes each have a 30-second timeout to prevent hangs on slow/unreachable services

## Out of Scope

- Dedicated `devops-auditor` agent (v1 is command-only, not agent)
- Integration into `/full-audit` as a 7th agent (future consideration)
- Docker/container auditing (project has no containers yet)
- Cloud infrastructure auditing (no IaC exists)
- Automated fix application (use `/fix-loop` for that)
- Sub-command arguments (`/devops-audit ci`, `/devops-audit agents`) — future enhancement

## Dependencies

- **Internal**: `.claude/agents/*.md` (agent definitions), `.claude/commands/*.md` (skill definitions),
  `.claude/guides/agent-coordination.md` (coordination rules), `CLAUDE.md` (boundary table)
- **External**: `gh` CLI (GitHub), `uv` (package manager), `pip-audit` (dev dependency)
- **Existing infrastructure**: `.claude/audits/` directory, standard YAML preamble format

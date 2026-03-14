---
name: devops-audit
status: backlog
created: 2026-03-14T00:14:04Z
progress: 0%
prd: .claude/prds/devops-audit.md
github: https://github.com/jobu711/options_arena/issues/494
---

# Epic: devops-audit

## Overview

Create a `/devops-audit` slash command (`.claude/commands/devops-audit.md`) that audits
the project's devops infrastructure — agent coordination, CI/CD pipeline, build config,
hooks, external services, and gap analysis. This is a Claude Code command file only; no
Python application code changes. The command runs 49 checks across 3 phases and outputs
findings to `.claude/audits/AUDIT_DEVOPS.md` in the standard YAML preamble + P1-P4 format.

## Architecture Decisions

- **Single command file** — `.claude/commands/devops-audit.md`, no dedicated agent. The
  command prompt instructs Claude to run checks directly using built-in tools (Read, Glob,
  Grep, Bash). This matches the project's pattern where commands orchestrate work.
- **Phased execution** — Phase 1 (static file reads, fast), Phase 2 (dynamic probes via
  background Bash, parallel), Phase 3 (gap analysis + report synthesis).
- **Existing report format** — Reuses the YAML preamble + severity level schema from
  `/full-audit` for consistency and future integration.
- **No new Python models** — This is infrastructure tooling, not application code.
- **Graceful degradation** — Phase 2 probes (`gh`, `pip-audit`, `options-arena health`)
  each have 30s timeouts and skip cleanly if tools are unavailable.

## Technical Approach

### Command Structure (`.claude/commands/devops-audit.md`)

Following the pattern of `full-audit.md`:
- Frontmatter: `allowed-tools: Read, Glob, Grep, Bash, Write`
- `<role>` section defining the audit persona
- `<task>` section with the objective
- `<instructions>` with 3 phases:
  - **Phase 1**: Static analysis (29 agent coordination checks + 10 CI/config/hook checks)
  - **Phase 2**: Dynamic probes (5 checks, launched as parallel background Bash)
  - **Phase 3**: Gap analysis (5 checks) + report consolidation
- `<constraints>` section with safety rules (read-only, timeout enforcement)

### Key File Dependencies (Read-Only)

| What to read | Purpose |
|--------------|---------|
| `.claude/agents/*.md` | Agent inventory, scope extraction |
| `.claude/commands/*.md` | Skill inventory, agent references |
| `.claude/guides/agent-coordination.md` | Canonical agent-to-module mapping |
| `CLAUDE.md` | Boundary table, ruff/mypy specs, context budget limits |
| `.github/workflows/*.yml` | CI gate validation |
| `pyproject.toml` | Build config, ruff/mypy/pytest settings |
| `web/package.json` | Frontend version |
| `.claude/settings.json` | Hook registration |
| `.claude/hooks/*.py` | Hook integrity |
| `.claude/context/progress.md` | Version reference |
| `.claude/audits/*.md` | Staleness check |

### Output

`.claude/audits/AUDIT_DEVOPS.md` — YAML preamble with finding counts, then sections
P1 through P4, each finding as `[category] file:line — Description. Impact. Fix.`

## Implementation Strategy

### Phased approach

1. **Task 1**: Create the command file with Phase 1 static checks (agent coordination
   categories A-F, 29 checks + CI/config/hook checks, 10 checks = 39 total)
2. **Task 2**: Add Phase 2 dynamic probes (5 parallel background Bash checks) and Phase 3
   gap analysis + report output (5 checks + consolidation into AUDIT_DEVOPS.md)
3. **Task 3**: Smoke test — run `/devops-audit` on the live repo, verify report format,
   check that it catches at least one real finding

### Risk mitigation

- **Command file size**: 49 checks in one prompt is large but feasible — organized into
  clearly labeled phases/categories with numbered checks for traceability
- **Phase 2 hangs**: Each probe has explicit 30s timeout via Bash tool's timeout parameter
- **Missing tools**: `gh`, `pip-audit` checked with `which` before use; clean skip if absent

### Testing approach

Manual smoke test (this is a `.md` command, not testable Python code):
1. Run `/devops-audit` and verify report is written
2. Verify YAML preamble is valid
3. Verify at least one finding is detected
4. Verify report follows P1-P4 format

## Task Breakdown Preview

- [ ] Task 1: Create command file with Phase 1 static analysis (39 checks)
- [ ] Task 2: Add Phase 2 dynamic probes + Phase 3 gap analysis & report output (10 checks + synthesis)
- [ ] Task 3: Smoke test and validate report output

## Dependencies

- **Internal**: Existing `.claude/agents/*.md`, `.claude/commands/*.md`, `.claude/guides/agent-coordination.md`, `CLAUDE.md` boundary table, `.claude/audits/` directory
- **External**: `gh` CLI (optional, graceful skip), `pip-audit` (optional), `uv`
- **No blocking dependencies** — this epic creates new infrastructure without modifying existing code

## Success Criteria (Technical)

1. `/devops-audit` produces `.claude/audits/AUDIT_DEVOPS.md` in <3 minutes
2. YAML preamble is machine-parseable with correct finding counts
3. Report catches at least one real finding on first run
4. Agent coordination section correctly maps all agents and their scopes
5. Format is compatible with existing `/full-audit` reports
6. Phase 2 probes each timeout at 30s without blocking the full audit

## Tasks Created

- [ ] #495 - Create devops-audit command with Phase 1 static analysis (parallel: false)
- [ ] #496 - Add Phase 2 dynamic probes and Phase 3 gap analysis with report output (parallel: false)
- [ ] #497 - Smoke test and validate devops-audit command (parallel: false)

Total tasks: 3
Parallel tasks: 0
Sequential tasks: 3
Estimated total effort: 2-3.5 hours

## Test Coverage Plan

Total test files planned: 0 (Claude Code command — `.md` file, no Python tests)
Total test cases planned: 0 automated / 10 manual validation checks

## Estimated Effort

- **Task 1**: ~45 min (largest task — writing 39 check specifications)
- **Task 2**: ~20 min (10 checks + report template)
- **Task 3**: ~15 min (run command, verify output, iterate if needed)
- **Total**: ~1.5 hours
- **Critical path**: Linear — Task 1 → Task 2 → Task 3

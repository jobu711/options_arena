---
name: legacy-code-removal
description: Full-stack dead code audit using vulture + knip with agent verification, producing a prioritized removal hit list
status: backlog
created: 2026-03-25T01:04:13Z
---

# PRD: legacy-code-removal

## Executive Summary

Run a tooling-first dead code audit across the entire Options Arena codebase (Python backend + Vue frontend). Use `vulture` and `knip` as automated first pass, then dispatch agents to verify findings, filter false positives, and cross-reference against intel-wave PRDs. Output is a prioritized hit list the user reviews before any deletions happen.

## Problem Statement

### What problem are we solving?

Despite 3 prior dead-code-cleanup epics and the hedge-fund-frontend rebuild (which deleted 21 files / -8,846 lines), there is likely function-level and type-level dead code lurking inside active modules. Previous cleanups focused on whole-file and whole-component removal but didn't audit individual functions, unused class methods, dead type exports, or stale test helpers within active files.

### Why is this important now?

The codebase is at a clean baseline (v3.0.0, all 43 epics complete). Before starting the intel-wave epic series, this is the ideal time to audit — the codebase is stable, nothing is in flight, and removing dead code now prevents carrying it forward into the next phase of development.

## User Stories

### As a developer, I want a comprehensive dead code report so I can decide what to remove

**Acceptance criteria**:
- Report covers both Python (`src/options_arena/`) and Vue (`web/src/`)
- Each finding has file path, line numbers, confidence level, and evidence
- Findings are tiered: HIGH / MEDIUM / LOW confidence
- Intel-wave PRD references are checked — future-use code is excluded
- Report is saved as a markdown artifact in `docs/audits/`

### As a developer, I want automated tooling configured so I can re-run audits later

**Acceptance criteria**:
- `vulture` installed as dev dependency with a tuned whitelist
- `knip` configured with Vue/Pinia/Vitest plugins
- Both tools can be run with a single command each

## Architecture & Design

### Chosen Approach

Tooling-first audit (Approach B) — automated tools (`vulture` for Python, `knip` for JS/TS) provide the initial sweep, then agent verification filters false positives and adds context. Two-layer approach maximizes coverage while minimizing noise.

### Module Changes

No production module changes. This is a read-only audit.

**New files**:

| File | Purpose |
|------|---------|
| `tools/dead_code_audit.py` | Runner script: executes vulture, parses output, generates structured report |
| `web/knip.config.ts` | Knip configuration with Vue/Pinia/Vitest plugin settings |
| `.vulture_whitelist.py` | False-positive whitelist for Pydantic, Typer, PydanticAI patterns |
| `docs/audits/dead-code-audit-YYYY-MM-DD.md` | Output artifact — the prioritized hit list |

### Data Models

No new Pydantic models. The audit output is a markdown report, not a runtime data structure.

### Core Logic

**Layer 1 — Automated Tools**

| Tool | Target | Catches |
|------|--------|---------|
| `vulture` | `src/options_arena/` | Unused functions, classes, variables, imports, unreachable code |
| `knip` | `web/` | Unused exports, components, composables, types, dependencies |

**Layer 2 — Agent Verification**

Each tool finding is verified by a code-analyzer agent that:
- Checks for dynamic references (decorators, `getattr`, plugin registration)
- Confirms the code isn't referenced by intel-wave PRD plans
- Assigns confidence: HIGH / MEDIUM / LOW
- Categorizes: dead function, dead class, dead file, dead export, dead type, dead test helper

**Layer 3 — Intel-Wave Cross-Reference**

Before finalizing, scan all 8 intel-wave PRDs (`.claude/prds/intel-wave*.md`) for references to any flagged code. Anything mentioned gets marked "KEEP — future use" and excluded from the removal list.

**Vulture whitelist patterns** (false positive prevention):
- `@field_validator` / `@model_validator` decorated methods
- `@app.command()` Typer CLI handlers
- `@agent.tool` PydanticAI tool functions
- Pydantic `model_config`, `__get_validators__`, `__get_pydantic_core_schema__`
- `__all__` exports
- FastAPI route handlers (`@router.get`, `@router.post`, etc.)
- WebSocket handlers

**Knip config**:
- Vue plugin for `.vue` SFC detection
- Ignore `web/src/types/` barrel re-exports
- Ignore test utilities in `web/src/__tests__/`
- Entry points: `web/src/main.ts`, `web/src/router/index.ts`

**Hit list entry format**:

```markdown
### [HIGH] `src/options_arena/scoring/normalization.py:145` — `_legacy_zscore()`
- **Type**: Dead function
- **Evidence**: 0 callers (vulture + grep confirmed)
- **Intel-wave check**: Not referenced
- **Lines**: 145-162 (18 lines)
- **Safe to remove**: Yes
```

**Tiers**:
1. **HIGH** — zero references, safe to delete
2. **MEDIUM** — likely dead but has indirect/dynamic reference possibility
3. **LOW** — suspicious but needs human judgment

## Requirements

### Functional Requirements

1. Install `vulture` as Python dev dependency via `uv add --dev vulture`
2. Install `knip` as Node dev dependency via `npm install -D knip`
3. Create `.vulture_whitelist.py` covering all framework decorator patterns
4. Create `web/knip.config.ts` with Vue/Pinia/Vitest plugins
5. Create `tools/dead_code_audit.py` runner that executes vulture and generates markdown
6. Run vulture against `src/options_arena/`, capturing all findings
7. Run knip against `web/`, capturing all findings
8. Agent-verify each finding for false positives and dynamic references
9. Cross-reference all findings against intel-wave PRDs
10. Generate prioritized hit list report at `docs/audits/dead-code-audit-YYYY-MM-DD.md`
11. Present report for user review before any deletions

### Non-Functional Requirements

- Audit must complete within a single session (no multi-day process)
- No production code changes during the audit phase
- All tool output is deterministic and reproducible
- Whitelist is documented so future maintainers understand why each entry exists

## API / CLI Surface

N/A — this is a tooling/audit epic, not a feature.

## Testing Strategy

No new tests for the audit itself. For the removal phase (after user approves):

- **Baseline**: `uv run pytest -m "not exhaustive" -n auto -q` before any deletions
- **After each batch**: Re-run pytest to confirm nothing breaks
- **Frontend**: `cd web && npm run test` after Vue deletions
- **Lint**: `uv run ruff check .` after Python deletions
- **Type check**: `uv run mypy src/ --strict` after Python deletions

## Success Criteria

- Comprehensive hit list covering both Python and Vue codebases
- Zero false positives in HIGH confidence tier
- Intel-wave PRD code correctly excluded
- Tooling is reusable for future audits (vulture whitelist + knip config persist)
- User can review the hit list and make informed deletion decisions

## Constraints & Assumptions

- **Intel-wave PRDs are off-limits** — any code referenced by `.claude/prds/intel-wave*.md` is excluded from removal candidates
- **Audit only** — no code is deleted until the user reviews and approves the hit list
- **Framework false positives are expected** — Pydantic validators, Typer commands, FastAPI routes, and PydanticAI tools all appear "unused" to static analysis but are framework-invoked
- **Dynamic references** — some code may be called via `getattr`, string-based dispatch, or plugin registration; agent verification layer handles these

## Out of Scope

- CI integration (adding vulture/knip to GitHub Actions) — can be a follow-up
- Automated removal — this PRD produces the hit list; removal is a separate decision
- Test coverage analysis — related but distinct concern
- Dependency audit (outdated/unused pip/npm packages) — separate concern
- Refactoring live code — only dead code identification and removal

## Dependencies

- `vulture` (Python package, dev dependency)
- `knip` (npm package, dev dependency)
- Existing test suites must pass at baseline before removals begin
- All 8 intel-wave PRDs must be readable for cross-reference

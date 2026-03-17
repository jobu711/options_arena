---
name: v2-release-prep
description: Full release hardening for v2.10.0 — audit, math verification, test validation, and release cut before AI Agency Evolution (v3)
status: planned
created: 2026-03-16T13:36:46Z
---

# PRD: v2-release-prep

## Executive Summary

Harden Options Arena v2 for a clean v2.10.0 release before beginning the AI Agency Evolution epic (v3). Three phased quality gates — cleanup & audit, verification, release cut — ensure zero P1 findings, mathematically verified formulas, 100% test pass rate, clean dependencies, and a tagged release with changelog.

## Problem Statement

### What problem are we solving?

Options Arena has completed all 9 phases and 34 epics, but has never had a formal release cut. There are no git tags, no CHANGELOG, version numbers are inconsistent (`pyproject.toml` says 2.8.0, `progress.md` said 2.9.0), stale worktrees litter the repo, and uncommitted changes sit on master. Before the major architectural leap of AI Agency Evolution (v3), the codebase needs a clean, verified, tagged baseline.

### Why is this important now?

The AI Agency Evolution epic will fundamentally restructure the agent layer, add monitoring, and introduce self-improvement. Starting that work on an unverified, untagged codebase means:
- No clean rollback point if v3 changes introduce regressions
- No baseline performance numbers to compare against
- Potential hidden bugs or CVEs carried forward into the new architecture
- Mathematical formulas (BSM, BAW, GARCH, Kelly, Bordley) never formally verified against cited papers

## User Stories

### Release Confidence
- **As the developer**, I want a verified v2.10.0 baseline so that when v3 development introduces regressions, I can diff against a known-good state.
  - *Acceptance*: Git tag `v2.10.0` on master, all tests passing at that commit.

### Math Integrity
- **As a user relying on pricing and scoring**, I want all financial formulas verified against their cited academic papers so I can trust the outputs.
  - *Acceptance*: `/math-audit` passes — BSM, BAW, Greeks, GARCH/EGARCH, Hurst R/S, Kelly criterion, log-odds pooling all match cited sources.

### Dependency Safety
- **As the developer**, I want zero critical/high CVEs in dependencies before starting a new epic.
  - *Acceptance*: `dep-auditor` reports no critical or high severity CVEs.

### Clean Baseline
- **As the developer**, I want consistent version numbers, a changelog, and no stale artifacts so the repo is professional and navigable.
  - *Acceptance*: `pyproject.toml`, `progress.md`, `tech-context.md` all say 2.10.0. CHANGELOG.md exists. No stale worktrees.

## Architecture & Design

### Chosen Approach: Phased Hardening with Quality Gates

Three phases with explicit go/no-go gates. Each phase has clear "done" criteria before proceeding. `/math-audit` runs alongside `/full-audit` in Phase 1 to verify all financial formulas against cited papers.

### Phase 1: Cleanup & Audit

#### 1a. Housekeeping
- Commit or resolve uncommitted changes on master (`progress.md`, `system-patterns.md`, `tech-context.md`, `test_regime_ml.py`)
- Purge 6 stale worktrees in `.claude/worktrees/`
- Note version inconsistency for Phase 3 resolution

#### 1b. Audit Battery (parallel)
- **`/full-audit`** — 7 agents in parallel:
  - `code-reviewer`: typed model conventions, NaN defense, type annotations, Pydantic patterns, financial precision
  - `security-auditor`: API endpoint security, env var handling, OWASP Top 10, WebSocket security, input validation
  - `dep-auditor`: CVE scan, unused deps, version constraints, license compliance
  - `bug-auditor`: asyncio bugs, resource leaks, race conditions, error handling gaps
  - `db-auditor`: SQLite queries, connections, migrations, serialization, data integrity
  - `architect-reviewer`: module boundaries, dependency direction, API design, boundary table compliance
  - `oa-python-reviewer`: financial precision, architecture boundaries, pricing/scoring/indicator math, PydanticAI patterns
- **`/math-audit`** — AI-powered formula verification:
  - BSM pricing (Merton 1973) — `pricing/bsm.py`
  - BAW American approximation (Barone-Adesi-Whaley 1987) — `pricing/american.py`
  - Greeks (delta, gamma, theta, vega, rho) — `pricing/greeks.py`
  - GARCH/EGARCH volatility forecasting — `indicators/vol_forecast.py`
  - Hurst exponent R/S analysis — `indicators/hurst.py` (or equivalent)
  - Kelly criterion position sizing — `analysis/position_sizing.py`
  - Log-odds pooling (Bordley 1982) — `agents/orchestrator.py`
  - Normalization functions — `scoring/normalization.py`
  - Composite scoring weights — `scoring/composite.py`

#### 1c. Triage & Fix
- Consolidate all findings from `/full-audit` and `/math-audit`
- Prioritize: P1 (must-fix before release) vs P2 (should-fix, time permitting)
- `/fix-loop` for P1s with user approval between iterations
- Document unfixed P2s as known limitations

#### Phase 1 Gate
- All P1 findings resolved
- No critical or high CVEs in dependencies
- `/math-audit` passes (all formulas match cited papers)

### Phase 2: Verification

#### 2a. Test Suite
- Full Python test suite: `uv run pytest tests/ -v` — all 4,816+ tests must pass
- Critical tier smoke: `uv run pytest -m critical -q`
- E2E suite: Playwright (107 tests, 17 spec files) — verify web UI end-to-end

#### 2b. Optional Extras Verification
- `[ml]` extra: install `arch` + `statsmodels`, verify GARCH/regime/macro tests pass
- `[pdf]` extra: install `weasyprint`, verify debate export to PDF works

#### 2c. Migration Integrity
- Fresh database creation from migration 001 through 033
- Verify no SQL errors, no gaps in schema
- Document intentional numbering gaps (migrations skip from 009 to 010, etc.)

#### 2d. Performance Baseline
- Time a single scan pipeline run (S&P 500 preset)
- Time a single debate (any ticker)
- Time a batch debate (3 tickers)
- Record results in `docs/performance-baseline-v2.10.0.md`
- Informational only — not a blocker

#### Phase 2 Gate
- 100% Python test pass rate
- 100% E2E test pass rate
- Optional extras install and function correctly
- Migrations run cleanly from scratch

### Phase 3: Release Cut

#### 3a. Version & Changelog
- Bump `pyproject.toml` version to `2.10.0`
- Generate `CHANGELOG.md` from git history (conventional commits grouped by epic/phase)
- Update `progress.md` version to 2.10.0
- Update `tech-context.md` if version is referenced

#### 3b. Documentation Alignment
- Run `python tools/docgen.py` to regenerate `docs/technical-reference.md`
- Verify CLAUDE.md context budget within limits (`wc -l` check)
- Ensure `progress.md` has no stale "In Progress" items (FinancialDatasets.ai status check)
- Clean up any stale epic references

#### 3c. Tag & Archive
- Final commit: `chore: release v2.10.0`
- Git tag: `v2.10.0`
- Archive any remaining completed epic tracking files

#### Phase 3 Gate
- `v2.10.0` tag exists on master
- `CHANGELOG.md` present and accurate
- All context files aligned on version 2.10.0
- Clean `git status` on master

## Requirements

### Functional Requirements
1. All 7 audit agents report clean (no P1 findings)
2. `/math-audit` verifies all financial formulas against cited papers
3. All Python tests pass (4,816+ unit + parametrized)
4. All E2E tests pass (107 Playwright tests)
5. Optional extras (`[ml]`, `[pdf]`) install and function
6. Database migrations run cleanly from scratch (001-033)
7. `CHANGELOG.md` generated from git history
8. Version bumped to 2.10.0 in all locations
9. Git tag `v2.10.0` created

### Non-Functional Requirements
1. No critical or high CVEs in runtime dependencies
2. No security audit P1 findings (OWASP Top 10 compliance)
3. Performance baseline captured (scan, debate, batch debate timing)
4. Stale artifacts cleaned (worktrees, uncommitted changes)

## API / CLI Surface

No new API or CLI changes. This is a hardening and release-cut epic only.

## Testing Strategy

- **Primary verification**: Existing test suite (no new tests unless audit fixes require them)
- **If audit fixes touch logic**: Targeted test additions for those specific changes
- **E2E**: Playwright suite validates integrated web UI
- **Migration**: Fresh DB creation as integration test
- **Optional extras**: Install-and-run verification for `[ml]` and `[pdf]`

## Success Criteria

1. Git tag `v2.10.0` on master with clean commit history
2. Zero P1 audit findings across all 7 agents + math audit
3. Zero critical/high dependency CVEs
4. 100% test pass rate (Python + E2E)
5. `CHANGELOG.md` exists with complete release history
6. Performance baseline document captured
7. All context files (`progress.md`, `tech-context.md`, `pyproject.toml`) aligned on v2.10.0

## Constraints & Assumptions

- **No new features**: This epic adds zero functionality. Only fixes, verification, and release artifacts.
- **P2 deferral**: P2 findings may be documented as known limitations rather than fixed, at user discretion.
- **Performance baseline is informational**: No performance targets — just capturing numbers for v3 comparison.
- **FinancialDatasets.ai epic**: Status unclear (listed as "In Progress" in progress.md but 0 open GitHub issues). Will be documented as-is, not resolved in this epic.
- **Migration gaps are intentional**: Numbering gaps in migration files (e.g., no 025a) are expected from the epic-based development process.

## Out of Scope

- New features or functionality
- AI Agency Evolution (v3) work
- FinancialDatasets.ai epic resolution
- PyPI packaging or public distribution
- Frontend unit tests (Vitest) — deferred to future work
- CI/CD pipeline changes

## Dependencies

- **Internal**: All existing audit agents (`/full-audit`), `/math-audit` skill, `/fix-loop` skill
- **External**: None — all verification is local
- **Tooling**: `uv`, `ruff`, `mypy`, `pytest`, `playwright`, `python tools/docgen.py`

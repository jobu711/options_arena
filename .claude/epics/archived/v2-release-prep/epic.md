---
name: v2-release-prep
status: completed
created: 2026-03-17T03:13:08Z
updated: 2026-03-17T22:00:00Z
completed: 2026-03-17T22:00:00Z
progress: 100%
prd: .claude/prds/v2-release-prep.md
github: https://github.com/jobu711/options_arena/issues/564
---

# Epic: v2-release-prep

## Overview

Harden Options Arena v2 for a clean v2.10.0 release before AI Agency Evolution (v3). This is a process epic — no new features, only fixes, verification, and release artifacts. Three phased quality gates: cleanup & audit, verification, release cut. Leverages existing `/full-audit`, `/math-audit`, and `/fix-loop` skills.

## Architecture Decisions

- **No new code architecture** — this is a hardening/release process epic
- **Leverage existing audit infrastructure** — 7 audit agents + `/math-audit` already exist
- **Version sourcing**: `api/app.py` will wire to `importlib.metadata.version()` to stay in sync with `pyproject.toml` (already done in `__init__.py`)
- **CHANGELOG format**: Manual generation grouped by epic/phase using conventional commit history. No new tooling — `git log` with `--format` is sufficient
- **Performance baseline**: Informational only, not a gate. Captured as markdown doc for v3 comparison

## Technical Approach

### Phase 1: Cleanup & Audit (Tasks 001-003)

Clean stale artifacts, run full audit battery (7 agents + math audit in parallel), triage findings, fix all P1s via `/fix-loop`.

Key concerns from research:
- `/math-audit` has stale scope refs (`analysis/hv_estimators.py` → should be `indicators/`)
- Prior `/full-audit` report is stale (predates dead-code-audit's 4,933 deletions)
- `position_sizing.py` documented as "Kelly criterion" but implements vol-regime-tier heuristic — documentation discrepancy

### Phase 2: Verification (Tasks 004-005)

Run full Python test suite (4,816+ tests), E2E Playwright suite (107 tests), verify optional extras (`[ml]`, `[pdf]`), migration integrity (fresh DB from 001-033), and capture performance baseline.

### Phase 3: Release Cut (Tasks 006-007)

Bump version to 2.10.0 across 6 locations (research identified all), generate CHANGELOG.md, regenerate docs, align context files, final commit, git tag `v2.10.0`.

### Infrastructure

- No deployment changes — local tool only
- No CI/CD changes — existing 4-gate pipeline unchanged
- E2E tests run locally (not in CI Gate 4, which only covers `vue-tsc` + build)

## Implementation Strategy

- **Phase 1** runs first (audit before verification)
- **Phase 2** runs after Phase 1 gate passes (all P1s resolved)
- **Phase 3** runs after Phase 2 gate passes (100% test pass)
- Tasks within phases can partially parallelize (audit + math-audit, tests + migration check)
- Fix-loop is the main variable — could be 0 iterations (no P1s) or 3+ iterations

## Task Breakdown Preview

### Phase 1: Cleanup & Audit
- [x] 001: Housekeeping — clean stale worktrees, archive stale epics, resolve working tree state
- [x] 002: Full audit battery — `/full-audit` (7 agents) + `/math-audit` in parallel, consolidate report
- [x] 003: Triage & fix P1 findings — prioritize, `/fix-loop` for P1s, document P2s as known limitations

### Phase 2: Verification
- [x] 004: Test suite verification — Python tests, E2E, optional extras (`[ml]`, `[pdf]`), migration integrity
- [x] 005: Performance baseline — time scan pipeline, single debate, batch debate, document results

### Phase 3: Release Cut
- [x] 006: Version bump & CHANGELOG — update all 6 version locations, generate CHANGELOG.md from git history
- [x] 007: Documentation alignment & release tag — docgen, context file alignment, final commit, git tag `v2.10.0`

## Dependencies

- **Internal skills**: `/full-audit`, `/math-audit`, `/fix-loop`, `/compound`
- **Internal tools**: `uv`, `ruff`, `mypy`, `pytest`, `playwright`, `python tools/docgen.py`
- **External**: None — all verification is local
- **Live API calls**: Performance baseline (Task 005) requires Yahoo Finance/CBOE for scan timing

## Success Criteria (Technical)

1. Zero P1 audit findings across 7 agents + math audit
2. Zero critical/high dependency CVEs
3. 100% Python test pass rate (4,816+ tests)
4. 100% E2E test pass rate (107 Playwright tests)
5. All formulas verified against cited papers (`/math-audit` clean)
6. Git tag `v2.10.0` on master with clean `git status`
7. `CHANGELOG.md` present with grouped release history
8. Version 2.10.0 in: `pyproject.toml`, `web/package.json`, `progress.md`, `api/app.py`, `docs/technical-reference.md`
9. Performance baseline document captured

## Estimated Effort

- **Overall**: Medium (M) — 2-3 days elapsed
- **Task 001** (Housekeeping): XS — 30 min
- **Task 002** (Audit battery): M — 1-2 hours (agent runtime + review)
- **Task 003** (Fix P1s): S-L variable — depends on finding count (0 P1s = skip, 5+ P1s = half day)
- **Task 004** (Test verification): S — 1 hour (mostly waiting for test runs)
- **Task 005** (Performance baseline): S — 30-60 min (requires live API)
- **Task 006** (Version & CHANGELOG): S — 1-2 hours (manual CHANGELOG grouping)
- **Task 007** (Doc alignment & tag): XS — 30 min
- **Critical path**: Task 003 (P1 fix count is unknown until audits complete)

## Tasks Created
- [x] #565 - Housekeeping & Stale Artifact Cleanup (parallel: true)
- [x] #567 - Full Audit Battery (parallel: false, depends: #565)
- [x] #570 - Triage & Fix P1 Findings (parallel: false, depends: #567)
- [x] #566 - Test Suite & Migration Verification (parallel: false, depends: #570)
- [x] #568 - Performance Baseline (parallel: true, depends: #570)
- [x] #569 - Version Bump & CHANGELOG (parallel: false, depends: #566, #568)
- [x] #571 - Documentation Alignment & Release Tag (parallel: false, depends: #569)

Total tasks: 7
Parallel tasks: 2 (#565, #568)
Sequential tasks: 5 (#567, #570, #566, #569, #571)
Estimated total effort: 6-15 hours (variable due to P1 fix count)

## Test Coverage Plan
Total test files planned: 0 (process epic — runs existing 4,816+ Python tests + 107 E2E tests)
Total test cases planned: 0 new (audit fixes in Task 003 may add targeted tests as needed)

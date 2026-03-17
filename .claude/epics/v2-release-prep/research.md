# Research: v2-release-prep

## PRD Summary

Harden Options Arena v2 for a clean v2.10.0 release before AI Agency Evolution (v3). Three phased quality gates: (1) cleanup & audit (7 agents + math-audit), (2) test verification + migration integrity + performance baseline, (3) version bump + CHANGELOG + git tag. No new features — fixes, verification, and release artifacts only.

## Relevant Existing Modules

- `pricing/` — BSM + BAW formulas subject to `/math-audit` verification (bsm.py: 458 lines, american.py: 774 lines)
- `indicators/` — GARCH/EGARCH (vol_forecast.py), Hurst (hurst.py), regime detection (regime_ml.py), HV estimators (hv_estimators.py) — all subject to math audit
- `scoring/` — normalization.py, composite.py, direction.py — standard techniques, no citation issues
- `agents/orchestrator.py` — log-odds pooling (Bordley 1982), Shannon entropy, Brier score — weak citations
- `analysis/position_sizing.py` — documented as "Kelly criterion" but implements vol-regime-tier heuristic
- `api/app.py` — hardcoded `version="1.5.0"` in FastAPI constructor, completely out of sync
- `data/migrations/` — 33 sequential files (001-033), no gaps
- `tools/docgen.py` — AST-based doc generator for `docs/technical-reference.md`

## Existing Patterns to Reuse

- **`/full-audit`**: Orchestrates 7 audit agents in parallel, outputs to `.claude/audits/FULL_AUDIT.md`. Prior audit exists but is stale (pre-dead-code-audit). Must re-run from scratch.
- **`/math-audit`**: 5-phase read-only formula verification command. Scope covers pricing/, indicators/, scoring/, analysis/. Has a stale scope reference (`analysis/hv_estimators.py` should be `indicators/hv_estimators.py`; `analysis/probability.py` does not exist).
- **`/fix-loop`**: Iterative audit-fix-verify with user approval between iterations. Max 3 iterations.
- **`/release-prep`**: 6-phase release workflow (audit → fix → verify → docs → compound → PR). Can be used as orchestration skeleton.
- **Conventional commits**: `chore:`, `feat:`, `fix:`, etc. — makes CHANGELOG grouping straightforward.
- **CI gates**: 4 gates (lint, typecheck, tests, frontend) already enforced on push/PR to master.
- **`pip-audit`**: Already wired into Gate 3 CI for CVE scanning.
- **`pytest-benchmark`**: 83 math functions benchmarked in `tests/audit/performance/test_benchmarks.py`.

## Version Locations — All Must Be Updated to 2.10.0

| File | Current | Action |
|------|---------|--------|
| `pyproject.toml` line 7 | `"2.8.0"` | Manual bump |
| `web/package.json` line 3 | `"2.8.0"` | Manual bump |
| `web/package-lock.json` lines 3, 9 | `"2.8.0"` | `npm install` after package.json change |
| `.claude/context/progress.md` | `2.8.0` | Manual edit |
| `src/options_arena/api/app.py` line 187 | `"1.5.0"` | Wire to `importlib.metadata` or manual bump |
| `docs/technical-reference.md` | `2.8.0` | Auto-updated by `python tools/docgen.py` |
| `src/options_arena/__init__.py` | Dynamic | Reads from pyproject.toml via `importlib.metadata` — no change needed |

## Existing Code to Extend

- **`tools/docgen.py`** — Already generates `docs/technical-reference.md`. Run after version bump.
- **`tools/math_audit_report.py`** — Generates markdown from `AuditReport`/`AuditFinding` models.
- **`tests/audit/`** — 3 categories: correctness (4 files), stability (4 files), performance (1 file). Infrastructure exists for math verification.
- **`tach.toml`** — Architecture boundary enforcement (`exact=true`, `forbid_circular_dependencies=true`). Can be run as additional verification.

## Potential Conflicts

- **`api/app.py` version="1.5.0"**: Completely out of sync. Must be fixed — either hardcode `"2.10.0"` or wire dynamically to `importlib.metadata.version("options-arena")`.
- **`/math-audit` scope stale**: References `analysis/hv_estimators.py` (should be `indicators/`) and `analysis/probability.py` (doesn't exist). Command file may need scope fix before running.
- **`system-patterns.md` says position_sizing.py implements "Kelly criterion"**: Actual implementation is a vol-regime-tier heuristic. Documentation discrepancy — needs correction.
- **FinancialDatasets.ai epic**: Listed as "In Progress" in progress.md but archived with 0 open GitHub issues. PRD says document as-is — update progress.md to clarify status.
- **Prior audit stale**: `.claude/audits/FULL_AUDIT.md` from `epic/scientific-ml-neural` branch predates dead-code-audit (4,933 deletions, 119 files changed). Must re-run fresh.

## Stale Artifacts to Clean

| Artifact | Status | Action |
|----------|--------|--------|
| 6 dirs in `.claude/worktrees/` | Not git worktrees, just abandoned session dirs | `rm -rf .claude/worktrees/agent-*` |
| `scientific-ml-integration/` epic | Completed, all children merged | Archive to `.claude/epics/archived/` |
| Git working tree | Clean (no uncommitted changes) | PRD concern already resolved |

## Open Questions

1. **CHANGELOG format**: Manual or scripted? No tooling exists for auto-generation. Conventional commit prefixes make manual grouping feasible. Should we group by epic/phase or by commit type?
2. **E2E tests**: Not in CI (Gate 4 only covers `vue-tsc` + `npm run build`). PRD requires 100% E2E pass — run locally only?
3. **`[neural]` extra**: Not mentioned in PRD optional extras verification (only `[ml]` and `[pdf]`). The `[neural]` extra (`lightning`, `torch`) exists in pyproject.toml — include in verification?
4. **`pip-licenses`**: In dev deps but not in CI. PRD mentions "no critical/high CVEs" but not license compliance. Skip or include?
5. **Performance baseline scope**: PRD says "time a single scan pipeline run (S&P 500 preset)" — this requires live API calls (Yahoo Finance, CBOE). Is that acceptable for a release-cut process?

## Citation Status (for /math-audit)

| File | Citation Quality | Notes |
|------|-----------------|-------|
| `pricing/bsm.py` | STRONG | Merton 1973, full formula in docstring |
| `pricing/american.py` | MODERATE | BAW 1987 in module docstring only, no inline refs |
| `indicators/vol_forecast.py` | STRONG | Bollerslev 1986, Dickey-Fuller 1979 — full journal refs |
| `indicators/hurst.py` | STRONG | Mandelbrot & Wallis 1969 — full journal ref |
| `indicators/regime_ml.py` | STRONG | Hamilton 1989 — full journal ref |
| `indicators/hv_estimators.py` | EXCELLENT | Yang & Zhang 2000 — equation-level refs |
| `agents/orchestrator.py` | WEAK | "Bordley 1982" year only, no full reference |
| `scoring/normalization.py` | N/A | Standard technique |
| `scoring/composite.py` | N/A | Standard technique |
| `analysis/position_sizing.py` | N/A | Custom heuristic (not Kelly despite docs) |

## Test Infrastructure Summary

- **Python tests**: 4,816 (27K parametrized) across 292 test files
- **Markers**: `critical` (<30s pre-commit), `exhaustive` (nightly), `integration`, `db`, `audit_correctness`, `audit_stability`, `audit_performance`
- **E2E**: 107 Playwright tests, 17 spec files, 6 projects (isolated DBs on ports 8001-8006), 4 parallel workers
- **CI**: 4 gates (lint, typecheck, tests, frontend) + nightly full suite + weekly benchmarks
- **Conftest**: xdist-safe, warns on unmarked tests, shared fixtures

## Recommended Architecture

This is a process epic, not a feature epic. No new code architecture needed. Execution follows the PRD's 3-phase structure directly:

1. **Phase 1** (Cleanup & Audit): Clean stale artifacts → `/full-audit` + `/math-audit` in parallel → triage → `/fix-loop` for P1s
2. **Phase 2** (Verification): Full test suite → E2E → optional extras → migration integrity → performance baseline
3. **Phase 3** (Release Cut): Version bump all locations → CHANGELOG.md → docgen → final commit → git tag `v2.10.0`

Each phase has a clear gate. The `/release-prep` skill can serve as orchestration skeleton but the PRD's 3-phase structure is more granular and should take precedence.

## Test Strategy Preview

- **No new tests expected** unless audit fixes touch logic
- **Existing audit tests**: `tests/audit/correctness/` (4 files), `tests/audit/stability/` (4 files) — run these as part of math verification
- **Migration test**: Create fresh DB from migrations 001-033, verify no SQL errors
- **Optional extras**: Install `uv pip install -e ".[ml]"` and `uv pip install -e ".[pdf]"`, run relevant test subsets
- **Performance**: `pytest -m audit_performance --benchmark-enable` for math function timing; manual timing for scan/debate/batch

## Estimated Complexity

**Medium (M)** — No new code to write. Complexity comes from:
- Running and triaging 7 audit agents + math audit (time-intensive but mechanical)
- Fixing P1 findings (unknown count until audits run)
- Version alignment across 6 files
- Manual CHANGELOG generation from git history (~35 epics worth of commits)
- Performance baseline requires live API calls

The fix-loop for P1s is the main variable — could be trivial (0 P1s) or significant (5+ P1s requiring code changes and test updates).

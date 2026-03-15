---
name: mathematical-computation-audit
status: backlog
created: 2026-03-14T14:42:25Z
progress: 0%
prd: .claude/prds/mathematical-computation-audit.md
github: https://github.com/jobu711/options_arena/issues/505
---

# Epic: mathematical-computation-audit

## Overview

Build a repeatable, CI-gated audit framework that validates all 87 mathematical functions across pricing (17), indicators (53), scoring (16), and orchestration (5) modules. Three deterministic test layers — correctness (academic + QuantLib cross-validation), stability (Hypothesis property-based + extreme inputs + NaN injection), and performance (pytest-benchmark) — form the permanent CI gates. A quant-analyst agent discovery layer runs on-demand to surface issues that deterministic tests miss. Read-only audit: no source code modifications to audited modules.

## Architecture Decisions

- **Pre-generated QuantLib baselines**: QuantLib is a dev-only dependency used solely by `tools/generate_quantlib_baselines.py` to produce JSON fixtures. Tests load JSON — QuantLib is never required at test runtime. If QuantLib wheels are unavailable for Python 3.13/Windows, baseline generation runs in a CI Linux container.
- **Explicit function registry over AST scanning**: A `MATH_FUNCTION_REGISTRY` dict in `tests/audit/conftest.py` maps module paths to function names. More maintainable than fragile AST parsing rules and makes the audit scope explicit and reviewable.
- **Hypothesis profiles**: `ci` profile (100 examples, <30s) for PR gates; `thorough` profile (1000 examples) for manual deep runs. Seed database `.hypothesis/` committed for reproducibility.
- **Performance baselines are informational**: pytest-benchmark runs weekly in CI (not per-commit — hardware variance makes per-commit noisy). >20% regression flags a warning, not a hard failure.
- **Agent discovery is non-blocking**: `/math-audit` skill findings are advisory. Confirmed issues are manually codified as new deterministic tests.
- **No new runtime dependencies**: hypothesis, pytest-benchmark, and QuantLib are dev-only.
- **Models in `models/audit.py`**: AuditFinding, AuditReport, AuditLayerSummary follow frozen model pattern. AuditSeverity/AuditLayer StrEnums go in `enums.py`.
- **CLI follows outcomes pattern**: `audit_app = typer.Typer()` registered via `app.add_typer()`, sync command wrapping async with `asyncio.run()`.

## Technical Approach

### No Frontend/API Components
This is a developer/CI tool only. No API endpoints, no frontend components.

### Backend Components
- **Models**: `AuditSeverity`, `AuditLayer` StrEnums + `AuditFinding`, `AuditLayerSummary`, `AuditReport` frozen Pydantic models
- **CLI**: `options-arena audit math` with flags `--correctness`, `--stability`, `--performance`, `--report`, `--discover`
- **Report generator**: `tools/math_audit_report.py` — pure function taking AuditReport model → markdown string
- **QuantLib baseline generator**: `tools/generate_quantlib_baselines.py` — dev-only script producing `quantlib_baselines.json`
- **Test suite**: `tests/audit/` with correctness/, stability/, performance/ subdirectories + reference_data/

### Infrastructure
- 3 new pytest markers: `audit_correctness`, `audit_stability`, `audit_performance`
- 2 new dev dependencies: `hypothesis`, `pytest-benchmark`
- 1 optional dev dependency: `QuantLib` (for baseline generation only)
- CI integration: `pytest -m "audit_correctness or audit_stability"` added to PR gate

## Implementation Strategy

Tasks are ordered by dependency. Tasks 1-2 are foundation. Tasks 3-5 are the three audit layers (3 & 4 can run in parallel). Tasks 6-7 are the CLI/report wrapper and agent discovery. Task 8 is CI integration.

## Task Breakdown Preview

- [ ] Task 1: Foundation — models, enums, dev dependencies, pytest markers, directory structure
- [ ] Task 2: Reference data — academic known-values JSON fixtures + QuantLib baseline generator tool
- [ ] Task 3: Correctness tests — all 87 functions vs academic + QuantLib baselines (4 test files)
- [ ] Task 4: Stability tests — Hypothesis strategies + extreme input battery + NaN/Inf injection for all modules (4 test files)
- [ ] Task 5: Performance benchmarks — pytest-benchmark for all function groups with baseline storage
- [ ] Task 6: CLI command + report generator — `audit math` subcommand + `math_audit_report.py` + coverage meta-test
- [ ] Task 7: Agent discovery skill — `/math-audit` skill definition + quant-analyst prompt enhancement
- [ ] Task 8: CI integration — add audit markers to GitHub Actions PR gate + weekly performance schedule

## Dependencies

### Internal
- All mathematical modules (read-only): `pricing/`, `indicators/`, `scoring/`, `agents/orchestrator.py`
- Existing test infrastructure: `conftest.py`, pytest markers, factories
- CLI registration: `cli/app.py` (add_typer pattern from outcomes.py)
- quant-analyst agent config: `.claude/agents/quant-analyst.md`

### External (dev-only)
| Package | Purpose |
|---------|---------|
| `hypothesis` | Property-based testing for stability layer |
| `pytest-benchmark` | Performance regression detection |
| `QuantLib` | Cross-validation oracle (baseline generation only, optional) |

### Blockers
- QuantLib Python 3.13/Windows wheel availability — mitigated by Docker/CI fallback for baseline generation

## Success Criteria (Technical)

1. All 87 mathematical functions have correctness tests with academic references + QuantLib cross-validation
2. Zero silent NaN propagation: every function produces finite output or raises clean ValueError on bad input
3. Performance baselines established for all functions with <5% variance between runs
4. Coverage meta-test asserts every registered function has tests in all 3 layers
5. `pytest -m "audit_correctness or audit_stability"` completes in <60s
6. `pytest -m audit_performance` completes in <120s
7. `options-arena audit math --report` produces valid markdown in <5s
8. Agent discovery surfaces at least 3 findings not caught by deterministic tests

## Estimated Effort

- **8 tasks** across a single epic
- **Complexity**: L (Large) — 87 functions × 3 layers, but read-only audit with well-established test patterns
- **Parallelism**: Tasks 3 & 4 can run in parallel after Task 2 completes
- **Critical path**: Tasks 1 → 2 → 3 → 6 (foundation → data → tests → CLI)

## Tasks Created
- [ ] #506 - Foundation — Models, Enums, Dev Dependencies, Markers, Directory Structure (parallel: false)
- [ ] #508 - Reference Data — Academic Known-Values JSON + QuantLib Baseline Generator (parallel: false)
- [ ] #510 - Correctness Tests — All 87 Functions vs Academic + QuantLib Baselines (parallel: true)
- [ ] #512 - Stability Tests — Hypothesis + Extreme Inputs + NaN Injection (parallel: true)
- [ ] #507 - Performance Benchmarks — pytest-benchmark for All Function Groups (parallel: true)
- [ ] #509 - CLI Command + Report Generator + Coverage Meta-Test (parallel: false)
- [ ] #511 - Agent Discovery Skill — /math-audit Skill + Quant-Analyst Prompt Enhancement (parallel: false)
- [ ] #513 - CI Integration — GitHub Actions PR Gate + Weekly Performance Schedule (parallel: false)

Total tasks: 8
Parallel tasks: 3 (#510, #512, #507 — after foundation complete)
Sequential tasks: 5 (#506, #508, #509, #511, #513)
Estimated total effort: 68-92 hours

## Test Coverage Plan
Total test files planned: 13
Total test cases planned: ~50+ test methods across correctness, stability, performance, CLI, coverage meta, report, and agent skill

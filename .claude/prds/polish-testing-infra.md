---
name: polish-testing-infra
description: Speed up CI pipeline, add model factories, improve test organization and parallel safety
status: backlog
created: 2026-03-10T14:22:09Z
---

# PRD: polish-testing-infra

## Executive Summary

Options Arena has ~4,400 Python tests and a 4-gate CI pipeline, but the infrastructure
has accumulated friction: no dependency caching in CI, no model factories for test data,
an empty root conftest, and no verification that all tests are xdist-safe. This epic
polishes the testing infrastructure to make CI faster, tests easier to write, and
parallel execution reliable.

## Problem Statement

1. **CI is slow** — Every gate runs `uv sync --frozen` from scratch with no caching.
   Four gates each install all dependencies independently. mypy has no cache persistence.
2. **No model factories** — Tests construct Pydantic models inline with verbose kwargs.
   Common models like `OptionContract`, `Quote`, `MarketContext` require 10+ fields each
   time, leading to boilerplate and inconsistency across test files.
3. **Scattered fixtures** — Root `tests/conftest.py` is empty (1 line). Fixtures live in
   4 module-level conftest files (459 lines total) with likely duplication. No shared
   utilities layer.
4. **Parallel safety unverified** — Tests run with `-n auto` but there's no systematic
   verification that all tests are xdist-safe (no shared state, no file conflicts,
   no ordering dependencies).

## User Stories

### US-1: Developer running CI
**As a** contributor pushing a PR,
**I want** CI to complete significantly faster,
**So that** I get feedback quickly and don't context-switch waiting for results.

**Acceptance criteria:**
- uv dependency cache restored between CI runs
- mypy cache restored between CI runs
- Total CI wall-clock time reduced (measured before/after)

### US-2: Developer writing new tests
**As a** developer adding tests for a new feature,
**I want** model factories that create valid test objects with sensible defaults,
**So that** I only specify the fields relevant to my test case.

**Acceptance criteria:**
- Factory functions exist for core models: `OptionContract`, `Quote`, `MarketContext`,
  `DebateResult`, `ScanResult`, `CompositeScore`
- Each factory produces a valid model instance with zero required args
- Fields can be overridden via kwargs
- Factories are importable from a single `tests/factories.py` module

### US-3: Developer running tests locally
**As a** developer running `pytest -n auto`,
**I want** confidence that all tests are parallel-safe,
**So that** I don't get intermittent failures from shared state or ordering dependencies.

**Acceptance criteria:**
- All tests pass with `-n auto` (parallel) and without `-n` (sequential)
- Any tests that require isolation are marked with `@pytest.mark.serial` or equivalent
- No tests write to shared file paths without unique temp directories

## Requirements

### Functional Requirements

#### FR-1: CI Dependency Caching
- Add `actions/cache` for uv's cache directory (`~/.cache/uv`) keyed on `uv.lock` hash
- Add `actions/cache` for mypy cache (`.mypy_cache/`) in the type-check gate
- Verify cache hit/miss behavior across consecutive runs

#### FR-2: Model Factories Module
- Create `tests/factories.py` with factory functions for core Pydantic models
- Each factory returns a valid, frozen-compatible model instance with realistic defaults
- Support kwarg overrides: `make_option_contract(strike=150.0, option_type=OptionType.PUT)`
- Use `Decimal` strings for price fields, proper UTC datetimes, valid StrEnum values
- No external dependencies (no `factory_boy` or `faker` — plain functions)

#### FR-3: Conftest Consolidation
- Audit all conftest files for duplicate or near-duplicate fixtures
- Move shared fixtures to root `tests/conftest.py` using the new factories
- Keep module-specific fixtures in their respective conftest files
- Ensure no fixture name collisions

#### FR-4: Parallel Test Safety Audit
- Run full suite with `-n auto` and verify all pass
- Run full suite sequentially and verify all pass
- Identify any tests with shared mutable state, temp file conflicts, or ordering deps
- Fix or isolate any unsafe tests found

### Non-Functional Requirements

- **No new dependencies** — factories use plain Python functions, no third-party libraries
- **Backwards compatible** — existing test imports and fixtures continue to work
- **Incremental** — each issue can be merged independently without breaking others

## Success Criteria

| Metric | Target |
|--------|--------|
| CI cache hit rate | >90% on repeat runs |
| CI total time (repeat run) | Measurably faster than baseline (capture before/after) |
| Factory coverage | Factories for 6+ core models |
| Root conftest | Shared fixtures moved from module conftest where duplicated |
| Parallel safety | 0 failures unique to `-n auto` mode |

## Constraints & Assumptions

- **GitHub Actions** is the CI platform (no migration)
- **uv** is the package manager (no pip/poetry)
- **pytest + pytest-xdist** is the test runner (no migration)
- Tests already pass on master — this is polish, not fixing broken tests
- The 2 known pre-existing failures in `test_expanded_context.py` are excluded from scope

## Out of Scope

- **Writing new feature tests** — this epic improves infra only, not test coverage
- **Framework migration** — no switching from pytest, Playwright, or GitHub Actions
- **Frontend unit tests** — Vitest/Vue Test Utils is separate future work
- **Performance benchmarks** — no benchmark suite or perf regression testing
- **E2E test improvements** — Playwright tests are not in scope for this epic
- **Coverage reporting** — can be a follow-up epic

## Dependencies

- Access to GitHub Actions workflow file (`.github/workflows/ci.yml`)
- Knowledge of uv cache directory structure on Ubuntu
- Understanding of mypy incremental cache format
- Familiarity with all Pydantic models in `src/options_arena/models/`

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Cache invalidation issues in CI | Medium | Key caches on lock file hash + Python version |
| Factory defaults drift from model changes | Low | Factories use model constructors — type errors caught by mypy |
| Conftest refactor breaks imports | Low | Run full test suite after each conftest change |

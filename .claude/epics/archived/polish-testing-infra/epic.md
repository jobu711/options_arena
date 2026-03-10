---
name: polish-testing-infra
status: backlog
created: 2026-03-10T15:04:45Z
progress: 0%
prd: .claude/prds/polish-testing-infra.md
github: https://github.com/jobu711/options_arena/issues/445
---

# Epic: polish-testing-infra

## Overview

Polish the testing infrastructure to make CI faster, tests easier to write, and parallel
execution verified. Four focused changes: CI dependency caching, model test factories,
conftest fixture consolidation, and parallel safety documentation.

## Architecture Decisions

- **No new dependencies** — factories are plain Python functions, no `factory_boy` or `faker`
- **Single factories module** at `tests/factories.py` — flat import path, no nested package
- **Reuse existing pattern** — `scoring/conftest.py:make_contract()` is the template for all factories
- **`astral-sh/setup-uv@v4` built-in caching** — use `enable-cache: true` instead of separate `actions/cache@v4` for uv; separate `actions/cache@v4` only for mypy
- **Parallel safety already verified** — research confirmed zero xdist conflicts across 247 files; this issue is documentation-only

## Technical Approach

### CI Dependency Caching (FR-1)

Modify `.github/workflows/ci.yml`:
1. Add `enable-cache: true` to all `astral-sh/setup-uv@v4` steps (gates 1-3)
2. Add `actions/cache@v4` for `.mypy_cache/` in the typecheck gate, keyed on `uv.lock` hash + source file hash
3. Verify via CI run logs that cache hits occur on repeat runs

### Model Factories Module (FR-2)

Create `tests/factories.py` with 9 factory functions:
- `make_option_contract(**kw)` — migrated from `scoring/conftest.py:make_contract()`
- `make_quote(**kw)` — 6 required fields with realistic defaults
- `make_market_context(**kw)` — 18 required + 58 optional fields, sensible defaults
- `make_ticker_score(**kw)` — composite score + nested signals
- `make_dimensional_scores(**kw)` — all-optional dimensional breakdown
- `make_agent_response(**kw)` — agent output with direction, confidence, reasoning
- `make_trade_thesis(**kw)` — risk agent output with strategy, entry/exit
- `make_debate_result(**kw)` — full debate with nested sub-factories
- `make_scan_result(**kw)` — scan pipeline output

Each factory: zero required args, proper `Decimal("...")` strings, `datetime.now(UTC)`,
valid `StrEnum` values, kwarg overrides. Frozen models constructed in one call.

Add `tests/unit/test_factories.py` to verify each factory produces a valid model,
kwargs override correctly, and frozen construction succeeds.

### Conftest Consolidation (FR-3)

1. Move `make_contract()` from `tests/unit/scoring/conftest.py` to `tests/factories.py` as `make_option_contract()` — update imports in scoring tests
2. Move shared config fixtures (`default_scan_config`, `default_pricing_config`) to root `tests/conftest.py`
3. Add factory-based convenience fixtures to root conftest for cross-module use
4. Delete empty `tests/unit/scan/conftest.py`
5. Keep domain-specific fixtures in their module conftest files (agents, api, scoring)

### Parallel Safety Documentation (FR-4)

Research already confirmed all tests are xdist-safe. Document this finding:
- Add parallel safety note to `tests/CLAUDE.md`
- No code changes needed — zero shared state, zero fixed paths, zero ordering deps

## Implementation Strategy

**Single wave** — all 4 issues are independent and can be merged in any order.
Recommended sequence for cleanest diffs:

1. CI caching (smallest change, immediate ROI)
2. Model factories (foundation for conftest consolidation)
3. Conftest consolidation (depends on factories existing)
4. Parallel safety docs (trivial, can go anytime)

Issues 1, 2, and 4 are fully independent. Issue 3 logically follows issue 2.

## Task Breakdown Preview

- [ ] Issue 1: Add CI dependency caching (uv + mypy) to GitHub Actions workflow
- [ ] Issue 2: Create model factory functions in `tests/factories.py` + unit tests
- [ ] Issue 3: Consolidate conftest fixtures using factories
- [ ] Issue 4: Document parallel test safety verification in `tests/CLAUDE.md`

## Dependencies

- **Internal**: Issue 3 (conftest) benefits from Issue 2 (factories) being done first
- **External**: None — all changes are within existing infrastructure
- **Prerequisite**: None — tests already pass on master

## Success Criteria (Technical)

| Metric | Target |
|--------|--------|
| CI cache hit | uv cache restored on repeat runs (visible in Actions logs) |
| mypy cache hit | `.mypy_cache` restored on repeat runs |
| Factory count | 9 factory functions covering 7+ core models |
| Factory tests | All factories produce valid models, kwargs work |
| Root conftest | Shared fixtures migrated, no duplicates |
| Parallel safety | Documented in `tests/CLAUDE.md` |
| Test suite | All existing tests still pass after changes |

## Estimated Effort

- **Overall**: Small-Medium (4 focused issues, no architectural changes)
- **Issue 1** (CI caching): ~15 lines of YAML changes
- **Issue 2** (factories): ~300 lines new code + ~100 lines tests
- **Issue 3** (conftest): ~50 lines moved/refactored
- **Issue 4** (parallel docs): ~10 lines documentation
- **Critical path**: Issue 2 → Issue 3 (sequential); Issues 1 and 4 independent

## Tasks Created

- [ ] #446 - Add CI dependency caching (uv + mypy) (parallel: true)
- [ ] #447 - Create model factory functions with unit tests (parallel: true)
- [ ] #448 - Consolidate conftest fixtures using factories (parallel: false, depends: #447)
- [ ] #449 - Document parallel test safety verification (parallel: true)

Total tasks: 4
Parallel tasks: 3
Sequential tasks: 1
Estimated total effort: 7.5 hours

## Test Coverage Plan

Total test files planned: 1
Total test cases planned: 13

# Research: polish-testing-infra

## PRD Summary

Speed up CI pipeline (add uv + mypy caching), create model factories for test data, consolidate scattered conftest fixtures, and verify parallel test safety with pytest-xdist.

## Relevant Existing Modules

- `.github/workflows/ci.yml` — 4-gate CI pipeline (lint, typecheck, tests, frontend). No uv caching, no mypy caching. Frontend gate already caches npm.
- `tests/` — 247 test files, ~4,400 tests (863 collected, ~24K parametrized). 5 conftest files (459 lines total).
- `src/options_arena/models/` — All Pydantic models that need factories (OptionContract, Quote, MarketContext, DebateResult, ScanResult, TickerScore, DimensionalScores).
- `pyproject.toml` — pytest config (asyncio_mode=auto, 4 markers, xdist, timeout=60s), mypy strict config.

## Existing Patterns to Reuse

### 1. Factory Function Pattern (scoring/conftest.py:97-141)
`make_contract()` already exists as a keyword-only builder function (NOT a pytest fixture) returning a frozen `OptionContract`. This is the exact pattern to replicate for all models.

### 2. Fixture Scoping Pattern
All fixtures use function scope (default). Database fixtures create fresh `:memory:` DBs with `yield` + cleanup. API fixtures create fresh FastAPI app instances with fresh dependency overrides per test.

### 3. UTC Datetime Convention
All timestamp fields use `datetime(..., tzinfo=UTC)`. Factories should default to `datetime.now(UTC)`.

### 4. Decimal String Convention
All price fields constructed as `Decimal("185.00")` (string-based). Factories should accept `Decimal | float | str` and normalize internally.

## Existing Code to Extend

### CI Workflow (`.github/workflows/ci.yml`)
- **Current**: 4 parallel gates, each runs `uv sync --frozen` cold. Only frontend caches npm.
- **Change**: Add `actions/cache@v4` for uv cache dir in gates 1-3. Add mypy cache in gate 2.
- **Key**: `astral-sh/setup-uv@v4` already used — check if it supports built-in caching.

### Conftest Files
| File | Lines | Fixtures | Action |
|------|-------|----------|--------|
| `tests/conftest.py` | 1 | 0 | Populate with shared fixtures using factories |
| `tests/unit/agents/conftest.py` | 202 | 10 | Keep agent-specific, refactor to use factories |
| `tests/unit/scoring/conftest.py` | 141 | 6+1 factory | Keep scoring-specific, extract `make_contract()` to factories |
| `tests/unit/api/conftest.py` | 114 | 8 | Keep API-specific (DI mocks, app setup) |
| `tests/unit/scan/conftest.py` | 1 | 0 | Delete (empty) |

### Models Requiring Factories (by boilerplate severity)

| Model | Required Fields | Complexity | Location |
|-------|----------------|------------|----------|
| MarketContext | 18 required + 58 optional | EXTREME | `models/analysis.py` |
| DebateResult | 7 complex nested models | CRITICAL | `agents/_parsing.py` |
| ScanResult | 3 complex nested types | VERY HIGH | `scan/models.py` |
| OptionContract | 11 required + 4 optional | HIGH | `models/options.py` |
| TickerScore | 3 required + nested signals | MEDIUM | `models/scan.py` |
| Quote | 6 required | MEDIUM | `models/market_data.py` |
| DimensionalScores | 0 required (all optional) | LOW | `models/scoring.py` |

**Note**: PRD lists `CompositeScore` but this model doesn't exist. It's a `float` field on `TickerScore`. Replace with `TickerScore` + `DimensionalScores` factories.

## Potential Conflicts

- **`make_contract()` already exists** in `scoring/conftest.py` — must migrate to `tests/factories.py` and update imports. Keep backward-compatible import or update all 141 lines of scoring tests.
- **Frozen models** — `OptionContract`, `Quote`, `DebateResult` are frozen. Factories must construct fully in one call (no post-init mutation).
- **MarketContext is NOT frozen** — it's populated incrementally in production. Factory can set all fields at once.

## Open Questions

1. **`astral-sh/setup-uv@v4` caching** — Does it have built-in cache support, or do we need separate `actions/cache@v4`? (Research needed at implementation time.)
2. **Factory location** — PRD says `tests/factories.py`. Should it be `tests/factories.py` or `tests/fixtures/factories.py`? Recommend `tests/factories.py` (simpler import path).
3. **Sub-factories for nested models** — DebateResult needs AgentResponse, TradeThesis, RunUsage sub-factories. How many helper factories total?

## Recommended Architecture

### CI Caching (Issue 1)
```yaml
# Each gate gets uv cache restoration
- uses: astral-sh/setup-uv@v4
  with:
    version: "latest"
    enable-cache: true  # If supported, otherwise actions/cache@v4

# Gate 2 additionally gets mypy cache
- uses: actions/cache@v4
  with:
    path: .mypy_cache
    key: mypy-${{ hashFiles('uv.lock') }}-${{ hashFiles('src/**/*.py') }}
    restore-keys: mypy-${{ hashFiles('uv.lock') }}-
```

### Model Factories (Issue 2)
```
tests/factories.py
├── make_option_contract(**kwargs) → OptionContract
├── make_quote(**kwargs) → Quote
├── make_market_context(**kwargs) → MarketContext
├── make_ticker_score(**kwargs) → TickerScore
├── make_dimensional_scores(**kwargs) → DimensionalScores
├── make_agent_response(**kwargs) → AgentResponse
├── make_trade_thesis(**kwargs) → TradeThesis
├── make_debate_result(**kwargs) → DebateResult
└── make_scan_result(**kwargs) → ScanResult
```
Each factory: zero required args, sensible defaults, kwarg overrides, proper Decimal/UTC/StrEnum handling.

### Conftest Consolidation (Issue 3)
- Move `default_scan_config`, `default_pricing_config` → root conftest
- Move `make_contract()` → `tests/factories.py` (rename to `make_option_contract`)
- Add factory-based fixtures to root conftest for cross-module use
- Delete empty `tests/unit/scan/conftest.py`

### Parallel Safety (Issue 4)
- **Already safe** — zero xdist conflicts found across 247 test files
- Zero global state, zero fixed file paths, zero ordering deps
- All DB tests use `:memory:`, all file tests use `tmp_path`
- Document this in `tests/CLAUDE.md` and close the issue

## Test Strategy Preview

- Factories themselves need tests: `tests/unit/test_factories.py`
  - Each factory produces valid model (no ValidationError)
  - Kwarg overrides work
  - Decimal/UTC/StrEnum defaults are correct
  - Frozen models don't raise on construction
- CI caching: manual verification via GitHub Actions run logs (cache hit/miss)
- Conftest: run full test suite after each consolidation step

## Estimated Complexity

**Medium (M)** — 4 well-scoped issues, no architectural changes, no new dependencies. Main effort is in the model factories (9 functions with realistic defaults) and CI workflow tuning. Parallel safety audit is already done (result: safe, no fixes needed).

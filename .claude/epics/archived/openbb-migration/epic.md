---
name: openbb-migration
status: completed
created: 2026-03-02T13:29:45Z
progress: 100%
prd: .claude/prds/openbb-migration.md
github: https://github.com/jobu711/options_arena/issues/192
---

# Epic: openbb-migration

## Overview

Migrate option chain fetching from yfinance-only to a `ChainProvider` protocol abstraction with CBOE via OpenBB as the primary provider and yfinance as automatic fallback. Introduces native Greeks from CBOE (bypassing local BAW/BSM when available), bid/ask IV fields, and three-tier Greeks resolution. Builds on the existing OpenBB infrastructure (Epic A: `OpenBBService`, `OpenBBConfig`, guarded imports).

## Architecture Decisions

1. **Protocol-based provider abstraction**: `ChainProvider` runtime `Protocol` with `fetch_chain()` and `fetch_expirations()` — keeps `OptionsDataService` as the orchestrator, providers are pluggable.
2. **Inline in `options_data.py`**: `ChainProvider` protocol and `YFinanceChainProvider` stay in `options_data.py` (refactor, not new file). `CBOEChainProvider` goes in a new `services/cboe_provider.py` since it has separate dependencies (OpenBB SDK).
3. **Sequential fallback, not aggregation**: CBOE → yfinance → error. V1 is simple priority ordering, not multi-source merging.
4. **Three-tier Greeks**: CBOE native → local BAW/BSM → None. `compute_greeks()` in `scoring/contracts.py` checks `contract.greeks is not None` to skip dispatch.
5. **`GreeksSource` enum** (already exists): `COMPUTED` for local BAW/BSM, `MARKET` for CBOE native. Wired to new `OptionContract.greeks_source` field.
6. **Backward-compatible defaults**: All new fields (`bid_iv`, `ask_iv`, `greeks_source`) default to `None`. `cboe_chains_enabled` defaults to `False`. Existing behavior unchanged until explicitly enabled.
7. **Reuse existing patterns**: `_get_obb()` guarded import from `openbb_service.py`, `_yf_call()` async wrapping pattern, `safe_decimal()`/`safe_float()` converters, `model_copy(update={...})` for frozen models.

## Technical Approach

### Service Layer (Primary Change)
- Define `ChainProvider` protocol with 2 methods
- Extract existing yfinance logic from `OptionsDataService` methods into `YFinanceChainProvider`
- Implement `CBOEChainProvider` using `obb.equity.options.chains(provider="cboe")` via `asyncio.to_thread()`
- `OptionsDataService` iterates providers with try/except fallback on `DataSourceUnavailableError`
- Constructor gains `openbb_config: OpenBBConfig | None = None` (backward compatible)

### Model Layer (Minimal Extensions)
- `OptionContract`: add `bid_iv: float | None`, `ask_iv: float | None`, `greeks_source: GreeksSource | None`
- `OpenBBConfig`: add `cboe_chains_enabled: bool = False`, `chains_cache_ttl: int = 60`, `chain_validation_mode: bool = False`
- All validators follow existing patterns (`math.isfinite() + >= 0`)

### Scoring Layer (Three-Tier Greeks)
- `compute_greeks()` in `contracts.py`: if `contract.greeks is not None`, skip `pricing/dispatch.py`, preserve existing greeks, set `greeks_source = GreeksSource.MARKET`
- When locally computing, set `greeks_source = GreeksSource.COMPUTED` via `model_copy()`
- No change to `filter_contracts()`, `select_expiration()`, or `select_by_delta()`

### DI Wiring (Thin — 5 Call Sites)
- CLI `commands.py`: 3 call sites add `openbb_config=settings.openbb`
- API `app.py`: 1 call site adds `openbb_config=settings.openbb`
- Test fixture: 1 call site (optional param, tests pass without it)

## Implementation Strategy

### Dependency Chain
```
Task 1 (Models) → Task 2 (Protocol + YFinance) → Task 3 (CBOE Provider) → Task 4 (Orchestration)
Task 1 (Models) → Task 5 (Three-Tier Greeks)
Task 4 + Task 5 → Task 6 (Wiring + Health + Validation)
Task 6 → Task 7 (Integration Tests + Cutover)
```

### Wave Execution
- **Wave 1**: Task 1 (models) — foundation, ~10 tests
- **Wave 2**: Tasks 2 + 5 in parallel (protocol extraction + three-tier Greeks) — ~20 tests
- **Wave 3**: Task 3 (CBOE provider, requires Context7 verification) — ~15 tests
- **Wave 4**: Task 4 (orchestration + fallback) — ~10 tests
- **Wave 5**: Tasks 6 + 7 (wiring, health, validation, integration) — ~30 tests

### Risk Mitigation
- Context7 verify CBOE field names before Task 3 implementation
- All new fields have `None` defaults — zero regression risk when `cboe_chains_enabled=False`
- Run full test suite after each wave

## Task Breakdown Preview

- [x] Task 1: Model & config extensions — `OptionContract` new fields, `OpenBBConfig` CBOE fields, validators
- [x] Task 2: ChainProvider protocol + YFinanceChainProvider extraction from `OptionsDataService`
- [x] Task 3: CBOEChainProvider implementation — CBOE via OpenBB SDK, field mapping, Greeks mapping
- [x] Task 4: Provider orchestration + fallback in `OptionsDataService`
- [x] Task 5: Three-tier Greeks resolution in `scoring/contracts.py`
- [x] Task 6: DI wiring (CLI + API + pipeline), health check extension, parallel validation mode
- [x] Task 7: Integration tests + cutover (enable CBOE as default)

## Dependencies

- **Epic A (openbb-integration)**: Must be merged to master first — provides `OpenBBService`, `OpenBBConfig`, guarded imports, health check infrastructure, `GreeksSource` enum
- **OpenBB Platform SDK**: Optional runtime dependency (guarded import, zero impact when missing)
- **Existing modules**: `OptionsDataService`, `OptionContract`, `scoring/contracts.py`, `pricing/dispatch.py` — extended, not replaced

## Success Criteria (Technical)

- `ChainProvider` protocol defined and implemented by 2 providers
- CBOE chains return native Greeks for S&P 500 tickers (when OpenBB installed)
- Three-tier Greeks resolution: CBOE → local BAW/BSM → None
- Automatic fallback CBOE → yfinance on CBOE failure
- Scan pipeline and debate path use provider-abstracted chains
- `recommend_contracts()` skips local Greeks when CBOE provides them
- Bid/ask IV populated from CBOE, `None` from yfinance
- Health check reports CBOE chain provider status
- All existing 2,773+ tests pass with `cboe_chains_enabled=False`
- `ruff check`, `mypy --strict`, `pytest` all pass
- No paid API keys required

## Estimated Effort

- **7 tasks**, ~85 new tests total
- **Modified files**: 6-7 (options_data.py, options.py, config.py, contracts.py, commands.py, app.py, health.py)
- **New files**: 1 (cboe_provider.py) + 4-5 test files
- **Critical path**: Task 3 (CBOE provider) depends on Context7 field verification
- **All patterns exist**: DI, async wrapping, guarded imports, frozen models — follows established templates

## Tasks Created

- [x] #193 - Model & Config Extensions (parallel: false — foundation)
- [x] #194 - ChainProvider Protocol + YFinanceChainProvider (parallel: true)
- [x] #196 - CBOEChainProvider Implementation (parallel: false)
- [x] #197 - Provider Orchestration + Fallback (parallel: false)
- [x] #195 - Three-Tier Greeks Resolution (parallel: true)
- [x] #198 - DI Wiring + Health Check + Validation Mode (parallel: false)
- [x] #199 - Integration Tests + Cutover (parallel: false)

Total tasks: 7
Parallel tasks: 2 (#194 + #195 can run in Wave 2)
Sequential tasks: 5
Estimated total effort: 26-37 hours

## Test Coverage Plan

Total test files planned: 6
Total test cases planned: ~85
- `tests/unit/models/test_option_contract_ext.py` (~13 tests)
- `tests/unit/services/test_chain_providers.py` (~10 tests)
- `tests/unit/services/test_cboe_provider.py` (~15 tests)
- `tests/unit/services/test_provider_orchestration.py` (~10 tests)
- `tests/unit/scoring/test_contracts_cboe.py` (~10 tests)
- `tests/unit/services/test_cboe_health.py` + `test_chain_validation.py` (~12 tests)
- `tests/integration/test_chain_migration.py` (~15 tests)

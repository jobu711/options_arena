---
name: openbb-migration
description: Migrate options chain fetching from yfinance to CBOE via OpenBB with native Greeks and provider abstraction
status: planned
created: 2026-03-02T07:24:21Z
---

# PRD: openbb-migration

## Executive Summary

Migrate the options chain data source from yfinance (current sole provider) to CBOE via OpenBB Platform SDK as the primary provider, with yfinance retained as automatic fallback. This introduces a `ChainProvider` protocol abstraction, native Greeks from CBOE (eliminating the need for local BAW/BSM computation when available), and enhanced chain data including separate bid/ask IV. The migration applies to both the scan pipeline (Phase 3) and the debate path — every code path that fetches option chains uses the new provider abstraction.

**Prerequisite**: This PRD builds on Epic A (openbb-integration, PR #184) which established `OpenBBService`, guarded imports, `OpenBBConfig`, and the never-raises contract. The existing `fetch_option_chains()` stub in the PRD becomes the implementation target here.

## Problem Statement

1. **No provider abstraction**: `OptionsDataService` is hardcoded to yfinance. Adding or swapping chain sources requires rewriting the service. No `Protocol` or interface exists for alternative providers.
2. **No native Greeks**: yfinance returns zero Greeks — all are computed locally via BAW/BSM in `pricing/dispatch.py`. This is correct but misses the market's actual implied Greeks and adds computation latency.
3. **Single-source risk**: Every options chain in the system flows through yfinance. If yfinance breaks (schema changes, rate limits, outages), the entire scan pipeline and debate system lose chain data with no fallback.
4. **Missing bid/ask IV**: yfinance provides a single `impliedVolatility` per contract. CBOE provides separate bid IV and ask IV, enabling better IV skew analysis and spread detection.
5. **Moneyness proxy for delta filtering**: Contract selection uses computed delta from local BAW/BSM. With native delta from CBOE, selection can use the market's own delta — more accurate and faster.

**Why now**: The OpenBB infrastructure (service, config, guarded imports, health checks) is fully built and tested (PR #184, +319 tests). The `cboe_chains_enabled` config flag already exists (defaulting to `False`). This epic flips that switch after building the provider layer.

## User Stories

### US-1: Provider-Abstracted Chain Fetching

**As** a developer maintaining Options Arena,
**I want** option chain fetching abstracted behind a `ChainProvider` protocol,
**So that** I can swap or add data sources without modifying business logic.

**Acceptance Criteria:**
- `ChainProvider` protocol defined with `fetch_chains(ticker, expiration)` and `fetch_expirations(ticker)` methods
- `CBOEChainProvider` implements the protocol using `obb.equity.options.chains(provider="cboe")`
- `YFinanceChainProvider` wraps existing `OptionsDataService` logic behind the protocol
- `OptionsDataService` accepts a list of providers and tries them in priority order
- Existing `fetch_chain()` and `fetch_expirations()` signatures remain unchanged for consumers

### US-2: Native Greeks from CBOE

**As** an options trader,
**I want** the system to use CBOE's native Greeks (delta, gamma, theta, vega) when available,
**So that** contract selection and risk assessment use market-implied values rather than model estimates.

**Acceptance Criteria:**
- When CBOE returns Greeks, they populate `OptionContract.greeks` directly
- When CBOE Greeks are missing or incomplete, local BAW/BSM computation fills gaps (second fallback)
- When both CBOE and local computation fail, `greeks` remains `None` (third tier)
- Greek values are sanity-checked (reasonable bounds: |delta| <= 1.0, gamma >= 0, vega >= 0)
- `OptionContract` gains a `greeks_source` field indicating origin: `"cboe"`, `"local"`, or `None`

### US-3: Enhanced Chain Data (Bid/Ask IV)

**As** an options analyst,
**I want** separate bid IV and ask IV from CBOE,
**So that** IV skew and spread analysis use finer-grained data.

**Acceptance Criteria:**
- `OptionContract` gains `bid_iv: float | None` and `ask_iv: float | None` fields
- Existing `market_iv` field continues to hold mid-IV (backward compatible)
- When CBOE provides bid/ask IV: `market_iv = (bid_iv + ask_iv) / 2`
- When only a single IV is available (yfinance fallback): `bid_iv` and `ask_iv` are `None`
- Contract selection can optionally use bid/ask IV for tighter filtering

### US-4: Automatic Fallback with Validation

**As** an operations-minded user,
**I want** CBOE chain fetching to automatically fall back to yfinance on failure,
**So that** scans and debates continue working even when CBOE is unavailable.

**Acceptance Criteria:**
- Fallback chain: CBOE → yfinance → None (pipeline handles None via existing patterns)
- Fallback triggers: CBOE timeout, HTTP error, empty response, import failure
- Each fallback event is logged at WARNING level with the reason
- Health check reports which provider is currently active
- Parallel validation mode compares CBOE vs yfinance output before cutover

### US-5: Scan + Debate Pipeline Integration

**As** a user running `options-arena scan` or `options-arena debate`,
**I want** CBOE chains used in both paths,
**So that** all analysis benefits from the improved data source.

**Acceptance Criteria:**
- Scan pipeline Phase 3 (`_phase_options()`) uses the provider-abstracted chain fetching
- Debate path (`_debate_single()`) uses the same provider abstraction
- `recommend_contracts()` in `scoring/contracts.py` leverages native Greeks when available (skips local computation)
- No change to scan Phase 1-2 or Phase 4 (OHLCV, indicators, persistence are unaffected)

## Requirements

### Functional Requirements

#### FR-1: ChainProvider Protocol

Define in `services/options_data.py`:

```python
class ChainProvider(Protocol):
    async def fetch_expirations(self, ticker: str) -> list[date]: ...
    async def fetch_chain(self, ticker: str, expiration: date) -> list[OptionContract]: ...
```

Both methods may raise `DataSourceUnavailableError` on failure. The orchestrating layer handles fallback.

#### FR-2: CBOEChainProvider

New class (in `services/options_data.py` or a new `services/cboe_provider.py`):

- Uses existing `OpenBBService` guarded import pattern (`_get_obb()`)
- Wraps `obb.equity.options.chains(symbol=ticker, provider="cboe")` via `asyncio.to_thread()` + `wait_for(timeout)`
- Maps CBOE response fields to `OptionContract`:
  | CBOE Field | OptionContract Field | Notes |
  |-----------|---------------------|-------|
  | `strike` | `strike` | `Decimal(str(value))` |
  | `bid` / `ask` | `bid` / `ask` | `Decimal(str(value))` |
  | `last_price` | `last` | `Decimal(str(value))` |
  | `volume` | `volume` | `int` |
  | `open_interest` | `open_interest` | `int` |
  | `implied_volatility` | `market_iv` | `float` (mid-IV) |
  | `delta` | `greeks.delta` | `float` or None |
  | `gamma` | `greeks.gamma` | `float` or None |
  | `theta` | `greeks.theta` | `float` or None |
  | `vega` | `greeks.vega` | `float` or None |
  | `bid_iv` (if present) | `bid_iv` | `float` or None |
  | `ask_iv` (if present) | `ask_iv` | `float` or None |
- Applies same liquidity filter as existing yfinance path
- Caching: same TTL pattern (`chain_cache_ttl` from `OpenBBConfig`, default 60s)
- Never-raises at the provider level: raises `DataSourceUnavailableError` on failure (orchestrator handles)

**IMPORTANT**: Exact CBOE field names must be verified via Context7 before implementation. The mapping above is estimated from the PRD and needs SDK verification.

#### FR-3: YFinanceChainProvider

Refactor existing `OptionsDataService._fetch_chain_yfinance()` logic into a class implementing `ChainProvider`:

- Extracts the existing yfinance-specific code (field mapping, `_yf_call()` wrapping)
- No behavioral change — same output as current `OptionsDataService.fetch_chain()`
- `greeks` always `None` (yfinance provides none)
- `bid_iv` and `ask_iv` always `None` (yfinance provides single IV only)
- `greeks_source` = `None`

#### FR-4: Provider Orchestration

`OptionsDataService` gains provider-aware chain fetching:

```python
class OptionsDataService:
    def __init__(
        self,
        config: ServiceConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
        openbb_config: OpenBBConfig | None = None,  # NEW
    ) -> None:
        self._providers: list[ChainProvider] = []
        if openbb_config and openbb_config.cboe_chains_enabled:
            self._providers.append(CBOEChainProvider(openbb_config, cache, limiter))
        self._providers.append(YFinanceChainProvider(config, cache, limiter))
```

`fetch_chain()` tries providers in order:
1. First provider (CBOE if enabled)
2. On `DataSourceUnavailableError` → log WARNING → try next provider
3. All providers exhausted → raise `DataSourceUnavailableError`

#### FR-5: Three-Tier Greeks Resolution

In `scoring/contracts.py` `recommend_contracts()`:

```
Tier 1: Contract already has greeks (from CBOE native) → use as-is
Tier 2: Contract has no greeks → compute via pricing/dispatch.py (BAW/BSM)
Tier 3: Local computation fails → greeks = None, contract excluded from delta selection
```

This replaces the current unconditional call to `pricing/dispatch.py`. When CBOE provides Greeks, the pricing module is never invoked — saving computation time.

#### FR-6: OptionContract Model Extensions

Extend `OptionContract` in `models/options.py`:

```python
# New fields (all backward-compatible with None defaults)
bid_iv: float | None = None          # Separate bid IV from CBOE
ask_iv: float | None = None          # Separate ask IV from CBOE
greeks_source: str | None = None     # "cboe", "local", or None
```

Validators:
- `bid_iv` and `ask_iv`: `math.isfinite()` + `>= 0.0` (IV is non-negative)
- `greeks_source`: constrain to `{"cboe", "local", None}` or use a StrEnum

#### FR-7: Parallel Validation Mode

Before enabling CBOE as default, a validation mode runs both providers and compares:

- Configurable via `OpenBBConfig.chain_validation_mode: bool = False`
- When enabled: fetch from CBOE AND yfinance, compare strike coverage, IV accuracy, Greeks reasonableness
- Log discrepancies at INFO level (structured: ticker, field, cboe_value, yf_value)
- Output validation report for operator review
- After validation period: set `cboe_chains_enabled=True` and `chain_validation_mode=False`

#### FR-8: Health Check Extension

Extend `services/health.py`:

- `check_cboe_chains()`: Test CBOE chain endpoint with known ticker (e.g., "AAPL")
- Report in health output: `cboe_chains: available/unavailable`
- Existing `check_openbb()` from Epic A extended, not duplicated

### Non-Functional Requirements

- **Zero paid dependencies**: CBOE via OpenBB is free, no API key required.
- **Backward compatibility**: All new `OptionContract` fields have `None` defaults. Existing tests produce identical results when `cboe_chains_enabled=False` (the default).
- **Performance**: CBOE chains should be comparable or faster than yfinance. When CBOE provides native Greeks, skip local BAW/BSM computation — net speed improvement for contract selection.
- **Graceful degradation**: If OpenBB SDK is not installed, `CBOEChainProvider` is not registered. yfinance-only operation is identical to pre-migration. If CBOE fails at runtime, automatic fallback to yfinance.
- **Test isolation**: All CBOE calls mockable. No test requires network access or OpenBB installation. CI runs without OpenBB SDK.
- **Windows compatibility**: `asyncio.to_thread()` wrapping only — no POSIX-specific patterns.

## Success Criteria

| Metric | Target |
|--------|--------|
| `ChainProvider` protocol defined and implemented by 2 providers | Pass |
| CBOE chains return native Greeks (delta, gamma, theta, vega) for S&P 500 tickers | Pass |
| Three-tier Greeks resolution works (CBOE → local BAW/BSM → None) | Pass |
| Automatic fallback CBOE → yfinance on CBOE failure | Pass |
| Scan pipeline Phase 3 uses provider-abstracted chains | Pass |
| Debate path uses provider-abstracted chains | Pass |
| `recommend_contracts()` skips local Greeks when CBOE provides them | Pass |
| Bid/ask IV populated when CBOE provides them | Pass |
| Parallel validation mode produces comparison report | Pass |
| All existing 2,773+ tests pass with `cboe_chains_enabled=False` | Pass |
| Health check reports CBOE chain provider status | Pass |
| `ruff check`, `mypy --strict`, `pytest` all pass | Pass |
| No paid API keys required | Pass |

## Phasing

### Phase 1: Provider Abstraction (~25 tests)

Foundation — define the protocol and refactor existing yfinance code behind it.

**Tasks:**
1. Define `ChainProvider` protocol in `services/options_data.py`
2. Extract `YFinanceChainProvider` from existing `OptionsDataService` internals
3. Implement `CBOEChainProvider` using `obb.equity.options.chains(provider="cboe")`
4. Add provider list + fallback logic to `OptionsDataService.__init__()`
5. Wire `OpenBBConfig` into `OptionsDataService` constructor (DI from CLI/API)
6. Update `OptionsDataService.fetch_chain()` to iterate providers with fallback
7. Verify existing behavior unchanged when `cboe_chains_enabled=False`

**Tests:**
- `ChainProvider` protocol conformance for both implementations
- CBOE field mapping (mocked SDK responses → `OptionContract`)
- Fallback: CBOE fails → yfinance succeeds
- Fallback: both fail → `DataSourceUnavailableError`
- Config toggle: `cboe_chains_enabled=False` → yfinance only

### Phase 2: Native Greeks Integration (~25 tests)

Map CBOE Greeks to `OptionContract` and implement three-tier resolution.

**Tasks:**
1. Extend `OptionContract` with `greeks_source: str | None = None`
2. Map CBOE delta/gamma/theta/vega to `OptionGreeks` in `CBOEChainProvider`
3. Add Greek sanity validators (|delta| <= 1.0, gamma >= 0, vega >= 0, theta <= 0 for long)
4. Update `recommend_contracts()` to skip `pricing/dispatch.py` when `greeks` is already populated
5. Implement three-tier resolution: CBOE native → local BAW/BSM → None
6. Verify `scoring/contracts.py` `select_by_delta()` works with both Greek sources

**Tests:**
- CBOE Greeks mapped correctly to `OptionGreeks` model
- Three-tier fallback: CBOE has Greeks → skip local computation
- Three-tier fallback: CBOE missing Greeks → compute locally
- Three-tier fallback: both fail → `greeks=None`, contract excluded from delta selection
- `greeks_source` correctly set to `"cboe"` or `"local"`
- Greek sanity checks reject unreasonable values

### Phase 3: Enhanced Chain Data (~20 tests)

Bid/ask IV, enhanced contract selection, scan + debate pipeline wiring.

**Tasks:**
1. Add `bid_iv` and `ask_iv` fields to `OptionContract` model
2. Map CBOE bid/ask IV in `CBOEChainProvider`
3. Compute `market_iv = (bid_iv + ask_iv) / 2` when both available
4. Wire provider-abstracted chains into scan pipeline `_phase_options()`
5. Wire provider-abstracted chains into debate path (`_debate_single()` / `run_debate()`)
6. Update `scoring/contracts.py` to leverage native delta for selection (skip moneyness proxy)
7. Ensure CLI and API service creation passes `OpenBBConfig` to `OptionsDataService`

**Tests:**
- Bid/ask IV populated from CBOE, `None` from yfinance
- `market_iv` computed as mid when bid/ask available
- Scan pipeline uses provider-abstracted chains end-to-end (mocked)
- Debate uses provider-abstracted chains end-to-end (mocked)
- Contract selection uses native delta when available

### Phase 4: Validation & Cutover (~15 tests)

Parallel validation, health checks, enable CBOE as default.

**Tasks:**
1. Implement parallel validation mode: fetch both providers, compare output
2. Log discrepancy report (strike coverage, IV delta, Greeks comparison)
3. Extend health check with `check_cboe_chains()` probe
4. Run validation across S&P 500 sample — review report
5. Set `cboe_chains_enabled=True` as default in `OpenBBConfig`
6. Keep yfinance fallback permanently (CBOE may have outages)
7. Performance benchmark: CBOE vs yfinance chain fetch times

**Tests:**
- Parallel validation produces comparison report
- Health check reports CBOE status
- Default config now has `cboe_chains_enabled=True`
- yfinance fallback still active when CBOE fails
- No regression in existing scan/debate tests

**Estimated total: ~85 new tests**

## Key Files

### New Files
| File | Purpose |
|------|---------|
| `src/options_arena/services/cboe_provider.py` | `CBOEChainProvider` implementation (or inline in `options_data.py`) |
| `tests/unit/services/test_chain_providers.py` | Provider protocol, CBOE mapping, fallback logic |
| `tests/unit/services/test_cboe_greeks.py` | Greeks mapping, three-tier resolution, sanity checks |
| `tests/integration/test_chain_migration.py` | End-to-end provider-abstracted chain fetching |

### Modified Files
| File | Change |
|------|--------|
| `src/options_arena/services/options_data.py` | `ChainProvider` protocol, `YFinanceChainProvider` extraction, provider list + fallback in `OptionsDataService` |
| `src/options_arena/models/options.py` | Add `bid_iv`, `ask_iv`, `greeks_source` fields to `OptionContract` |
| `src/options_arena/models/enums.py` | Add `GreeksSource(StrEnum)` if using enum for greeks_source |
| `src/options_arena/scoring/contracts.py` | Skip local Greeks when already populated, use native delta for selection |
| `src/options_arena/scan/pipeline.py` | Pass `OpenBBConfig` to `OptionsDataService`, use provider-abstracted chains |
| `src/options_arena/cli/commands.py` | Pass `openbb_config` when constructing `OptionsDataService` |
| `src/options_arena/api/app.py` | Pass `openbb_config` when constructing `OptionsDataService` in lifespan |
| `src/options_arena/services/health.py` | Add `check_cboe_chains()` probe |
| `src/options_arena/models/config.py` | Add `chain_validation_mode: bool = False` to `OpenBBConfig` |

### Reference Files (Read-Only)
| File | Why |
|------|-----|
| `src/options_arena/services/openbb_service.py` | Guarded import pattern, `_get_obb()`, async wrapping |
| `src/options_arena/pricing/dispatch.py` | Greeks computation entry point (called as Tier 2 fallback) |
| `src/options_arena/models/analysis.py` | `MarketContext` — consumes `OptionContract` with Greeks |

## Constraints & Assumptions

- **Builds on Epic A**: `OpenBBService`, `OpenBBConfig`, guarded imports, and never-raises patterns already exist. This epic does not re-implement them.
- **Free CBOE data**: CBOE via OpenBB (`provider="cboe"`) is free with no API key. If this changes, the feature degrades to yfinance-only (not broken).
- **OpenBB SDK optional**: System functions without OpenBB installed. `CBOEChainProvider` is not registered when SDK is missing. Zero behavioral change for users without OpenBB.
- **Schema verification required**: CBOE response field names and types must be verified via Context7 before implementing `CBOEChainProvider`. The field mapping in FR-2 is estimated and may need adjustment.
- **yfinance fallback is permanent**: Even after CBOE becomes the default, yfinance remains as fallback. Never remove it.
- **One provider change at a time**: This epic changes the chain source only. OHLCV, quotes, ticker info, and universe data remain on yfinance.

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| CBOE chain format differs significantly from yfinance | Field mapping complexity, potential data loss | Context7 verification before coding; extensive unit tests on mapping |
| CBOE native Greeks differ from local BAW/BSM values | Scoring inconsistency during transition | Parallel validation mode; log discrepancies; configurable source preference |
| CBOE rate limiting under scan load (50+ tickers) | Chain fetch failures, slow scans | Rate limiter on CBOE provider; cache-first strategy; yfinance fallback |
| OpenBB SDK CBOE provider changes API | `CBOEChainProvider` breaks | Pin OpenBB version; guarded import; yfinance fallback covers outage |
| `OptionContract` model changes break downstream | Scoring, debate, persistence regressions | All new fields have `None` defaults; existing tests pass unchanged |
| Performance regression from provider abstraction layer | Slower chain fetching | Benchmark in Phase 4; abstraction is thin (one protocol dispatch) |

## Out of Scope

- **OHLCV migration**: yfinance remains the OHLCV source. Only option chains move to CBOE.
- **Multiple simultaneous chain providers**: V1 is sequential fallback (CBOE → yfinance), not aggregation.
- **Provider abstraction for quotes/info**: Only option chains get the `ChainProvider` protocol.
- **Streaming chains**: Point-in-time snapshot fetching only. No WebSocket or real-time chain updates.
- **Database schema changes**: Chain data continues through existing persistence path. No new migrations for provider metadata.
- **UI changes**: No frontend work in this epic. Provider source is a backend concern.
- **Scoring engine integration of bid/ask IV**: V1 stores bid/ask IV on the contract but scoring continues to use mid-IV (`market_iv`).

## Dependencies

- **Epic A (openbb-integration)**: Must be merged to master first. Provides `OpenBBService`, `OpenBBConfig`, guarded imports, health check infrastructure.
- **openbb-wiring (optional)**: Independent — wiring CLI/API lifecycle for enrichment is separate from chain migration. Can proceed in parallel.
- **OpenBB Platform SDK**: Optional runtime dependency (already established in Epic A).
- **Existing modules**: `OptionsDataService`, `OptionContract`, `scoring/contracts.py`, `pricing/dispatch.py` — extended, not replaced.

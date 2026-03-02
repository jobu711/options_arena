---
name: openbb-integration
description: Integrate OpenBB Platform SDK for fundamentals, unusual flow, news sentiment, and CBOE options chain migration
status: backlog
created: 2026-03-01T18:32:26Z
---

# PRD: openbb-integration

## Executive Summary

Integrate OpenBB Platform SDK into Options Arena as a supplementary data layer alongside the existing yfinance/FRED/CBOE stack. This unlocks three new analytical capabilities — fundamentals, unusual options flow, and news sentiment — that enrich the AI debate agents with data they currently lack. A second epic migrates options chain fetching from yfinance to CBOE via OpenBB, providing professional-grade chains with native Greeks while retaining yfinance as fallback.

All phases use strictly free data providers. No paid API keys are required at any stage.

## Problem Statement

Options Arena's current data stack has significant blind spots:

1. **No fundamental data**: Debate agents argue about options contracts without knowing the company's revenue, margins, debt, or valuation. A bear case citing "expensive valuation" has no P/E ratio to anchor it.
2. **No unusual activity signals**: Large block trades and volume/OI spikes — the strongest short-term directional signals in options markets — are invisible to the system.
3. **No sentiment signals**: News catalysts and market sentiment that drive options pricing are absent from the debate context.
4. **Fragile options chains**: yfinance provides no Greeks, no SLA, and schema changes without warning. All Greeks are computed locally via BAW/BSM, which is correct but misses the market's actual implied Greeks.
5. **Single-source risk**: Every data path runs through yfinance with no redundancy for the most critical data (option chains).

**Why now**: The debate system, scoring engine, and web UI are mature (v2.1.0, 2,454 tests). The bottleneck has shifted from "can we analyze options" to "how good is the data feeding the analysis." OpenBB Platform provides a standardized Python SDK wrapping 100+ providers — several completely free — that fills every gap above without introducing vendor lock-in.

## User Stories

### US-1: Fundamental-Enriched Debate

**As** an options trader reviewing AI debate output,
**I want** bull/bear/risk agents to cite actual financial metrics (P/E, revenue growth, debt ratios),
**So that** their arguments are grounded in company fundamentals rather than pure technicals.

**Acceptance Criteria:**
- MarketContext includes key fundamental metrics (P/E, forward P/E, PEG, debt-to-equity, revenue growth, profit margins)
- Bull and bear agents reference fundamentals in their arguments when relevant
- Fundamentals appear in a dedicated section of the debate context
- Missing fundamentals (e.g., for ETFs) degrade gracefully — agents proceed without them

### US-2: Unusual Options Flow Awareness

**As** an options trader,
**I want** the system to detect and surface unusual options activity (volume spikes, large blocks),
**So that** I can see institutional flow signals alongside the AI debate verdict.

**Acceptance Criteria:**
- Unusual flow data is fetched for debate tickers via Stockgrid (free, no API key)
- Flow signals are included in MarketContext for agent consumption
- Risk agent considers unusual flow when assessing position risk
- Scan results indicate when unusual activity is detected for a ticker

### US-3: News Sentiment Context

**As** an options trader about to enter a position,
**I want** to see recent news sentiment for the underlying ticker,
**So that** I can factor catalysts and sentiment into my decision.

**Acceptance Criteria:**
- Recent news headlines are fetched via Yahoo News (through OpenBB)
- Local NLP (VADER) scores sentiment without requiring external API calls
- Aggregate sentiment (bullish/bearish/neutral) is included in MarketContext
- Debate agents can reference news catalysts in their arguments
- No paid API key required

### US-4: CBOE Options Chains with Native Greeks

**As** a developer maintaining Options Arena,
**I want** to source options chains from CBOE (via OpenBB) with native Greeks,
**So that** we have professional-grade chain data and reduce dependence on yfinance.

**Acceptance Criteria:**
- CBOE is the primary options chain provider; yfinance is automatic fallback
- When CBOE provides Greeks (delta, gamma, theta, vega), they are used directly
- When CBOE Greeks are missing, local BAW/BSM computation fills in (second fallback)
- Separate bid IV and ask IV are available when the provider supplies them
- Chain quality (strike coverage, expiration range) is equal or better than yfinance
- No paid API key required (CBOE data via OpenBB is free)

### US-5: Data Source Health Visibility

**As** an operations-minded user,
**I want** `options-arena health` to show the status of OpenBB data sources,
**So that** I can diagnose data quality issues.

**Acceptance Criteria:**
- Health command shows OpenBB connection status
- Individual provider availability (Yahoo fundamentals, Stockgrid, CBOE chains) is reported
- Degraded providers are flagged with which fallback is active

## Requirements

### Functional Requirements

#### FR-1: OpenBB Service Layer (Foundation)

A new `OpenBBService` class in `services/openbb_service.py` wrapping the OpenBB Platform SDK:

- **Class-based DI**: Receives `OpenBBConfig` (from AppSettings), cache instance, and rate limiter via `__init__`. Explicit `close()` method.
- **Async wrapping**: OpenBB SDK is synchronous. All calls wrapped via `asyncio.to_thread()` + `asyncio.wait_for(timeout=N)` — same pattern as existing yfinance wrapper.
- **Never-raises contract**: Every public method catches exceptions and returns `None` or a fallback value. Failures are logged, never propagated.
- **Cache-first**: Same two-tier caching pattern (in-memory LRU + SQLite WAL) as existing services.
- **Rate limiting**: Per-provider token bucket. Stockgrid and Yahoo via OpenBB each get independent rate limiters.

**Public methods:**
```
fetch_fundamentals(ticker: str) -> FundamentalSnapshot | None
fetch_unusual_flow(ticker: str) -> UnusualFlowSnapshot | None
fetch_news_sentiment(ticker: str, limit: int = 10) -> NewsSentimentSnapshot | None
fetch_option_chains(ticker: str) -> OptionChainResult | None   # Epic B
check_health() -> OpenBBHealthStatus
```

#### FR-2: Pydantic Models (NEW: `models/openbb.py`)

New typed models for OpenBB data — all follow project conventions (frozen, validators, no raw dicts):

```
FundamentalSnapshot(BaseModel, frozen=True):
    ticker: str
    pe_ratio: float | None
    forward_pe: float | None
    peg_ratio: float | None
    price_to_book: float | None
    debt_to_equity: float | None
    revenue_growth: float | None          # YoY %
    profit_margin: float | None
    market_cap: int | None
    fetched_at: datetime                  # UTC validator

UnusualFlowSnapshot(BaseModel, frozen=True):
    ticker: str
    net_call_premium: float | None        # Net $ flow into calls
    net_put_premium: float | None         # Net $ flow into puts
    call_volume: int | None
    put_volume: int | None
    put_call_ratio: float | None
    fetched_at: datetime                  # UTC validator

NewsSentimentSnapshot(BaseModel, frozen=True):
    ticker: str
    headlines: list[NewsHeadline]          # Up to N recent headlines
    aggregate_sentiment: float             # -1.0 (bearish) to 1.0 (bullish)
    sentiment_label: SentimentLabel        # StrEnum: BULLISH/BEARISH/NEUTRAL
    article_count: int
    fetched_at: datetime                  # UTC validator

NewsHeadline(BaseModel, frozen=True):
    title: str
    published_at: datetime | None
    sentiment_score: float                # -1.0 to 1.0 (VADER compound)
    source: str | None

SentimentLabel(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"

OpenBBHealthStatus(BaseModel, frozen=True):
    openbb_available: bool
    yahoo_fundamentals: bool
    stockgrid_flow: bool
    cboe_chains: bool                     # Epic B
    last_checked: datetime
```

#### FR-3: Configuration Extension

Extend `AppSettings` with a nested `OpenBBConfig(BaseModel)`:

```
OpenBBConfig(BaseModel):
    enabled: bool = True                  # Master kill switch
    fundamentals_enabled: bool = True
    unusual_flow_enabled: bool = True
    news_sentiment_enabled: bool = True
    cboe_chains_enabled: bool = False     # Epic B — off until migration
    fundamentals_cache_ttl: int = 3600    # 1 hour
    flow_cache_ttl: int = 300             # 5 minutes
    news_cache_ttl: int = 900             # 15 minutes
    chains_cache_ttl: int = 60            # 1 minute (Epic B)
    request_timeout: int = 15             # seconds
    max_retries: int = 2
```

Env var pattern: `ARENA_OPENBB__ENABLED=false` disables all OpenBB fetching.

#### FR-4: MarketContext Enrichment

Extend `MarketContext` (in `models/analysis.py`) with optional fields:

```
# Fundamentals (Epic A, Phase 1)
pe_ratio: float | None = None
forward_pe: float | None = None
peg_ratio: float | None = None
price_to_book: float | None = None
debt_to_equity: float | None = None
revenue_growth: float | None = None
profit_margin: float | None = None

# Unusual flow (Epic A, Phase 2)
net_call_premium: float | None = None
net_put_premium: float | None = None
options_put_call_ratio: float | None = None

# News sentiment (Epic A, Phase 3)
news_sentiment: float | None = None           # -1.0 to 1.0
news_sentiment_label: str | None = None       # "bullish"/"bearish"/"neutral"
recent_headlines: list[str] | None = None     # Up to 5 headline strings
```

All fields are `None` by default — fully backward compatible. The existing `completeness_ratio()` method should account for these new fields.

#### FR-5: Agent Prompt Enrichment

Extend `_parsing.py` (or equivalent prompt-building module) to render new context sections when data is available:

```
## Fundamental Profile
- P/E: 28.5 | Forward P/E: 24.1 | PEG: 1.8
- Debt/Equity: 1.45 | Profit Margin: 25.3%
- Revenue Growth (YoY): 12.8%

## Unusual Options Flow
- Net Call Premium: $4.2M | Net Put Premium: -$1.1M
- Put/Call Ratio: 0.62 (bullish skew)

## News Sentiment
- Aggregate: Bullish (0.42)
- "AAPL beats Q4 earnings expectations" (0.78)
- "Apple announces $100B buyback program" (0.65)
- "Supply chain concerns linger for iPhone" (-0.32)
```

Sections are omitted entirely when the corresponding data is `None` — agents never see empty sections.

#### FR-6: CBOE Options Chain Provider (Epic B)

Replace yfinance as the primary options chain source:

- **Provider abstraction**: `ChainProvider` protocol with `fetch_chains(ticker) -> OptionChainResult | None`
- **CBOE provider** (primary): Uses `obb.equity.options.chains(ticker, provider="cboe")`
- **yfinance provider** (fallback): Existing `OptionsDataService.fetch_option_chain()` logic
- **Fallback chain**: CBOE → yfinance → None (pipeline handles None via existing patterns)
- **Native Greeks**: When CBOE returns delta/gamma/theta/vega, populate `OptionContract` Greeks fields directly
- **Local Greeks fallback**: When provider Greeks are missing, dispatch to `pricing/dispatch.py` (existing BAW/BSM) — second fallback layer
- **Separate bid/ask IV**: When available from CBOE, store both. Existing `implied_volatility` field remains as mid-IV for backward compatibility.
- **Contract selection**: Enhanced selection logic can use native Greeks for better filtering (e.g., filter by actual delta rather than moneyness proxy)

#### FR-7: Health Check Extension

Extend `services/health.py` to probe OpenBB provider availability:

- Test Yahoo fundamentals with a known ticker (e.g., "AAPL")
- Test Stockgrid endpoint availability
- Test CBOE chain endpoint (Epic B)
- Report per-provider status in `HealthReport`
- Existing health checks unchanged — OpenBB checks are additive

### Non-Functional Requirements

- **Zero paid dependencies**: All providers used must be free with no API key, or free-tier with no key required. This is a hard constraint across all phases.
- **Backward compatibility**: All new MarketContext fields are optional with `None` defaults. Existing debates, scans, and tests produce identical results when OpenBB is disabled.
- **Performance**: OpenBB fetches run in parallel with existing data fetches via `asyncio.gather`. Net scan time increase should be < 2 seconds for the debate path (fundamentals + flow + sentiment are fetched once per ticker, not per-contract).
- **Graceful degradation**: If OpenBB SDK import fails (not installed), the service layer returns `None` for all methods and logs a warning. The system operates identically to pre-integration.
- **Test isolation**: All OpenBB calls are mockable. No test requires network access or OpenBB installation. CI runs without OpenBB SDK installed.
- **Windows compatibility**: No POSIX-only patterns. `asyncio.to_thread()` wrapping works on all platforms.

## Provider Matrix

| Data Type | Provider | Free? | API Key? | OpenBB Method | Fallback |
|-----------|----------|-------|----------|---------------|----------|
| OHLCV | yfinance (existing) | Yes | No | N/A (keep existing) | Cache |
| Option Chains | CBOE via OpenBB (Epic B) | Yes | No | `obb.equity.options.chains(provider="cboe")` | yfinance (existing) |
| Greeks | CBOE native (Epic B) | Yes | No | Included in chains response | Local BAW/BSM |
| Fundamentals | Yahoo via OpenBB | Yes | No | `obb.equity.fundamental.overview(provider="yfinance")` | None (new capability) |
| Unusual Flow | Stockgrid via OpenBB | Yes | No | `obb.equity.darkpool.otc(provider="stockgrid")` | None (new capability) |
| News + Sentiment | Yahoo News via OpenBB + local VADER | Yes | No | `obb.news.world(provider="yfinance")` + `nltk.sentiment.vader` | None (new capability) |
| Risk-Free Rate | FRED (existing) | Yes | No | N/A (keep existing) | Config fallback |
| Ticker Universe | CBOE CSV (existing) | Yes | No | N/A (keep existing) | Cached list |

## Epic Structure

### Epic A: OpenBB New Capabilities (Supplement Pattern)

Adds fundamentals, unusual flow, and news sentiment as supplementary data sources alongside the existing stack. No existing data paths are modified.

**Phase 1 — Fundamentals (P0)**
- Create `models/openbb.py` with `FundamentalSnapshot`, `OpenBBHealthStatus`, and supporting models
- Create `services/openbb_service.py` with `OpenBBService` class
- Extend `AppSettings` with `OpenBBConfig` nested model
- Implement `fetch_fundamentals()` using `obb.equity.fundamental.overview(provider="yfinance")`
- Extend `MarketContext` with fundamental fields
- Wire fundamentals into `build_market_context()` in orchestrator
- Add fundamental context section to agent prompt rendering
- Unit tests: ~40 (models, service, config, prompt rendering)

**Phase 2 — Unusual Options Flow (P1)**
- Implement `fetch_unusual_flow()` using Stockgrid via OpenBB
- Add `UnusualFlowSnapshot` model
- Extend `MarketContext` with flow fields
- Wire flow data into `build_market_context()`
- Add flow context section to agent prompt rendering
- Consider adding flow signal to scan results display (CLI + Web UI)
- Unit tests: ~30 (models, service, prompt rendering, scan display)

**Phase 3 — News Sentiment (P2)**
- Implement `fetch_news_sentiment()` using Yahoo News via OpenBB
- Add local VADER sentiment scoring (nltk or standalone vaderSentiment package)
- Add `NewsSentimentSnapshot`, `NewsHeadline`, `SentimentLabel` models
- Extend `MarketContext` with sentiment fields
- Wire sentiment into `build_market_context()`
- Add sentiment context section to agent prompt rendering
- Unit tests: ~30 (models, service, VADER scoring, prompt rendering)

**Phase 4 — Health & Polish**
- Extend health check with OpenBB provider probes
- Add integration tests (mocked OpenBB responses end-to-end)
- CLI `health` command shows OpenBB status
- Web UI health page shows OpenBB provider status
- Documentation updates
- Unit tests: ~20 (health, integration)

**Estimated total: ~120 new tests**

### Epic B: CBOE Options Chain Migration

Migrates options chain fetching from yfinance to CBOE via OpenBB. This is a data source swap, not a new capability — the consumer interface remains unchanged.

**Phase 1 — Provider Abstraction**
- Define `ChainProvider` protocol in `services/options_data.py`
- Implement `CBOEChainProvider` using `obb.equity.options.chains(provider="cboe")`
- Implement `YFinanceChainProvider` wrapping existing logic
- Add fallback chain: CBOE → yfinance
- Config flag: `OpenBBConfig.cboe_chains_enabled` (off by default)
- Unit tests: ~25 (provider abstraction, CBOE parsing, fallback logic)

**Phase 2 — Native Greeks Integration**
- Map CBOE Greeks fields to existing `OptionContract` model
- Implement three-tier Greeks resolution: CBOE native → local BAW/BSM → None
- Ensure `pricing/dispatch.py` is only called when provider Greeks are missing
- Validate Greek values are within reasonable bounds (sanity checks)
- Unit tests: ~25 (Greeks mapping, fallback tiers, validation)

**Phase 3 — Enhanced Chain Data**
- Extract separate bid IV and ask IV when CBOE provides them
- Existing `implied_volatility` field = mid-IV for backward compatibility
- Enhanced contract selection using native delta (instead of moneyness proxy)
- Update scoring layer to leverage native Greeks when available
- Unit tests: ~20 (bid/ask IV, contract selection, scoring)

**Phase 4 — Validation & Cutover**
- Parallel validation: run both providers, compare output quality
- Logging: report discrepancies between CBOE and yfinance chain data
- Enable `cboe_chains_enabled=True` by default after validation
- Keep yfinance fallback permanently (CBOE may have outages)
- Performance benchmarking: CBOE vs yfinance chain fetch times
- Unit tests: ~15 (parallel comparison, cutover, benchmarks)

**Estimated total: ~85 new tests**

## Key Files Affected

### New Files
| File | Purpose |
|------|---------|
| `src/options_arena/models/openbb.py` | ~9 Pydantic models for OpenBB data |
| `src/options_arena/services/openbb_service.py` | OpenBB service with async wrapping, caching, never-raises |

### Modified Files
| File | Change |
|------|--------|
| `src/options_arena/models/config.py` | Add `OpenBBConfig(BaseModel)` nested in `AppSettings` |
| `src/options_arena/models/analysis.py` | Add ~15 optional fields to `MarketContext` |
| `src/options_arena/models/__init__.py` | Re-export new models |
| `src/options_arena/services/__init__.py` | Re-export `OpenBBService` |
| `src/options_arena/services/health.py` | Add OpenBB provider health checks |
| `src/options_arena/services/options_data.py` | Epic B: `ChainProvider` protocol, CBOE provider, fallback chain |
| `src/options_arena/agents/orchestrator.py` | Wire OpenBB data into `build_market_context()` |
| `src/options_arena/agents/_parsing.py` | Render fundamental/flow/sentiment context sections |
| `src/options_arena/scan/pipeline.py` | Parallel OpenBB fetches in Phase 2 or 3 |
| `src/options_arena/cli/app.py` | Health command OpenBB status display |
| `src/options_arena/api/routes/health.py` | Health endpoint OpenBB status |
| `web/src/types/` | TypeScript interfaces for new data |
| `web/src/pages/HealthPage.vue` | Display OpenBB provider status |

### Test Files (New)
| File | Coverage |
|------|----------|
| `tests/unit/models/test_openbb_models.py` | All new Pydantic models |
| `tests/unit/services/test_openbb_service.py` | OpenBB service methods, caching, error handling |
| `tests/unit/agents/test_openbb_prompts.py` | Prompt rendering with fundamental/flow/sentiment data |
| `tests/unit/services/test_chain_providers.py` | Epic B: CBOE provider, fallback chain |
| `tests/integration/test_openbb_pipeline.py` | End-to-end with mocked OpenBB |

## Success Criteria

| Metric | Target |
|--------|--------|
| Fundamentals available in debate context for S&P 500 tickers | Pass |
| Unusual flow data fetched from Stockgrid (free, no key) | Pass |
| News sentiment scored locally via VADER | Pass |
| CBOE chains with native Greeks as primary source (Epic B) | Pass |
| yfinance fallback works when CBOE is unavailable | Pass |
| All new fields optional — zero regression in existing 2,454 tests | Pass |
| `options-arena health` reports OpenBB provider status | Pass |
| No paid API keys required for any phase | Pass |
| OpenBB disabled via config runs identically to pre-integration | Pass |
| `ruff check`, `mypy --strict`, `pytest` all pass | Pass |

## Constraints & Assumptions

- **Strictly free providers**: No phase requires paid API keys. Yahoo (via OpenBB), Stockgrid, and CBOE are all free. If a provider changes pricing, the feature degrades to disabled (not broken).
- **OpenBB SDK is optional**: The system must function without OpenBB installed. Import is guarded; missing SDK logs a warning and all OpenBB methods return `None`.
- **Supplement, not replace**: Epic A adds data alongside existing sources. No existing yfinance OHLCV or FRED calls are modified. Epic B replaces chains only after parallel validation.
- **Pre-fetch only**: All OpenBB data is fetched before the debate starts and injected into MarketContext. Agents do not query data sources during debate (no MCP, no tool use). This preserves data consistency (all agents see the same snapshot) and avoids latency spikes.
- **VADER for sentiment**: Use local VADER sentiment scoring (no cloud NLP API). VADER is a well-established lexicon-based sentiment analyzer that works well for financial news headlines. No API key, no network call for scoring.
- **One OpenBB service instance**: Created in app factory / CLI startup alongside existing services. Passed via DI, never instantiated in business logic.

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| OpenBB SDK adds significant dependency weight | Larger install, potential conflicts | Guard import; make OpenBB optional. Document `pip install openbb` as opt-in. |
| Stockgrid changes API or goes offline | Unusual flow data unavailable | Never-raises contract; feature degrades to None. Flow data is P1, not critical path. |
| CBOE chain format differs from yfinance | Contract model mapping issues | Parallel validation phase; extensive unit tests on field mapping. |
| VADER misclassifies financial headlines | Inaccurate sentiment signals | Sentiment is context only (not scored). Agents can disagree with sentiment label. |
| Rate limiting from Yahoo via OpenBB | Fundamentals fetch fails under load | Cache-first (1h TTL), rate limiter, per-ticker isolation |

## Out of Scope

- **Paid data providers** (FMP, Polygon, Intrinio): Not included in any phase. Could be added later behind the same `OpenBBConfig` pattern.
- **Real-time streaming**: OpenBB WebSocket/streaming capabilities are not used. All fetches are point-in-time snapshots.
- **MCP server for agents**: Agents receive pre-fetched data only. No MCP tool use during debate.
- **OpenBB technical indicators**: We keep our own indicator engine (`indicators/`). OpenBB's `obb.technical.*` is not used.
- **Provider abstraction for OHLCV**: yfinance OHLCV remains as-is. Only option chains get a provider abstraction (Epic B).
- **Sub-industry fundamental comparisons**: No sector-relative valuation metrics in v1.
- **Fundamental scoring**: Fundamentals feed into debate context only, not into the composite scoring engine.

## Dependencies

- **OpenBB Platform SDK** (`openbb`): New optional dependency. Added via `uv add openbb` as optional extra.
- **VADER sentiment** (`vaderSentiment` or `nltk`): For local sentiment scoring. Lightweight, no API key.
- **Existing services**: `MarketDataService`, `OptionsDataService`, `HealthService` — extended, not replaced.
- **Existing models**: `MarketContext`, `OptionContract`, `HealthReport` — extended with optional fields.
- **Epic A before Epic B**: Fundamentals/flow/sentiment (Epic A) is independent of chain migration (Epic B). Both can run in parallel but Epic A is lower risk and should ship first.

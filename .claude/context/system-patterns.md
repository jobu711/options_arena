# System Patterns

**Layered architecture with strict module boundaries.** Each layer communicates through
typed Pydantic v2 models. Module boundary table and key rules are in `CLAUDE.md`.

## Unique Design Patterns

### Repository Pattern (Persistence)
- `Database` handles connection lifecycle, WAL mode, migrations
- `Repository` provides typed CRUD operations (`save_scan_run()`, `get_latest_scan()`, etc.)
- All queries return typed models, never raw dicts

### Immutable Models
- `frozen=True` on data models representing snapshots (quotes, contracts, verdicts)
- Computed fields (`mid`, `spread`, `dte`) derived at access time

### Re-export Pattern
- Each package `__init__.py` re-exports its public API
- Consumers import from the package, not submodules: `from options_arena.models import OptionContract`

### NaN/Inf Defense Pattern
- **`math.isfinite()` at model boundaries**: Every numeric validator must check `isfinite()` before range checks — NaN silently passes `v >= 0`.
- **`math.isfinite()` at computation entry**: Pricing/scoring guard non-finite inputs at entry.
- **NaN for undefined ratios**: Division-by-zero returns `float("nan")`, not `0.0`.
- **Display guards**: CLI checks `isfinite()` before formatting, falls back to `"--"`.
- **OHLCV candle validators**: Rejects zero/negative/non-finite prices; `model_validator` rejects impossible candles.
- **Zero-price rejection**: `fetch_quote()`/`fetch_ticker_info()` raise `TickerNotFoundError` when price is None/<=0.
- **MarketContext completeness**: Optional fields are `float | None`. `completeness_ratio()` measures populated fields. Debate requires >=60%; <80% warns.

### Service Layer Patterns
- **Class-based DI**: `config`, `cache`, `limiter` via `__init__`. Explicit `close()`. Cache-first strategy.
- **httpx**: one `AsyncClient` per service, closed via `aclose()`. Retry with exponential backoff (1s→16s).
- **yfinance wrapping**: `_yf_call(fn, *args)` — `to_thread(fn, *args)` + `wait_for(timeout)`. CRITICAL: pass callable + args separately, NOT `to_thread(fn())`.
- **Two-tier caching**: in-memory LRU + SQLite WAL. Market-hours-aware TTL.
- **Rate limiting**: Token bucket (`time.monotonic()`) + `asyncio.Semaphore`.
- **Batch isolation**: `asyncio.gather(*tasks, return_exceptions=True)` — one failure never crashes batch.
- **FRED/OpenBB never raise**: return fallback/None on error.

### PydanticAI Agent Pattern
- Module-level `Agent[Deps, OutputType]` instances (bull, bear, risk, volatility) — no classes
- `model=None` at init, actual model passed at `agent.run(model=...)` time (enables `TestModel`)
- `@dataclass` deps (`DebateDeps`), `output_type=PydanticModel` for structured JSON output
- `retries=2`, `model_settings=ModelSettings(extra_body={"num_ctx": 8192})`
- `@agent.output_validator` delegates to shared helpers: `build_cleaned_agent_response()` (bull/bear) and `build_cleaned_trade_thesis()` (risk) — strips `<think>` tags without costly retries
- **Shared prompt appendix**: `PROMPT_RULES_APPENDIX` (confidence calibration, data anchors, citation rules, IV rank vs percentile, Greeks guidance) appended to bull/bear/risk prompts. Volatility uses its own prompt contract. `RISK_STRATEGY_TREE` appended to risk only.
- **Groq-only**: `build_debate_model()` builds `GroqModel` directly (no provider abstraction)
- **Per-agent timeout**: `config.agent_timeout` (60s default)
- **Bull rebuttal** (optional, `enable_rebuttal`): bull runs a second time with `bear_counter_argument` set. Uses string concatenation (`_REBUTTAL_PREFIX` + text + `_REBUTTAL_SUFFIX`), NOT `str.format()` — safe for LLM text with curly braces.
- **Parallel rebuttal + volatility**: when both enabled, run via `asyncio.gather` (independent)
- **Score-confidence clamping**: `TradeThesis` model_validator clamps confidence ≤0.5 when scores contradict direction
- **Citation density**: `compute_citation_density()` measures fraction of context labels cited in agent output
- Orchestrator never raises: catches errors → data-driven fallback (confidence=0.3)

### Debate Orchestration Flow
```
1. build_market_context() → MarketContext
2. build_debate_model(config) → GroqModel
3. Bull → Bear (receives bull argument) → [Rebuttal + Volatility in parallel if both enabled]
   → Risk (receives all) → TradeThesis
4. Compute citation density, accumulate RunUsage, persist to ai_theses (incl. debate_mode, citation_density)
On any error: data-driven fallback (is_fallback=True, confidence=0.3)
```

### Batch Debate & Export Patterns
- `_debate_single()` reusable for single and batch; `_batch_async()` iterates sequentially with per-ticker error isolation
- `reporting/debate_export.py` generates markdown/PDF from `DebateResult`; PDF via optional `weasyprint`

### Scan Pipeline Data Flow
```
Phase 1: Universe (~5,286 CBOE tickers) → OHLCV fetch
Phase 2: Indicators → normalize → score → direction
Phase 3: Liquidity pre-filter → Top 50 → option chains → recommend contracts
Phase 4: Persist to SQLite
```

### Web API Patterns
- **App factory**: `create_app()` with `lifespan()` — services created once, stored on `app.state`
- **Dependency injection**: `Depends()` providers in `deps.py` — `get_repo()`, `get_market_data()`, etc.
- **Operation mutex**: Single `asyncio.Lock` — one scan or batch debate at a time. Lock acquired
  atomically in handler, released in background task's `finally` block (not `async with lock:`).
- **Background tasks**: `asyncio.create_task()` for scans/debates. Counter-based IDs (no DB placeholder).
- **WebSocket bridge**: `WebSocketProgressBridge` converts sync `ProgressCallback` → `asyncio.Queue`
  → WebSocket JSON events. Queue cleanup in `finally` blocks to prevent memory leaks.
- **Loopback-only**: `serve` command rejects non-loopback `--host` values (security).
- **Static serving**: Explicit catch-all GET `/{path:path}` route (not `StaticFiles(html=True)`) serves
  static files if they exist, otherwise `index.html` for Vue Router history mode. `/assets` mounted
  separately via `StaticFiles`. Configurable DB path via `DataConfig.db_path` for test isolation.

### Watchlist Pattern
- SQLite-backed watchlist with `WatchlistItem` model (ticker, added_at, notes)
- Repository CRUD: `add_to_watchlist()`, `remove_from_watchlist()`, `get_watchlist()`
- API routes: `/api/watchlist` (GET/POST/DELETE)
- CLI subcommand: `options-arena watchlist add/remove/list`
- Frontend: WatchlistPage with add/remove, TickerDrawer integration

### Score History & Trending Pattern
- `HistoryPoint` (ticker, composite_score, direction, scanned_at) from scan_runs join ticker_scores
- `TrendingTicker` (ticker, consecutive_scans, latest_score, score_change, direction)
- Repository: `get_score_history(ticker, limit)`, `get_trending_tickers(direction, min_scans)`
- Frontend: ScoreHistoryChart (Chart.js line), SparklineChart (inline mini-chart)

### Scan Delta Pattern
- `TickerDelta` and `ScanDiff` models compare current vs previous scan
- API: `/api/scans/{id}/diff` returns movers (new, dropped, score changes)
- Frontend: delta badges on ScanResultsPage

### Sector Filtering Pattern
- `GICSSector` StrEnum (11 GICS sectors) + `SECTOR_ALIASES` dict (30+ case-insensitive aliases)
- `field_validator("sectors", mode="before")` normalizes aliases → enum, deduplicates via `dict.fromkeys()`
- `UniverseService.build_sector_map()` maps S&P 500 tickers → GICSSector from Wikipedia data
- `UniverseService.filter_by_sectors()` pure helper with OR logic across selected sectors
- Pipeline Phase 1 applies sector filter; Phase 2-3 enriches TickerScore with sector + company_name
- Migration 008 adds nullable `sector`/`company_name` columns to `ticker_scores`
- ETF preset: 60+ curated seed tickers verified via yfinance, 24h cache

### Earnings Calendar Pattern
- `market_data.fetch_earnings_date()` via yfinance calendar, cached
- `next_earnings` field on `TickerScore` (persisted in migration 007)
- Earnings warning injected into debate prompts when within 7 days
- Frontend: earnings date column + overlay on scan results

### ChainProvider Pattern (Option Chain Abstraction)
- **Protocol**: `ChainProvider` with `fetch_chain()` method — `CBOEChainProvider` (primary) + `YFinanceChainProvider` (fallback)
- **Three-tier Greeks**: CBOE native Greeks → local BAW/BSM computation → exclude contract
- **Orchestration**: `options_data.py` tries CBOE with timeout, falls back to yfinance on any exception
- **DI wiring**: Provider injected at 5 call sites (CLI + API); config-gated via `cboe_chains_enabled`

### OpenBB Enrichment Pattern (Optional)
- **Guarded imports**: `_get_obb()`/`_get_vader()` return SDK or `None` — never-raises contract
- **Config-gated**: `OpenBBConfig.enabled` master toggle + per-source toggles (fundamentals, flow, sentiment)
- **MarketContext**: 11 enrichment fields + `enrichment_ratio()` (separate from `completeness_ratio()`)
- **Models**: 5 frozen (`FundamentalSnapshot`, `UnusualFlowSnapshot`, `NewsHeadline`, `NewsSentimentSnapshot`, `OpenBBHealthStatus`)

For detailed algorithm specs, see `system-patterns-reference.md`.

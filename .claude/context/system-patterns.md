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
- **MarketContext completeness**: Optional fields are `float | None`. `completeness_ratio()` measures populated fields. <0.4 → data-driven fallback; <0.6 → warning (proceed with caution); >=0.6 → full debate.

### Service Layer Patterns
- **Class-based DI**: `config`, `cache`, `limiter` via `__init__`. Explicit `close()`. Cache-first strategy.
- **httpx**: one `AsyncClient` per service, closed via `aclose()`. Retry with exponential backoff (1s->16s).
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
- **Shared prompt appendix**: `PROMPT_RULES_APPENDIX` appended to bull/bear/risk. `RISK_STRATEGY_TREE` appended to risk only.
- **Groq-only**: `build_debate_model()` builds `GroqModel` directly (no provider abstraction)
- **Single debate path**: `run_debate()` (v1 eliminated, v2 renamed). No legacy code paths.
- **Bull rebuttal** (optional): bull runs a second time with `bear_counter_argument` set. Uses string concatenation, NOT `str.format()` — safe for LLM text with curly braces.
- **Score-confidence clamping**: `TradeThesis` model_validator clamps confidence <=0.5 when scores contradict direction
- **Citation density**: `compute_citation_density()` measures fraction of context labels cited in agent output
- Orchestrator never raises: catches errors -> data-driven fallback (confidence=0.3)
- **Domain context partitioning**: Phase 1 agents receive only domain-specific context via `render_trend_context()`, `render_volatility_context()`, `render_flow_context()`, `render_fundamental_context()` — no composite score or direction anchoring
- **Log-odds pooling**: Bordley 1982 weighted confidence compounding replaces naive averaging. `AGENT_VOTE_WEIGHTS` sum intentionally < 1.0 (risk excluded from directional voting)
- **Ensemble diversity**: `_vote_entropy()` (Shannon entropy of direction votes), `compute_agreement_score()` (fraction agreeing with majority). Confidence capped at 0.4 when agreement < 0.4
- **Agent prediction persistence**: `AgentPrediction` model + migration 025 + `extract_agent_predictions()`. In v2, "bull" field holds trend output; bear is skipped (static fallback)

### Scan Pipeline & Debate Flow — See `scan/CLAUDE.md` and `agents/CLAUDE.md`

### Batch Debate & Export Patterns
- `_debate_single()` reusable for single and batch; `_batch_async()` iterates sequentially with per-ticker error isolation
- `reporting/debate_export.py` generates markdown/PDF from `DebateResult`; PDF via optional `weasyprint`

### Web API Patterns
- **App factory**: `create_app()` with `lifespan()` — services created once, stored on `app.state`
- **Dependency injection**: `Depends()` providers in `deps.py` — `get_repo()`, `get_market_data()`, etc.
- **Operation mutex**: Single `asyncio.Lock` — one scan or batch debate at a time. Lock acquired
  atomically in handler, released in background task's `finally` block (not `async with lock:`).
- **Background tasks**: `asyncio.create_task()` for scans/debates. Counter-based IDs (no DB placeholder).
- **WebSocket bridge**: `WebSocketProgressBridge` converts sync `ProgressCallback` -> `asyncio.Queue`
  -> WebSocket JSON events. Queue cleanup in `finally` blocks to prevent memory leaks.
- **Loopback-only**: `serve` command rejects non-loopback `--host` values (security).
- **Static serving**: Explicit catch-all GET `/{path:path}` route serves static files if they exist,
  otherwise `index.html` for Vue Router history mode. `/assets` mounted via `StaticFiles`.

### Watchlist Pattern
- SQLite-backed `WatchlistItem` model, Repository CRUD, API `/api/watchlist`, CLI `watchlist`

### Score History, Trending & Scan Delta
- `HistoryPoint`/`TrendingTicker` from scan_runs join ticker_scores; `ScoreHistoryChart`/`SparklineChart`
- `TickerDelta`/`ScanDiff`: `/api/scans/{id}/diff` returns movers; delta badges on frontend

### Sector Filtering Pattern
- `GICSSector` StrEnum + `SECTOR_ALIASES` dict, `field_validator` normalizes aliases, deduplicates via `dict.fromkeys()`
- Pipeline Phase 1 applies sector filter; Phase 2-3 enriches with sector + company_name

### Earnings Calendar Pattern
- `market_data.fetch_earnings_date()` via yfinance; warning in debate prompts when within 7 days

### ChainProvider Pattern (Option Chain Abstraction)
- **Protocol**: `ChainProvider` with `fetch_chain()` — `CBOEChainProvider` (primary) + `YFinanceChainProvider` (fallback)
- **Three-tier Greeks**: CBOE native -> local BAW/BSM computation -> exclude contract
- **Orchestration**: `options_data.py` tries CBOE with timeout, falls back to yfinance on exception

### OpenBB Enrichment Pattern (Optional)
- **Guarded imports**: `_get_obb()`/`_get_vader()` return SDK or `None` — never-raises contract
- **Config-gated**: `OpenBBConfig.enabled` master toggle + per-source toggles
- **MarketContext**: 11 enrichment fields + `enrichment_ratio()` (separate from `completeness_ratio()`)

### Intelligence Service Pattern (Market Recon)
- `IntelligenceService`: multi-source aggregation (OpenBB fundamentals, flow, sentiment)
- Config-gated per source; never-raises contract; enrichment injected into debate agent prompts

### Analytics Persistence Pattern (Outcome Tracking)
- **Contract persistence**: Phase 3 captures `entry_stock_price`; Phase 4 persists `RecommendedContract` + `NormalizationStats`
- **Outcome collection**: `OutcomeCollector` fetches quotes at T+1/T+5/T+10/T+20, computes P&L
- **Expired handling**: ITM -> intrinsic value; OTM -> expired worthless (-100%)
- **Analytics queries**: 6 typed results, 9 API endpoints on `/api/analytics`, CLI `outcomes` subcommand

### Metadata Index Pattern (Ticker Classification Cache)
- **Persistent cache**: SQLite table `ticker_metadata` — GICS sector, industry group, market cap tier
- **Bulk upsert**: `Repository.upsert_metadata_batch()` for ~5K CBOE tickers
- **Pipeline integration**: Phase 1 enriches tickers from cache; `universe index` CLI rebuilds
- **API**: `/api/universe/metadata` + `/api/universe/metadata/stats` endpoints
- **Staleness**: 30-day TTL; `MetadataStats` tracks coverage and freshness

### S&P 500 Heatmap Pattern
- **Batch quotes**: `BatchQuote` model + `fetch_batch_daily_changes()` fetches daily % change for all S&P 500 tickers
- **Chunked download**: Batches chunked to prevent timeout on large universe
- **API**: `GET /api/market/heatmap` returns `list[HeatmapTicker]` (ticker, change_pct, sector, market_cap)
- **Frontend**: `MarketHeatmap.vue` — client-side squarify treemap layout, color-coded by % change
- **State**: Pinia `heatmap` store with async fetch + caching

For detailed algorithm specs, see `system-patterns-reference.md`.

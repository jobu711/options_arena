# Progress Archive

Historical completion logs for Options Arena. Current state is in `progress.md`.

## Epic 10: Web UI (2026-02-26) — #121, PR #130

Full-stack Web UI: Vue 3 SPA (TypeScript, Pinia, Vue Router, PrimeVue Aura dark) +
FastAPI backend. `options-arena serve` command launches uvicorn with browser auto-open.
REST endpoints for scan, debate, export, health, universe, config. WebSocket progress
streaming for scans (4-phase) and debates (agent steps + batch). Operation mutex via
`asyncio.Lock` (409 if busy). Loopback-only host guard. 11 bug fixes from code analysis
(race conditions, memory leaks, temp file cleanup, type safety, WebSocket lifecycle).
+93 new tests (82 API + 8 serve + 3 misc). Issues: #122-#129.

## Epic 9: Data Integrity Hardening (2026-02-26) — #114

End-to-end data integrity across all pipeline layers. OHLCV candle validators,
OptionGreeks NaN defense, zero-price rejection, MarketContext completeness,
debate quality gate (60% minimum), cache TTL validation, NaN propagation guards.
+82 new tests. Issues: #115-#119, PR #120.

## Epic 8: Groq-Only Migration + 12 Debate Improvements (2026-02-25)

Removed Ollama, Groq sole LLM provider. Simplified DebateConfig, Groq health check,
parallel rebuttal+volatility, score-confidence clamping, citation density, A/B logging.

## Epic 7: Debate Export (2026-02-25) — #107

Markdown/PDF export via `--export md|pdf`. Issues: #109-#113.

## Epic 6: Multi-Ticker Batch Debate (2026-02-25) — #101

`debate --batch` and `--batch-limit N`. Issues: #102-#106.

## Epic 5: Bull Rebuttal Round (2026-02-25) — #93

Optional bull rebuttal phase. Issues: #94-#99.

## Completed Work (Phase 1)

### Issue #18 — Models, Enums, Exceptions (Done)
### Issue #19 — Persistence Layer / SQLite (Done)
### Issue #20 — Services Layer (Done)
### Issue #21 — Technical Indicators (Done)
### Issue #14 — Analysis & Scoring Engine (Done)
### Issue #15 — AI Debate System (Done)
### Issue #16 — Reporting & CLI Integration (Done)
### Issue #17 — Comprehensive Test Suite (Done)

## Post-Phase 1 Fixes (Cherry-picked after rollback)

- `c1ab1ba` — CBOE CSV parser fix, Windows spinner crash fix, universe cache persistence
- `57b2a9c` — Switch universe source from weekly-only to full CBOE directory
- `f523d63` — Fetch S&P 500 constituents from Wikipedia for universe classification
- `d235b31` — Remove stale hooks and clear hook settings
- `9ae037c` — Add rotating file logger for persistent DEBUG output
- `c9da1c1` — Suppress aiosqlite DEBUG noise in file logger
- `5f1c472` — Filter index symbols, raise OHLCV minimum to 200, cache fetch failures
- `c225bfc` — Fix 0 option recommendations in scan pipeline
- `5942264` — Add liquidity pre-filter to scan pipeline (dollar volume + min price)
- `9c0d213` — Fix 3 cascading failures: isolate indicator try/except, SMA tiebreaker for direction ties, remove service-level delta filter

## Scan Pipeline Logic Fix (Implemented)

Four changes to resolve 0 option recommendations:

1. **Normalization: skip universally-missing indicators** — The 4 options-specific
   indicators (22% weight) were defaulting to 50.0 for all tickers, diluting score
   discrimination. Now skipped entirely; composite_score() renormalizes the remaining
   14 real indicators automatically.

2. **ADX trend threshold lowered 20.0 → 15.0** — Recovers tickers with weak trends
   (ADX 15-20) that were being classified NEUTRAL and skipped.

3. **Zero-bid filter softened** — Service layer now only rejects contracts where both
   bid AND ask are zero (truly dead). Contracts with bid=0/ask>0 pass through to the
   analysis layer. Spread filtering moved from service to analysis layer with zero-bid
   exemption (spread check is meaningless when bid=0).

4. **Delta range widened + fallback** — Primary range expanded from [0.30, 0.40] to
   [0.20, 0.50]. Fallback picks closest-to-0.35 within [0.10, 0.80] if nothing in
   primary range.

## PydanticAI Migration (Completed 2026-02-20)

Replaced hand-rolled `LLMClient`, manual JSON parsing, and custom retry logic
with PydanticAI agent framework. Epic: 8 issues (#74-#81), all merged.

- `bb3b6bd` — Install pydantic-ai, create `model_config.py` with `build_ollama_model()`
- `536f8d6` — Simplify prompts to string constants (remove `PromptMessage` class)
- `2f7f41c` — Rewrite bull/bear/risk as PydanticAI `Agent` instances with typed `output_type`
- `ff1a690` — Simplify `_parsing.py` to models + constants only (~170 → ~70 lines)
- `deeaada` — Adapt orchestrator to PydanticAI agents (`RunUsage` accumulation)
- `86cd3c3` — Delete `llm_client.py` (272 lines removed), update exports
- `9a6ec05` — Rewrite agent tests using PydanticAI `TestModel`
- `827b131` — Fix regressions: wire `num_ctx=8192`, add think-tag `@output_validator`, restore `OLLAMA_HOST` env var

Net result: ~300 lines removed from agents module, zero changes outside `agents/` + `cli.py`.

## Options Arena Rewrite (PRD Created 2026-02-21)

From-scratch rewrite of Option Alpha v3, renaming to `options_arena` (PEP 8 compliant).
PRD: `.claude/prds/options-arena.md` — status: backlog.

**Key changes from v3:**
- BAW (Barone-Adesi-Whaley) pricing for American options (fixes critical European BSM misapplication)
- `analysis/` split into `pricing/` + `scoring/` packages
- New `scan/` module replaces 430-line `cli.py` scan function
- Data-driven `IndicatorSpec` registry replaces 14 copy-paste indicator blocks
- `AppSettings` centralizes scattered constants
- `IndicatorSignals` typed model replaces `dict[str, float]` on `TickerScore`
- `DividendSource` enum + 3-tier waterfall for dividend yield extraction with dollar-rate cross-validation (FR-M7/M7.1 updated 2026-02-22)
- AI debate, reporting, web UI deferred to v2

**8 implementation phases**, ~810 tests target.

### Phase 1: Project Bootstrap & Models (Complete — 2026-02-22)
- Branch: `epic/phase-1-bootstrap-models` (PR #12 merged to master)
- All 11 issues completed (#1–#11)
- 220 tests passing (ruff, pytest, mypy --strict all green)
- Implemented: enums (11 StrEnums), exceptions, AppSettings config, all Pydantic models
  (OHLCV, Quote, TickerInfo, OptionGreeks, OptionContract, SpreadLeg, OptionSpread,
  MarketContext, AgentResponse, TradeThesis, IndicatorSignals, ScanRun, TickerScore, HealthStatus)
- Hardened: strict UTC enforcement on all datetime fields, confidence [0,1] validators,
  MacdSignal/ScanPreset StrEnums (no raw strings), market_iv >= 0, quantity >= 1, non-empty legs
- Package re-exports via `__init__.py` with `__all__`

### PRD Updates (2026-02-22)
- FR-M3.1: Added `DividendSource` enum (`FORWARD`, `TRAILING`, `COMPUTED`, `NONE`)
- FR-M7: Expanded dividend yield spec — 3-tier waterfall from yfinance `info["dividendYield"]` > `info["trailingAnnualDividendYield"]` > `Ticker.get_dividends(period="1y")` sum / price > `0.0`. Field is `float` (never `None`), with provenance tracking. Values are decimal fractions (0.005 = 0.5%).
- FR-M7.1 (new): Waterfall detail — fall-through on `None` only (not falsy; `0.0` is valid for growth stocks). Cross-validation: when yield and dollar-rate (`dividendRate`, `trailingAnnualDividendRate`) both available, warn on >20% divergence. Audit fields `dividend_rate: float | None` and `trailing_dividend_rate: float | None` added to `TickerInfo`.
- FR-SV1: Service layer dividend extraction updated to match FR-M7.1 waterfall + dollar-rate cross-validation + `get_dividends(period="1y")` for computed tier. All yfinance `.info` keys are camelCase (`dividendYield`, `trailingAnnualDividendYield`, `dividendRate`, `trailingAnnualDividendRate`).
- FR-SV2: Corrected false assumption — yfinance option chains provide `impliedVolatility` but **no Greeks** (no delta/gamma/theta/vega/rho). All Greeks computed locally via `pricing/dispatch.py`. `impliedVolatility` passed through as `market_iv` for IV solver seed and cross-check.
- FR-S4: Removed "fallback" framing — `pricing/dispatch.py` is the sole source of Greeks for all contracts, not a fallback for missing yfinance data.
- Section 8 assumption corrected to reflect yfinance chain columns (Context7-verified).
- FR-SV3: Added Wikipedia table implementation detail — `pd.read_html(url, attrs={"id": "constituents"})` targets table by stable HTML id (not positional index). Columns: `Symbol`, `Security`, `GICS Sector`, `GICS Sub-Industry`, `Headquarters Location`, `Date added`, `CIK`, `Founded`. Ticker translation needed (`.` → `-` for yfinance). Section 8 assumption updated with column-level specificity.
- FR-M5/M5.1/M6: Expanded `AppSettings` spec with Context7-verified pydantic-settings v2 patterns. `AppSettings(BaseSettings)` is the sole `BaseSettings` subclass; `ScanConfig`, `PricingConfig`, `ServiceConfig` are nested `BaseModel` submodels. `SettingsConfigDict(env_prefix="ARENA_", env_nested_delimiter="__")` enables env overrides like `ARENA_SCAN__TOP_N=30`. Full field inventory added in FR-M5.1. No `.env` file in MVP.
- FR-P1/P2/P3: Corrected IV solver strategy (Context7-verified). BSM IV: manual Newton-Raphson (analytical vega via `norm.pdf`, quadratic convergence). BAW IV: **`scipy.optimize.brentq`** (NOT Newton-Raphson — BAW has no analytical vega w.r.t. IV; brentq is bracket-based, guaranteed convergent, no derivative needed). Dispatch routes solver by `ExerciseStyle`. scipy dependency description updated across PRD and tech-context.

### Phase 2: Pricing Engine (Complete — 2026-02-22)
- Branch: `epic/phase-2-pricing` (merged to master)
- All 6 issues completed (#14–#19), GitHub issues auto-closed
- 434 tests passing (162 pricing + 272 models), ruff + mypy --strict all green
- Implemented:
  - `bsm.py` — Merton 1973 European BSM with continuous dividend yield `q`
  - `american.py` — BAW 1987 analytical approximation for American options
  - `dispatch.py` — unified routing by `ExerciseStyle` (AMERICAN→BAW, EUROPEAN→BSM)
  - `_common.py` — shared helpers (input validation, intrinsic value, boundary Greeks)
  - Newton-Raphson IV solver (BSM, analytical vega), brentq IV solver (BAW, bracket-based)
  - Analytical BSM Greeks (delta, gamma, theta, vega, rho)
  - Finite-difference BAW Greeks (bump-and-reprice, 11 evaluations per call)
  - FR-P4 verified: `american_call == bsm_call` when `q = 0`
  - FR-P5 verified: `american_put >= bsm_put` always
- Post-merge fixes: code analysis warnings addressed, 52 edge case tests added
- `logic.md` business logic documentation added

### Phase 3: Technical Indicators (Complete — 2026-02-23)
- Branch: `master` (merged directly, no epic branch)
- 18 indicator functions across 6 modules, 606 total tests on master
- Commits: `61e247d` (initial port), `8b6c523` (hardening), `7d0b973` (CodeRabbit fixes), `a528731` (final)
- Modules: `indicators/trend.py`, `indicators/oscillators.py`, `indicators/volatility.py`,
  `indicators/volume.py`, `indicators/moving_averages.py`, `indicators/options_specific.py`
- All indicators: pure pandas in/out, NaN warmup, vectorized operations only

### Phase 4: Scoring Module (Complete — 2026-02-23, PR #28 merged)
- Branch: `epic/phase-4-scoring` (PR #28 merged to master 2026-02-23)
- All 6 issues completed (#21–#27), GitHub issues auto-closed via PR
- 102 scoring tests, ruff + mypy --strict all green, zero architecture violations
- Implemented:
  - `normalization.py` — percentile-rank normalize with tie handling, inversion, active indicator detection
  - `composite.py` — weighted geometric mean (18 indicators, 6 categories, weights sum to 1.0)
  - `direction.py` — ADX/RSI/SMA signal aggregation with SMA tiebreaker
  - `contracts.py` — **rewrite** (not cherry-pick): Greeks via `pricing/dispatch.py` (BAW/BSM),
    delta targeting [0.20, 0.50] primary + [0.10, 0.80] fallback, zero-bid exemption,
    all thresholds from `PricingConfig`
  - `scoring/CLAUDE.md` — module conventions, v3-to-Arena field name mapping
- Key design decisions:
  - `contracts.py` uses `pricing/dispatch.py` as sole Greeks source (no local BSM/BAW imports)
  - `score_universe()` returns percentile-ranked signals; `determine_direction()` needs raw values
  - All thresholds from `ScanConfig`/`PricingConfig` — no hardcoded magic numbers
- Post-merge fixes: code analysis findings (`bc722bb`), CodeRabbit `math.isfinite` guards (`a9c4cc1`)

### Phase 5: Services Layer (Complete — 2026-02-23, PR #38 merged)
- Branch: `epic/phase-5-services` (PR #38 merged to master 2026-02-23, epic closed)
- All 8 issues completed (#30–#37), 163 new tests, 871 total
- ruff + pytest + mypy --strict all green on 39 source files
- Implemented (complete rewrite, no v3 cherry-pick):
  - `helpers.py` — `fetch_with_retry()` exponential backoff (1s→16s), `safe_decimal/int/float` with NaN/inf rejection
  - `rate_limiter.py` — Token bucket + `asyncio.Semaphore` dual-layer rate control
  - `cache.py` — Two-tier (in-memory LRU + SQLite WAL), 8 named TTL constants, `is_market_hours()` for 9:30-16:00 ET
  - `market_data.py` — `MarketDataService`: OHLCV, quotes, ticker info, 3-tier dividend waterfall (FR-M7.1), cross-validation, `MarketCapTier`, batch fetch with error isolation
  - `options_data.py` — `OptionsDataService`: chain fetching, yfinance column mapping to `OptionContract`, liquidity filter with zero-bid exemption, `ExerciseStyle.AMERICAN`, `greeks=None`
  - `fred.py` — `FredService`: FRED API risk-free rate, percentage-to-decimal, never raises (graceful fallback)
  - `universe.py` — `UniverseService`: CBOE optionable tickers, Wikipedia S&P 500 with `pd.read_html(attrs={"id": "constituents"})`, ticker translation (`.`→`-`)
  - `health.py` — `HealthService`: pre-flight checks (yfinance, FRED, Ollama, CBOE), concurrent `check_all()`, latency measurement
  - `__init__.py` — Re-exports 7 public classes, `helpers.py` internal only
- Key design: async-first, config-driven thresholds, DI constructors, explicit `close()`, typed Pydantic returns at all boundaries
- `ServiceConfig.fred_api_key: str | None = None` added (backward-compatible)

### Phase 6: Data Layer (Complete — 2026-02-23, PR #45, epic closed)
- Branch: `epic/phase-6-data` (PR #45 open, epic #39 closed)
- All 5 issues completed (#40–#44), 34 new tests, 905 total
- ruff + pytest + mypy --strict all green on 42 source files
- Implemented (full rewrite, no v3 cherry-pick):
  - `data/CLAUDE.md` — Module conventions, aiosqlite patterns (Context7-verified)
  - `data/migrations/001_initial.sql` — 6 tables: scan_runs, ticker_scores, service_cache, ai_theses, watchlists, watchlist_tickers
  - `database.py` — `Database` class: async connect/close, WAL mode, FK enabled, aiosqlite.Row factory, sequential migration runner with schema_version tracking
  - `repository.py` — `Repository` class: typed CRUD for ScanRun/TickerScore, IndicatorSignals JSON round-trip, StrEnum/datetime serialization, parameterized queries only
  - `__init__.py` — Re-exports Database, Repository with `__all__`
- Key design: :memory: for tests, DI constructors, idempotent connect/close, batch insert via executemany
- Post-review fixes: deterministic ORDER BY on scores query, migration filename filter, unused param removal (CodeRabbit PR #45)

### Phase 7: Scan Pipeline (Complete — 2026-02-23, PR #53 merged, epic closed)
- Branch: `epic/phase-7-scan-pipeline` (PR #53 merged to master 2026-02-23, epic #46 closed)
- All 6 issues completed (#47–#52), 156 new tests (131 unit + 25 integration), 1061 total
- ruff + pytest + mypy --strict all green on 46 source files
- Implemented (full rewrite, replaces v3's monolithic 430-line `cli.py` scan function):
  - `scan/progress.py` — `ScanPhase` StrEnum (4 phases), `CancellationToken` (thread-safe), `ProgressCallback` protocol
  - `scan/indicators.py` — `InputShape` enum, `IndicatorSpec` dataclass, `INDICATOR_REGISTRY` (14 entries), `ohlcv_to_dataframe()`, `compute_indicators()`
  - `scan/models.py` — Pipeline-internal models: `UniverseResult`, `ScoringResult`, `OptionsResult`, `ScanResult`
  - `scan/pipeline.py` — `ScanPipeline` class: 4 async phases (universe, scoring, options, persist), cancellation between phases, progress callbacks, DI for all 5 services + repository
  - `scan/__init__.py` — Re-exports 5 public names with `__all__`
- Key design decisions:
  - 14-indicator registry (not 18) — 4 options-specific indicators need chain data unavailable in Phase 2
  - Raw signals retained separately from normalized (percentile-ranked) signals for direction classification
  - Liquidity pre-filter (avg dollar volume + min price) applied before expensive option chain fetches
  - Per-ticker timeout (30s) + error isolation — one failed ticker never crashes the scan
  - FRED risk-free rate fetched once per scan (not per ticker)
  - `OptionContract.greeks` always `None` from services — computed by `recommend_contracts()` via `pricing/dispatch.py`
- Post-merge fixes: phases_completed bounds, ETFS preset warning, per-ticker timeout, event loop yielding (`5d465e2`), CodeRabbit review fixes (`5edf044`)

### Phase 8: CLI Module (Complete — 2026-02-23, PR #61 merged, epic closed)
- Branch: `epic/phase-8-cli` (PR #61 merged to master 2026-02-23, epic #54 closed)
- All 6 issues completed (#55–#60), 25 new tests, 1086 total
- ruff + pytest + mypy --strict all green on 51 source files
- Implemented (final phase — completes MVP 1.0.0):
  - `cli/app.py` — Typer app, `@app.callback()`, dual-handler logging (RichHandler + RotatingFileHandler)
  - `cli/commands.py` — `scan`, `health`, `universe` (refresh/list/stats) commands
  - `cli/rendering.py` — `render_scan_table()`, `render_health_table()`, disclaimer constant
  - `cli/progress.py` — `RichProgressCallback` implementing `ProgressCallback` protocol
  - `cli/__init__.py` — Re-exports `app` for pyproject.toml entry point
  - `cli/CLAUDE.md` — Module conventions, logging patterns, testing patterns
- Key design: sync Typer commands + `asyncio.run()`, `signal.signal()` for Windows SIGINT,
  `markup=False` on RichHandler, progress on stderr, results on stdout
- Post-merge fixes: 5 bug fixes (market_iv falsy check, sectors warning, resource leak,
  progress total, db path), 2 CodeRabbit fixes (LOG_DIR path, handler close)
- Entry point: `options-arena = "options_arena.cli:app"` in pyproject.toml

### Phase 9: AI Debate System (Complete — 2026-02-24, PR #69 merged, epic closed)
- Branch: `epic/ai-debate` (PR #69 merged to master 2026-02-24, epic #62 closed)
- All 6 issues completed (#63–#68), 126 new tests, 1212 total
- ruff + pytest + mypy --strict all green on 58 source files
- Implemented:
  - `agents/model_config.py` — `build_ollama_model()`, `_resolve_host()` (config > env > default)
  - `agents/_parsing.py` — `DebateDeps` and `DebateResult` dataclasses, constants
  - `agents/bull.py` — Bull PydanticAI agent with system prompt + `<think>` tag output validator
  - `agents/bear.py` — Bear agent with dynamic prompt (receives bull argument via `<<<BULL_ARGUMENT>>>`)
  - `agents/risk.py` — Risk agent with dynamic prompt (receives both arguments) → `TradeThesis`
  - `agents/orchestrator.py` — `run_debate()`, `build_market_context()`, data-driven fallback, never-raises pattern
  - `cli/commands.py` — `debate` command with `--history`, `--fallback-only` flags
  - `cli/rendering.py` — Rich panel rendering for debate output + debate history table
  - `data/repository.py` — `save_debate()`, `get_debates_for_ticker()` with `DebateRow` dataclass
  - `models/config.py` — `DebateConfig(BaseModel)` nested on `AppSettings`
  - `data/migrations/002_debate_columns.sql` — ALTER TABLE for token/model/duration/fallback columns
- Key design: sequential agents (Bull → Bear → Risk), `model=None` at init + override at run,
  `TestModel` for unit tests, data-driven fallback (confidence=0.3) when Ollama unavailable,
  per-agent timeout (90s) + total timeout (300s)
- Post-merge fixes: 14 bug fixes (model=None pattern, nullable FK, isfinite guards, display
  guards, KeyboardInterrupt handler, validators), 10 CodeRabbit suggestions accepted
- `.coderabbit.yaml` added for automated PR reviews

## Post-MVP Hardening (2026-02-23)

Full codebase analysis identified 15 NaN/Inf edge cases across 12 source files.
All fixed in commit `4a91c3a`, 1086 tests passing, ruff + mypy --strict green.

**High priority (NaN bypass on validators):**
- `models/options.py`: gamma, vega, market_iv validators now reject NaN/Inf via `math.isfinite()`
- `models/market_data.py`: dividend_yield validator rejects NaN/Inf and negative values
- `models/scan.py`: composite_score validator enforces [0, 100] with finite check
- `indicators/volatility.py`: bb_width div-by-zero guard with `.replace(0.0, np.nan)`

**Medium priority (logic correctness):**
- `scoring/composite.py`: `math.isfinite()` guard skips NaN/Inf indicator values
- `scoring/direction.py`: non-finite inputs short-circuit to NEUTRAL; SMA tiebreaker handles 0.0
- `indicators/options_specific.py`: put_call_ratio returns NaN (not 0.0) for undefined ratio
- `services/cache.py`: OHLCV TTL changed from permanent (0) to 6 hours (stale daily bars)
- `services/options_data.py`: expirations cached with "reference" TTL (24h) instead of "chain" (5min)

**Low priority (defense in depth):**
- `pricing/bsm.py`: bsm_price, bsm_greeks, bsm_vega guard NaN sigma at entry
- `pricing/american.py`: american_price guards NaN sigma; BAW non-convergence log promoted to WARNING
- `cli/rendering.py`: IV display guards non-finite market_iv with "--" fallback

## Scan Tuning (2026-02-23)

Three changes to improve scan coverage:

1. **CBOE URL → full equity/index options directory**: Changed from weekly-only endpoint
   (`/available_weeklys/get_csv_download/`, ~663 tickers) to the full CBOE symbol directory
   (`/markets/us/options/symbol-directory/equity-index-options?download=csv`, ~5,286 tickers).
   Added `follow_redirects=True` to httpx client and `skipinitialspace=True` to `pd.read_csv()`
   to handle CBOE CSV format (spaces after commas in header). Column matching updated to
   recognize `Stock Symbol` column name.

2. **DTE range widened**: `dte_max` increased from 60 → 365 days. Midpoint target shifted
   from 45 → 197.5 days. Allows LEAPS-range options for longer-horizon analysis.

3. **Spread filter relaxed**: `max_spread_pct` increased from 10% → 30%. The previous 10%
   threshold was calibrated for near-term (30-60 DTE) options. Far-dated options (6-12 months)
   naturally have wider bid-ask spreads; the tight filter was eliminating most contracts at
   those expirations, leaving only 1-2 deep ITM contracts with extreme deltas.

## Groq Cloud API Support (2026-02-24, PR #70 merged)

Added Groq as an alternative cloud LLM provider for the AI debate system.

- `0e9bee1` — feat: add Groq cloud API support (DebateProvider enum, GroqProvider, build_groq_model)
- `72ae6c8` — fix: harden Groq support — NaN validators, provider-aware timeouts, exhaustive dispatch
- `a573848` — refactor: extract fallback-only timeout magic number into named constant
- **DebateProvider** StrEnum (`OLLAMA`, `GROQ`) — configurable via `ARENA_DEBATE__PROVIDER=groq`
- **DebateConfig** hardened: `field_validator` on `temperature` [0.0, 2.0], `agent_timeout`/`groq_timeout`/`max_total_duration` > 0 with `math.isfinite()` guards
- **Provider-aware timeouts**: Ollama uses `agent_timeout` (600s), Groq uses `groq_timeout` (60s)
- **`build_debate_model()`**: match/case dispatch with exhaustive handling (replaces if/else)
- **`strip_think_tags()`**: empty-string fallback preserves original text when stripping produces empty
- 50 new tests (validators, Groq provider, orchestrator, parsing edge cases)

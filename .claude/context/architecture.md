# Architecture -- Design Patterns & Module Constraints

Tier 1 reference for cross-module work. Boundary table and pattern summaries are in CLAUDE.md.
For algorithm details, see `algorithms.md`. For product context, see `product.md`.

## Design Patterns

### Repository (Persistence) -- Mixin Decomposition
- `Database` handles connection lifecycle, WAL mode, migrations
- `Repository` composed via multiple inheritance: `BaseMixin` (connection helpers), `ScanMixin`, `DebateMixin`, `AnalyticsMixin`, `MetadataMixin`, `LearningMixin` (EvalMixin removed in dead-code-cleanup)
- Single public class, all queries return typed models

### Re-export
- Each package `__init__.py` re-exports its public API
- Consumers import from the package, not submodules

### NaN/Inf Defense (Layered)
- Model boundaries: `isfinite()` before range checks in validators
- Computation entry: pricing/scoring guard non-finite inputs
- Undefined ratios: division-by-zero returns `float("nan")`, not `0.0`
- Display: CLI checks `isfinite()` before formatting, falls back to `"--"`
- OHLCV candles: reject zero/negative/non-finite prices; model_validator rejects impossible candles
- Zero-price: `fetch_quote()`/`fetch_ticker_info()` raise `TickerNotFoundError` when price is None/<=0
- MarketContext: `completeness_ratio()` measures populated fields. <0.4 = fallback; <0.6 = warning; >=0.6 = full analysis

### Service Layer
- `ServiceBase[ConfigT]` generic mixin: `_config`, `_cache`, `_limiter`, `_log`, opt-in helpers (`_retried_fetch`, `_yf_call`)
- Logger: `self._log = logging.getLogger(type(self).__module__)`
- `close()` chain: subclasses override and call `await super().close()`
- httpx: one `AsyncClient` per service, closed via `aclose()`, retry with exponential backoff (1s->16s)
- yfinance: `_yf_call(fn, *args)` -- CRITICAL: pass callable + args separately, NOT `to_thread(fn())`
- Two-tier caching: in-memory LRU + SQLite WAL, market-hours-aware TTL
- Rate limiting: token bucket (`time.monotonic()`) + `asyncio.Semaphore`
- FRED/OpenBB never raise: return fallback/None on error

### Recommendation Pipeline (Unified)
- 6 desk recommendation agents -> synthesis agent -> `PositionRecommendation`
- `run_recommendation()` sole entry point, never-raises, fallback with `confidence=0.2`
- Module-level `Agent[Deps, OutputType]` instances, `model=None` at init, actual at `agent.run(model=...)`
- `retries=2`, `model_settings` via `_build_model_settings()` (per-provider)
- `@output_validator` strips `<think>` tags on all agents
- `PROMPT_RULES_APPENDIX` appended to recommendation + synthesis prompts (NOT desk prompts)
- `build_debate_model()` dispatches on `LLMProvider` enum: `GroqModel` or `AnthropicModel`
- Domain context partitioning: agents receive only domain-specific context, no composite score anchoring
- Backward compat: `DebateResult` (in `_parsing.py`), `DebatePhase` retained for old data parsing

### Synthesis Agent
- `Agent[SynthesisDeps, PositionRecommendation]` -- weighs 6 assessments, selects contract
- `SynthesisDeps`: context, assessments, contracts, ticker_score, learned_patterns, tuned_weights, tools_used
- `DomainAssessment` base + 6 subclasses; `AnyAssessment` discriminated union via `Discriminator("desk")` + `Tag()`
- `PositionRecommendation`: 21 fields, `LLMDecimal` prices, frozen
- Dynamic injection of `<<<TUNED_WEIGHTS>>>` and `<<<LEARNED_PATTERNS>>>` blocks
- 2 tools: `synth_fetch_current_quote`, `synth_fetch_chain_summary`

### Desk Agents (Interactive)
- 7 agents: Volatility, Risk, Trend, Flow, Fundamental, Contrarian, Research -- `Agent[DeskDeps, str]`
- `DeskDeps` dataclass with service instances + `tools_used: list[str]`
- Per-desk toolset builders in `_toolsets.py`; tools: never-raise, `TICKER_RE` validation, `isfinite()` guards
- `UsageLimits(request_limit=N+2, tool_calls_limit=N)` budget enforcement
- `DeskResponse` frozen model; `DESK_SUCCESS_CONFIDENCE = 0.7`

### Intent Routing (Agency)
- `classify_intent()` maps queries to `DeskType` + `QueryType` via keyword stem matching
- Single-word: `\b{kw}` (word-start); multi-word: substring match; default: `DeskType.RESEARCH`
- `route_query()`: classify -> select desk -> run agent -> persist -> return `DeskResponse`

### Learning & Weight Tuning
- Indicator weights: P&L correlation adjusts `INDICATOR_WEIGHTS` based on predictive power
- Vote weights: agent prediction accuracy adjusts `AGENT_VOTE_WEIGHTS`
- `tune_indicator_weights()` / `tune_vote_weights()` -- never-raises

### Strategy Mining & Playbook
- Dimensional grouping: sector x IV bucket x DTE bucket x direction
- Significance: chi-squared (p < 0.05), min 20 samples/cell, 100 total outcomes
- Rules: `candidate` -> human approval -> `approved`; `render_learned_patterns()` -> `<<<LEARNED_PATTERNS>>>` block
- All 7 desk agents inject learned patterns via `DeskDeps.learned_patterns` in dynamic system prompts

### Confidence Decay
- Exponential decay on strategy rule confidence over time
- Auto-demote `approved` -> `candidate` when confidence drops below threshold

### Model Routing (Complexity-Based)
- `_assess_complexity()`: scores 0.0-1.0 from MarketContext + TickerScore heuristics
- `route_model_tier()`: Risk desk never FAST, synthesis always PREMIUM
- `build_model_for_tier()`: constructs model per tier via config model name override
- `DeskMetrics`: per-desk timing, model tier/name, token usage
- `AssessmentSummary`: direction votes, avg confidence, disagreement, risk flags
- `RecommendationCost`: aggregated tokens + estimated USD from `cost_per_million_tokens` map
- `RoutingConfig` on `DebateConfig`: opt-in (default False), thresholds, tier model names

### Scan Pipeline
- Thin orchestrator (`pipeline.py`) delegates to 4 phase modules
- Phase 1: universe + sector filtering + auto-index missing tickers (non-fatal)
- Phase 2: indicators + composite scoring + optional ML indicators
- Phase 3: chain fetch + contract selection (liquidity pre-filter first)
- Phase 4: SQLite persistence
- `index_tickers()`: protocol-based DI, semaphore concurrency, shared by CLI and Phase 1

### Web API
- App factory with `lifespan()` -- services created once on `app.state`
- `Depends()` providers in `deps.py` for DI
- Operation mutex: `asyncio.Lock`, one scan/batch at a time (409 if busy)
- Background tasks via `asyncio.create_task()`, counter-based IDs
- WebSocket bridge: sync callback -> `asyncio.Queue` -> WebSocket JSON events
- Loopback-only; catch-all GET serves static files or `index.html` for Vue Router

### ChainProvider (Option Chain Abstraction)
- Protocol: `ChainProvider.fetch_chain()` -- CBOE primary + yfinance fallback
- Three-tier Greeks: CBOE native -> local BAW/BSM -> exclude contract

### Analytics & Backtesting
- Outcome collection at T+1/T+5/T+10/T+20; expired: ITM->intrinsic, OTM->worthless
- 6 typed results + 7 backtesting queries; `AnalyticsMixin` provides all query methods
- `BacktestConfig` for geometric vs arithmetic compounding

### Other Patterns
- **Sector filtering**: `GICSSector` StrEnum + `SECTOR_ALIASES`, `field_validator` normalizes
- **Earnings calendar**: warning in prompts when within 7 days
- **OpenBB enrichment**: guarded imports, config-gated, 11 enrichment fields (enrichment_ratio() removed — was hardcoded 0.0)
- **Metadata index**: `ticker_metadata` SQLite table, 30-day TTL, bulk upsert
- **Liquidity scoring**: spread (70%) + OI depth (30%), inverted normalization, floor guards
- **Heatmap**: `BatchQuote` + chunked download, client-side squarify treemap
- **ML pipeline**: guarded imports for arch/statsmodels, config-gated per feature (GARCH, regime, macro, Hurst)
- **ToolResponse**: frozen model with `ToolStatus` enum, all tool wrappers return it
- **Batch export**: `_recommendation_single()` reusable; `export_recommendation_markdown()` for output
- **FiniteFieldsMixin**: shared `validate_all_finite` model_validator extracted from 9 config classes

## Module Constraints

### models/
- `IndicatorSignals` has named `float | None` fields (4 dead fields removed: vix_term_structure, risk_on_off_score, sector_relative_momentum, vix_correlation)
- `OptionGreeks` must set `pricing_model` and validate delta in [-1,1]
- Decimal fields need `field_serializer` to `str` for JSON precision
- `recommendation.py`: `RecommendationResult` needs `arbitrary_types_allowed=True` for `RunUsage`
- `LLMDecimal = Annotated[Decimal, WithJsonSchema({"type": "string"})]` for agent output types

### agents/
- 7 desk + 6 recommendation + 1 synthesis agent
- No inter-agent imports; orchestrator coordinates
- Toolset builders in `_toolsets.py` with `TICKER_RE` validation

### agents/prompts/
- 7 desk + 6 recommendation + 1 synthesis prompt files
- Recommendation/synthesis: `*_SYSTEM_PROMPT` + `PROMPT_RULES_APPENDIX`; desk: NO appendix
- < 8000 chars per prompt; static only -- dynamic injection in agent modules

### services/
- yfinance camelCase: `dividendYield`, `openInterest`, `impliedVolatility`
- `safe_float()` rejects NaN/Inf; `time.monotonic()` for rate limiting

### pricing/
- BSM: Merton 1973 with dividend yield `q` in every formula
- BAW IV: `brentq` not Newton-Raphson; BAW Greeks: 11 bump-and-reprice evaluations
- Guard `T=0` in denominators; clamp IV to `[1e-6, 5.0]`; use `math.log/sqrt/exp` not numpy

### scoring/
- Zero-bid exemption: `bid=0/ask>0` skips spread check
- Composite: weighted geometric mean, floor 0.5; 27 weights sum to 1.0
- Inverted indicators: bb_width, atr_pct, keltner_width, chain_spread_pct

### indicators/
- Wilder's: `ewm(alpha=1/period, adjust=False)` -- no SMA seed
- Standard EMA (Keltner): MUST seed with SMA of first `period` values
- Bollinger: population std dev `ddof=0`; division-by-zero: `replace(0.0, np.nan)`
- `validate_aligned()` required on all multi-Series functions
- MACD signal is EMA of MACD line, NOT of price

### scan/
- `determine_direction()` needs RAW indicator values, not normalized
- 15 indicators in INDICATOR_REGISTRY; 4 options-specific need chain data (Phase 3)
- Function name != field name: `stoch_rsi`->`stochastic_rsi`, `atr_percent`->`atr_pct`
- Risk-free rate fetched ONCE; services injected, never created by pipeline

### data/
- `await db.commit()` after EVERY write -- aiosqlite does NOT auto-commit
- `db.row_factory = aiosqlite.Row` for named column access
- `executescript()` issues implicit COMMIT; `PRAGMA foreign_keys=ON` required
- `ScanRun` is frozen -- `save_scan_run()` returns `int` ID

### api/
- Services on `app.state`, never per-request
- WebSocket: `queue.put_nowait()` (sync callback), cleanup queues to prevent leaks

### cli/
- Close ALL services in `finally` -- leaked connections = leaked TCP handles
- Progress bars to stderr, result tables to stdout (enables piping)
- Double Ctrl+C: first = graceful, second = force exit (code 130)

### reporting/
- Pure functions, no I/O, no disclaimers

### analysis/
- Pure computation: valuation, correlation, performance, position sizing -- no API calls

### learning/
- `weight_tuner.py`: indicator + vote weight tuning
- `strategy_book.py`: mine_patterns, filter_significant, generate_rules, render_learned_patterns
- Pure computation in, results out; orchestration wrappers handle DB

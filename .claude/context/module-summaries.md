# Module Summaries — Critical Constraints

Condensed from 13 module CLAUDE.md files. Read the full module CLAUDE.md for deep work.

## models/
- `frozen=True` on snapshots: OHLCV, Quote, OptionContract, OptionGreeks
- `IndicatorSignals` has 18 named `float | None` fields — NOT `dict[str, float]`
- `OptionGreeks` must set `pricing_model` (BSM or BAW) and validate delta in [-1,1]
- `dividend_yield: float = 0.0` never None; waterfall fall-through is `is None` not falsy
- Every `confidence` field needs `[0.0, 1.0]` validator; every `datetime` needs UTC validator
- Decimal fields need `field_serializer` to `str` for JSON precision
- `BaseSettings` only on `AppSettings`; sub-configs (`ScanConfig` etc.) are plain `BaseModel`
- `recommendation.py`: `DomainAssessment` base + 6 subclasses, `AnyAssessment` discriminated union (`Discriminator("desk")` + `Tag()`), `PositionRecommendation` (21 fields, Decimal prices), `RecommendationResult` (`arbitrary_types_allowed=True` for `RunUsage`)

## agents/
- **Desk agents** (7): Volatility, Risk, Trend, Flow, Fundamental, Contrarian, Research — `Agent[DeskDeps, str]` for interactive queries
- **Recommendation agents** (6): One per desk (excl. Research) — `Agent[DeskDeps, *Assessment]` producing typed `DomainAssessment` subclasses
- **Synthesis agent** (1): `Agent[SynthesisDeps, PositionRecommendation]` — weighs 6 domain assessments, produces contract recommendation. `run_synthesis()` never-raises with fallback.
- **Recommendation orchestrator**: `run_recommendation()` — primary entry point. Runs 6 desk recommendation agents → synthesis agent → `RecommendationResult`. Never raises.
- **Routing**: `_routing.py` — intent classification (`classify_intent`) + desk dispatch (`route_query`)
- No inter-agent imports — orchestrator coordinates recommendation; desks are independent
- `Agent(model=None)` at init, actual model at `agent.run(model=...)` — enables TestModel
- All desk agents: `@output_validator` using `strip_think_tags()` + post-run defense-in-depth
- Synthesis agent: `@output_validator` strips think tags from `PositionRecommendation` string fields
- `run_recommendation()` / `run_*_desk_query()` / `run_synthesis()` never raise — catch all exceptions
- Desk agents access services via `DeskDeps` (tool-based data fetching, not pre-fetched)
- `asyncio.wait_for(agent.run(...), timeout=config.agent_timeout)` on every agent call
- `_toolsets.py`: per-desk toolset builders + `build_synthesis_toolset()` with `TICKER_RE` validation, `isfinite()` guards, sanitized errors
- **Backward compat**: `DebateResult`, `DebatePhase`, `DebateProgressCallback` retained in `_context.py` for old data parsing. Not in `__all__`.
- **Debate agents deleted**: 6 debate agents, 6 debate prompts, orchestrator.py — all removed in cutover epic

## agents/prompts/
- 7 desk prompt files + 6 recommendation prompt files + 1 synthesis prompt file
- Recommendation + Synthesis: `*_SYSTEM_PROMPT` constant concatenated with `PROMPT_RULES_APPENDIX`
- Desk: `DESK_*_PROMPT` constant, conversational, NO `PROMPT_RULES_APPENDIX`
- < 8000 chars per prompt; static only — dynamic injection stays in agent modules

## services/
- `asyncio.to_thread(fn, *args)` NOT `to_thread(fn())` — latter runs synchronously
- `return_exceptions=True` on ALL `asyncio.gather` in batch operations
- One `httpx.AsyncClient` per service; close via `await client.aclose()` in `close()`
- yfinance field names are camelCase: `dividendYield`, `openInterest`, `impliedVolatility`
- `safe_float()` rejects NaN/Inf; `time.monotonic()` for rate limiting (not `time.time()`)
- FRED never raises — returns fallback rate on any error

## pricing/
- BSM uses Merton 1973 with dividend yield `q` — every formula includes `e^(-qT)` terms
- BAW IV solver: `scipy.optimize.brentq` NOT Newton-Raphson (no analytical vega w.r.t. IV)
- `OptionGreeks` must set `pricing_model=PricingModel.BSM` or `BAW`
- BAW Greeks: centered finite-difference bump-and-reprice (11 BAW evaluations per call)
- Guard `T=0`: `sigma * sqrt(T)` in denominators; clamp IV iterations to `[1e-6, 5.0]`
- Use `math.log/sqrt/exp` for scalars, not numpy

## scoring/
- Import `pricing/dispatch` only — never `pricing/bsm` or `pricing/american` directly
- `IndicatorSignals` typed model, not `dict[str, float]`
- Zero-bid exemption: `bid=0/ask>0` skips spread check in contract filtering
- Composite score uses weighted geometric mean with floor value 0.5 (prevents log(0))
- 27 indicator weights sum to 1.0; inverted indicators: bb_width, atr_pct, keltner_width, chain_spread_pct

## indicators/
- Wilder's smoothing: `ewm(alpha=1/period, adjust=False)` — do NOT SMA-seed
- Standard EMA (Keltner): MUST seed with SMA of first `period` values
- Bollinger Bands: population std dev `ddof=0`, not sample `ddof=1`
- Division-by-zero: `denominator.replace(0.0, np.nan)` before every division
- IV Rank != IV Percentile (range-based vs count-based)
- `validate_aligned()` required on all multi-Series functions
- MACD signal is EMA of MACD line, NOT of price

## scan/
- `determine_direction()` needs RAW indicator values, not normalized (0-100) from TickerScore
- Only 15 indicators in INDICATOR_REGISTRY — 4 options-specific need chain data (Phase 3)
- Function name != field name: `stoch_rsi`->`stochastic_rsi`, `atr_percent`->`atr_pct`
- Risk-free rate: fetched ONCE for entire scan via FredService
- `OptionContract.greeks` is always None from services — populated by `recommend_contracts()`
- Liquidity pre-filter (avg dollar volume, min price) runs BEFORE expensive chain fetches
- Services injected via constructor — pipeline never creates or closes services

## data/
- `await db.commit()` after EVERY write — aiosqlite does NOT auto-commit
- Named column access: `db.row_factory = aiosqlite.Row` then `row["column_name"]`
- `model_dump_json()` / `model_validate_json()` for IndicatorSignals serialization
- `executescript()` issues implicit COMMIT before running (sqlite3 behavior)
- `PRAGMA foreign_keys=ON` required — SQLite defaults to OFF
- `ScanRun` is frozen — `save_scan_run()` returns `int` ID, don't mutate the model
- `LearningMixin`: strategy rule + agent memory CRUD (save/get/update rules, save/get memories)

## api/
- Services created in `lifespan()`, stored on `app.state` — never per-request
- FastAPI auto-serializes Pydantic models — no manual `model_dump()` in routes
- Operation mutex: `asyncio.Lock` — one scan or batch debate at a time (409 if busy)
- WebSocket bridge: `queue.put_nowait()` (sync callback), never `await queue.put()`
- Bind to `127.0.0.1` only — exposing to network is a security issue
- Clean up WebSocket queues on completion/disconnect to prevent memory leaks

## cli/
- Sync Typer commands + `asyncio.run()` — never `async def` on Typer commands
- `RichHandler(markup=False)` — `[TICKER]` brackets crash Rich markup parser
- `signal.signal()` for SIGINT — `loop.add_signal_handler()` unsupported on Windows
- Close ALL services in `finally` block — leaked connections = leaked TCP handles
- Progress bars to stderr, result tables to stdout (enables piping)
- Double Ctrl+C pattern: first = graceful cancel, second = force exit (code 130)

## reporting/
- No disclaimers (removed AUDIT-010)
- Pure functions — no I/O; all input/output via typed Pydantic models

## analysis/
- No API calls — data comes from caller
- Pure computation: valuation, correlation, performance, position sizing

## learning/
- Middle-stack: accesses `models/`, `data/`, `scoring/` — never `services/`, `agents/`, `cli/`, `api/`, `pricing/`
- Never-raises contract on all orchestration functions
- `weight_tuner.py`: indicator weight tuning (P&L correlation) + vote weight tuning (agent accuracy)
- `strategy_book.py`: pattern mining (mine_patterns, filter_significant, generate_rules, render_learned_patterns, run_strategy_mining)
- Pure computation functions take data in, return results out; orchestration wrappers handle DB
- Returns Pydantic models or typed aliases, never raw dicts
- `render_learned_patterns()` produces `<<<LEARNED_PATTERNS>>>` block for desk prompt injection

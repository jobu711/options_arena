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
- **`math.isfinite()` at model boundaries**: Every Pydantic validator on numeric fields that use
  `v < 0` or range checks must ALSO check `math.isfinite(v)` first, because NaN comparisons
  always return False (NaN silently passes `v >= 0`).
- **`math.isfinite()` at computation entry**: Pricing and scoring functions guard non-finite inputs
  at entry before any arithmetic.
- **NaN for undefined ratios**: Division-by-zero returns `float("nan")` (not `0.0`) when
  mathematically undefined.
- **Display guards**: CLI rendering checks `math.isfinite()` before formatting, falls back to `"--"`.

### Service Layer Patterns
- **Class-based DI**: Each service receives `config`, `cache`, `limiter` via `__init__`. Explicit `close()`.
- **Cache-first**: check cache → fetch if miss → store → return
- **Shared httpx client**: one `AsyncClient` per service instance, closed via `await client.aclose()`
- **Retry with backoff**: `fetch_with_retry()` accepts zero-arg async factory, exponential backoff (1s→16s)
- **yfinance wrapping**: `_yf_call(fn, *args)` — `asyncio.to_thread(fn, *args)` + `wait_for(timeout)`. CRITICAL: pass callable + args separately, NOT `to_thread(fn())`.
- **Two-tier caching**: in-memory LRU + SQLite WAL. Market-hours-aware TTL via `zoneinfo.ZoneInfo("America/New_York")`.
- **Rate limiting**: Token bucket (`time.monotonic()`, NOT `time.time()`) + `asyncio.Semaphore`.
- **Batch isolation**: `asyncio.gather(*tasks, return_exceptions=True)` — one failed ticker never crashes batch.
- **FRED never raises**: always returns float, falls back to `PricingConfig.risk_free_rate_fallback`.

### PydanticAI Agent Pattern
- Module-level `Agent[Deps, OutputType]` instances (bull, bear, risk, volatility) — no classes
- `model=None` at init, actual model passed at `agent.run(model=...)` time (enables `TestModel`)
- `@dataclass` deps (`DebateDeps`), `output_type=PydanticModel` for structured JSON output
- `retries=2`, `model_settings=ModelSettings(extra_body={"num_ctx": 8192})` for Ollama
- `@agent.output_validator` delegates to shared helpers: `build_cleaned_agent_response()` (bull/bear) and `build_cleaned_trade_thesis()` (risk) — strips `<think>` tags without costly retries
- **Shared prompt appendix**: `PROMPT_RULES_APPENDIX` (confidence calibration, data anchors, citation rules) appended to bull/bear/risk prompts. Volatility uses its own prompt contract. `RISK_STRATEGY_TREE` appended to risk only.
- **Multi-provider**: `DebateProvider` enum (`OLLAMA`, `GROQ`), `build_debate_model()` match/case dispatch
- **Provider-aware timeouts**: Ollama `agent_timeout` (600s), Groq `groq_timeout` (60s)
- Sequential execution: Bull → Bear → Volatility (optional, config-gated) → Risk
- Orchestrator never raises: catches errors → data-driven fallback (confidence=0.3)

### Debate Orchestration Flow
```
1. build_market_context() → MarketContext
2. build_debate_model(config) → OllamaModel or GroqModel
3. Bull → Bear (receives bull argument) → Volatility (optional) → Risk (receives all) → TradeThesis
4. Accumulate RunUsage, persist to ai_theses table
On any error: data-driven fallback (is_fallback=True, confidence=0.3)
```

### Scan Pipeline Data Flow
```
Phase 1: Universe (~5,286 CBOE tickers) → OHLCV fetch
Phase 2: Indicators → normalize → score → direction
Phase 3: Liquidity pre-filter → Top 50 → option chains → recommend contracts
Phase 4: Persist to SQLite
```

For detailed algorithm specs, see `system-patterns-reference.md`.

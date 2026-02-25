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

### Batch Debate Pattern
- `_debate_single()` extracted from `_debate_async()` — reusable for single and batch
- `_batch_async()` loads top N scores from latest scan, creates services once, iterates sequentially
- Error isolation: per-ticker try/except, failures logged and included in summary table
- `render_batch_summary_table()` renders compact Rich Table at the end

### Debate Export Pattern
- `reporting/debate_export.py` generates markdown from `DebateResult`
- PDF via optional `weasyprint` dependency (graceful `ImportError` if missing)
- `--export md|pdf` and `--export-dir` flags on debate command
- Export happens after rendering, before disclaimer

### Scan Pipeline Data Flow
```
Phase 1: Universe (~5,286 CBOE tickers) → OHLCV fetch
Phase 2: Indicators → normalize → score → direction
Phase 3: Liquidity pre-filter → Top 50 → option chains → recommend contracts
Phase 4: Persist to SQLite
```

For detailed algorithm specs, see `system-patterns-reference.md`.

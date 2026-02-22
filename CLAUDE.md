# CLAUDE.md — Options Analysis Tool

@.claude/context/tech-context.md
@.claude/context/progress.md
@.claude/context/system-patterns.md

## What This Project Does
AI-powered options analysis tool for American Style options fo U.S Equities . Three AI agents (Bull, Bear, Risk) debate via Ollama
local models (Llama 3.1 8B) on options contracts. The tool fetches market data, computes
technical indicators, runs a structured single-pass debate, and produces a verdict with
risk assessment. Data-driven fallback when Ollama is unreachable.

## Tech Stack
- **Python 3.13+** — use modern syntax: `match`, `type X = ...`, `X | None` unions, `StrEnum`
- **Package manager**: `uv` — always `uv add <pkg>`, never `pip install` or manual pyproject.toml edits
- **Linter/Formatter**: `ruff` — runs on save, don't fight it
- **Type checker**: `mypy --strict` — full annotations on every function, no exceptions
- **Async**: `asyncio` + `httpx` — the debate loop and data fetching are async
- **Models**: Pydantic v2 — all structured data crosses module boundaries as typed models, never raw dicts
- **AI SDK**: `pydantic-ai` + `OllamaProvider` (local Llama 3.1 8B via OpenAI-compat endpoint). See `agents/CLAUDE.md`
- **Data**: `pandas` + `numpy` for indicators, `yfinance` wrapped in services — see `services/CLAUDE.md`

## Project Layout
```
src/Option_Alpha/
    __init__.py
    cli.py              # Entry point (not yet implemented)
    agents/             # AI debate agents (Ollama)            → has own CLAUDE.md
      prompts/          # Prompt templates & versioning        → has own CLAUDE.md
    indicators/         # Technical indicator math              → has own CLAUDE.md
    models/             # Pydantic models, enums, schemas      → has own CLAUDE.md ✅
      enums.py          #   OptionType, PositionSide, SignalDirection, GreeksSource, SpreadType
      market_data.py    #   OHLCV, Quote, TickerInfo
      options.py        #   OptionGreeks, OptionContract, SpreadLeg, OptionSpread
      analysis.py       #   MarketContext, AgentResponse, TradeThesis
      scan.py           #   ScanRun, TickerScore
      health.py         #   HealthStatus
    services/           # Data fetching, caching, rate limits  → has own CLAUDE.md
    analysis/           # Fundamental analysis, scoring, signals
    reporting/          # Report generation & disclaimers      → has own CLAUDE.md
    utils/              # Validators, formatters, helpers ✅
      exceptions.py     #   DataFetchError hierarchy
tests/                  # Unit + integration tests             → has own CLAUDE.md ✅
  unit/models/          #   154 tests for all models, enums, exceptions
data/                   # Cached data (SQLite, CSV)
reports/                # Generated output (gitignored)
```
## Module-Level Instructions — MANDATORY
Before creating, editing, or reviewing ANY file in a module below, you MUST first read
that module's CLAUDE.md. These contain rules that override or extend the root instructions.

A task touching files in `agents/prompts/` requires reading BOTH `agents/CLAUDE.md` AND
`agents/prompts/CLAUDE.md` — child rules inherit from parent.

Do NOT write or modify code in any of these modules until you have read the corresponding
CLAUDE.md in the current conversation. If you have not read it yet, read it now before proceeding.

## Options Domain Knowledge

### Key Concepts Claude Must Understand
- An **option contract** has: ticker, type (call/put), strike price, expiration date, bid, ask, volume, open interest, implied volatility, and Greeks (delta, gamma, theta, vega, rho).
- **Greeks** are sensitivity measures: delta (price), gamma (delta acceleration), theta (time decay), vega (volatility), rho (interest rates).
- **IV Rank** ≠ **IV Percentile**. Rank = where current IV sits in its 52-week range. Percentile = % of days IV was lower. Never confuse them.
- **DTE** (days to expiration) drives everything — theta decay accelerates as DTE shrinks.
- Options have **bid-ask spreads** that indicate liquidity. Wide spread = illiquid = dangerous.
- The **mid price** `(bid + ask) / 2` is a better fair value estimate than `last` which can be stale.

### Financial Precision Rules
- Prices, P&L, cost basis: `Decimal` (constructed from strings: `Decimal("1.05")`).
- Greeks, IV, indicators, ratios: `float` (speed over precision).
- Volume, open interest: `int` (always whole numbers).
- Dates: `datetime.date` for expiration, `datetime.datetime` with `UTC` for timestamps. Never strings.

## Code Patterns — Project-Wide

### NO RAW DICTS — Typed Models Everywhere
This is the most commonly violated rule. **Every function that returns structured data
MUST return a Pydantic model, a dataclass, or a StrEnum — NEVER a `dict`, `dict[str, Any]`,
`dict[str, float]`, or any `dict` variant.**

Violations Claude keeps making:
```python
# WRONG — returning a raw dict
def get_greeks(contract: OptionContract) -> dict[str, float]:
    return {"delta": 0.45, "gamma": 0.03}

# RIGHT — return a typed model
def get_greeks(contract: OptionContract) -> OptionGreeks:
    return OptionGreeks(delta=0.45, gamma=0.03, theta=-0.08, vega=0.15, rho=0.02)

# WRONG — dict as a function parameter for structured data
def analyze(data: dict[str, Any]) -> AnalysisReport: ...

# RIGHT — typed model as parameter
def analyze(context: MarketContext) -> AnalysisReport: ...

# WRONG — dict field on a Pydantic model
class DebateArgument(BaseModel):
    greeks_cited: dict[str, float]   # NO — this is a raw dict

# RIGHT — typed model or constrained structure
class GreeksCited(BaseModel):
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    rho: float | None = None
```

This applies to: function returns, function parameters, model fields, intermediate variables
passed between modules, and API response parsing. The ONLY exception is `indicators/` which
uses pandas Series/DataFrames (not dicts) as its data interchange format.

### Architecture Boundaries
- `services/` is the ONLY layer that touches external APIs or data sources.
- `indicators/` takes pandas Series/DataFrames in, returns pandas Series/DataFrames out. No API calls, no models.
- `agents/` orchestrates the debate loop. Agents have no knowledge of each other.
- `models/` defines data shapes. No business logic, no I/O.
- `analysis/` and `reporting/` consume models — they never fetch data directly.

### Error Handling
- Custom domain exceptions: `TickerNotFoundError`, `InsufficientDataError`, `DataSourceUnavailableError`, `RateLimitExceededError`.
- Never bare `except:` — always catch specific types.
- `logging` module only — never `print()` in library code. `print()` is reserved for `cli.py`.
- Fail fast at boundaries (CLI args, API responses). Don't validate deep inside calculations.

### Naming
- Variables: `implied_vol_30d`, `daily_prices_df`, `atm_call` — descriptive, no abbreviations.
- Constants: `RSI_OVERBOUGHT = 70`, `DEFAULT_DEBATE_ROUNDS = 3` — uppercase, defined once.
- DataFrames: `daily_prices_df`, `option_chain_df` — always suffixed `_df`.
- No magic numbers anywhere.

### Async Convention
- The debate orchestrator, data fetching, and agent calls are all `async`.
- Pick ONE client type per module — don't mix sync/async.
- Use `asyncio.wait_for(coro, timeout=N)` on every external call. No unbounded waits.
- Use `asyncio.gather(*tasks, return_exceptions=True)` for batch operations — don't let one failure crash the batch.

## Verification — Run Before Every Commit
```bash
uv run ruff check . --fix && uv run ruff format .   # lint + format
uv run pytest tests/ -v                              # all tests
uv run mypy src/ --strict                            # type checking
```
Always run all three via `uv run`. A task is not done until all pass.

## Context7 Verification — Mandatory for External Library Interfaces

Before writing or modifying code that depends on the shape of data returned by an external
library (yfinance, pandas, scipy, httpx, etc.), you MUST use Context7 (`resolve-library-id`
then `query-docs`) to verify the actual field names, column names, return types, and method
signatures. Do NOT rely on training data assumptions — libraries change between versions.

### When to verify
- **Writing a new service method** that parses library output (e.g., yfinance `option_chain()`,
  `Ticker.info`, `Ticker.get_dividends()`).
- **Adding or modifying a Pydantic model** whose fields map to external library data shapes
  (e.g., `OptionContract` fields matching yfinance chain columns).
- **Using `pd.read_html()`**, `pd.read_csv()`, or any parser where column names come from
  an external source (e.g., Wikipedia table headers).
- **Calling a library function** with parameters you haven't used before in this project.

### What to verify
- **Field/column names**: exact spelling, casing (e.g., yfinance uses camelCase in `.info`).
- **Return types**: what the function actually returns (DataFrame, dict, Series, namedtuple).
- **Parameter signatures**: required vs optional args, default values, valid options.
- **Data shapes**: which fields can be `None`, which are always present, value ranges.

### How to verify
```
1. resolve-library-id  — get the Context7 library ID
2. query-docs          — ask the specific question about the data shape
3. Document findings   — update the relevant PRD requirement or system-patterns.md
                         with "(Context7-verified)" annotation
```

### Examples of assumptions that were wrong before verification
- "yfinance option chains include Greeks (delta, gamma, theta, vega)" — **FALSE**,
  chains only include `impliedVolatility`. All Greeks must be computed locally.
- "Wikipedia S&P 500 table can be fetched with `pd.read_html(url)[0]`" — **FRAGILE**,
  the table has `id="constituents"` and should be targeted with `attrs={"id": "constituents"}`.

Do NOT commit code that maps external library output to typed models without Context7
verification in the current conversation. If Context7 is unavailable, note the assumption
as **unverified** in a code comment and in the relevant PRD section.

## Current Status
- **Phase 1 MVP**:


## Git Discipline
- Atomic commits: `feat: add Bollinger Bands with configurable std dev`, not `update stuff`.
- Branch per feature. Never commit directly to main.
- Every commit message starts with: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, or `chore:`.

## What Claude Gets Wrong — Global (Fix These)
- Don't create god-class `OptionAlpha` objects — split into focused modules per the architecture above.
- Don't return raw dicts from any function — always typed models. This includes `dict[str, float]`, `dict[str, Any]`, etc. See "NO RAW DICTS" section above.
- Don't use `print()` outside `cli.py` — use `logging`.
- Don't ignore `SettingWithCopyWarning` from pandas — fix with `.copy()`.
- Don't skip the disclaimer on any user-facing output — import from `reporting/disclaimer.py`.
- Don't mix sync and async in the same module — pick one.
- Don't call APIs directly from analysis/indicator code — go through `services/`.
- Don't use `Optional[X]` — use `X | None`.
- Don't use `typing.List`, `typing.Dict` — use `list`, `dict` lowercase.
- Don't forget to read the sub-level CLAUDE.md before working in any module.


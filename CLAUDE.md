# CLAUDE.md — Options Arena

@.claude/context/tech-context.md
@.claude/context/progress.md
@.claude/context/system-patterns.md

## What This Project Does

AI-powered options analysis tool for American-style options on U.S. equities. Three AI
agents (Bull, Bear, Risk) debate via Ollama local models (Llama 3.1 8B) on options
contracts. The tool fetches market data, computes technical indicators, runs a structured
single-pass debate, and produces a verdict with risk assessment. Data-driven fallback
when Ollama is unreachable.

## Tech Stack

- **Python 3.13+** — use modern syntax: `match`, `type X = ...`, `X | None` unions, `StrEnum`
- **Package manager**: `uv` — always `uv add <pkg>`, never `pip install` or manual pyproject.toml edits
- **Linter/Formatter**: `ruff` (target `py313`, line-length 99, rules: E, F, I, UP, B, SIM, ANN)
- **Type checker**: `mypy --strict` — full annotations on every function, no exceptions
- **Async**: `asyncio` + `httpx` — debate loop, data fetching, and scan pipeline are async
- **Models**: Pydantic v2 — all structured data crosses module boundaries as typed models, never raw dicts
- **Config**: `pydantic-settings` v2 — single `AppSettings(BaseSettings)` root, nested `BaseModel` submodels
- **AI SDK**: `pydantic-ai` + Ollama (local Llama 3.1 8B). See `agents/CLAUDE.md`
- **Pricing**: `scipy` — BSM (Merton 1973) + BAW (Barone-Adesi-Whaley 1987) for American options
- **CLI**: `typer` + `rich` — subcommands, Rich tables, progress bars, colored terminal output
- **Data**: `pandas` + `numpy` for indicators, `yfinance` wrapped in services, `aiosqlite` for persistence

## Project Layout

```
src/options_arena/
    __init__.py
    cli/                # Typer CLI entry point (Phase 8)         → has own CLAUDE.md
      __init__.py       #   Re-exports `app` for pyproject.toml entry point
      app.py            #   Typer app, @app.callback(), configure_logging()
      commands.py       #   scan, health, universe commands
      rendering.py      #   render_scan_table(), render_health_table(), disclaimer
      progress.py       #   RichProgressCallback (ProgressCallback protocol)
    agents/             # PydanticAI debate agents (Ollama)       → has own CLAUDE.md
      prompts/          #   Prompt templates & versioning         → has own CLAUDE.md
    models/             # Pydantic models, enums, config          → has own CLAUDE.md
      enums.py          #   11 StrEnums: OptionType, ExerciseStyle, SignalDirection, etc.
      market_data.py    #   OHLCV, Quote, TickerInfo
      options.py        #   OptionGreeks, OptionContract, SpreadLeg, OptionSpread
      analysis.py       #   MarketContext, AgentResponse, TradeThesis
      scan.py           #   ScanRun, TickerScore, IndicatorSignals
      health.py         #   HealthStatus, CheckResult
      config.py         #   AppSettings, ScanConfig, PricingConfig, ServiceConfig
    pricing/            # BSM + BAW option pricing & Greeks       → has own CLAUDE.md
      bsm.py            #   Merton 1973 European BSM (analytical Greeks, Newton-Raphson IV)
      american.py       #   BAW 1987 American approximation (finite-diff Greeks, brentq IV)
      dispatch.py       #   ExerciseStyle routing: AMERICAN→BAW, EUROPEAN→BSM
      _common.py        #   Shared validation, intrinsic value, boundary Greeks
    indicators/         # Technical indicator math (18 functions) → has own CLAUDE.md
      trend.py          #   ADX, Aroon, SuperTrend
      oscillators.py    #   RSI, MACD, Stochastic, CCI
      volatility.py     #   Bollinger Bands, Keltner Channels, ATR
      volume.py         #   OBV, VWAP, relative volume
      moving_averages.py#   SMA, EMA, DEMA
      options_specific.py#  Options-specific indicators
    scoring/            # Normalization, composite, contracts     → has own CLAUDE.md
      normalization.py  #   Percentile-rank normalize, inversion, active indicators
      composite.py      #   Weighted geometric mean (18 indicators, 6 categories)
      direction.py      #   ADX/RSI/SMA signal aggregation → SignalDirection
      contracts.py      #   Contract selection: Greeks via dispatch, delta targeting
    services/           # External API access, caching, rate limiting → has own CLAUDE.md
      market_data.py    #   MarketDataService: OHLCV, quotes, ticker info, dividend waterfall
      options_data.py   #   OptionsDataService: chains, column mapping, liquidity filter
      fred.py           #   FredService: FRED API risk-free rate (never raises)
      universe.py       #   UniverseService: CBOE tickers, Wikipedia S&P 500
      health.py         #   HealthService: pre-flight checks, latency measurement
      cache.py          #   Two-tier: in-memory LRU + SQLite WAL, market-hours TTL
      rate_limiter.py   #   Token bucket + asyncio.Semaphore
      helpers.py        #   fetch_with_retry(), safe_decimal/int/float (internal only)
    scan/               # 4-phase pipeline orchestration           → has own CLAUDE.md
      pipeline.py       #   ScanPipeline: universe → scoring → options → persist
      indicators.py     #   IndicatorSpec registry (14 entries), ohlcv_to_dataframe()
      models.py         #   Pipeline-internal: UniverseResult, ScoringResult, OptionsResult, ScanResult
      progress.py       #   ScanPhase enum, CancellationToken, ProgressCallback protocol
    data/               # SQLite persistence (WAL, migrations)    → has own CLAUDE.md
      database.py       #   Database: connect/close, WAL, FK, migration runner
      repository.py     #   Repository: typed CRUD for ScanRun/TickerScore
    analysis/           # Future: enhanced scoring, signals       → has own CLAUDE.md
    reporting/          # Future: report generation & disclaimers → has own CLAUDE.md
    utils/
      exceptions.py     #   DataFetchError hierarchy
data/
    migrations/         # Sequential SQL migration files
      001_initial.sql   #   6 tables: scan_runs, ticker_scores, service_cache, etc.
tests/                  # 1,061 tests                             → has own CLAUDE.md
  unit/
    models/             #   220 tests — all models, enums, exceptions, config
    pricing/            #   214 tests — BSM, BAW, dispatch, IV solvers, edge cases
    indicators/         #   172 tests — all 18 indicators, warmup, edge cases
    scoring/            #   102 tests — normalization, composite, direction, contracts
    services/           #   163 tests — all 7 services, caching, rate limiting
    data/               #    34 tests — database, repository, migrations
    scan/               #   131 tests — pipeline phases, indicators, progress
  integration/
    scan/               #    25 tests — end-to-end pipeline verification
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
- **American vs European exercise**: American options can be exercised any time before expiry (all U.S. equity options). European only at expiry. This project uses BAW for American, BSM for European.
- **yfinance option chains provide NO Greeks** — only `impliedVolatility`. All Greeks are computed locally via `pricing/dispatch.py`. This is the single most common assumption error.

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

```python
# WRONG — raw dict
def get_greeks(contract: OptionContract) -> dict[str, float]: ...

# RIGHT — typed model
def get_greeks(contract: OptionContract) -> OptionGreeks: ...

# WRONG — dict field on a model
class DebateArgument(BaseModel):
    greeks_cited: dict[str, float]

# RIGHT — typed model field
class DebateArgument(BaseModel):
    greeks_cited: OptionGreeks
```

This applies to: function returns, function parameters, model fields, intermediate variables
passed between modules, and API response parsing. The ONLY exception is `indicators/` which
uses pandas Series/DataFrames (not dicts) as its data interchange format.

### Architecture Boundaries

| Module | Responsibility | Can Access | Cannot Access |
|--------|---------------|------------|---------------|
| `models/` | Data shapes + config only | Nothing | APIs, logic, I/O |
| `services/` | External API access | `models/` | Business logic |
| `indicators/` | Pure math (pandas in/out) | pandas, numpy | APIs, models, I/O |
| `pricing/` | BSM + BAW pricing, Greeks, IV | `models/`, `scipy` | APIs, pandas, services |
| `scoring/` | Normalization, composite, direction, contracts | `models/`, `pricing/dispatch` | APIs, services, `pricing/bsm` or `pricing/american` directly |
| `data/` | SQLite persistence | `models/` | APIs, business logic |
| `scan/` | Pipeline orchestration (4 async phases) | `models/`, `services/`, `scoring/`, `indicators/`, `data/` | `pricing/` directly, `httpx`, `yfinance`, `print()` |
| `utils/` | Exception hierarchy | Nothing | APIs, logic, I/O |
| `agents/` | PydanticAI debate orchestration | `models/`, `services/`, `pydantic_ai` | Other agents, indicators |
| `analysis/` | Future: enhanced scoring, signals | `models/`, `services/` output, `pricing/` | APIs directly |
| `reporting/` | Future: output generation | `models/` | APIs, data fetching |
| `cli/` | Terminal interface (top of stack) | Everything | N/A |

**Key boundary rules**:
- `services/` is the ONLY layer that touches external APIs or data sources.
- `indicators/` takes pandas in, returns pandas out. No API calls, no Pydantic models.
- `scoring/` imports from `pricing/dispatch` only — never `pricing/bsm` or `pricing/american`.
- `scan/` orchestrates but never calls `pricing/` directly (that's `scoring/contracts.py`'s job).
- `agents/` have no knowledge of each other. The orchestrator coordinates them.
- `models/` defines data shapes. No business logic, no I/O.

### Pydantic Model Patterns (Context7-verified)

```python
from pydantic import BaseModel, ConfigDict, field_validator

# Immutable snapshot model
class Quote(BaseModel):
    model_config = ConfigDict(frozen=True)
    # fields...

# UTC datetime enforcement (required on EVERY datetime field)
@field_validator("timestamp")
@classmethod
def _validate_utc(cls, v: datetime) -> datetime:
    if v.tzinfo is None or v.utcoffset() != timedelta(0):
        raise ValueError("must be UTC")
    return v

# Confidence bounds (required on EVERY confidence field)
@field_validator("confidence")
@classmethod
def _validate_confidence(cls, v: float) -> float:
    if not 0.0 <= v <= 1.0:
        raise ValueError("must be between 0.0 and 1.0")
    return v
```

### Configuration Pattern (Context7-verified: pydantic-settings v2)

```python
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

# Nested submodels are BaseModel, NOT BaseSettings
class ScanConfig(BaseModel):
    top_n: int = 50
    min_score: float = 0.0

class PricingConfig(BaseModel):
    risk_free_rate_fallback: float = 0.05

# Single BaseSettings root — the ONLY BaseSettings subclass in the project
class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ARENA_",
        env_nested_delimiter="__",     # ARENA_SCAN__TOP_N=30 → settings.scan.top_n
    )
    scan: ScanConfig = ScanConfig()
    pricing: PricingConfig = PricingConfig()
```

**DI pattern**: `cli/` creates `AppSettings()`, passes `settings.scan` to scan pipeline,
`settings.pricing` to pricing module. Modules accept their config slice, not the full
`AppSettings`. `AppSettings()` with no args is a valid production config.

### CLI Patterns (Context7-verified: Typer + Rich)

```python
import asyncio
import typer

app = typer.Typer()

# Typer does NOT support async commands reliably — always use asyncio.run()
@app.command()
def scan(preset: ScanPreset = ScanPreset.SP500) -> None:
    """Run the scan pipeline."""
    asyncio.run(_scan_async(preset))

# Global callback runs BEFORE any command — configure logging here
@app.callback()
def main(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    """Options Arena — AI-powered American-style options analysis."""
    configure_logging(verbose=verbose)
```

**Rich logging — critical gotcha** (Context7-verified):
```python
from rich.logging import RichHandler
from rich.console import Console

# MUST use markup=False — library logs contain [AAPL] brackets that
# Rich would interpret as style tags, causing crashes
handler = RichHandler(
    markup=False,          # Prevents [ticker] bracket crashes
    show_path=False,       # Module paths clutter terminal
    console=Console(stderr=True),  # Separates logging from data output
)
```

**SIGINT handler**: Use `signal.signal()`, NOT `loop.add_signal_handler()` which is
unsupported on Windows. Double-press pattern: first Ctrl+C sets `CancellationToken`,
second raises `SystemExit(130)`.

### Error Handling

- Custom domain exceptions: `TickerNotFoundError`, `InsufficientDataError`, `DataSourceUnavailableError`, `RateLimitExceededError`.
- Never bare `except:` — always catch specific types.
- `logging` module only — never `print()` in library code. `print()` is reserved for `cli/`.
- Fail fast at boundaries (CLI args, API responses). Don't validate deep inside calculations.

### Naming

- Variables: `implied_vol_30d`, `daily_prices_df`, `atm_call` — descriptive, no abbreviations.
- Constants: `RSI_OVERBOUGHT = 70`, `DEFAULT_DEBATE_ROUNDS = 3` — uppercase, defined once.
- DataFrames: `daily_prices_df`, `option_chain_df` — always suffixed `_df`.
- No magic numbers anywhere.

### Async Convention

- The scan pipeline, data fetching, and agent calls are all `async`.
- Pick ONE client type per module — don't mix sync/async.
- Use `asyncio.wait_for(coro, timeout=N)` on every external call. No unbounded waits.
- Use `asyncio.gather(*tasks, return_exceptions=True)` for batch operations — don't let one failure crash the batch.
- Typer commands are sync wrappers: `def scan() -> None: asyncio.run(_scan_async())`.

## Verification — Run Before Every Commit

```bash
uv run ruff check . --fix && uv run ruff format .   # lint + format
uv run pytest tests/ -v                              # all tests (1,061)
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
- **Setting up Typer commands, Rich handlers, or pydantic-settings config** — verify parameter
  names, enum support, and async compatibility.

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

### Assumptions that were wrong before Context7 verification

- "yfinance option chains include Greeks (delta, gamma, theta, vega)" — **FALSE**.
  Chains only include `impliedVolatility`. All Greeks computed locally via `pricing/dispatch.py`.
- "Wikipedia S&P 500 table can be fetched with `pd.read_html(url)[0]`" — **FRAGILE**.
  Target with `attrs={"id": "constituents"}`.
- "Typer supports async command functions" — **UNRELIABLE**.
  Always use sync def + `asyncio.run()`.
- "RichHandler handles all log messages safely" — **FALSE**.
  `markup=False` required to prevent `[ticker]` bracket crashes.
- "pydantic-settings nested delimiter just works" — **PARTIALLY**.
  `env_nested_delimiter="__"` can mismatch on fields with underscores; may need
  `env_nested_max_split` for complex nesting.

Do NOT commit code that maps external library output to typed models without Context7
verification in the current conversation. If Context7 is unavailable, note the assumption
as **unverified** in a code comment and in the relevant PRD section.

## Current Status

- **Phases 1–7**: Complete (models, pricing, indicators, scoring, services, data, scan pipeline)
- **Phase 8 (CLI)**: Next — Typer commands, Rich rendering, SIGINT, logging. Epic: `.claude/epics/phase-8-cli/epic.md`
- **Tests**: 1,061 (all passing on `master`)
- **GitHub**: 0 open issues, 53 closed
- **Scan pipeline**: Producing 8 recommendations per run (verified)

## Git Discipline

- Atomic commits: `feat: add Bollinger Bands with configurable std dev`, not `update stuff`.
- Branch per feature. Never commit directly to main.
- Every commit message starts with: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, or `chore:`.

## What Claude Gets Wrong — Fix These

### Type System Violations
- Don't return raw dicts from any function — always typed models. This includes `dict[str, float]`, `dict[str, Any]`, etc.
- Don't use `Optional[X]` — use `X | None`.
- Don't use `typing.List`, `typing.Dict` — use `list`, `dict` lowercase.
- Don't use raw `str` for categorical fields — always use a `StrEnum` from `enums.py`.
- Don't leave `float` fields unbounded when domain constraints exist — `market_iv >= 0`, `quantity >= 1`, non-empty `legs` lists, etc. Validate at the model boundary.

### Pydantic Validation Mistakes
- Don't add `datetime` fields without a UTC validator — every `datetime` field on a Pydantic model must have a `field_validator` that rejects naive datetimes (`tzinfo is None`) AND non-UTC timezones (`utcoffset() != timedelta(0)`).
- Don't forget `field_validator` on `confidence` fields — any float representing confidence/probability must be constrained to `[0.0, 1.0]` on every model that has it.
- Don't check only `tzinfo is not None` for datetime validation — that allows EST, PST, etc. The correct check is: reject if `v.tzinfo is None or v.utcoffset() != timedelta(0)`.

### Architecture Violations
- Don't create god-class `OptionAlpha` objects — split into focused modules per the boundaries above.
- Don't call APIs directly from analysis/indicator/scoring code — go through `services/`.
- Don't mix sync and async in the same module — pick one.
- Don't import `pricing/bsm` or `pricing/american` from `scoring/` — use `pricing/dispatch` only.
- Don't use `print()` outside `cli/` — use `logging.getLogger(__name__)`.

### Common Oversights
- Don't ignore `SettingWithCopyWarning` from pandas — fix with `.copy()`.
- Don't skip the disclaimer on any user-facing output.
- Don't forget to read the sub-level CLAUDE.md before working in any module.
- Don't assume yfinance provides Greeks — it only provides `impliedVolatility`. All Greeks come from `pricing/dispatch.py`.
- Don't use `loop.add_signal_handler()` — it doesn't work on Windows. Use `signal.signal()`.
- Don't use `async def` on Typer commands — use sync def + `asyncio.run()`.
- Don't use `RichHandler(markup=True)` — library logs contain `[TICKER]` brackets that crash Rich's markup parser. Always `markup=False`.

# CLAUDE.md — Options Arena

@.claude/context/tech-context.md
@.claude/context/progress.md
@.claude/context/system-patterns.md

## What This Project Does

AI-powered options analysis tool for American-style options on U.S. equities. Three AI
agents (Bull, Bear, Risk) debate via Groq cloud API (Llama 3.3 70B) on options
contracts. The tool fetches market data, computes technical indicators, runs a structured
single-pass debate, and produces a verdict with risk assessment. Data-driven fallback
when the LLM provider is unreachable.

## Tech Stack

- **Python 3.13+** — use modern syntax: `match`, `type X = ...`, `X | None` unions, `StrEnum`
- **Package manager**: `uv` — always `uv add <pkg>`, never `pip install` or manual pyproject.toml edits
- **Linter/Formatter**: `ruff` (target `py313`, line-length 99, rules: E, F, I, UP, B, SIM, ANN)
- **Type checker**: `mypy --strict` — full annotations on every function, no exceptions
- **Async**: `asyncio` + `httpx` — debate loop, data fetching, and scan pipeline are async
- **Models**: Pydantic v2 — all structured data crosses module boundaries as typed models, never raw dicts
- **Config**: `pydantic-settings` v2 — single `AppSettings(BaseSettings)` root, nested `BaseModel` submodels
- **AI SDK**: `pydantic-ai` + Groq (cloud Llama 3.3 70B). See `agents/CLAUDE.md`
- **Pricing**: `scipy` — BSM (Merton 1973) + BAW (Barone-Adesi-Whaley 1987) for American options
- **CLI**: `typer` + `rich` — subcommands, Rich tables, progress bars, colored terminal output
- **Data**: `pandas` + `numpy` for indicators, `yfinance` wrapped in services, `aiosqlite` for persistence

## Project Layout

```
src/options_arena/
    cli/          # Typer CLI entry point                    → has own CLAUDE.md
    agents/       # PydanticAI debate agents (Groq)           → has own CLAUDE.md
      prompts/    #   Prompt templates & versioning          → has own CLAUDE.md
    models/       # Pydantic models, enums, config           → has own CLAUDE.md
    pricing/      # BSM + BAW option pricing & Greeks        → has own CLAUDE.md
    indicators/   # Technical indicator math (18 functions)  → has own CLAUDE.md
    scoring/      # Normalization, composite, contracts      → has own CLAUDE.md
    services/     # External API access, caching, rate limit → has own CLAUDE.md
    scan/         # 4-phase pipeline orchestration           → has own CLAUDE.md
    data/         # SQLite persistence (WAL, migrations)     → has own CLAUDE.md
    api/          # FastAPI REST + WebSocket backend          → has own CLAUDE.md
    reporting/    # Report generation & disclaimers          → has own CLAUDE.md
    utils/        # DataFetchError exception hierarchy
data/migrations/  # Sequential SQL migration files
web/              # Vue 3 SPA (TypeScript, Pinia, PrimeVue)  → has own CLAUDE.md
tests/            # 1,577 tests (unit + integration)         → has own CLAUDE.md
```

Each module's CLAUDE.md has the detailed file listing. Read it before modifying that module.

## Module-Level Instructions — MANDATORY

Before creating, editing, or reviewing ANY file in a module, you MUST first read
that module's CLAUDE.md. These contain rules that override or extend the root instructions.

A task touching files in `agents/prompts/` requires reading BOTH `agents/CLAUDE.md` AND
`agents/prompts/CLAUDE.md` — child rules inherit from parent.

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
| `api/` | FastAPI REST + WebSocket (top of stack) | `models/`, `services/`, `data/`, `scan/`, `agents/`, `reporting/` | N/A |
| `cli/` | Terminal interface (top of stack) | Everything | N/A |

**Key boundary rules**:
- `services/` is the ONLY layer that touches external APIs or data sources.
- `indicators/` takes pandas in, returns pandas out. No API calls, no Pydantic models.
- `scoring/` imports from `pricing/dispatch` only — never `pricing/bsm` or `pricing/american`.
- `scan/` orchestrates but never calls `pricing/` directly (that's `scoring/contracts.py`'s job).
- `agents/` have no knowledge of each other. The orchestrator coordinates them.
- `models/` defines data shapes. No business logic, no I/O.
- `api/` and `cli/` are sibling entry points — neither imports from the other.

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

# Single BaseSettings root — the ONLY BaseSettings subclass in the project
class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ARENA_",
        env_nested_delimiter="__",     # ARENA_SCAN__TOP_N=30 → settings.scan.top_n
    )
    scan: ScanConfig = ScanConfig()
```

**DI pattern**: `cli/` creates `AppSettings()`, passes config slices to modules.
`AppSettings()` with no args is a valid production config.

### CLI Patterns (Context7-verified: Typer + Rich)

```python
import asyncio
import typer

app = typer.Typer()

# Typer does NOT support async commands — always use asyncio.run()
@app.command()
def scan(preset: ScanPreset = ScanPreset.SP500) -> None:
    asyncio.run(_scan_async(preset))
```

**Critical gotchas**:
- `RichHandler(markup=False)` — library logs contain `[AAPL]` brackets that crash Rich markup
- `signal.signal()` for SIGINT, NOT `loop.add_signal_handler()` (unsupported on Windows)

### Error Handling

- Custom domain exceptions: `TickerNotFoundError`, `InsufficientDataError`, `DataSourceUnavailableError`, `RateLimitExceededError`.
- Never bare `except:` — always catch specific types.
- `logging` module only — never `print()` in library code. `print()` is reserved for `cli/`.

### Naming

- Variables: `implied_vol_30d`, `daily_prices_df`, `atm_call` — descriptive, no abbreviations.
- Constants: `RSI_OVERBOUGHT = 70` — uppercase, defined once. No magic numbers.
- DataFrames: always suffixed `_df`.

### Async Convention

- Pick ONE client type per module — don't mix sync/async.
- `asyncio.wait_for(coro, timeout=N)` on every external call. No unbounded waits.
- `asyncio.gather(*tasks, return_exceptions=True)` for batch operations.
- Typer commands are sync wrappers: `def scan() -> None: asyncio.run(_scan_async())`.

## Verification — Run Before Every Commit

```bash
uv run ruff check . --fix && uv run ruff format .   # lint + format
uv run pytest tests/ -v                              # all tests
uv run mypy src/ --strict                            # type checking
```

Always run all three via `uv run`. A task is not done until all pass.

## Context7 Verification

Before writing code that maps external library output to typed models, use Context7
(`resolve-library-id` → `query-docs`) to verify field names, return types, and signatures.
Full protocol: `.claude/guides/context7-verification.md`.

## Git Discipline

- Atomic commits: `feat: add Bollinger Bands with configurable std dev`, not `update stuff`.
- Branch per feature. Never commit directly to main.
- Every commit message starts with: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, or `chore:`.

## What Claude Gets Wrong — Fix These

- Don't return raw dicts — always typed models (including `dict[str, float]`, `dict[str, Any]`).
- Don't use `Optional[X]` — use `X | None`. Don't use `typing.List`/`Dict` — use lowercase.
- Don't use raw `str` for categorical fields — use `StrEnum` from `enums.py`.
- Don't add `datetime` fields without UTC validator (`v.tzinfo is None or v.utcoffset() != timedelta(0)`).
- Don't forget `field_validator` on `confidence` fields — constrain to `[0.0, 1.0]`.
- Don't leave numeric validators without `math.isfinite()` — NaN silently passes `v >= 0`.
- Don't import `pricing/bsm` or `pricing/american` from `scoring/` — use `pricing/dispatch` only.
- Don't use `print()` outside `cli/` — use `logging.getLogger(__name__)`.
- Don't assume yfinance provides Greeks — only `impliedVolatility`. All Greeks from `pricing/dispatch.py`.
- Don't use `async def` on Typer commands — use sync def + `asyncio.run()`.
- Don't use `RichHandler(markup=True)` — `[TICKER]` brackets crash Rich. Always `markup=False`.
- Don't use `loop.add_signal_handler()` — unsupported on Windows. Use `signal.signal()`.

## Guides (Load When Needed)

Reference guides in `.claude/guides/` — NOT auto-loaded, read when relevant:

| Guide | When to load |
|-------|-------------|
| `context7-verification.md` | Writing code that maps external library output to models |
| `agent-coordination.md` | Multi-agent parallel work on same epic |
| `branch-operations.md` | Git branching for epics |
| `worktree-operations.md` | Git worktree parallel development |
| `path-standards.md` | Documentation/GitHub sync with path privacy |
| `strip-frontmatter.md` | Preparing markdown for GitHub sync |
| `frontmatter-operations.md` | Creating/editing YAML frontmatter |
| `test-execution.md` | Running tests with test-runner agent |
| `use-ast-grep.md` | Structural code search/refactoring |

## Context Budget Policy

Auto-loaded context has a strict budget. Every line costs attention on all tasks.

| Category | Current | Max |
|----------|---------|-----|
| CLAUDE.md | 278 lines | 350 lines |
| @-referenced context files | 216 lines | 300 lines |
| .claude/rules/ files | 379 lines | 400 lines |
| **Grand total** | **873** | **1,050** |

Rules:
- `progress.md`: Current state only. Move completed work to `progress-archive.md`.
- `system-patterns.md`: Unique patterns only. No duplication with CLAUDE.md.
- Rules: Only universally-needed rules in `.claude/rules/`. Workflow-specific → `.claude/guides/`.
- When adding content to any auto-loaded file, remove or move equal or greater content.
- Verify: `wc -l CLAUDE.md .claude/context/progress.md .claude/context/system-patterns.md .claude/context/tech-context.md .claude/rules/*.md`

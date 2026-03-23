# CLAUDE.md -- Options Arena

## What This Project Does

AI-powered options analysis for American-style options on U.S. equities. Six desk
recommendation agents + synthesis agent produce a `PositionRecommendation` via Groq
(Llama 3.3 70B) or Anthropic. Fetches market data, computes 27 technical indicators,
runs structured AI analysis, and outputs a risk-assessed recommendation with contract
selection. Data-driven fallback when the LLM provider is unreachable.

## Tech Stack

- **Python 3.13+** -- modern syntax: `match`, `type X = ...`, `X | None` unions, `StrEnum`
- **Package manager**: `uv` -- always `uv add <pkg>`, never `pip install`
- **Linter/Formatter**: `ruff` (target `py313`, line-length 99, rules: E, F, I, UP, B, SIM, ANN)
- **Type checker**: `mypy --strict` -- full annotations on every function
- **Async**: `asyncio` + `httpx` -- recommendation loop, data fetching, scan pipeline
- **Models**: Pydantic v2 -- all structured data crosses boundaries as typed models, never raw dicts
- **Config**: `pydantic-settings` v2 -- single `AppSettings(BaseSettings)` root, nested `BaseModel` submodels
- **AI SDK**: `pydantic-ai` + Groq (default) / Anthropic (`--provider anthropic`)
- **Pricing**: `scipy` -- BSM (Merton 1973) + BAW (Barone-Adesi-Whaley 1987)
- **CLI**: `typer` + `rich` -- subcommands, Rich tables, progress bars
- **Data**: `pandas` + `numpy` for indicators, `yfinance` via services, `aiosqlite` for persistence

## Project Layout

```
src/options_arena/
    cli/          # Typer CLI entry point
    agents/       # PydanticAI recommendation + desk agents
      prompts/    #   Prompt templates & versioning
    models/       # Pydantic models, enums, config
    pricing/      # BSM + BAW option pricing & Greeks
    indicators/   # Technical indicator math (18 functions)
    scoring/      # Normalization, composite, contracts
    services/     # External API access, caching, rate limit
    scan/         # 4-phase pipeline orchestration
    data/         # SQLite persistence (WAL, migrations)
    api/          # FastAPI REST + WebSocket backend
    reporting/    # Report generation
    analysis/     # Vol surface, HV estimators, valuation
    learning/     # Weight tuning, strategy mining
    utils/        # DataFetchError exception hierarchy
data/migrations/  # Sequential SQL migration files
web/              # Vue 3 SPA (TypeScript, Pinia, PrimeVue)
tests/            # ~370 files, 27K+ parametrized + 107 E2E
```

## Context Router -- Read Before Working

| Task Type | Read These First |
|-----------|-----------------|
| Bug fix in single module | That module's `CLAUDE.md` |
| Cross-module feature | `.claude/context/architecture.md` + affected module `CLAUDE.md` files |
| Pricing / scoring / indicators | `.claude/context/algorithms.md` + module `CLAUDE.md` |
| PRD / brainstorming / design | `.claude/context/product.md` |
| New to project / onboarding | `.claude/context/architecture.md` + `.claude/context/product.md` |
| Audit / review | `.claude/context/architecture.md` |
| Check current state / progress | `.claude/context/progress.md` |
| Workflow guides (git, testing, etc.) | `.claude/guides/` directory (load specific guide when needed) |

## Module-Level Instructions -- MANDATORY

Before creating, editing, or reviewing ANY file in a module, you MUST first read that
module's `CLAUDE.md`. Child modules inherit parent rules (e.g., `agents/prompts/` requires
reading both `agents/CLAUDE.md` and `agents/prompts/CLAUDE.md`).

## Architecture Boundaries

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
| `agents/` | PydanticAI debate orchestration | `models/`, `services/`, `pydantic_ai`, `analysis/` (desk tools only) | Other agents, indicators |
| `reporting/` | Report generation & disclaimers | `models/` | APIs, services |
| `analysis/` | Vol surface, HV estimators | `models/`, `pricing/`, `scipy` | APIs, services, I/O |
| `learning/` | Weight tuning algorithms | `models/`, `data/`, `scoring/` | `services/`, `agents/`, `cli/`, `api/`, `pricing/` |
| `api/` | FastAPI REST + WebSocket (top of stack) | `models/`, `services/`, `data/`, `scan/`, `agents/`, `reporting/`, `learning/` | N/A |
| `cli/` | Terminal interface (top of stack) | Everything | N/A |

**Key boundary rules**:
- `services/` is the ONLY layer that touches external APIs or data sources.
- `indicators/` takes pandas in, returns pandas out. No API calls, no Pydantic models.
- `scoring/` imports from `pricing/dispatch` only -- never `pricing/bsm` or `pricing/american`.
- `scan/` orchestrates but never calls `pricing/` directly (that's `scoring/contracts.py`'s job).
- `agents/` have no knowledge of each other. The orchestrator coordinates them.
- `models/` defines data shapes. No business logic, no I/O.
- `api/` and `cli/` are sibling entry points -- neither imports from the other.

## Code Patterns -- Project-Wide

**No raw dicts**: Every function returning structured data MUST return a Pydantic model, dataclass, or StrEnum -- never `dict`, `dict[str, Any]`, or `dict[str, float]`. Only exception: `indicators/` uses pandas Series/DataFrames.

**Immutable snapshots**: Use `ConfigDict(frozen=True)` on data models representing point-in-time snapshots (quotes, contracts, verdicts).

**Pydantic models**: Every `datetime` field needs a UTC validator. Every `confidence` field needs a `[0.0, 1.0]` validator. Every numeric validator must check `math.isfinite()` before range checks.

**Configuration**: Only one `BaseSettings` subclass (`AppSettings`). All nested configs are plain `BaseModel`. Env prefix `ARENA_`, nested delimiter `__`.

**CLI commands**: Sync Typer commands with `asyncio.run()` for async work -- Typer does not support `async def`. Use `RichHandler(markup=False)` always. Use `signal.signal()` for SIGINT (not `loop.add_signal_handler()`, unsupported on Windows).

**Error handling**: Custom domain exceptions only (`TickerNotFoundError`, `InsufficientDataError`, etc.). Never bare `except:`. Use `logging` -- never `print()` outside `cli/`.

**Naming**: Descriptive variables (`implied_vol_30d`, `daily_prices_df`), uppercase constants (`RSI_OVERBOUGHT = 70`), `_df` suffix on DataFrames. No abbreviations, no magic numbers.

**Async**: One client type per module. `asyncio.wait_for(coro, timeout=N)` on every external call. `asyncio.gather(*tasks, return_exceptions=True)` for batch operations.

**Financial precision**: Prices/P&L use `Decimal` (from strings: `Decimal("1.05")`). Greeks/IV/ratios use `float`. Volume/OI use `int`. Dates use `datetime.date`; timestamps use `datetime.datetime` with UTC.

**Agent pattern**: `Agent(model=None)` at init, actual model at `agent.run(model=...)`. All desk/recommendation runners never-raise -- catch all exceptions. Use `LLMDecimal` (not bare `Decimal`) for agent output types (Groq rejects Pydantic's Decimal regex).

**Self-improvement**: After corrections, run `/compound` to capture solutions. Before fragile-area tasks, check `docs/solutions/` for past fixes.

**Context7 verification**: Before mapping external library output to models, use Context7 to verify field names, return types, and signatures.

## What Claude Gets Wrong -- Fix These

- Never return raw dicts -- always typed models (including `dict[str, float]`, `dict[str, Any]`)
- Use `X | None` not `Optional[X]`; use lowercase `list`/`dict` not `typing.List`/`Dict`
- Use `StrEnum` for categorical fields, not raw `str`
- Every `datetime` field needs UTC validator; every `confidence` field needs `[0.0, 1.0]` validator
- Every numeric validator must check `math.isfinite()` first -- NaN passes `v >= 0` silently
- Import `pricing/dispatch` from `scoring/`, never `pricing/bsm` or `pricing/american` directly
- Use `logging.getLogger(__name__)` in library code, never `print()` (reserved for `cli/`)
- yfinance provides NO Greeks -- only `impliedVolatility`. All Greeks come from `pricing/dispatch.py`
- Typer commands must be sync (`def`) with `asyncio.run()`, never `async def`
- Use `RichHandler(markup=False)` always -- `[TICKER]` brackets crash Rich markup
- Use `signal.signal()` for SIGINT, not `loop.add_signal_handler()` (Windows incompatible)
- Use `LLMDecimal` not bare `Decimal` on PydanticAI agent output types (Groq rejects the regex)

## Options Domain Knowledge

- **IV Rank** is not **IV Percentile**. Rank = position in 52-week range. Percentile = % of days IV was lower.
- **yfinance chains provide NO Greeks** -- only `impliedVolatility`. All Greeks computed locally via `pricing/dispatch.py`.
- **American options** (all U.S. equity) use BAW pricing. European (SPX) would use BSM.
- **Mid price** `(bid + ask) / 2` is fair value estimate; `last` can be stale.
- **Dividend yield** uses `float` default `0.0`, never `None`. Waterfall fall-through checks `is None`, not falsy.

## Verification -- Run Before Every Commit

```bash
uv run ruff check . --fix && uv run ruff format .   # lint + format
uv run pytest -m critical -q                         # critical tier (<30s pre-commit)
uv run pytest -m "not exhaustive" -n auto -q         # standard suite (CI-level)
uv run pytest tests/ -v                              # all tests (verbose, for debugging)
uv run mypy src/ --strict                            # type checking
python tools/docgen.py                               # regenerate technical reference
python tools/tldr_analyzer.py                        # refresh TLDR code summaries
```

Always run lint, tests, and type checking via `uv run`. A task is not done until all pass.

## Git Discipline

- Atomic commits: `feat: add Bollinger Bands with configurable std dev`, not `update stuff`.
- Branch per feature. Never commit directly to main.
- Every commit message starts with: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, or `chore:`.

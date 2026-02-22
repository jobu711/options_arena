---
created: 2026-02-17T08:51:05Z
last_updated: 2026-02-17T08:51:05Z
version: 1.0
author: Claude Code PM System
---

# Project Style Guide

## Python Version & Syntax

- **Python 3.13+** required
- Use modern syntax: `match` statements, `type X = ...` aliases, `X | None` (not `Optional[X]`)
- Use `list`, `dict`, `tuple` lowercase (not `typing.List`, `typing.Dict`)
- Use `StrEnum` for string enumerations

## Naming Conventions

| Element | Convention | Example |
|---------|-----------|---------|
| Variables | Descriptive, no abbreviations | `implied_vol_30d`, `daily_prices_df`, `atm_call` |
| Constants | Uppercase, defined once | `RSI_OVERBOUGHT = 70`, `DEFAULT_DEBATE_ROUNDS = 3` |
| DataFrames | Suffixed `_df` | `daily_prices_df`, `option_chain_df` |
| Functions | Snake case, verb-noun | `compute_rsi()`, `save_scan_run()` |
| Classes | PascalCase | `OptionContract`, `MarketContext` |
| Modules | Snake case | `moving_averages.py`, `market_data.py` |

## Code Formatting

- **Line length**: 99 characters (ruff enforced)
- **Formatter**: ruff (runs on save)
- **Import sorting**: isort via ruff (rule `I`)
- No magic numbers anywhere — use named constants

## Type Annotations

- **Full annotations on every function** — `mypy --strict` enforced
- Use `X | None` not `Optional[X]`
- Use lowercase generics: `list[str]`, `dict[str, float]`
- Pydantic `ConfigDict(frozen=True)` on immutable models

## Error Handling

- Custom domain exceptions from `utils/exceptions.py`
- Never bare `except:` — always catch specific types
- `logging` module only — never `print()` in library code (`print()` reserved for `cli.py`)
- Fail fast at boundaries (CLI args, API responses)

## Async Patterns

- `async`/`await` for all external calls (data fetching, LLM, database)
- One client type per module — don't mix sync/async
- `asyncio.wait_for(coro, timeout=N)` on every external call
- `asyncio.gather(*tasks, return_exceptions=True)` for batch operations

## Testing Conventions

- Framework: pytest with pytest-asyncio
- Never `==` for float comparisons — use `pytest.approx()`
- Never hardcode dates dependent on `today` — mock `date.today()`
- Never hit real APIs — mock all external services
- Fixture files in `tests/fixtures/` (small: 100-250 rows)
- Tolerances documented per type (see `tests/CLAUDE.md`)

## Git Conventions

- Atomic commits with conventional prefixes: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`
- Branch per feature, never commit directly to main
- All three checks must pass before commit: ruff, pytest, mypy

## Documentation

- Every function: docstring with formula + reference (for indicators)
- Module `CLAUDE.md` files define per-module rules
- No unnecessary comments — code should be self-explanatory
- Don't add docstrings/comments to code you didn't change

## Anti-Patterns to Avoid

- No god-class `OptionAlpha` objects — use focused modules
- No raw dicts from functions — always typed models
- No `SettingWithCopyWarning` — fix with `.copy()`
- No mixing sync/async in same module
- No calling APIs from analysis/indicator code
- No skipping disclaimers on user-facing output

---
created: 2026-02-17T08:51:05Z
last_updated: 2026-02-23T12:06:57Z
version: 5.3
author: Claude Code PM System
---

# Tech Context

## Language & Runtime

- **Python 3.13+** — uses modern syntax: `match`, `type X = ...`, `X | None` unions, `StrEnum`
- **Package manager**: `uv` — always `uv add <pkg>`, never `pip install`

## Dependencies

### Runtime
| Package | Version | Purpose |
|---------|---------|---------|
| pydantic | >=2.12.5 | Typed data models at all boundaries |
| pandas | >=3.0.0 | Technical indicator computation |
| numpy | >=2.4.2 | Numeric operations for indicators |
| aiosqlite | >=0.22.1 | Async SQLite for persistence layer |
| yfinance | >=1.2.0 | Market data: OHLCV, options chains, quotes |
| httpx | >=0.28.1 | Async HTTP client for FRED, Ollama, Anthropic health checks |
| scipy | >=1.17.0 | BSM pricing (`stats.norm.cdf`/`.pdf`), BAW IV solver (`optimize.brentq`) |
| pydantic-ai | >=1.62.0 | Type-safe agent framework for AI debate agents |
| ollama | >=0.6.1 | Local LLM server (accessed via PydanticAI + OllamaProvider) |
| typer | >=0.24.0 | CLI framework with subcommands |
| rich | >=14.3.2 | Terminal output formatting (tables, colors, progress) |
| pydantic-settings | >=2.13.0 | Configuration management |

### Dev
| Package | Version | Purpose |
|---------|---------|---------|
| ruff | >=0.15.1 | Linter + formatter (runs on save) |
| mypy | >=1.19.1 | Type checker (`--strict` mode) |
| pytest | >=9.0.2 | Test framework |
| pytest-asyncio | >=1.3.0 | Async test support |
| pytest-cov | >=7.0.0 | Coverage reporting |
| pandas-stubs | >=3.0.0.260204 | Type stubs for pandas |
| scipy-stubs | >=1.17.0.2 | Type stubs for scipy |

## Build System

- **Build backend**: Hatchling
- **Source layout**: `src/options_arena/` (src-based layout)
- **Wheel packages**: `["src/options_arena"]`

## Tool Configuration

### Ruff
- Target: Python 3.13
- Line length: 99
- Rules: E, F, I, UP, B, SIM, ANN (errors, pyflakes, isort, pyupgrade, bugbear, simplify, annotations)

### Mypy
- `strict = true`
- `warn_return_any = true`
- `warn_unused_configs = true`

### Pytest
- Async mode via `pytest-asyncio`
- Verbose output: `uv run pytest tests/ -v`

## Verification Commands

```bash
uv run ruff check . --fix && uv run ruff format .   # lint + format
uv run pytest tests/ -v                              # all tests
uv run mypy src/ --strict                            # type checking
```

All three must pass before any commit.

## External Services (Phase 5 — Implemented)

| Service | Module | Protocol | Purpose | Fallback |
|---------|--------|----------|---------|----------|
| Yahoo Finance | `market_data.py`, `options_data.py` | yfinance via `asyncio.to_thread` | OHLCV, quotes, ticker info, option chains | N/A (required) |
| FRED | `fred.py` | httpx REST API | 10yr Treasury → risk-free rate | `PricingConfig.risk_free_rate_fallback` (5%) |
| CBOE | `universe.py` | httpx CSV download | Optionable ticker universe | Cached list (24h TTL) |
| Wikipedia | `universe.py` | `pd.read_html` via `asyncio.to_thread` | S&P 500 constituents + GICS sectors | Cached list (24h TTL) |
| Ollama | `health.py` (check only) | HTTP localhost:11434 | LLM debate agents (Llama 3.1 8B) | Data-driven verdict |

## Database

- **SQLite** with WAL mode
- Context-managed connections via `aiosqlite`
- Sequential migrations in `data/migrations/`
- Repository pattern for typed queries

## Web UI

No web UI currently implemented. Phase 1 is CLI-only. Web UI is planned for a future phase.

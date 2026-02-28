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
| httpx | >=0.28.1 | Async HTTP client for FRED, Groq health checks |
| scipy | >=1.17.0 | BSM pricing (`stats.norm.cdf`/`.pdf`), BAW IV solver (`optimize.brentq`) |
| pydantic-ai | >=1.62.0 | Type-safe agent framework for AI debate agents |
| typer | >=0.24.0 | CLI framework with subcommands |
| rich | >=14.3.2 | Terminal output formatting (tables, colors, progress) |
| pydantic-settings | >=2.13.0 | Configuration management |
| lxml | >=6.0.2 | HTML parsing for Wikipedia S&P 500 table |

### Web Runtime (separate `web/package.json`)
| Package | Version | Purpose |
|---------|---------|---------|
| vue | ^3.5.29 | SPA framework (Composition API + `<script setup>`) |
| vue-router | ^5.0.3 | Client-side routing (8 routes, lazy-loaded) |
| pinia | ^3.0.4 | State management (scan, debate, health, operation, watchlist stores) |
| primevue | ^4.5.4 | UI component library (DataTable, Dialog, Toast, Drawer) |
| @primeuix/themes | ^2.0.3 | Aura dark theme preset |
| vite | ^7.3.1 | Dev server + build tool |
| typescript | ^5.9.3 | Type checking (`vue-tsc --noEmit`) |
| @playwright/test | ^1.52.0 | E2E testing (38 tests, 4 parallel workers) |

### Python Web Dependencies (now in main `pyproject.toml` dependencies)
| Package | Version | Purpose |
|---------|---------|---------|
| fastapi | >=0.133.1 | REST API + WebSocket backend |
| uvicorn[standard] | >=0.41.0 | ASGI server for FastAPI |

### Optional
| Package | Version | Purpose |
|---------|---------|---------|
| weasyprint | >=63.0 | PDF export for debate results (`pip install options-arena[pdf]`) |

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
- Custom markers: `integration` (may require external services like Groq)

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
| Groq | `agents/orchestrator.py`, `health.py` | PydanticAI + GroqProvider (cloud API) | LLM debate agents (llama-3.3-70b-versatile) | Data-driven verdict |

## Database

- **SQLite** with WAL mode
- Context-managed connections via `aiosqlite`
- Sequential migrations in `data/migrations/`
- Repository pattern for typed queries

## CLI Entry Point

- **Command**: `options-arena` (installed via `pyproject.toml` `[project.scripts]`)
- **Entry point**: `options_arena.cli:app` (Typer app)
- **Commands**: `scan`, `health`, `universe` (refresh/list/stats), `debate` (`--batch`, `--export md|pdf`), `serve`, `watchlist` (add/remove/list)
- **Logging**: Dual-handler (RichHandler stderr + RotatingFileHandler `logs/options_arena.log`)
- **SIGINT**: `signal.signal()` double-press pattern (graceful then force)

## Web UI

- **Backend**: FastAPI app factory (`src/options_arena/api/`) — REST + WebSocket, served by uvicorn
- **Frontend**: Vue 3 SPA (`web/`) — TypeScript, Pinia stores, PrimeVue Aura dark theme
- **Launch**: `options-arena serve` (loopback-only, auto-opens browser)
- **Dev mode**: Vite dev server (:5173) proxies `/api/*` and `/ws/*` to FastAPI (:8000)
- **Production**: FastAPI serves `web/dist/` via catch-all GET route + `/assets` mount — single process, single port
- **E2E tests**: Playwright (38+ tests) — page objects, API mocks, fake WebSocket via `addInitScript`, 4 parallel workers with isolated DBs
- **WebSocket**: Real-time progress for scans (4-phase) and debates (agent steps, batch)
- **Operation mutex**: `asyncio.Lock` — one scan or batch debate at a time (409 if busy)

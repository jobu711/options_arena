# Tech Context

## Language & Runtime

- **Python 3.13+** — uses modern syntax: `match`, `type X = ...`, `X | None` unions, `StrEnum`
- **Package manager**: `uv` — always `uv add <pkg>`, never `pip install`

## Dependencies (Runtime Python)

| Package | Version | Purpose |
|---------|---------|---------|
| pydantic | >=2.12.5 | Typed data models at all boundaries |
| pandas | >=3.0.0 | Technical indicator computation |
| numpy | >=2.4.2 | Numeric operations for indicators |
| aiosqlite | >=0.22.1 | Async SQLite for persistence layer |
| yfinance | >=1.2.0 | Market data: OHLCV, options chains, quotes |
| httpx | >=0.28.1 | Async HTTP client for FRED, Groq health checks |
| scipy | >=1.17.0 | BSM pricing (`stats.norm.cdf`/`.pdf`), BAW IV solver (`optimize.brentq`) |
| pydantic-ai-slim[groq,anthropic] | >=1.62,<2.0 | Type-safe agent framework for AI debate agents |
| typer | >=0.24.0 | CLI framework with subcommands |
| rich | >=14.3.2 | Terminal output formatting (tables, colors, progress) |
| pydantic-settings | >=2.13.0 | Configuration management |
| anthropic | >=0.83.0 | Anthropic API client for Claude debate agents |

| fastapi | >=0.133.1 | REST API + WebSocket backend |
| uvicorn[standard] | >=0.41.0 | ASGI server for FastAPI |

| arch | >=8.0,<9 | GARCH/EGARCH volatility forecasting (optional `[ml]`) |
| statsmodels | >=0.14,<0.15 | Markov-switching regime detection, ADF tests (optional `[ml]`) |

For web/optional/dev deps, build system, and tool config: `.claude/guides/dependency-reference.md`

## External Services

| Service | Module | Protocol | Purpose | Fallback |
|---------|--------|----------|---------|----------|
| Yahoo Finance | `market_data.py`, `options_data.py` | yfinance via `asyncio.to_thread` | OHLCV, quotes, ticker info, option chains | N/A (required) |
| FRED | `fred.py` | httpx REST API | Risk-free rate + macro series (GDP, CPI, unemployment, yield curve) | Fallback defaults per series |
| CBOE | `universe.py`, `cboe_provider.py` | httpx CSV + OpenBB SDK | Optionable universe + option chains (primary) | Cached list (24h TTL) / yfinance fallback |
| GitHub CSV | `universe.py` | httpx + `pd.read_csv` via `asyncio.to_thread` | S&P 500 constituents + GICS sectors | Cached list (24h TTL) |
| Groq | `agents/orchestrator.py`, `health.py` | PydanticAI + GroqProvider (cloud API) | LLM debate agents (llama-3.3-70b-versatile) | Data-driven verdict |
| Anthropic | `agents/model_config.py`, `health.py` | PydanticAI + AnthropicModel (cloud API) | LLM debate agents (Claude, `--provider anthropic`) | Groq (default) |
| OpenBB | `openbb_service.py`, `health.py` | OpenBB SDK (guarded import) | Fundamentals, unusual flow, news sentiment | `None` (optional enrichment) |

## Database

- **SQLite** with WAL mode, context-managed `aiosqlite`, sequential migrations in `data/migrations/`

## CLI Entry Point

- **Command**: `options-arena` — entry point `options_arena.cli:app` (Typer)
- **Commands**: `scan` (`--sector`), `health`, `universe`, `debate` (`--batch`, `--export md`, `--provider`, `--cost-summary`), `serve`, `outcomes` (collect, summary, backtest, equity-curve), `agency` (ask, history, `learn` (status, weights, mine, playbook, decay)), `audit`, `eval` (check, report, list)
- **Logging**: Dual-handler (RichHandler stderr + RotatingFileHandler `logs/options_arena.log`)
- **SIGINT**: `signal.signal()` double-press pattern (graceful then force)

## Web UI

- **Backend**: FastAPI app factory — REST + WebSocket, served by uvicorn
- **Frontend**: Vue 3 SPA (`web/`) — TypeScript, Pinia stores, PrimeVue Aura dark theme
- **Launch**: `options-arena serve` (loopback-only, auto-opens browser)
- **Dev mode**: Vite (:5173) proxies to FastAPI (:8000)
- **Production**: FastAPI serves `web/dist/` via catch-all GET + `/assets` mount
- **E2E tests**: Playwright (107 tests across 17 spec files, 4 parallel workers, isolated DBs)
- **WebSocket**: Real-time progress for scans and debates
- **Operation mutex**: `asyncio.Lock` — one scan or batch debate at a time (409 if busy)

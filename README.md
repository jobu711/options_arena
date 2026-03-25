# Options Arena

AI-powered options analysis platform for American-style options on U.S. equities. Six specialized desk agents and a synthesis agent produce structured position recommendations via Groq (Llama 3.3 70B) or Anthropic. The system fetches live market data, computes 27 technical indicators, prices options with BSM/BAW models, runs multi-agent AI analysis, and outputs risk-assessed recommendations with specific contract selection.

This is an analysis-only tool — no trade execution, no broker integration.

## How It Works

### Scan Pipeline

A 4-phase async pipeline screens the options universe:

1. **Universe** — Pulls ~5,286 optionable tickers from CBOE (or S&P 500 / ETF presets), applies sector and market-cap filters
2. **Scoring** — Computes 27 technical indicators, normalizes into a composite score, classifies directional bias
3. **Options** — Enriches top-N tickers with option chain data, locally-computed Greeks (BSM/BAW), and contract recommendations
4. **Persist** — Saves everything to SQLite for history, analytics, and outcome tracking

### AI Recommendation

Six desk agents independently analyze a ticker, then a synthesis agent weighs their assessments:

| Agent | Focus |
|-------|-------|
| **Trend** | Momentum, trend strength, regime context |
| **Volatility** | IV rank, term structure, vol regime |
| **Flow** | Options flow signals, unusual activity |
| **Fundamental** | Financial health, valuation metrics |
| **Risk** | Downside scenarios, position sizing |
| **Contrarian** | Alternative scenarios, consensus challenges |

The synthesis agent produces a `PositionRecommendation` with a specific contract, entry/exit prices, confidence score, and risk assessment. When the LLM is unavailable, a data-driven fallback generates recommendations from scores alone.

### Interactive Agency

Seven desk agents accept natural language queries with tool-use capabilities. An intent router dispatches questions to the right desk. Queries and responses persist for conversation history.

### Learning Loop

The system improves over time:
- **Indicator weight tuning** — adjusts scoring weights based on P&L correlation
- **Vote weight tuning** — adjusts agent influence based on prediction accuracy
- **Strategy mining** — discovers winning patterns across sector, IV, DTE, and direction dimensions
- **Confidence decay** — exponentially decays stale strategy rules

## Features

- **Multi-agent AI debate** — 6 desk + 1 synthesis agent via PydanticAI (Groq or Anthropic), with complexity-based model routing (FAST/STANDARD/PREMIUM tiers)
- **Options pricing engine** — BSM (European) + BAW (American) with full Greeks computed locally. yfinance provides only implied volatility.
- **27 technical indicators** — RSI, MACD, Bollinger Bands, ATR, OBV, Stochastic, Keltner Channels, and more. Pure pandas math.
- **Composite scoring** — Weighted geometric mean across momentum, value, volatility, and technical factors
- **Outcome tracking** — P&L collection at T+1, T+5, T+10, T+20 days with win-rate analytics and equity curves
- **Backtesting** — Sector, DTE, IV, and direction performance breakdowns with drawdown analysis
- **Web dashboard** — Single-screen AI trading desk (Vue 3 + PrimeVue), real-time WebSocket progress, analytics with 5 tabs
- **CLI** — Rich terminal interface with progress bars, colored tables, and subcommands
- **Watchlists** — SQLite-backed custom ticker lists that feed into the scan pipeline
- **Metadata index** — Persistent GICS sector/industry/market-cap classification for ~5K tickers
- **ML pipeline** (optional) — GARCH volatility, regime detection, macro factors, Hurst exponent

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.13+ |
| Package Manager | [uv](https://docs.astral.sh/uv/) |
| Models | Pydantic v2 (typed models at all boundaries — no raw dicts) |
| AI Framework | PydanticAI + Groq (Llama 3.3 70B) / Anthropic |
| Web Backend | FastAPI + Uvicorn (REST + WebSocket) |
| Web Frontend | Vue 3, TypeScript, Pinia, PrimeVue (Aura dark) |
| CLI | Typer + Rich |
| Pricing | SciPy (BSM + BAW) |
| Data | pandas + numpy, yfinance, aiosqlite (SQLite WAL) |
| HTTP | httpx (async) |
| Config | pydantic-settings v2 (`ARENA_` prefix) |
| Linting | ruff (E, F, I, UP, B, SIM, ANN) |
| Type Checking | mypy --strict |

## Quick Start

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager
- Node.js 22+ (for frontend)
- A [Groq API key](https://console.groq.com/) (free tier available)

### Install

```bash
git clone https://github.com/jobu711/options_arena.git
cd options_arena

# Python
uv sync

# Frontend
cd web && npm install && npm run build && cd ..
```

### Configure

```bash
export GROQ_API_KEY="your-key-here"
```

All settings use env vars with `ARENA_` prefix and `__` nested delimiter:

```bash
export ARENA_SCAN__TOP_N=50
export ARENA_SCAN__MIN_SCORE=5.0
export ARENA_DEBATE__PROVIDER=anthropic   # switch to Anthropic
export ANTHROPIC_API_KEY="your-key-here"  # if using Anthropic
```

### Usage

```bash
# Scan the universe
options-arena scan
options-arena scan --preset sp500 --sector "Information Technology" --direction bullish

# AI recommendation
options-arena debate AAPL
options-arena debate --batch --batch-limit 5
options-arena debate TSLA --export md --export-dir ./reports

# Interactive desk queries
options-arena agency ask "What's the vol regime for NVDA?"
options-arena agency chat

# Web dashboard
options-arena serve                        # http://127.0.0.1:8000

# Health check
options-arena health

# Universe management
options-arena universe stats
options-arena universe index

# Watchlists
options-arena watchlist create my-picks
options-arena watchlist add my-picks AAPL TSLA NVDA

# Outcome tracking
options-arena outcomes collect
options-arena outcomes summary
options-arena outcomes equity-curve

# Learning
options-arena learn tune-indicators
options-arena learn tune-votes
options-arena learn mine
options-arena learn playbook
```

Use `--help` on any command for full options.

## Project Structure

```
src/options_arena/          166 files, ~52K lines
    cli/                    Typer CLI entry point
    agents/                 PydanticAI agents (6 recommendation + 1 synthesis + 7 desk)
      prompts/              Prompt templates & versioning
    models/                 Pydantic models, enums, config
    pricing/                BSM + BAW option pricing & Greeks
    indicators/             Technical indicator math (27 indicators)
    scoring/                Normalization, composite scoring, contracts
    services/               External API access, caching, rate limiting
    scan/                   4-phase async pipeline orchestration
    data/                   SQLite persistence (WAL, 41 migrations)
    api/                    FastAPI REST + WebSocket backend
    reporting/              Report generation & disclaimers
    analysis/               Vol surface, HV estimators, valuation
    learning/               Weight tuning, strategy mining, confidence decay
    utils/                  Exception hierarchy

web/                        Vue 3 SPA (76 files, TypeScript, Pinia, PrimeVue)
tests/                      395 test files, 16.6K+ passing
data/migrations/            41 sequential SQL migration files
```

## Architecture

Layered architecture with strict module boundaries enforced by convention. Every cross-module value is a typed Pydantic model — no raw dicts.

```
┌───────────────────────────────────────────────┐
│  CLI (Typer + Rich)  │  Web API (FastAPI)      │  ← Entry points
├──────────────────────┴────────────────────────┤
│  Agents (PydanticAI debate orchestration)      │
│  Scan (4-phase async pipeline)                 │
│  Reporting (markdown export)                   │
│  Learning (weight tuning, strategy mining)     │
├────────────────────────────────────────────────┤
│  Scoring (composite, normalization, contracts) │
│  Pricing (BSM + BAW via dispatch)              │
│  Indicators (pandas in → pandas out)           │
│  Analysis (vol surface, HV, valuation)         │
├────────────────────────────────────────────────┤
│  Services (yfinance, FRED, CBOE, Groq, OpenBB)│
│  Data (SQLite WAL, migrations, repository)     │
├────────────────────────────────────────────────┤
│  Models (Pydantic v2, enums, config)           │
└────────────────────────────────────────────────┘
```

Key boundaries:
- **services/** is the only layer that touches external APIs
- **indicators/** takes pandas in, returns pandas out — no API calls, no Pydantic models
- **scoring/** imports from `pricing/dispatch` only — never internal pricing modules
- **agents/** have no knowledge of each other; the orchestrator coordinates them
- **api/** and **cli/** are sibling entry points — neither imports from the other

## External Services

| Service | Purpose | Required |
|---------|---------|----------|
| Yahoo Finance | OHLCV, quotes, option chains | Yes |
| Groq | LLM debate agents (Llama 3.3 70B) | No (data-driven fallback) |
| Anthropic | Alternative LLM provider (Claude) | No (optional) |
| FRED | Risk-free rate (10yr Treasury) | No (5% fallback) |
| CBOE | Optionable universe + option chains | No (yfinance fallback) |
| OpenBB | Fundamentals, flow, sentiment | No (optional enrichment) |

## Development

```bash
# Dev dependencies
uv sync --group dev
cd web && npm install

# Lint + format
uv run ruff check . --fix && uv run ruff format .

# Type check
uv run mypy src/ --strict

# Tests
uv run pytest -m critical -q              # Critical tier (<30s)
uv run pytest -m "not exhaustive" -n auto  # Standard suite
uv run pytest tests/ -v                    # Full suite

# Frontend
cd web && npm run dev                      # Vite dev server at :5173
cd web && npx vue-tsc --noEmit             # Type check
```

CI runs 4 gates on every push: lint, typecheck, Python tests, frontend build.

## Optional Extras

```bash
uv sync --extra ml       # GARCH, regime detection, macro factors, Hurst exponent
uv sync --extra neural   # PyTorch Lightning (experimental)
```

## License

[AGPL-3.0-only](LICENSE) — you can view, fork, and modify this code, but any distribution or network deployment of a modified version must release the full source under the same license.

## Disclaimer

This tool is for **educational and research purposes only**. It does not constitute financial advice. Options trading involves substantial risk of loss and is not suitable for all investors. Always do your own research and consult a qualified financial advisor before making investment decisions.

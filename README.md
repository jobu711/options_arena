# Options Arena

AI-powered options analysis tool for American-style options on U.S. equities. Eight AI agents (Bull, Bear, Risk, Volatility, Contrarian, Flow, Fundamental, Trend) debate via Groq cloud API (Llama 3.3 70B) on options contracts, producing structured verdicts with risk assessments.

## Features

- **AI Debate Engine** — Eight specialized agents (Bull, Bear, Risk, Volatility, Contrarian, Flow, Fundamental, Trend) argue over options contracts using PydanticAI + Groq (Llama 3.3 70B). Structured single-pass debate with optional bull rebuttal. Data-driven fallback when LLM is unavailable.
- **Options Pricing** — BSM (Black-Scholes-Merton) for European-style and BAW (Barone-Adesi-Whaley) for American-style options. All Greeks computed locally — yfinance provides only implied volatility.
- **4-Phase Scan Pipeline** — Async pipeline: universe filtering → scoring → options enrichment → persistence. Sector, market cap, IV rank, and direction filters.
- **18 Technical Indicators** — RSI, MACD, Bollinger Bands, ATR, OBV, Stochastic, and more. Pure pandas math with no external API dependencies.
- **Composite Scoring** — Multi-factor scoring (momentum, value, volatility, technical) with normalization and direction classification.
- **Web Dashboard** — Vue 3 SPA with real-time WebSocket progress, sortable/filterable DataTables, agent cards, and dark theme (PrimeVue Aura).
- **CLI Interface** — Rich terminal output with progress bars, colored tables, and subcommands for scanning, debating, health checks, and more.
- **Outcome Tracking** — Collects P&L at T+1/5/10/20 days for recommended contracts. Analytics queries and summary reports.
- **Watchlist Management** — SQLite-backed custom ticker lists that feed into the scan pipeline.
- **Metadata Index** — Persistent ticker classification cache (GICS sector, industry group, market cap tier) for ~5K CBOE tickers.
- **Market Intelligence** — Optional OpenBB enrichment for fundamentals, unusual options flow, and news sentiment.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.13+ |
| Models | Pydantic v2 (typed models at all boundaries) |
| AI Framework | PydanticAI + Groq (Llama 3.3 70B) |
| Web Backend | FastAPI + Uvicorn (REST + WebSocket) |
| Web Frontend | Vue 3, TypeScript, Pinia, PrimeVue |
| CLI | Typer + Rich |
| Pricing | SciPy (BSM + BAW) |
| Data | pandas + numpy, yfinance, aiosqlite (SQLite WAL) |
| HTTP | httpx (async) |
| Config | pydantic-settings v2 |

## Quick Start

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager
- Node.js 22+ (for frontend build)
- A [Groq API key](https://console.groq.com/) (for AI debate agents)

### Installation

```bash
git clone https://github.com/jobu711/options_arena.git
cd options_arena

# Install Python dependencies
uv sync

# Build the frontend
cd web && npm install && npm run build && cd ..
```

### Configuration

Set your Groq API key:

```bash
export GROQ_API_KEY="your-key-here"
# or
export ARENA_DEBATE__API_KEY="your-key-here"
```

All configuration uses environment variables with the `ARENA_` prefix and `__` nested delimiter:

```bash
export ARENA_SCAN__TOP_N=50          # Top N tickers to score
export ARENA_SCAN__MIN_SCORE=5.0     # Minimum composite score
```

### Usage

#### Run a scan

```bash
# Scan S&P 500 constituents (default)
options-arena scan

# Scan with filters
options-arena scan --preset sp500 --sector "Information Technology" --min-score 6.0 --direction bullish
```

#### Run an AI debate

```bash
# Single ticker debate
options-arena debate AAPL

# Batch debate on top scan results
options-arena debate --batch --batch-limit 5

# Export debate report
options-arena debate TSLA --export md --export-dir ./reports
```

#### Launch the web dashboard

```bash
options-arena serve
# Opens http://127.0.0.1:8000 in your browser
```

#### Other commands

```bash
options-arena health                  # Check external service availability
options-arena universe stats          # Show universe statistics
options-arena universe index          # Rebuild metadata index
options-arena watchlist create my-list  # Create a watchlist
options-arena watchlist add my-list AAPL TSLA NVDA
options-arena outcomes collect        # Collect P&L outcomes
options-arena outcomes summary        # View analytics
```

Use `--help` on any command for full options:

```bash
options-arena --help
options-arena scan --help
options-arena debate --help
```

## Project Structure

```
src/options_arena/
    cli/          # Typer CLI entry point
    agents/       # PydanticAI debate agents (Bull, Bear, Risk, Volatility, Contrarian, Flow, Fundamental, Trend)
      prompts/    # Prompt templates & versioning
    models/       # Pydantic models, enums, config
    pricing/      # BSM + BAW option pricing & Greeks
    indicators/   # Technical indicator math (18 functions)
    scoring/      # Normalization, composite scoring, contracts
    services/     # External API access, caching, rate limiting
    scan/         # 4-phase async pipeline orchestration
    data/         # SQLite persistence (WAL, migrations)
    api/          # FastAPI REST + WebSocket backend
    reporting/    # Report generation & disclaimers
    utils/        # Exception hierarchy

web/              # Vue 3 SPA (TypeScript, Pinia, PrimeVue)
tests/            # 3,959 tests (3,921 Python unit + 38 E2E)
data/migrations/  # Sequential SQL migration files
```

## Architecture

Layered architecture with strict module boundaries. Each layer communicates through typed Pydantic v2 models — no raw dicts cross module boundaries.

```
┌─────────────────────────────────────────────┐
│  CLI (Typer + Rich)  │  Web API (FastAPI)    │  ← Entry points
├──────────────────────┴──────────────────────┤
│  Agents (PydanticAI debate orchestration)    │
│  Scan (4-phase async pipeline)               │
│  Reporting (markdown/PDF export)             │
├──────────────────────────────────────────────┤
│  Scoring (composite, normalization)          │
│  Pricing (BSM + BAW via dispatch)            │
│  Indicators (pandas in/out)                  │
├──────────────────────────────────────────────┤
│  Services (yfinance, FRED, CBOE, Groq)      │
│  Data (SQLite WAL, migrations, repository)   │
├──────────────────────────────────────────────┤
│  Models (Pydantic v2, enums, config)         │
└──────────────────────────────────────────────┘
```

Key boundaries:
- `services/` is the only layer that touches external APIs
- `indicators/` takes pandas in, returns pandas out — no API calls, no Pydantic models
- `scoring/` imports from `pricing/dispatch` only — never internal pricing modules
- `agents/` have no knowledge of each other; the orchestrator coordinates them
- `api/` and `cli/` are sibling entry points — neither imports from the other

## External Services

| Service | Purpose | Required |
|---------|---------|----------|
| Yahoo Finance | OHLCV, quotes, option chains | Yes |
| Groq | LLM debate agents (Llama 3.3 70B) | No (data-driven fallback) |
| FRED | Risk-free rate (10yr Treasury) | No (5% fallback) |
| CBOE | Optionable universe + option chains | No (yfinance fallback) |
| OpenBB | Fundamentals, flow, sentiment | No (optional enrichment) |

## Development

### Prerequisites

```bash
uv sync --group dev    # Install dev dependencies
cd web && npm install   # Install frontend dependencies
```

### Running Tests

```bash
# All Python tests
uv run pytest tests/ -v

# With coverage
uv run pytest tests/ --cov=src/options_arena

# Frontend type check
cd web && npx vue-tsc --noEmit
```

### Linting & Type Checking

```bash
uv run ruff check . --fix && uv run ruff format .   # Lint + format
uv run mypy src/ --strict                            # Type checking
```

### Frontend Development

```bash
cd web
npm run dev    # Vite dev server at :5173 (proxies to FastAPI :8000)
```

In a separate terminal:
```bash
options-arena serve --reload    # FastAPI with hot reload
```

### CI Pipeline

GitHub Actions runs 4 gates on every push and PR:

1. **Lint & Format** — `ruff check` + `ruff format --check`
2. **Type Check** — `mypy src/ --strict`
3. **Python Tests** — `pip-audit` security scan + `pytest`
4. **Frontend** — `vue-tsc --noEmit` + `npm run build`

## How It Works

### Scan Pipeline

1. **Universe** — Fetches optionable tickers from CBOE, applies sector/market-cap/direction filters
2. **Scoring** — Computes 18 technical indicators, normalizes into composite scores, classifies direction
3. **Options** — Enriches top-N tickers with option chain data, Greeks, and contract recommendations
4. **Persist** — Saves scan results, scores, and recommended contracts to SQLite

### AI Debate

1. Market data and technical indicators are assembled into a structured context
2. **Bull agent** argues the bullish case with confidence scoring and key points
3. **Bear agent** argues the bearish case independently
4. **Bull rebuttal** (optional) — Bull responds to Bear's counter-arguments
5. **Volatility agent** assesses IV rank, term structure, and vol regime
6. **Contrarian agent** challenges consensus with alternative scenarios
7. **Flow agent** analyzes options flow signals and unusual activity
8. **Fundamental agent** evaluates financial health and valuation metrics
9. **Trend agent** assesses momentum, trend strength, and regime context
10. **Risk agent** synthesizes all arguments into a final verdict with trade thesis
11. Results are persisted and available via CLI, API, and web dashboard

### Outcome Tracking

After debates produce contract recommendations, the outcome collector tracks actual P&L:
- Fetches market prices at T+1, T+5, T+10, and T+20 days
- Handles expired contracts (ITM → intrinsic value, OTM → expired worthless)
- Analytics queries surface win rates, average returns, and performance by direction

## Disclaimer

This tool is for **educational and research purposes only**. It does not constitute financial advice. Options trading involves substantial risk of loss and is not suitable for all investors. Always do your own research and consult a qualified financial advisor before making investment decisions.

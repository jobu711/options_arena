# MCP Financial Tools Guide

Load this guide when debugging Fundamental agent data, validating MarketContext enrichment,
or backtesting debate verdicts.

## Financial Datasets MCP Server

**Setup**: Set `FINANCIAL_DATASETS_API_KEY` env var (get key at https://financialdatasets.ai).

### Available Tools

| Tool | Purpose |
|------|---------|
| `get-income-statements` | Revenue, net income, EPS, margins |
| `get-balance-sheets` | Assets, liabilities, equity breakdown |
| `get-cash-flow-statements` | Operating/investing/financing cash flows |
| `get-stock-prices` | Historical OHLCV price data |
| `get-crypto-prices` | Cryptocurrency price data |
| `get-news` | Financial news articles |

### When to Use

- **Debugging Fundamental agent**: Cross-reference P/E, EPS, revenue data against what
  `IntelligenceService` fetches from OpenBB
- **Validating MarketContext**: Compare enrichment fields against independent source
- **Ad-hoc research**: Quick financial data lookup during development without writing code

### Example Queries

```
# Check AAPL fundamentals for debugging
get-income-statements ticker=AAPL period=quarterly limit=4

# Validate price data against yfinance
get-stock-prices ticker=MSFT interval=daily limit=30
```

## QuantConnect MCP Server

**Setup**: Requires Docker Desktop. Set `QC_USER_ID` and `QC_API_TOKEN` env vars
(get credentials at https://www.quantconnect.com/settings#account-api).

### Key Tool Categories (64 tools total)

| Category | Tools | Purpose |
|----------|-------|---------|
| Projects | create, read, update, delete | Manage backtest projects |
| Backtesting | create-backtest, read-backtest | Run strategy backtests |
| Optimization | estimate, create, read | Parameter optimization |
| Live Trading | create, read, update, stop, liquidate | Live algo management |
| Docs Search | search-docs | Search QuantConnect documentation |

### When to Use

- **Backtesting verdicts**: Test if debate recommendations would have been profitable
- **Validating contracts**: Check historical performance of recommended strike/expiry combos
- **Strategy research**: Explore options strategies in QuantConnect's framework

### Example Workflow

1. Create a project with a simple options strategy
2. Backtest against historical data for the ticker/expiry in question
3. Compare backtest P&L against debate verdict's expected outcome

## Financial Datasets vs Existing Data Sources

| Need | Use | Why |
|------|-----|-----|
| Real-time quotes | yfinance (`services/market_data.py`) | Already integrated, cached |
| Option chains | CBOE/yfinance (`services/options_data.py`) | Already integrated with Greeks |
| Fundamentals (prod) | OpenBB (`services/openbb_service.py`) | Already integrated in pipeline |
| Fundamentals (debug) | Financial Datasets MCP | Independent cross-reference |
| Historical backtesting | QuantConnect MCP | Full backtest engine |
| Quick financial lookup | Financial Datasets MCP | No code needed, instant |

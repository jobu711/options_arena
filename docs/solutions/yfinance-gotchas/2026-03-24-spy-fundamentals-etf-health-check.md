---
title: "SPY health check causes spurious 404 errors (ETF has no fundamentals)"
date: 2026-03-24
module: options_arena.services.health
problem_type: yfinance_gotcha
severity: medium
symptoms:
  - "HTTP Error 404: No fundamentals data found for symbol: SPY on every server startup"
  - "HTTP Error 401: Invalid Crumb errors during heatmap batch downloads"
tags:
  - yfinance
  - health-check
  - etf
  - spy
  - fundamentals
  - invalid-crumb
root_cause: "Intelligence health check used SPY (an ETF) for get_analyst_price_targets() — ETFs have no analyst targets, causing yfinance to log 404 errors. Heatmap batch downloads triggered noisy 401 'Invalid Crumb' errors from yfinance internals."
---

## Problem

Every server startup logged two types of spurious errors:

1. `HTTP Error 404: No fundamentals data found for symbol: SPY` — from the intelligence
   health check calling `get_analyst_price_targets()` on SPY.
2. `HTTP Error 401: Invalid Crumb` — from yfinance's internal auth layer during
   `yf.download()` batch calls for the heatmap.

Neither error was fatal (both caught and handled), but they cluttered logs and confused
users into thinking the server was broken.

## Root Cause

1. SPY is an S&P 500 ETF. ETFs don't have analyst price targets or fundamentals data.
   yfinance's `get_analyst_price_targets()` calls Yahoo's `quoteSummary` endpoint which
   returns 404 for ETFs. The health check still reported OK (caught the exception), but
   yfinance logged the HTTP error to stderr.

2. `yf.download()` uses cookie-based auth with a "crumb" token. The crumb occasionally
   expires or fails validation, causing transient 401 errors. These are retried internally
   by yfinance but the error is still logged.

## Solution

1. Changed intelligence health check probe ticker from `SPY` to `AAPL` (a stock with
   analyst coverage).

2. Temporarily raise yfinance logger level to `CRITICAL` during `_download_chunk()` to
   suppress transient 401 noise, then restore the original level in a `finally` block.

## Prevention Rule

Never use ETF tickers (SPY, QQQ, IWM, etc.) for health checks that probe stock-specific
data (fundamentals, analyst targets, earnings). Use a liquid large-cap stock (AAPL, MSFT)
instead. For noisy third-party loggers, suppress at the logger level during known-noisy
operations rather than globally.

## Related

- `src/options_arena/services/health.py` line 309 — intelligence health check
- `src/options_arena/services/market_data.py` — `_download_chunk()` logger suppression

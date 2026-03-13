---
title: "yfinance option chains provide no Greeks — only impliedVolatility"
date: 2026-03-13
module: options_arena.services.options_data
problem_type: yfinance_gotcha
severity: critical
symptoms:
  - "Greeks are None or missing after fetching option chain"
  - "AttributeError when accessing delta/gamma/theta on yfinance data"
  - "Assumption that yfinance returns full Greeks"
tags:
  - yfinance
  - greeks
  - delta
  - gamma
  - theta
  - vega
  - impliedVolatility
  - options
root_cause: "yfinance option chain data includes only impliedVolatility — no delta, gamma, theta, vega, or rho"
---

## Problem

Code that fetches option chains via yfinance and expects Greeks (delta, gamma, theta,
vega, rho) to be present in the response. The data only includes `impliedVolatility`.

## Root Cause

yfinance's option chain API returns: strike, lastPrice, bid, ask, volume, openInterest,
impliedVolatility, and other market fields. It does NOT return any Greeks. This is a
limitation of the Yahoo Finance data source, not a bug.

## Solution

All Greeks are computed locally via `pricing/dispatch.py`, which uses BSM (European) or
BAW (American) pricing models. The flow:
1. Fetch option chain from yfinance (or CBOE)
2. Extract `impliedVolatility` from the chain
3. Pass IV + other inputs to `pricing/dispatch.compute_greeks()`
4. Greeks are returned as `OptionGreeks` model with `pricing_model` field

## Prevention Rule

**Never assume yfinance provides Greeks.** When writing code that needs Greeks, always
import from `pricing/dispatch` and call `compute_greeks()`. The only field yfinance
provides related to options pricing is `impliedVolatility`.

## Related

- `src/options_arena/pricing/dispatch.py` — Greek computation entry point
- `src/options_arena/services/options_data.py` — Option chain fetching
- CLAUDE.md principle: "yfinance option chains provide NO Greeks"

# LLM Tool Input Validation & Error Sanitization

## Problem

PydanticAI desk agent tools accept parameters from the LLM at runtime. The LLM
controls `ticker: str` and `tickers: list[str]` parameters that are passed directly
to service layer calls (yfinance, SQLite). Without validation:

1. **SSRF risk**: Arbitrary strings passed to yfinance HTTP client as URL path components.
2. **Unbounded resource consumption**: LLM can pass unlimited tickers to correlation tool.
3. **Information disclosure**: `f"Error: {exc}"` leaks internal paths, URLs, DB schema
   details through the LLM to the user.
4. **NaN propagation**: Zero prices from bad data cause division-by-zero, producing
   `nan` correlation values that confuse the LLM.

## Solution

### 1. Ticker Validation at Tool Boundary

```python
from options_arena.models.enums import TICKER_RE

def _validate_ticker(ticker: str) -> str | None:
    if not TICKER_RE.match(ticker.upper()):
        return f"Error: invalid ticker format: {ticker!r}"
    return None

async def fetch_quote(ctx: RunContext[DeskDeps], ticker: str) -> str:
    if err := _validate_ticker(ticker):
        ctx.deps.tools_used.append("fetch_quote")
        return err
    # ... proceed with validated ticker
```

### 2. Bounded Input Lists

```python
_MAX_CORRELATION_TICKERS = 5

async def fetch_correlation(ctx, ticker, tickers):
    capped = tickers[:_MAX_CORRELATION_TICKERS]
```

### 3. Sanitized Error Messages

```python
# WRONG — leaks internals
return f"Error: {exc}"

# RIGHT — generic message, full details to debug log
logger.debug("fetch_quote failed for %s: %s", ticker, exc)
return f"Error: could not fetch quote for {ticker}"
```

### 4. NaN Defense in Computed Values

```python
# Guard zero prices before division
if any(p <= 0.0 for p in prices):
    return (t, None)

# Guard non-finite correlation before formatting
if not math.isfinite(corr_val):
    lines.append(f"  {t}: N/A (unstable)")
    continue
```

## When to Apply

- Any PydanticAI tool function that accepts LLM-controlled string parameters
- Any tool that formats computed numeric values for LLM consumption
- Any error path in a tool that could expose internal state

## Files

- `src/options_arena/agents/_toolsets.py` — all 5 tool wrappers
- `src/options_arena/agents/volatility_desk.py` — desk query runner
- `src/options_arena/agents/risk_desk.py` — desk query runner

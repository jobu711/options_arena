# CLAUDE.md — Reporting

## Purpose
Generate analysis reports from debate verdicts and market data.
Every report includes metadata for reproducibility.

## Files
- `generator.py` — main report builder
- `formatters.py` — Markdown, HTML, terminal (`rich`) formatters
- ~~`disclaimer.py`~~ — removed (AUDIT-010)

## Every Report Must Include (in order)
1. **Header**: ticker, option type, strike, expiration, DTE, timestamp (UTC)
2. **Market Snapshot**: price, IV rank/percentile, key Greeks, indicators
3. **Strategy Summary**: position, max profit/loss, breakeven, probability of profit
4. **Debate Summary**: bull/bear cases condensed, winner, confidence
5. **Key Factors**: 3-5 driving data points
6. **Risk Assessment**: primary risks with quantified impact
7. **Metadata Block**: data source, timestamp, AI models + prompt versions, token usage, duration

## Display Rules
- Greeks: always with dollar-impact interpretation (theta×100 = $/day, vega×100 = $/1% IV)
- Indicators: always with signal context ("overbought", "bullish", etc.)
- Strategy P&L table when a spread is recommended
- File naming: `{TICKER}_{DATE}_{STRIKE}_{TYPE}_analysis.{ext}`

## Output Formats
- **Markdown** (default): GitHub-flavored, tables for data
- **HTML** (optional): inline CSS, no JS, print-friendly, standalone
- **Terminal**: `rich` — green=bullish, red=bearish, yellow=caution

## Disclaimer — Removed (AUDIT-010)
No disclaimer text in exports, CLI, or any rendering path.

## What Claude Gets Wrong
- Don't generate reports without metadata block
- Don't add disclaimer text (removed AUDIT-010)
- Don't show raw Greeks without dollar-impact interpretation
- Don't show indicators without signal context
- Don't omit P&L table when spread is recommended
- Don't use raw dicts — all report I/O uses typed Pydantic models

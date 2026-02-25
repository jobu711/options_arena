---
name: debate-batch-mode
status: backlog
created: 2026-02-24T21:49:24Z
progress: 0%
prd: .claude/prds/ai-debate-enhance.md
parent: .claude/epics/ai-debate-enhance/epic.md
github: [Will be updated when synced to GitHub]
---

# Epic 6: Multi-Ticker Batch Debate

## Overview

Users must manually run `options-arena debate TICKER` for each ticker after a scan. With
8+ recommendations, this is tedious. This epic adds `--batch` and `--batch-limit` flags
that debate top-scored tickers from the latest scan run sequentially.

## Scope

### PRD Requirements Covered
FR-C1 (Multi-Ticker Batch Debate)

### The Elegant Approach

**Extract `_debate_single()`.** The existing `_debate_async()` function already does:
fetch quote + info + chains -> recommend contracts -> run debate -> render. Factor this
into a reusable `_debate_single()` that takes a `TickerScore` and services, returns a
`DebateResult`. The batch loop calls it for each ticker. The single-ticker path also
calls it (no duplicate code).

```python
async def _debate_single(
    ticker_score: TickerScore,
    settings: AppSettings,
    market_data: MarketDataService,
    options_data: OptionsDataService,
    fred: FredService,
    repo: Repository,
) -> DebateResult:
    """Run a complete debate for one ticker: fetch data, run agents, persist."""
    ...
```

**Error isolation per ticker.** If AAPL's debate fails, MSFT's debate still runs.
Each ticker wrapped in try/except, failures logged and included in summary.

**Summary table at the end.** After all debates, render a compact Rich table:
ticker | direction | confidence | strategy | fallback? | duration.

### Deliverables

**`src/options_arena/cli/commands.py`** — Modify `debate` command:

```python
@app.command()
def debate(
    ticker: str | None = typer.Argument(None, help="Ticker (omit for --batch)"),
    batch: bool = typer.Option(False, "--batch", help="Debate top tickers from latest scan"),
    batch_limit: int = typer.Option(5, "--batch-limit", help="Max tickers in batch"),
    history: bool = typer.Option(False, "--history", help="Show past debates"),
    fallback_only: bool = typer.Option(False, "--fallback-only", help="Force data-driven path"),
) -> None:
```

Validation: `--batch` requires no `ticker` argument; single-ticker requires `ticker`.

Extract `_debate_single()` from existing `_debate_async()` logic. New `_batch_async()`:

```python
async def _batch_async(batch_limit: int, fallback_only: bool) -> None:
    # Load latest scan + top N scores
    # Create services once (shared across all tickers)
    # For each ticker: _debate_single() with error isolation
    # Render summary table
```

**`src/options_arena/cli/rendering.py`** — Add `render_batch_summary_table()`:

```python
def render_batch_summary_table(
    results: list[tuple[str, DebateResult | None, str | None]],  # ticker, result, error
) -> Table:
```

### Tests (~10)
- Batch with 3 mock tickers: all succeed, summary table rendered
- Batch with 1 failure: other tickers continue, failure shown in summary
- Batch with no scan data: error message
- `--batch-limit 2` limits to 2 tickers
- `--batch` without ticker argument: works
- Single ticker without `--batch`: existing behavior preserved
- `_debate_single()` returns `DebateResult` on success
- Service lifecycle: services created once, closed once (not per ticker)

### Verification Gate
```bash
uv run ruff check . --fix && uv run ruff format .
uv run pytest tests/ -v
uv run mypy src/ --strict
```

## Dependencies
- **Blocked by**: Epics 1-5 (all debate enhancements should be in place)
- **Blocks**: Epic 7 (export needs batch results)

## Key Decision
Services are created once and shared across all tickers in a batch. This avoids
creating/closing 5 services x N tickers. The existing service DI pattern supports this
naturally — services are stateless beyond their httpx client.

---
name: phase-8-cli
status: backlog
created: 2026-02-22T08:50:13Z
progress: 0%
prd: .claude/prds/options-arena.md
parent: .claude/epics/options-arena/epic.md
github: [Will be updated when synced to GitHub]
---

# Epic 8: CLI & End-to-End

## Overview

Build the thin CLI layer that wires everything together: `scan`, `health`, and `universe` commands via Typer, Rich output formatting, SIGINT graceful shutdown, and rotating file logger. Then run end-to-end verification.

## Scope

### PRD Requirements Covered
FR-C1, FR-C2, FR-C3, FR-C4, FR-C5, FR-C6, SC-1, SC-2

### Deliverables

**`src/options_arena/cli.py`:**

- `scan` command:
  - Options: `--preset full|sp500|etfs`, `--sectors` (comma-separated), `--top-n` (default 50), `--min-score` (default 0.0)
  - Creates `AppSettings()` (picks up env vars), overrides from CLI args into `ScanConfig`
  - Creates `ScanPipeline`, `CancellationToken`, `RichProgressCallback`
  - Runs pipeline, renders Rich table with results
  - Displays disclaimer (imported from future `reporting/disclaimer.py` or inline for MVP)

- `health` command:
  - Checks all services (yfinance, FRED, CBOE, Ollama)
  - Renders Rich status table (green/red per service)

- `universe` subcommands:
  - `refresh` — re-fetch CBOE universe + S&P 500 constituents
  - `list` — display tickers with `--sector`, `--preset` filters
  - `stats` — universe size, sector breakdown, S&P 500 count

- `RichProgressCallback`:
  - Implements `ProgressCallback` protocol
  - Maps phase transitions to `console.print` with Rich formatting
  - Shows current phase, progress bar or spinner

- SIGINT handler:
  - `signal.signal(SIGINT, handler)` sets `CancellationToken.cancel()`
  - Pipeline checks token between phases and exits gracefully

- Logging:
  - Rotating file handler for DEBUG output (`logs/options_arena.log`)
  - Console handler for user-facing INFO+ output
  - Suppress `aiosqlite` DEBUG noise

**Tests (`tests/unit/cli/`):**
- Command parsing: valid args, invalid args, defaults
- RichProgressCallback: protocol compliance
- SIGINT: token cancellation behavior
- ~20 tests total

**End-to-end verification:**
```bash
uv run ruff check . --fix && uv run ruff format .
uv run pytest tests/ -v
uv run mypy src/ --strict
uv run options-arena scan --preset sp500 --top-n 20
uv run options-arena health
uv run options-arena universe stats
```

### Verification Gate
All three automated checks pass AND `scan --preset sp500` produces 8+ recommendations.

## Dependencies
- **Blocked by**: All other epics (1-7) — CLI is top of stack
- **Blocks**: Nothing — this is the final epic

## Key Decisions
- CLI is thin (~300 lines) — all logic lives in `scan/`, `services/`, `scoring/`
- `print()` is allowed ONLY in `cli.py` — all library code uses `logging`
- `AppSettings()` constructed once in CLI, slices passed to modules
- No web UI — CLI only for MVP

## Estimated Tests: ~20

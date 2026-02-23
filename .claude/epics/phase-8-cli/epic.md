---
name: phase-8-cli
status: backlog
created: 2026-02-22T08:50:13Z
updated: 2026-02-23T20:47:20Z
progress: 0%
prd: .claude/prds/options-arena.md
parent: .claude/epics/options-arena/epic.md
github: https://github.com/jobu711/options_arena/issues/54
---

# Epic 8: CLI & End-to-End

## Overview

Build the thin CLI entry point that wires every module together. Three Typer commands
(`scan`, `health`, `universe`) backed by Rich rendering, dual-handler logging (RichHandler
for console + RotatingFileHandler for file), SIGINT graceful shutdown with double-press
force exit, and full service lifecycle management. Then run end-to-end verification proving
the entire pipeline produces real contract recommendations.

This is the **final epic** -- the dependency root where `AppSettings`, services, database,
and pipeline all get instantiated, used, and torn down.

**Module CLAUDE.md**: `src/options_arena/cli/CLAUDE.md` -- read before writing any code.

## Scope

### PRD Requirements Covered

| Requirement | Description |
|-------------|-------------|
| FR-C1 | `scan` command with `--preset`, `--sectors`, `--top-n`, `--min-score` options |
| FR-C2 | `health` command checking all external services |
| FR-C3 | `universe` subcommands: `refresh`, `list`, `stats` |
| FR-C4 | `RichProgressCallback` implementing `ProgressCallback` protocol |
| FR-C5 | SIGINT handler setting `CancellationToken` for graceful shutdown |
| FR-C6 | Logging: rotating file handler (DEBUG) + Rich console handler (INFO+) |
| SC-1 | All 3 verification checks pass (ruff, pytest, mypy --strict) |
| SC-2 | Scan produces 8+ contract recommendations on S&P 500 preset |
| NFR-9 | `logging` module only in library code -- `print()` reserved for `cli.py` |

---

## Deliverables

### 1. `pyproject.toml` Entry Point

```toml
[project.scripts]
options-arena = "options_arena.cli:app"
```

With `cli/` as a package, `__init__.py` re-exports `app` from `app.py`.
Typer app objects are callable. When the entry point calls `app()`, Typer handles CLI
parsing and dispatches to the matched command. Enables `uv run options-arena scan`.

### 2. `src/options_arena/cli/` package (~300-400 lines total)

| File | Purpose |
|------|---------|
| `__init__.py` | Re-exports `app` for `pyproject.toml` entry point |
| `app.py` | Typer app, `@app.callback()`, `configure_logging()` |
| `commands.py` | `scan`, `health`, `universe` commands + `_scan_async()` |
| `rendering.py` | Pure rendering: `render_scan_table()`, `render_health_table()`, disclaimer |
| `progress.py` | `RichProgressCallback` implementing `ProgressCallback` protocol |

#### Logging Configuration (FR-C6) -- `configure_logging()`

Dual-handler setup called ONCE in `@app.callback()` before any command runs:

| Handler | Type | Level | Target | Format |
|---------|------|-------|--------|--------|
| Console | `rich.logging.RichHandler` | INFO (default) or DEBUG (`--verbose`) | stderr | Rich-formatted, `datefmt="[%X]"`, `rich_tracebacks=True`, `markup=False` |
| File | `logging.handlers.RotatingFileHandler` | DEBUG (always) | `logs/options_arena.log` | `%(asctime)s \| %(levelname)-8s \| %(name)s \| %(message)s` |

**Rotation**: 5 MB max, 3 backup files, UTF-8 encoding.

**Suppressed loggers** (set to WARNING): `aiosqlite`, `httpx`, `httpcore`, `yfinance`.

**Critical details** (Context7-verified):
- `RichHandler(markup=False)` -- library log messages contain `[AAPL]` brackets that Rich
  would interpret as style tags, causing crashes. Must be `False`.
- `RichHandler(show_path=False)` -- module paths clutter terminal; they exist in the file log
  via `%(name)s`.
- `Console(stderr=True)` on RichHandler -- separates logging from data output so
  `options-arena scan > results.txt` works cleanly.
- `root.handlers.clear()` before adding -- prevents duplicate handlers on re-entry (tests).
- Never use `logging.basicConfig()` -- it conflicts with manual handler setup.

All library modules already use `logging.getLogger(__name__)` and produce log records.
`configure_logging()` determines where those records are sent. This is the stdlib best practice.

#### Global Callback -- `@app.callback()`

```python
@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show DEBUG output in console"),
) -> None:
    """Options Arena -- AI-powered American-style options analysis."""
    configure_logging(verbose=verbose)
```

Runs before ANY command. Guarantees logging is configured for `scan`, `health`, and
`universe` commands.

#### `scan` Command (FR-C1, FR-C4, FR-C5)

**CLI Options** (Context7-verified: Typer Enum support):

| Option | Type | Default | Source |
|--------|------|---------|--------|
| `--preset` | `ScanPreset` (StrEnum) | `sp500` | Typer auto-generates choices from enum |
| `--top-n` | `int` | `50` (from `ScanConfig.top_n`) | Override |
| `--min-score` | `float` | `0.0` (from `ScanConfig.min_score`) | Override |
| `--sectors` | `str \| None` | `None` | Comma-separated GICS sectors |

**Flow**:
1. Create `AppSettings()`, apply CLI arg overrides to `settings.scan`
2. Create infrastructure: `ServiceCache`, `RateLimiter`, `Database` (connect), `Repository`
3. Create services: `MarketDataService`, `OptionsDataService`, `FredService`, `UniverseService`
4. Create `ScanPipeline(settings, market_data, options_data, fred, universe_svc, repo)`
5. Set up SIGINT handler with `CancellationToken`
6. Create `RichProgressCallback` inside `Rich.Progress` context manager
7. `await pipeline.run(preset, token, callback)` -- returns `ScanResult`
8. Render results table, summary stats, disclaimer
9. Close ALL services in `finally` block
10. Restore default SIGINT handler in `finally` block

**Async wrapping** (Context7-verified: Typer does NOT natively support async reliably):
```python
@app.command()
def scan(...) -> None:
    asyncio.run(_scan_async(...))
```

Never use `async def` on Typer commands. `asyncio.run()` is the cross-platform pattern.

#### `health` Command (FR-C2)

1. Create `AppSettings()`, `HealthService(settings.service)`
2. `statuses = await health_svc.check_all()` -- concurrent, never blocks
3. Render Rich status table: service name, UP/DOWN (green/red), latency ms, error
4. Close `HealthService` in `finally`
5. Exit code 0 if all UP, 1 if any DOWN

#### `universe` Subcommands (FR-C3)

Registered as a sub-Typer:
```python
universe_app = typer.Typer(help="Manage the optionable ticker universe.", no_args_is_help=True)
app.add_typer(universe_app, name="universe")
```

| Subcommand | Options | Behavior |
|------------|---------|----------|
| `refresh` | None | Force re-fetch CBOE universe + S&P 500 constituents. Display counts. |
| `list` | `--sector`, `--preset` | Display tickers matching filters. Tabular Rich output. |
| `stats` | None | Universe size, sector breakdown, S&P 500 count. |

All require `UniverseService` (create, use, close in `finally`).

#### `RichProgressCallback` (FR-C4)

Class implementing `ProgressCallback` protocol with Rich `Progress` integration
(Context7-verified: Rich Progress with SpinnerColumn + BarColumn + TimeElapsedColumn):

```python
class RichProgressCallback:
    def __init__(self, progress: Progress) -> None:
        self._progress = progress
        self._task_ids: dict[ScanPhase, int] = {}

    def __call__(self, phase: ScanPhase, current: int, total: int) -> None:
        if phase not in self._task_ids:
            self._task_ids[phase] = self._progress.add_task(
                f"[cyan]{phase.value.title()}", total=total or None,
            )
        self._progress.update(self._task_ids[phase], completed=current, total=total)
```

Phase descriptions map to user-friendly labels:
- `UNIVERSE` -> "Fetching universe"
- `SCORING` -> "Scoring tickers"
- `OPTIONS` -> "Analyzing options"
- `PERSIST` -> "Saving results"

Progress goes to **stderr** (`Console(stderr=True)`) to avoid corrupting piped stdout.
`transient=False` keeps completed phases visible.

#### SIGINT Handler (FR-C5)

Cross-platform (Windows + Unix). Uses `signal.signal()`, NOT `loop.add_signal_handler()`
which is unsupported on Windows.

**Double-press UX convention** (Docker, npm pattern):
- First Ctrl+C: `token.cancel()`, print "[yellow]Cancelling after current phase..."
- Second Ctrl+C: `raise SystemExit(130)` (immediate force exit)

Handler is registered INSIDE the async function (after `asyncio.run()` starts) to override
asyncio's default SIGINT-to-KeyboardInterrupt behavior. Restored in `finally` block.

Exit code 130 = 128 + SIGINT(2), Unix convention.

#### Disclaimer (Regulatory)

Inline constant for MVP. Printed after every scan results table:

```python
DISCLAIMER = (
    "[dim]This tool is for educational and informational purposes only. "
    "It does not constitute financial advice. Options trading involves "
    "substantial risk of loss. Past performance does not guarantee future results.[/dim]"
)
```

#### Scan Results Rendering

Rich Table with trading-convention styling:

| Column | Justify | Style | Format |
|--------|---------|-------|--------|
| Ticker | left | bold white | `AAPL` |
| Score | right | cyan | `87.3` (1 decimal) |
| Direction | center | green/red/yellow by direction | `BULLISH` |
| Type | center | -- | `CALL` / `PUT` |
| Strike | right | -- | `$185.00` (2 decimals) |
| Exp | right | -- | `2026-04-17` |
| DTE | right | -- | `53` |
| Delta | right | -- | `0.3512` (4 decimals) |
| IV | right | -- | `32.1%` (1 decimal) |
| Bid/Ask | right | -- | `$2.45/$2.65` |

Tickers with no contract recommendation show `--` in contract columns.

Summary line after table: `"N tickers scanned, M scored, K recommendations in X.Xs"`

---

## Issue Decomposition

### Issue 1: Logging + Entry Point (~50 lines)

**Deliverables**:
- `configure_logging(verbose: bool)` function with dual handlers
- `@app.callback()` with `--verbose` flag
- `[project.scripts]` entry in `pyproject.toml`
- Typer app skeleton (`app = typer.Typer(...)`)

**Tests** (~5):
- `configure_logging()` creates RichHandler + RotatingFileHandler
- Noisy loggers suppressed to WARNING
- `--verbose` lowers console handler to DEBUG
- Log directory created if missing
- `root.handlers.clear()` prevents duplicates on re-call

**Acceptance**: `uv run options-arena --help` prints help text. Log file created in `logs/`.

---

### Issue 2: `health` Command (~40 lines)

**Deliverables**:
- `health` command: create `HealthService`, `check_all()`, render table, close
- `render_health_table(statuses)` function
- Exit code 0/1 based on service availability

**Tests** (~3):
- Command parsing (no args needed)
- Health table rendering with mixed UP/DOWN statuses
- Exit code reflects service health

**Acceptance**: `uv run options-arena health` shows service status table.

---

### Issue 3: `universe` Subcommands (~60 lines)

**Deliverables**:
- `universe_app` sub-Typer with `refresh`, `list`, `stats` commands
- Service lifecycle for each subcommand (create, use, close)
- Tabular output for `list`, summary output for `stats`

**Tests** (~3):
- `universe stats` produces output
- `universe list --sector Technology` filters correctly
- `universe refresh` triggers fetch

**Acceptance**: `uv run options-arena universe stats` shows universe breakdown.

---

### Issue 4: `RichProgressCallback` + SIGINT Handler (~50 lines)

**Deliverables**:
- `RichProgressCallback` class satisfying `ProgressCallback` protocol
- `setup_sigint_handler(token, console)` with double-press logic
- Phase-to-description mapping

**Tests** (~4):
- `RichProgressCallback` satisfies `ProgressCallback` (isinstance check)
- Phase transitions create new progress tasks
- `CancellationToken` set on first SIGINT
- Second SIGINT raises SystemExit(130)

**Acceptance**: Protocol compliance verified. SIGINT behavior tested.

---

### Issue 5: `scan` Command + Rendering (~150 lines)

**Deliverables**:
- `scan` command with full option parsing
- `_scan_async()` with service lifecycle, pipeline creation, progress, SIGINT
- `render_scan_table(result: ScanResult)` with trading-convention styling
- Summary stats line + disclaimer
- Cancelled scan handling (partial results display)

**Tests** (~5):
- Scan command parsing: valid presets, invalid preset rejection, default values
- `render_scan_table()` with mock ScanResult
- Cancelled scan displays partial results message
- Service cleanup called even on error
- Disclaimer always printed

**Acceptance**: `uv run options-arena scan --preset sp500 --top-n 20` runs the full pipeline.

**Depends on**: Issues 1, 4 (logging + progress/SIGINT must exist first).

---

### Issue 6: End-to-End Verification + Polish

**Deliverables**:
- All three verification checks pass:
  ```bash
  uv run ruff check . --fix && uv run ruff format .
  uv run pytest tests/ -v
  uv run mypy src/ --strict
  ```
- Live scan produces 8+ recommendations:
  ```bash
  uv run options-arena scan --preset sp500 --top-n 20
  uv run options-arena health
  uv run options-arena universe stats
  ```
- Fix any ruff/mypy violations introduced by `cli.py`
- Update `__init__.py` re-exports if needed

**No new tests** -- this issue verifies existing tests + live behavior.

**Depends on**: Issues 1-5 all complete.

**Acceptance**: SC-1 (all checks pass) AND SC-2 (8+ recommendations on sp500).

---

## Key Decisions

| Decision | Rationale | Context7 Source |
|----------|-----------|-----------------|
| Sync Typer commands + `asyncio.run()` | Typer async is experimental, unreliable on Windows | Typer docs -- no async examples in stable API |
| `RichHandler(markup=False)` | Library logs contain `[ticker]` brackets that crash Rich markup parser | Rich RichHandler API docs |
| `signal.signal()` not `loop.add_signal_handler()` | Windows does not support `loop.add_signal_handler()` | Python asyncio docs |
| Console logging to stderr, data to stdout | Enables `options-arena scan > results.txt` piping | Rich Console docs |
| Double-press Ctrl+C (graceful then force) | UX convention from Docker, npm, trading terminals | Industry standard |
| `RotatingFileHandler` (5MB x 3) | Prevents unbounded log growth; 3 backups = ~20MB max | Python logging docs |
| `root.handlers.clear()` before setup | Prevents duplicate handlers in tests and re-entry | stdlib logging best practice |
| No structlog | Project already uses `logging.getLogger(__name__)` in 15+ modules; adding structlog = convention change + new dep | Evaluated, rejected |
| No `.env` file | MVP uses env vars + constructor args. `env_file=".env"` added later without model changes | pydantic-settings v2 docs |

## Dependencies

- **Blocked by**: Epics 1-7 (all complete -- models, pricing, indicators, scoring, services, data, scan)
- **Blocks**: Nothing -- this is the final epic

## Estimated Tests: ~20

| Test File | Count | Coverage |
|-----------|-------|----------|
| `test_logging.py` | 5 | Handler setup, suppression, verbose flag, dir creation, idempotency |
| `test_commands.py` | 5 | Scan/health/universe arg parsing via CliRunner |
| `test_progress.py` | 3 | Protocol compliance, phase transitions, total updates |
| `test_sigint.py` | 3 | Token cancellation, double-press force exit, handler restoration |
| `test_rendering.py` | 4 | Scan table, health table, summary stats, disclaimer presence |

## Verification Gate

All three automated checks pass:
```bash
uv run ruff check . --fix && uv run ruff format .   # zero violations
uv run pytest tests/ -v                              # all tests pass (~925 total)
uv run mypy src/ --strict                            # zero type errors
```

AND live validation:
```bash
uv run options-arena scan --preset sp500 --top-n 20  # 8+ recommendations
uv run options-arena health                          # all services checked
uv run options-arena universe stats                  # universe breakdown displayed
```

## Tasks Created

- [ ] #58 - Logging + Entry Point (parallel: false) — foundation
- [ ] #59 - health Command (parallel: true) — depends on #58
- [ ] #60 - universe Subcommands (parallel: true) — depends on #58
- [ ] #55 - RichProgressCallback + SIGINT Handler (parallel: true) — depends on #58
- [ ] #56 - scan Command + Rendering (parallel: false) — depends on #58, #55
- [ ] #57 - End-to-End Verification + Polish (parallel: false) — depends on #58-#60, #55-#56

Total tasks: 6
Parallel tasks: 3 (#59, #60, #55 can run concurrently after #58)
Sequential tasks: 3 (#58, #56, #57)
Estimated total effort: 13-17 hours

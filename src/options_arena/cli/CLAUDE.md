# CLAUDE.md -- CLI Module (`cli/`)

## Purpose

The **thin top-of-stack entry point** that wires every module together. The CLI package
creates all dependencies (services, pipeline, database), runs async operations, renders
results, and tears everything down. All business logic lives in the modules below it.

The `cli/` package is the ONLY place in the project where `print()` is permitted (via
Rich `Console`). Every other module uses `logging.getLogger(__name__)`.

Use Glob to discover files. The package stays small (~6 files). Split only when a single
file exceeds ~200 lines.

---

## Architecture Rules

| Rule | Detail |
|------|--------|
| **Thin layer** | Arg parsing + service wiring + Rich rendering. Zero business logic. |
| **`print()` via Console** | Use `console.print()` (Rich), never bare `print()`. Console directs to stderr for logging, stdout for data. |
| **Sync Typer, async internals** | Typer commands are sync. Wrap async work in `asyncio.run()`. |
| **DI at the top** | `cli/` creates `AppSettings`, services, `Database`, `Repository`, `ScanPipeline`. Modules receive their config slice. |
| **Service lifecycle** | Create all services before use, close ALL in `finally` block. One leaked client = one leaked TCP connection. |
| **Config override** | CLI args override `AppSettings` defaults. Priority: CLI args > env vars > field defaults. |
| **Exit codes** | `0` = success, `1` = error, `130` = SIGINT (Unix convention). Use `raise typer.Exit(code=N)`. |

### Import Rules

`cli/` is the dependency root -- everything flows inward. Nothing imports from `cli/`.
Can import: `models/`, `services/`, `data/`, `scan/`, `agents/`, `reporting/`, `learning/`,
stdlib (`asyncio`, `logging`, `signal`, `sys`, `pathlib`), external (`typer`, `rich`).

---

## Commands

| Command | Key Flags | Purpose |
|---------|-----------|---------|
| `scan` | `--preset`, `--sector`, `--top-n`, `--min-score` | Run 4-phase pipeline |
| `health` | -- | Check all external service connectivity + latency |
| `universe` | `refresh`, `list`, `stats`, `sectors`, `index` | Manage ticker universe |
| `debate` | `--batch`, `--batch-limit`, `--export`, `--provider`, `--cost-summary` | AI recommendation (single/batch) |
| `outcomes` | `collect`, `summary`, `backtest`, `equity-curve` | Contract outcome tracking |
| `agency` | `ask`, `chat` | Interactive AI desk queries |
| `learn` | `tune-indicators`, `tune-votes`, `status`, `mine`, `playbook`, `decay` | Weight tuning, strategy mining |
| `serve` | `--host`, `--port`, `--verbose` | Launch FastAPI + Vue SPA |
| `audit` | -- | Math computation audit tools |
| `eval` | `check`, `report`, `list` | Eval harness for agent regression testing |

### Typer Pattern

Typer does NOT natively support async. Commands are synchronous wrappers:

```python
@app.command()
def scan(...) -> None:
    asyncio.run(_scan_async(...))
```

Never use `async def` on Typer commands -- experimental and unreliable on Windows.

`ScanPreset(StrEnum)` works directly with Typer. Typer auto-generates choices from members.

Global `@app.callback()` runs before ANY command -- configure logging there.

---

## Logging Configuration

### Architecture

Dual-handler setup configured in `configure_logging()`:

- **RichHandler**: stderr, INFO (or DEBUG with `--verbose`), `markup=False`, `show_path=False`,
  `rich_tracebacks=True`. Format: `"%(message)s"`.
- **RotatingFileHandler**: `logs/options_arena.log`, always DEBUG, 5 MB max, 3 backups, utf-8.
  Format: `"%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"`.

Suppressed loggers (set to WARNING): `aiosqlite`, `httpx`, `httpcore`, `yfinance`.

### Critical Rules

1. **Call `configure_logging()` in `@app.callback()`** -- runs before ANY command, guaranteeing
   all modules get proper handlers.
2. **Never call `logging.basicConfig()`** -- only works once and conflicts with manual setup.
3. **`root.handlers.clear()`** -- prevents duplicate handlers if called twice (e.g., in tests).
4. **`markup=False`** on RichHandler -- log messages from library code contain `[brackets]`
   (e.g., `log.info("Fetched [AAPL] OHLCV")`). With `markup=True`, Rich crashes or garbles.
5. **`show_path=False`** -- module paths like `options_arena.services.market_data` are noise
   in user-facing console. They're in the file log via `%(name)s`.
6. **`Console(stderr=True)`** -- Rich logging goes to stderr. Scan results to stdout.
   Enables piping: `options-arena scan --preset sp500 > results.txt`.
7. **File handler is always DEBUG** -- even without `--verbose`, every DEBUG log from every
   module goes to the rotating file. Primary debugging tool for production issues.

### What Library Modules Already Do

Every module: `logger = logging.getLogger(__name__)`. They call `logger.debug(...)`,
`logger.info(...)`, `logger.warning(...)`. They NEVER configure handlers. `cli/` is
the sole handler configurator.

---

## SIGINT / Graceful Shutdown

### Cross-Platform Pattern (Windows + Unix)

Uses `signal.signal()` (NOT `loop.add_signal_handler()` -- unsupported on Windows).

### Rules

1. **Set handler INSIDE the async function** (after `asyncio.run()` starts) -- overrides
   asyncio's default SIGINT-to-KeyboardInterrupt behavior.
2. **Double-press = force exit** -- first Ctrl+C cancels gracefully (pipeline finishes current
   phase). Second Ctrl+C terminates immediately.
3. **Restore default handler** in `finally`: `signal.signal(signal.SIGINT, signal.SIG_DFL)`.
4. **Exit code 130** for SIGINT -- Unix convention (`128 + signal number`, SIGINT = 2).
5. **`CancellationToken` is instance-scoped** -- created per scan invocation. Never global.

---

## Service Lifecycle

### Creation + Teardown

Services created in the async command function, closed in `finally`:

1. `AppSettings()` -- one per invocation, not global
2. Services: `MarketDataService`, `OptionsDataService`, `FredService`, `UniverseService`
3. `Database` + `Repository`
4. `ScanPipeline` receives all via constructor (DI pattern)

### Rules

1. **Close in `finally`** -- even on exception or cancellation, TCP connections and DB
   handles must be released.
2. **Pipeline never creates services** -- receives them via constructor.
3. **One `AppSettings()` per invocation** -- not global, not module-level.
4. **Database path** -- `data/options_arena.db` relative to CWD.

---

## Rich Output Conventions

### Rendering Rules

- Direction colors: green=BULLISH, red=BEARISH, yellow=NEUTRAL (trading convention).
- Numeric precision: scores to 1 decimal, Greeks to 4 decimals, prices to 2 decimals.
- Right-align numeric columns in tables.
- Non-finite values: check `math.isfinite()` before formatting, fall back to `"--"`.

### Progress

- Progress bars to **stderr** (`Console(stderr=True)`) -- doesn't interfere with piped stdout.
- `transient=False` -- keeps completed phases visible.
- `ProgressCallback` protocol: `__call__(phase: ScanPhase, current: int, total: int) -> None`.
- `RichProgressCallback` maps `ScanPhase` to Rich task descriptions.

### Entry Point

The `pyproject.toml` entry point `options-arena = "options_arena.cli:app"` calls
through `__init__.py` which re-exports `app` from `app.py`. Typer `app` objects are
callable -- `app()` handles CLI parsing and dispatches to matched command.

---

## Disclaimers

Removed (AUDIT-010). Do not add disclaimer text to CLI output or any rendering path.

---

## Testing Guidance (~20 tests)

### What to Test

- `configure_logging()`: handler setup (RichHandler + RotatingFileHandler), noisy logger suppression.
- Typer command parsing via `CliRunner` (mock async internals).
- `RichProgressCallback` protocol compliance.
- `CancellationToken` behavior (cancel state, non-global).
- Table rendering data transforms (input -> table rows).

### What NOT to Test

- Actual Rich rendering output (fragile, terminal-dependent).
- Actual network calls (mock services).
- `signal.signal()` directly (unreliable in pytest). Test `CancellationToken` instead.
- `asyncio.run()` -- test the async function directly with `pytest-asyncio`.

---

## What Claude Gets Wrong -- CLI-Specific (Fix These)

1. **`async def` on Typer commands** -- Typer's async support is experimental. Always sync
   commands + `asyncio.run()`. Only cross-platform-safe pattern.

2. **`logging.basicConfig()`** -- Never use it. Creates default StreamHandler conflicting with RichHandler.

3. **Forgetting `root.handlers.clear()`** -- Re-calling `configure_logging()` (tests) creates
   duplicate handlers, producing double log lines.

4. **`markup=True` on RichHandler** -- Library log messages contain `[brackets]` (ticker symbols).
   Rich interprets these as style tags, causing crashes. Always `markup=False`.

5. **Progress on stdout** -- Progress bars to stderr, results to stdout. Enables piping.

6. **Forgetting to close services** -- Every service with httpx/DB MUST close in `finally`.
   Leaked connections cause resource exhaustion.

7. **Global `CancellationToken`** -- Instance-scoped per `run()` call. A global token breaks
   if two scans ever run concurrently (future web UI scenario).

8. **`loop.add_signal_handler()`** -- NOT supported on Windows. Use `signal.signal()` only.

9. **Hardcoded thresholds in CLI** -- All defaults from `AppSettings`. Never put magic numbers
   like `top_n=50` as CLI-only defaults that diverge from `ScanConfig.top_n`.

10. **Bare `print()`** -- Never. Use `console.print()`. Ensures consistent formatting and
    respects stderr/stdout separation.

11. **Testing Rich output strings** -- Don't assert on rendered Rich text. Test the data model
    transformations instead.

12. **Adding disclaimers** -- Removed (AUDIT-010). Do not add disclaimer text to any output.

13. **`Optional[X]` syntax** -- Use `X | None`. Python 3.13+.

14. **Creating services inside the pipeline** -- Services created in `cli/` and injected.
    Pipeline never creates, configures, or closes services.

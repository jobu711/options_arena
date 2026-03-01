# CLAUDE.md -- CLI Module (`cli/`)

## Purpose

The **thin top-of-stack entry point** that wires every module together. The CLI package is the
ONLY place that touches Typer, Rich rendering, signal handling, and logging configuration. It
creates all dependencies (services, pipeline, database), runs async operations, renders results,
and tears everything down. All business logic lives in the modules below it.

The `cli/` package is also the ONLY place in the project where `print()` is permitted (via
Rich `Console`). Every other module uses `logging.getLogger(__name__)`.

## Files

| File | Purpose |
|------|---------|
| `__init__.py` | Re-exports `app` for the `pyproject.toml` entry point |
| `app.py` | Typer app instance, `@app.callback()` with `--verbose`, `configure_logging()` |
| `commands.py` | `scan`, `health`, `universe` commands + `_scan_async()` |
| `rendering.py` | Pure rendering functions: `render_scan_table()`, `render_health_table()`, disclaimer |
| `progress.py` | `RichProgressCallback` class implementing `ProgressCallback` protocol |

If the package stays small (~300-400 lines total), collapsing `app.py` + `commands.py` into
a single `app.py` is acceptable. Split only if any single file exceeds ~200 lines.

---

## Architecture Rules

| Rule | Detail |
|------|--------|
| **Thin layer** | Arg parsing + service wiring + Rich rendering. Zero business logic. |
| **`print()` via Console** | Use `console.print()` (Rich), never bare `print()`. Console directs to stderr for logging, stdout for data. |
| **Sync Typer, async internals** | Typer commands are sync. Wrap async work in `asyncio.run()`. |
| **DI at the top** | `cli/` creates `AppSettings`, services, `Database`, `Repository`, `ScanPipeline`. Modules receive their config slice. |
| **Service lifecycle** | Create all services before use, close ALL in `finally` block. One leaked client = one leaked TCP connection. |
| **Config override** | CLI args override `AppSettings` defaults. Env vars override field defaults. Priority: CLI args > env vars > field defaults. |
| **Exit codes** | `0` = success, `1` = error, `130` = SIGINT (Unix convention). Use `raise typer.Exit(code=N)`. |

### Import Rules

| Can Import From | Cannot Import From |
|----------------|-------------------|
| `models/` (all models, enums, config) | Nothing imports from `cli/` |
| `services/` (all service classes, cache, rate limiter) | |
| `data/` (Database, Repository) | |
| `scan/` (ScanPipeline, ScanPhase, CancellationToken, ProgressCallback, ScanResult) | |
| stdlib: `asyncio`, `logging`, `signal`, `sys`, `pathlib` | |
| External: `typer`, `rich` (Console, Table, Progress, Panel, Text, RichHandler) | |

`cli/` is the dependency root -- everything flows inward. Nothing imports from it.

---

## Logging Configuration (Context7-Verified)

### Architecture

```
+--------------------------------------------------------------+
|                     Root Logger                               |
|  Level: DEBUG (capture everything from all modules)           |
+----------------------------+---------------------------------+
|   RichHandler              |    RotatingFileHandler           |
|   Level: INFO (default)    |    Level: DEBUG                  |
|   or DEBUG (--verbose)     |    -> logs/options_arena.log     |
|   -> stderr                |    maxBytes: 5_242_880 (5 MB)   |
|   format: "%(message)s"   |    backupCount: 3                |
|   datefmt: "[%X]"         |    encoding: utf-8               |
|   rich_tracebacks=True     |    format: see below             |
|   markup=False             |                                  |
|   show_path=False          |                                  |
+----------------------------+---------------------------------+

Suppressed loggers (set to WARNING):
  - aiosqlite     -- floods DEBUG with every SQL statement
  - httpx         -- floods DEBUG with request/response details
  - yfinance      -- floods DEBUG with download progress
  - httpcore      -- floods DEBUG with connection pool events
```

### Implementation Pattern (Context7-Verified: Rich RichHandler)

```python
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler

LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "options_arena.log"
FILE_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
NOISY_LOGGERS = ("aiosqlite", "httpx", "httpcore", "yfinance")


def configure_logging(*, verbose: bool = False) -> None:
    """Configure dual-handler logging: Rich console + rotating file.

    Must be called ONCE at CLI startup before any module code runs.
    All library modules already use ``logging.getLogger(__name__)`` --
    this function configures where those log records are sent.

    Args:
        verbose: If True, lower console handler to DEBUG. File handler
                 is always DEBUG regardless.
    """
    LOG_DIR.mkdir(exist_ok=True)

    # Root logger captures everything
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers.clear()  # Prevent duplicate handlers on re-entry

    # Console handler: Rich-formatted, INFO+ by default
    console_handler = RichHandler(
        level=logging.DEBUG if verbose else logging.INFO,
        console=Console(stderr=True),
        show_time=True,
        show_level=True,
        show_path=False,        # Module paths clutter the terminal
        markup=False,           # Don't interpret [tags] in log messages as Rich markup
        rich_tracebacks=True,
        tracebacks_show_locals=False,
    )
    console_handler.setFormatter(logging.Formatter("%(message)s", datefmt="[%X]"))

    # File handler: plain text, DEBUG, rotating
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=5_242_880,     # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(FILE_FORMAT, datefmt="%Y-%m-%d %H:%M:%S"))

    root.addHandler(console_handler)
    root.addHandler(file_handler)

    # Suppress noisy third-party loggers
    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
```

### Critical Rules

1. **Call `configure_logging()` in `@app.callback()`** -- this runs before ANY command, guaranteeing
   all modules get proper handlers even for `health` or `universe` commands.
2. **Never call `logging.basicConfig()`** -- it only works once and conflicts with manual setup.
3. **`root.handlers.clear()`** -- prevents duplicate handlers if `configure_logging` is called
   twice (e.g., in tests).
4. **`markup=False`** on RichHandler -- log messages from library code may contain `[brackets]`
   (e.g., `log.info("Fetched [AAPL] OHLCV")`). With `markup=True`, Rich interprets these as
   style tags and crashes or garbles output.
5. **`show_path=False`** -- module paths like `options_arena.services.market_data` add noise
   to user-facing console output. They're useful in the file log (via `%(name)s` in format).
6. **`Console(stderr=True)`** -- Rich logging goes to stderr. Scan result tables go to stdout.
   This lets users pipe results: `options-arena scan --preset sp500 > results.txt`.
7. **File handler is always DEBUG** -- even without `--verbose`, every log from every module
   (including DEBUG from pricing/scoring/services) goes to the rotating file. This is the
   primary debugging tool for production issues.

### What Library Modules Already Do

Every module in the project follows this pattern:

```python
import logging
logger = logging.getLogger(__name__)
```

They call `logger.debug(...)`, `logger.info(...)`, `logger.warning(...)`. They NEVER configure
handlers. `cli/` is the sole handler configurator. This is the stdlib logging best practice.

---

## Typer Command Structure (Context7-Verified)

### App + Subcommand Pattern

```python
import typer

app = typer.Typer(
    name="options-arena",
    help="AI-powered American-style options analysis.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

universe_app = typer.Typer(
    help="Manage the optionable ticker universe.",
    no_args_is_help=True,
)
app.add_typer(universe_app, name="universe")
```

### Async Wrapping (Context7-Verified: Typer does not natively support async)

Typer commands are synchronous. The scan pipeline, service calls, and database are all async.
Bridge with `asyncio.run()`:

```python
@app.command()
def scan(
    preset: ScanPreset = typer.Option(ScanPreset.SP500, help="Scan preset"),
    top_n: int = typer.Option(50, "--top-n", help="Top N tickers for options analysis"),
    min_score: float = typer.Option(0.0, "--min-score", help="Minimum composite score"),
    sectors: str | None = typer.Option(None, "--sectors", help="Comma-separated GICS sectors"),
) -> None:
    """Run the full scan pipeline: universe -> scoring -> options -> persist."""
    asyncio.run(_scan_async(preset, top_n, min_score, sectors))
```

**Never use `async def` on a Typer command.** Typer's async support is experimental and
unreliable on Windows. `asyncio.run()` is the battle-tested cross-platform pattern.

### Enum Options (Context7-Verified)

`ScanPreset(StrEnum)` works directly with Typer. Typer auto-generates choices from enum members:

```python
preset: ScanPreset = typer.Option(ScanPreset.SP500, help="Scan preset: full, sp500, etfs")
```

The CLI user types `--preset sp500` and Typer converts to `ScanPreset.SP500`.

### Global Callback for Pre-Command Setup

```python
@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show DEBUG output in console"),
) -> None:
    """Options Arena -- AI-powered American-style options analysis."""
    configure_logging(verbose=verbose)
```

The callback runs before ANY command. This guarantees logging is configured for `scan`,
`health`, and `universe` commands alike.

---

## Rich Output Patterns (Context7-Verified)

### Console Instances

```python
# Shared console for user-facing output (stdout)
console = Console()

# Errors and warnings go to stderr
err_console = Console(stderr=True)
```

### Scan Results Table

```python
from rich.table import Table
from rich.text import Text

def render_scan_table(result: ScanResult) -> Table:
    """Render scan results as a Rich table.

    Financial conventions:
    - Green for BULLISH, red for BEARISH, yellow for NEUTRAL
    - Scores to 1 decimal, Greeks to 4 decimals, prices to 2 decimals
    - Right-align numeric columns
    """
    table = Table(title=f"Scan Results -- {result.scan_run.preset.upper()}")

    table.add_column("Ticker", style="bold white", no_wrap=True)
    table.add_column("Score", justify="right", style="cyan")
    table.add_column("Direction", justify="center")
    table.add_column("Type", justify="center")
    table.add_column("Strike", justify="right")
    table.add_column("Exp", justify="right")
    table.add_column("DTE", justify="right")
    table.add_column("Delta", justify="right")
    table.add_column("IV", justify="right")
    table.add_column("Bid/Ask", justify="right")

    # Direction color mapping (trading convention)
    direction_styles = {
        "bullish": "bold green",
        "bearish": "bold red",
        "neutral": "bold yellow",
    }

    for score in result.scores:
        contracts = result.recommendations.get(score.ticker, [])
        # ... build rows with styled Text objects
    return table
```

### Health Status Table

```python
def render_health_table(statuses: list[HealthStatus]) -> Table:
    table = Table(title="Service Health")
    table.add_column("Service", style="bold")
    table.add_column("Status", justify="center")
    table.add_column("Latency", justify="right")
    table.add_column("Error")

    for s in statuses:
        status_text = Text("UP", style="bold green") if s.available else Text("DOWN", style="bold red")
        latency = f"{s.latency_ms:.0f}ms" if s.latency_ms is not None else "--"
        table.add_row(s.service_name, status_text, latency, s.error or "")
    return table
```

### Progress Callback (Context7-Verified: Rich Progress)

```python
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn

class RichProgressCallback:
    """Maps ProgressCallback protocol to Rich Progress display.

    Satisfies: ProgressCallback Protocol
      def __call__(self, phase: ScanPhase, current: int, total: int) -> None
    """

    def __init__(self, progress: Progress) -> None:
        self._progress = progress
        self._task_ids: dict[ScanPhase, int] = {}

    def __call__(self, phase: ScanPhase, current: int, total: int) -> None:
        if phase not in self._task_ids:
            description = {
                ScanPhase.UNIVERSE: "[cyan]Fetching universe",
                ScanPhase.SCORING:  "[cyan]Scoring tickers",
                ScanPhase.OPTIONS:  "[cyan]Analyzing options",
                ScanPhase.PERSIST:  "[cyan]Saving results",
            }[phase]
            self._task_ids[phase] = self._progress.add_task(
                description, total=total or None
            )
        self._progress.update(self._task_ids[phase], completed=current, total=total)
```

Usage in scan command:

```python
with Progress(
    SpinnerColumn(),
    TextColumn("[progress.description]{task.description}"),
    BarColumn(),
    TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
    TimeElapsedColumn(),
    console=Console(stderr=True),
    transient=False,
) as progress:
    callback = RichProgressCallback(progress)
    result = await pipeline.run(preset, token, callback)
```

Key: Progress goes to **stderr** (`Console(stderr=True)`) so it doesn't interfere with
piped stdout. `transient=False` keeps completed phases visible.

---

## SIGINT / Graceful Shutdown

### Cross-Platform Pattern (Windows + Unix)

```python
import signal
from types import FrameType

def setup_sigint_handler(
    token: CancellationToken,
    console: Console,
) -> None:
    """Register Ctrl+C handler. First press = graceful cancel, second = force exit.

    Uses signal.signal() (not loop.add_signal_handler()) because
    loop.add_signal_handler() is NOT supported on Windows.
    """
    sigint_count = 0

    def handler(signum: int, frame: FrameType | None) -> None:
        nonlocal sigint_count
        sigint_count += 1
        if sigint_count == 1:
            token.cancel()
            console.print("\n[yellow]Cancelling after current phase completes...[/]")
        else:
            console.print("\n[red]Force exit.[/]")
            raise SystemExit(130)

    signal.signal(signal.SIGINT, handler)
```

### Rules

1. **Set handler INSIDE the async function** (after `asyncio.run()` starts) -- this overrides
   asyncio's default SIGINT-to-KeyboardInterrupt behavior.
2. **Double-press = force exit** -- UX convention from Docker, npm, etc. First Ctrl+C cancels
   gracefully (pipeline finishes current phase). Second Ctrl+C terminates immediately.
3. **Restore default handler** in `finally` block: `signal.signal(signal.SIGINT, signal.SIG_DFL)`.
4. **Exit code 130** for SIGINT -- Unix convention (`128 + signal number`, SIGINT = 2).
5. **`CancellationToken` is instance-scoped** -- created per scan invocation. Never global.

---

## Service Lifecycle

### Creation + Teardown Pattern

```python
async def _scan_async(preset: ScanPreset, ...) -> None:
    settings = AppSettings()
    # Override from CLI args
    settings.scan.top_n = top_n

    cache = ServiceCache(settings.service)
    limiter = RateLimiter(settings.service.rate_limit_rps, settings.service.max_concurrent_requests)
    db = Database("data/options_arena.db")
    await db.connect()
    repo = Repository(db)

    market_data = MarketDataService(settings.service, cache, limiter)
    options_data = OptionsDataService(settings.service, cache, limiter)
    fred = FredService(settings.service, cache, limiter)
    universe_svc = UniverseService(settings.service, cache, limiter)

    pipeline = ScanPipeline(settings, market_data, options_data, fred, universe_svc, repo)

    try:
        # ... run pipeline, render results
        pass
    finally:
        # Close ALL services -- order doesn't matter, just close them
        await market_data.close()
        await options_data.close()
        await fred.close()
        await universe_svc.close()
        await db.close()
```

### Rules

1. **Close in `finally`** -- even on exception or cancellation, TCP connections and DB handles
   must be released.
2. **Pipeline never creates services** -- it receives them via constructor (DI pattern).
3. **One `AppSettings()` per invocation** -- not global, not module-level. Created in the command function.
4. **Database path** -- `data/options_arena.db` relative to CWD. `Database` class handles WAL mode and migrations.

---

## Entry Point Configuration

Add to `pyproject.toml`:

```toml
[project.scripts]
options-arena = "options_arena.cli:app"
```

With `cli/` as a package, `__init__.py` re-exports `app`:

```python
# src/options_arena/cli/__init__.py
from options_arena.cli.app import app

__all__ = ["app"]
```

This lets users run `uv run options-arena scan --preset sp500` after install.
Typer app objects are callable -- when the entry point calls `app()`, Typer's
`__call__` method handles CLI parsing and dispatches to the matched command.

---

## Testing Patterns (~20 tests)

### Test Structure

```
tests/unit/cli/
    __init__.py
    test_logging.py        # configure_logging() handler setup
    test_commands.py        # Typer command parsing via CliRunner
    test_progress.py        # RichProgressCallback protocol compliance
    test_sigint.py          # CancellationToken + handler behavior
    test_rendering.py       # Table rendering functions (pure, no async)
```

### Typer Testing (Context7-Verified)

```python
from typer.testing import CliRunner
from options_arena.cli import app

runner = CliRunner()

def test_scan_default_args() -> None:
    # Mock the async internals, test arg parsing only
    result = runner.invoke(app, ["scan"])
    assert result.exit_code == 0

def test_scan_invalid_preset() -> None:
    result = runner.invoke(app, ["scan", "--preset", "invalid"])
    assert result.exit_code != 0
```

### Logging Tests

```python
def test_configure_logging_creates_two_handlers(tmp_path: Path) -> None:
    """Verify dual-handler setup: RichHandler + RotatingFileHandler."""
    # Monkeypatch LOG_DIR to tmp_path
    configure_logging(verbose=False)
    root = logging.getLogger()
    handler_types = {type(h).__name__ for h in root.handlers}
    assert "RichHandler" in handler_types
    assert "RotatingFileHandler" in handler_types

def test_noisy_loggers_suppressed() -> None:
    configure_logging()
    for name in ("aiosqlite", "httpx", "httpcore", "yfinance"):
        assert logging.getLogger(name).level >= logging.WARNING
```

### Progress Tests

```python
def test_rich_progress_callback_protocol_compliance() -> None:
    """RichProgressCallback satisfies ProgressCallback Protocol."""
    from options_arena.scan.progress import ProgressCallback
    # ... construct with mock Progress, verify isinstance check
    assert isinstance(callback, ProgressCallback)
```

### What NOT to Test

- Don't test actual Rich rendering output (fragile, changes with terminal width).
- Don't test actual network calls (mock services in integration tests, not CLI unit tests).
- Don't test `signal.signal()` directly (unreliable in pytest). Test `CancellationToken` behavior instead.
- Don't test `asyncio.run()` -- test the async function directly with `pytest-asyncio`.

---

## Disclaimer — Removed (AUDIT-010)

Disclaimers were removed in the production-audit epic per PRD decision. No disclaimer
text should be added to CLI output or any rendering path.

---

## What Claude Gets Wrong -- CLI-Specific (Fix These)

1. **`async def` on Typer commands** -- Typer's async support is experimental. Always use sync
   commands + `asyncio.run()`. This is the only cross-platform-safe pattern.

2. **`logging.basicConfig()`** -- Never use it. It only works on the first call and creates a
   default StreamHandler that conflicts with RichHandler. Use manual root logger configuration.

3. **Forgetting `root.handlers.clear()`** -- Without this, re-calling `configure_logging()` (e.g.,
   in tests) creates duplicate handlers, producing double log lines.

4. **`markup=True` on RichHandler** -- Library log messages contain `[brackets]` (ticker symbols,
   config keys). Rich interprets these as style tags, causing crashes or garbled output. Always
   `markup=False`.

5. **Progress on stdout** -- Progress bars and spinners must go to stderr. Results tables go to
   stdout. This enables piping: `options-arena scan > results.txt` without progress bar corruption.

6. **Forgetting to close services** -- Every service with an httpx client or DB connection MUST be
   closed in a `finally` block. Leaked connections cause resource exhaustion on repeated invocations.

7. **Global `CancellationToken`** -- Token is instance-scoped, created per `run()` call. A global
   token breaks if two scans ever run concurrently (future web UI scenario).

8. **`loop.add_signal_handler()`** -- NOT supported on Windows. Use `signal.signal()` only.

9. **Hardcoded thresholds in CLI** -- All defaults come from `AppSettings` field defaults. CLI
   options override them. Never put magic numbers like `top_n=50` as CLI-only defaults that
   diverge from `ScanConfig.top_n`.

10. **Printing without Rich** -- Never bare `print()`. Use `console.print()` for all user output.
    This ensures consistent formatting and respects stderr/stdout separation.

11. **Testing Rich output strings** -- Don't assert on rendered Rich text (terminal-dependent).
    Test the data model transformations (input -> table rows) instead.

12. **Adding disclaimers** -- Disclaimers were removed (AUDIT-010). Do not add disclaimer text to any output.

13. **`Optional[X]` syntax** -- Use `X | None`. Never import from `typing`. Python 3.13+.

14. **Creating services inside the pipeline** -- Services are created in `cli/` and injected.
    Pipeline never creates, configures, or closes services.

"""Typer application instance and dual-handler logging configuration.

The ``@app.callback()`` runs before ANY command, guaranteeing all modules
get proper handlers even for ``health`` or ``universe`` commands.
"""

import atexit
import logging
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
from pathlib import Path
from queue import Queue

import typer
from rich.console import Console
from rich.logging import RichHandler

# Resolve log directory from project root (src/options_arena/cli/app.py → parents[3])
LOG_DIR = Path(__file__).resolve().parents[3] / "logs"
LOG_FILE = LOG_DIR / "options_arena.log"
FILE_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
NOISY_LOGGERS = ("aiosqlite", "httpx", "httpcore", "yfinance")

# Module-level listener reference so atexit can stop it
_queue_listener: QueueListener | None = None

app = typer.Typer(
    name="options-arena",
    help="Options Arena -- AI-powered American-style options analysis.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


def configure_logging(*, verbose: bool = False, json_mode: bool = False) -> None:
    """Configure dual-handler logging: Rich console + queue-backed rotating file.

    The file handler runs inside a ``QueueListener`` on a separate thread,
    avoiding Windows file-locking issues with ``RotatingFileHandler`` when
    log rotation occurs under concurrent writes.

    Must be called ONCE at CLI startup before any module code runs.
    All library modules already use ``logging.getLogger(__name__)`` --
    this function configures where those log records are sent.

    Args:
        verbose: If True, lower console handler to DEBUG. File handler
                 is always DEBUG regardless.
        json_mode: If True, use JSON formatting for the file handler
                   instead of plain text.
    """
    global _queue_listener  # noqa: PLW0603

    # Stop any existing listener from a previous call (e.g. tests)
    if _queue_listener is not None:
        _queue_listener.stop()
        _queue_listener = None

    LOG_DIR.mkdir(exist_ok=True)

    # Root logger captures everything
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    for h in root.handlers[:]:
        h.close()
    root.handlers.clear()  # Prevent duplicate handlers on re-entry

    # Console handler: Rich-formatted, INFO+ by default
    console_handler = RichHandler(
        level=logging.DEBUG if verbose else logging.INFO,
        console=Console(stderr=True),
        show_time=True,
        show_level=True,
        show_path=False,
        markup=False,
        rich_tracebacks=True,
        tracebacks_show_locals=False,
    )
    console_handler.setFormatter(logging.Formatter("%(message)s", datefmt="[%X]"))

    # File handler: plain text or JSON, DEBUG, rotating — runs inside QueueListener
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=5_242_880,  # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)

    if json_mode:
        from pythonjsonlogger.json import JsonFormatter  # noqa: PLC0415

        json_formatter = JsonFormatter(
            fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
            rename_fields={"asctime": "timestamp", "levelname": "level"},
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(json_formatter)
    else:
        file_handler.setFormatter(logging.Formatter(FILE_FORMAT, datefmt="%Y-%m-%d %H:%M:%S"))

    # QueueHandler + QueueListener: file handler runs on a separate thread,
    # avoiding Windows file-locking issues during log rotation.
    log_queue: Queue[logging.LogRecord] = Queue()
    queue_handler = QueueHandler(log_queue)
    queue_handler.setLevel(logging.DEBUG)

    _queue_listener = QueueListener(log_queue, file_handler, respect_handler_level=True)
    _queue_listener.start()
    atexit.register(_queue_listener.stop)

    root.addHandler(console_handler)
    root.addHandler(queue_handler)

    # Suppress noisy third-party loggers
    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show DEBUG output in console"),
    json_log: bool = typer.Option(False, "--json-log", help="Enable JSON-formatted file logging"),
) -> None:
    """Options Arena -- AI-powered American-style options analysis."""
    configure_logging(verbose=verbose, json_mode=json_log)

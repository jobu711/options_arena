"""Rich progress bar integration and SIGINT signal handling for CLI.

``RichProgressCallback`` maps ``ScanPhase`` updates to Rich Progress bar tasks.
``setup_sigint_handler`` implements double-press Ctrl+C: graceful then force.
"""

from __future__ import annotations

import signal
from types import FrameType

from rich.console import Console
from rich.progress import Progress, TaskID

from options_arena.scan.progress import CancellationToken, ScanPhase

# Phase-to-description mapping (user-friendly labels)
_PHASE_DESCRIPTIONS: dict[ScanPhase, str] = {
    ScanPhase.UNIVERSE: "[cyan]Fetching universe",
    ScanPhase.SCORING: "[cyan]Scoring tickers",
    ScanPhase.OPTIONS: "[cyan]Analyzing options",
    ScanPhase.PERSIST: "[cyan]Saving results",
}


class RichProgressCallback:
    """Maps ProgressCallback protocol to Rich Progress display.

    Satisfies the ``ProgressCallback`` protocol from ``scan/progress.py``::

        def __call__(self, phase: ScanPhase, current: int, total: int) -> None

    Args:
        progress: Rich Progress instance to update.
    """

    def __init__(self, progress: Progress) -> None:
        self._progress = progress
        self._task_ids: dict[ScanPhase, TaskID] = {}

    def __call__(self, phase: ScanPhase, current: int, total: int) -> None:
        """Report progress for the given scan phase."""
        effective_total = total if total > 0 else None
        if phase not in self._task_ids:
            description = _PHASE_DESCRIPTIONS.get(phase, f"[cyan]{phase.value.title()}")
            self._task_ids[phase] = self._progress.add_task(
                description,
                total=effective_total,
            )
        self._progress.update(self._task_ids[phase], completed=current, total=effective_total)


def setup_sigint_handler(
    token: CancellationToken,
    console: Console,
) -> None:
    """Register Ctrl+C handler. First press = graceful cancel, second = force exit.

    Uses ``signal.signal()`` (not ``loop.add_signal_handler()``) because
    ``loop.add_signal_handler()`` is NOT supported on Windows.

    Args:
        token: CancellationToken to set on first Ctrl+C.
        console: Rich Console for printing cancellation messages.
    """
    sigint_count = 0

    def handler(signum: int, frame: FrameType | None) -> None:
        nonlocal sigint_count
        sigint_count += 1
        if sigint_count == 1:
            token.cancel()
            console.print("\n[yellow]Cancelling after current phase completes...[/yellow]")
        else:
            console.print("\n[red]Force exit.[/red]")
            raise SystemExit(130)

    signal.signal(signal.SIGINT, handler)

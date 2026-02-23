"""Scan pipeline progress tracking — ScanPhase enum, CancellationToken, ProgressCallback.

Provides the foundational types used by all scan pipeline modules:
  - ``ScanPhase`` — StrEnum for the 4 pipeline phases.
  - ``CancellationToken`` — thread-safe, instance-scoped cancellation.
  - ``ProgressCallback`` — framework-agnostic progress reporting protocol.
"""

from __future__ import annotations

import threading
from enum import StrEnum
from typing import Protocol, runtime_checkable


class ScanPhase(StrEnum):
    """The four sequential phases of a scan pipeline run."""

    UNIVERSE = "universe"
    SCORING = "scoring"
    OPTIONS = "options"
    PERSIST = "persist"


class CancellationToken:
    """Thread-safe, instance-scoped cancellation for scan pipeline.

    Created per ``ScanPipeline.run()`` invocation.  The CLI hooks ``Ctrl+C``
    to call ``token.cancel()``.  The pipeline checks ``is_cancelled`` between
    phases (not mid-phase).
    """

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        """Signal cancellation.  Idempotent — safe to call multiple times."""
        self._event.set()

    @property
    def is_cancelled(self) -> bool:
        """Check whether cancellation was requested."""
        return self._event.is_set()


@runtime_checkable
class ProgressCallback(Protocol):
    """Framework-agnostic callback for reporting scan progress.

    Parameters
    ----------
    phase : ScanPhase
        Current pipeline phase.
    current : int
        Items processed so far within the phase.
    total : int
        Total items expected for the phase.
    """

    def __call__(self, phase: ScanPhase, current: int, total: int) -> None: ...

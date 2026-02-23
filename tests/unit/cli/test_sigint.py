"""Tests for setup_sigint_handler — CancellationToken integration and double-press behavior."""

from __future__ import annotations

import signal
from unittest.mock import MagicMock

import pytest

from options_arena.cli.progress import setup_sigint_handler
from options_arena.scan.progress import CancellationToken


@pytest.fixture(autouse=True)
def _restore_sigint_handler() -> None:  # noqa: ANN202
    """Save and restore the original SIGINT handler so tests don't break pytest."""
    original = signal.getsignal(signal.SIGINT)
    yield  # type: ignore[misc]
    signal.signal(signal.SIGINT, original)


def test_cancellation_token_set_on_first_call() -> None:
    """First Ctrl+C sets the CancellationToken."""
    token = CancellationToken()
    console = MagicMock()

    setup_sigint_handler(token, console)
    handler = signal.getsignal(signal.SIGINT)
    assert callable(handler)

    # Simulate first Ctrl+C
    handler(signal.SIGINT, None)

    assert token.is_cancelled is True
    console.print.assert_called_once()


def test_second_call_raises_system_exit_130() -> None:
    """Second Ctrl+C raises SystemExit(130)."""
    token = CancellationToken()
    console = MagicMock()

    setup_sigint_handler(token, console)
    handler = signal.getsignal(signal.SIGINT)
    assert callable(handler)

    # First press — graceful cancel
    handler(signal.SIGINT, None)

    # Second press — force exit
    with pytest.raises(SystemExit, match="130"):
        handler(signal.SIGINT, None)


def test_handler_registered_as_sigint() -> None:
    """After setup, signal.getsignal(SIGINT) returns our custom handler."""
    token = CancellationToken()
    console = MagicMock()

    setup_sigint_handler(token, console)
    handler = signal.getsignal(signal.SIGINT)

    # Must not be the default or SIG_IGN — it should be our custom handler
    assert handler is not signal.SIG_DFL
    assert handler is not signal.SIG_IGN
    assert callable(handler)

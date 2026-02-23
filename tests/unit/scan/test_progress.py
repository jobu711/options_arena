"""Unit tests for options_arena.scan.progress.

Tests ScanPhase enum, CancellationToken, and ProgressCallback protocol.
"""

from __future__ import annotations

import threading
from enum import StrEnum

from options_arena.scan.progress import CancellationToken, ProgressCallback, ScanPhase

# ---------------------------------------------------------------------------
# ScanPhase (4 members)
# ---------------------------------------------------------------------------


class TestScanPhase:
    def test_scan_phase_has_exactly_four_members(self) -> None:
        assert len(ScanPhase) == 4

    def test_scan_phase_values_are_lowercase(self) -> None:
        assert ScanPhase.UNIVERSE == "universe"
        assert ScanPhase.SCORING == "scoring"
        assert ScanPhase.OPTIONS == "options"
        assert ScanPhase.PERSIST == "persist"

    def test_scan_phase_is_str_enum(self) -> None:
        assert issubclass(ScanPhase, StrEnum)

    def test_scan_phase_exhaustive_iteration(self) -> None:
        assert set(ScanPhase) == {
            ScanPhase.UNIVERSE,
            ScanPhase.SCORING,
            ScanPhase.OPTIONS,
            ScanPhase.PERSIST,
        }

    def test_scan_phase_string_serialization(self) -> None:
        assert str(ScanPhase.UNIVERSE) == "universe"
        assert str(ScanPhase.SCORING) == "scoring"
        assert str(ScanPhase.OPTIONS) == "options"
        assert str(ScanPhase.PERSIST) == "persist"

    def test_scan_phase_members_accessible_by_name(self) -> None:
        assert ScanPhase["UNIVERSE"] is ScanPhase.UNIVERSE
        assert ScanPhase["SCORING"] is ScanPhase.SCORING
        assert ScanPhase["OPTIONS"] is ScanPhase.OPTIONS
        assert ScanPhase["PERSIST"] is ScanPhase.PERSIST

    def test_scan_phase_importable_from_package(self) -> None:
        """Verify re-export from scan package __init__.py."""
        from options_arena.scan import ScanPhase as ReExported

        assert ReExported is ScanPhase


# ---------------------------------------------------------------------------
# CancellationToken
# ---------------------------------------------------------------------------


class TestCancellationToken:
    def test_starts_not_cancelled(self) -> None:
        token = CancellationToken()
        assert token.is_cancelled is False

    def test_cancel_sets_is_cancelled(self) -> None:
        token = CancellationToken()
        token.cancel()
        assert token.is_cancelled is True

    def test_cancel_is_idempotent(self) -> None:
        token = CancellationToken()
        token.cancel()
        token.cancel()
        assert token.is_cancelled is True

    def test_multiple_tokens_are_independent(self) -> None:
        token_a = CancellationToken()
        token_b = CancellationToken()

        token_a.cancel()

        assert token_a.is_cancelled is True
        assert token_b.is_cancelled is False

    def test_cancel_visible_from_another_thread(self) -> None:
        token = CancellationToken()
        seen: list[bool] = []

        def worker() -> None:
            token.cancel()

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(timeout=2.0)

        seen.append(token.is_cancelled)
        assert seen == [True]

    def test_is_cancelled_before_cancel_from_thread(self) -> None:
        """A thread can observe not-cancelled then cancelled in order."""
        token = CancellationToken()
        observations: list[bool] = []
        barrier = threading.Barrier(2, timeout=2.0)

        def observer() -> None:
            observations.append(token.is_cancelled)
            barrier.wait()  # sync: main thread will cancel
            barrier.wait()  # sync: main thread has cancelled
            observations.append(token.is_cancelled)

        thread = threading.Thread(target=observer)
        thread.start()

        barrier.wait()  # observer recorded first observation
        token.cancel()
        barrier.wait()  # let observer record second observation

        thread.join(timeout=2.0)
        assert observations == [False, True]

    def test_importable_from_package(self) -> None:
        from options_arena.scan import CancellationToken as ReExported

        assert ReExported is CancellationToken


# ---------------------------------------------------------------------------
# ProgressCallback Protocol
# ---------------------------------------------------------------------------


class RecordingCallback:
    """Test helper that records all (phase, current, total) invocations."""

    def __init__(self) -> None:
        self.calls: list[tuple[ScanPhase, int, int]] = []

    def __call__(self, phase: ScanPhase, current: int, total: int) -> None:
        self.calls.append((phase, current, total))


class TestProgressCallback:
    def test_recording_callback_satisfies_protocol(self) -> None:
        recorder = RecordingCallback()
        assert isinstance(recorder, ProgressCallback)

    def test_recording_callback_records_invocations(self) -> None:
        recorder = RecordingCallback()
        recorder(ScanPhase.UNIVERSE, 0, 100)
        recorder(ScanPhase.UNIVERSE, 50, 100)
        recorder(ScanPhase.UNIVERSE, 100, 100)

        assert len(recorder.calls) == 3
        assert recorder.calls[0] == (ScanPhase.UNIVERSE, 0, 100)
        assert recorder.calls[1] == (ScanPhase.UNIVERSE, 50, 100)
        assert recorder.calls[2] == (ScanPhase.UNIVERSE, 100, 100)

    def test_plain_function_satisfies_protocol(self) -> None:
        def noop_callback(phase: ScanPhase, current: int, total: int) -> None:
            pass

        assert isinstance(noop_callback, ProgressCallback)

    def test_lambda_satisfies_protocol(self) -> None:
        cb = lambda phase, current, total: None  # noqa: E731
        assert isinstance(cb, ProgressCallback)

    def test_importable_from_package(self) -> None:
        from options_arena.scan import ProgressCallback as ReExported

        assert ReExported is ProgressCallback

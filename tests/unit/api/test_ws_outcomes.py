"""Tests for WebSocket bridge outcomes_collected and scan background outcome injection."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from options_arena.api.ws import WebSocketProgressBridge
from options_arena.models import ScanPreset, ScanRun, ScanSource
from options_arena.models.analytics import ContractOutcome
from options_arena.models.enums import OutcomeCollectionMethod
from options_arena.scan import ScanResult


def _make_scan_run(*, scan_id: int = 42) -> ScanRun:
    """Create a minimal ScanRun for testing."""
    return ScanRun(
        id=scan_id,
        started_at=datetime(2026, 3, 7, 12, 0, 0, tzinfo=UTC),
        completed_at=datetime(2026, 3, 7, 12, 5, 0, tzinfo=UTC),
        preset=ScanPreset.SP500,
        source=ScanSource.MANUAL,
        tickers_scanned=100,
        tickers_scored=50,
        recommendations=10,
    )


def _make_scan_result(*, cancelled: bool = False, scan_id: int = 42) -> ScanResult:
    """Create a minimal ScanResult for testing."""
    return ScanResult(
        scan_run=_make_scan_run(scan_id=scan_id),
        scores=[],
        recommendations={},
        risk_free_rate=0.05,
        cancelled=cancelled,
        phases_completed=4,
    )


def _make_mock_outcome(*, rc_id: int = 1) -> ContractOutcome:
    """Create a minimal ContractOutcome for testing."""
    return ContractOutcome(
        id=1,
        recommended_contract_id=rc_id,
        holding_days=5,
        collection_method=OutcomeCollectionMethod.MARKET,
        collected_at=datetime(2026, 3, 7, 12, 10, 0, tzinfo=UTC),
    )


# ---------------------------------------------------------------------------
# WebSocketProgressBridge.complete() — outcomes_collected parameter
# ---------------------------------------------------------------------------


class TestWsBridgeOutcomesCollected:
    """Tests for outcomes_collected in WebSocketProgressBridge.complete()."""

    def test_complete_includes_outcomes_collected(self) -> None:
        """Verify outcomes_collected appears in queue payload."""
        bridge = WebSocketProgressBridge()
        bridge.complete(42, cancelled=False, outcomes_collected=5)
        event = bridge.queue.get_nowait()
        assert "outcomes_collected" in event
        assert event["outcomes_collected"] == 5

    def test_complete_default_zero(self) -> None:
        """Verify outcomes_collected defaults to 0 when not passed."""
        bridge = WebSocketProgressBridge()
        bridge.complete(42, cancelled=False)
        event = bridge.queue.get_nowait()
        assert event["outcomes_collected"] == 0

    def test_complete_with_nonzero_outcomes(self) -> None:
        """Verify outcomes_collected carries through with positive value."""
        bridge = WebSocketProgressBridge()
        bridge.complete(99, cancelled=True, outcomes_collected=17)
        event = bridge.queue.get_nowait()
        assert event["type"] == "complete"
        assert event["scan_id"] == 99
        assert event["cancelled"] is True
        assert event["outcomes_collected"] == 17


# ---------------------------------------------------------------------------
# _run_scan_background — outcome collection injection
# ---------------------------------------------------------------------------


class TestScanBackgroundOutcomeCollection:
    """Tests for outcome collection in _run_scan_background()."""

    @pytest.mark.asyncio
    async def test_collects_outcomes_on_success(self) -> None:
        """Verify collect_outcomes() called after successful non-cancelled scan."""
        from options_arena.api.routes.scan import _run_scan_background

        result = _make_scan_result(cancelled=False, scan_id=42)
        mock_pipeline = MagicMock()
        mock_pipeline.run = AsyncMock(return_value=result)

        mock_collector_instance = MagicMock()
        mock_collector_instance.collect_outcomes = AsyncMock(return_value=[])

        bridge = WebSocketProgressBridge()
        lock = asyncio.Lock()
        await lock.acquire()

        # Build mock request with app.state
        mock_analytics = MagicMock()
        mock_analytics.collection_timeout = 120.0
        mock_request = MagicMock()
        mock_request.app.state.settings.analytics = mock_analytics
        mock_request.app.state.repo = MagicMock()
        mock_request.app.state.market_data = MagicMock()
        mock_request.app.state.options_data = MagicMock()
        mock_request.app.state.active_scans = {1: MagicMock()}
        mock_request.app.state.scan_queues = {1: bridge.queue}

        with patch(
            "options_arena.api.routes.scan.OutcomeCollector",
            return_value=mock_collector_instance,
        ) as mock_oc_class:
            await _run_scan_background(
                mock_request,
                1,
                ScanPreset.SP500,
                ScanSource.MANUAL,
                MagicMock(),
                bridge,
                mock_pipeline,
                lock,
            )

        mock_oc_class.assert_called_once_with(
            config=mock_analytics,
            repository=mock_request.app.state.repo,
            market_data=mock_request.app.state.market_data,
            options_data=mock_request.app.state.options_data,
        )
        mock_collector_instance.collect_outcomes.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_outcomes_on_cancel(self) -> None:
        """Verify collection skipped when result.cancelled is True."""
        from options_arena.api.routes.scan import _run_scan_background

        result = _make_scan_result(cancelled=True, scan_id=42)
        mock_pipeline = MagicMock()
        mock_pipeline.run = AsyncMock(return_value=result)

        bridge = WebSocketProgressBridge()
        lock = asyncio.Lock()
        await lock.acquire()

        mock_request = MagicMock()
        mock_request.app.state.active_scans = {1: MagicMock()}
        mock_request.app.state.scan_queues = {1: bridge.queue}

        with patch(
            "options_arena.api.routes.scan.OutcomeCollector",
        ) as mock_oc_class:
            await _run_scan_background(
                mock_request,
                1,
                ScanPreset.SP500,
                ScanSource.MANUAL,
                MagicMock(),
                bridge,
                mock_pipeline,
                lock,
            )

        mock_oc_class.assert_not_called()

    @pytest.mark.asyncio
    async def test_outcomes_count_passed_to_bridge(self) -> None:
        """Verify len(outcomes) passed as outcomes_collected to bridge.complete()."""
        from options_arena.api.routes.scan import _run_scan_background

        outcomes = [_make_mock_outcome(rc_id=i) for i in range(3)]
        result = _make_scan_result(cancelled=False, scan_id=42)
        mock_pipeline = MagicMock()
        mock_pipeline.run = AsyncMock(return_value=result)

        mock_collector_instance = MagicMock()
        mock_collector_instance.collect_outcomes = AsyncMock(return_value=outcomes)

        bridge = WebSocketProgressBridge()
        lock = asyncio.Lock()
        await lock.acquire()

        mock_analytics = MagicMock()
        mock_analytics.collection_timeout = 120.0
        mock_request = MagicMock()
        mock_request.app.state.settings.analytics = mock_analytics
        mock_request.app.state.repo = MagicMock()
        mock_request.app.state.market_data = MagicMock()
        mock_request.app.state.options_data = MagicMock()
        mock_request.app.state.active_scans = {1: MagicMock()}
        mock_request.app.state.scan_queues = {1: bridge.queue}

        with patch(
            "options_arena.api.routes.scan.OutcomeCollector",
            return_value=mock_collector_instance,
        ):
            await _run_scan_background(
                mock_request,
                1,
                ScanPreset.SP500,
                ScanSource.MANUAL,
                MagicMock(),
                bridge,
                mock_pipeline,
                lock,
            )

        # Drain the queue and find the complete event
        event = bridge.queue.get_nowait()
        assert event["type"] == "complete"
        assert event["outcomes_collected"] == 3

    @pytest.mark.asyncio
    async def test_outcomes_failure_nonfatal(self) -> None:
        """Verify scan succeeds even if collect_outcomes() raises."""
        from options_arena.api.routes.scan import _run_scan_background

        result = _make_scan_result(cancelled=False, scan_id=42)
        mock_pipeline = MagicMock()
        mock_pipeline.run = AsyncMock(return_value=result)

        mock_collector_instance = MagicMock()
        mock_collector_instance.collect_outcomes = AsyncMock(
            side_effect=RuntimeError("DB connection lost")
        )

        bridge = WebSocketProgressBridge()
        lock = asyncio.Lock()
        await lock.acquire()

        mock_analytics = MagicMock()
        mock_analytics.collection_timeout = 120.0
        mock_request = MagicMock()
        mock_request.app.state.settings.analytics = mock_analytics
        mock_request.app.state.repo = MagicMock()
        mock_request.app.state.market_data = MagicMock()
        mock_request.app.state.options_data = MagicMock()
        mock_request.app.state.active_scans = {1: MagicMock()}
        mock_request.app.state.scan_queues = {1: bridge.queue}

        with patch(
            "options_arena.api.routes.scan.OutcomeCollector",
            return_value=mock_collector_instance,
        ):
            # Should NOT raise — the exception is caught internally
            await _run_scan_background(
                mock_request,
                1,
                ScanPreset.SP500,
                ScanSource.MANUAL,
                MagicMock(),
                bridge,
                mock_pipeline,
                lock,
            )

        # The complete event should still be sent with outcomes_collected=0
        event = bridge.queue.get_nowait()
        assert event["type"] == "complete"
        assert event["scan_id"] == 42
        assert event["outcomes_collected"] == 0
        assert event["cancelled"] is False

    @pytest.mark.asyncio
    async def test_pipeline_failure_emits_error_then_complete(self) -> None:
        """Verify outer pipeline.run() failure emits error + complete events."""
        from options_arena.api.routes.scan import _run_scan_background

        mock_pipeline = MagicMock()
        mock_pipeline.run = AsyncMock(side_effect=RuntimeError("Pipeline exploded"))

        bridge = WebSocketProgressBridge()
        lock = asyncio.Lock()
        await lock.acquire()

        mock_request = MagicMock()
        mock_request.app.state.active_scans = {1: MagicMock()}
        mock_request.app.state.scan_queues = {1: bridge.queue}

        with patch(
            "options_arena.api.routes.scan.OutcomeCollector",
        ) as mock_oc_class:
            await _run_scan_background(
                mock_request,
                1,
                ScanPreset.SP500,
                ScanSource.MANUAL,
                MagicMock(),
                bridge,
                mock_pipeline,
                lock,
            )

        # OutcomeCollector should never be constructed when pipeline fails
        mock_oc_class.assert_not_called()

        # First event: error
        error_event = bridge.queue.get_nowait()
        assert error_event["type"] == "error"

        # Second event: complete with outcomes_collected=0
        complete_event = bridge.queue.get_nowait()
        assert complete_event["type"] == "complete"
        assert complete_event["scan_id"] == 1
        assert complete_event["cancelled"] is False
        assert complete_event["outcomes_collected"] == 0

    @pytest.mark.asyncio
    async def test_outcomes_timeout_nonfatal(self) -> None:
        """Verify scan succeeds if collect_outcomes() times out."""
        from options_arena.api.routes.scan import _run_scan_background

        result = _make_scan_result(cancelled=False, scan_id=42)
        mock_pipeline = MagicMock()
        mock_pipeline.run = AsyncMock(return_value=result)

        mock_collector_instance = MagicMock()
        mock_collector_instance.collect_outcomes = AsyncMock(
            side_effect=TimeoutError("collection timed out")
        )

        bridge = WebSocketProgressBridge()
        lock = asyncio.Lock()
        await lock.acquire()

        mock_request = MagicMock()
        mock_request.app.state.settings.analytics = MagicMock()
        mock_request.app.state.settings.analytics.collection_timeout = 1.0
        mock_request.app.state.repo = MagicMock()
        mock_request.app.state.market_data = MagicMock()
        mock_request.app.state.options_data = MagicMock()
        mock_request.app.state.active_scans = {1: MagicMock()}
        mock_request.app.state.scan_queues = {1: bridge.queue}

        with patch(
            "options_arena.api.routes.scan.OutcomeCollector",
            return_value=mock_collector_instance,
        ):
            await _run_scan_background(
                mock_request,
                1,
                ScanPreset.SP500,
                ScanSource.MANUAL,
                MagicMock(),
                bridge,
                mock_pipeline,
                lock,
            )

        event = bridge.queue.get_nowait()
        assert event["type"] == "complete"
        assert event["scan_id"] == 42
        assert event["outcomes_collected"] == 0
        assert event["cancelled"] is False

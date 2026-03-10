"""Tests for OutcomeCollector auto-scheduler.

Covers:
  - AnalyticsConfig auto_collect_enabled default is False.
  - AnalyticsConfig auto_collect_hour_utc accepts 0-23, rejects 24 and -1.
  - _seconds_until_next_run when target hour is in the future today.
  - _seconds_until_next_run when target hour has passed today (next day).
  - _seconds_until_next_run when exactly at the target hour (next day).
  - run_scheduler calls collect_outcomes once before cancellation.
  - run_scheduler handles CancelledError cleanly.
  - run_scheduler recovers from collect_outcomes errors.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from options_arena.models.config import AnalyticsConfig
from options_arena.services.outcome_collector import OutcomeCollector

# ---------------------------------------------------------------------------
# TestSchedulerConfig
# ---------------------------------------------------------------------------


class TestSchedulerConfig:
    """Validate AnalyticsConfig auto-collect fields."""

    def test_default_disabled(self) -> None:
        """AnalyticsConfig() has auto_collect_enabled=False by default."""
        config = AnalyticsConfig()
        assert config.auto_collect_enabled is False

    def test_default_hour(self) -> None:
        """AnalyticsConfig() has auto_collect_hour_utc=6 by default."""
        config = AnalyticsConfig()
        assert config.auto_collect_hour_utc == 6

    @pytest.mark.parametrize("hour", [0, 1, 6, 12, 23])
    def test_valid_hour(self, hour: int) -> None:
        """Hours 0-23 are accepted."""
        config = AnalyticsConfig(auto_collect_hour_utc=hour)
        assert config.auto_collect_hour_utc == hour

    def test_invalid_hour_rejected(self) -> None:
        """Hour 24 raises ValidationError."""
        with pytest.raises(ValidationError, match="must be 0-23"):
            AnalyticsConfig(auto_collect_hour_utc=24)

    def test_negative_hour_rejected(self) -> None:
        """Hour -1 raises ValidationError."""
        with pytest.raises(ValidationError, match="must be 0-23"):
            AnalyticsConfig(auto_collect_hour_utc=-1)


# ---------------------------------------------------------------------------
# TestSecondsUntilNextRun
# ---------------------------------------------------------------------------


def _make_collector(hour: int = 6) -> OutcomeCollector:
    """Build an OutcomeCollector with minimal mocks for scheduler testing."""
    config = AnalyticsConfig(auto_collect_hour_utc=hour)
    repo = MagicMock()
    market_data = MagicMock()
    return OutcomeCollector(
        config=config,
        repository=repo,
        market_data=market_data,
    )


class TestSecondsUntilNextRun:
    """Validate _seconds_until_next_run() time calculation."""

    def test_future_today(self) -> None:
        """When target hour is later today, returns seconds until that hour."""
        collector = _make_collector(hour=15)
        # Mock: it's currently 10:00:00 UTC
        mock_now = datetime(2026, 3, 9, 10, 0, 0, tzinfo=UTC)
        with patch(
            "options_arena.services.outcome_collector.datetime",
        ) as mock_dt:
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            seconds = collector._seconds_until_next_run()

        # Expect ~5 hours = 18000 seconds
        assert seconds == pytest.approx(5 * 3600, abs=1.0)

    def test_past_today(self) -> None:
        """When target hour has passed today, returns seconds until tomorrow."""
        collector = _make_collector(hour=6)
        # Mock: it's currently 20:00:00 UTC
        mock_now = datetime(2026, 3, 9, 20, 0, 0, tzinfo=UTC)
        with patch(
            "options_arena.services.outcome_collector.datetime",
        ) as mock_dt:
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            seconds = collector._seconds_until_next_run()

        # 20:00 today -> 06:00 tomorrow = 10 hours = 36000 seconds
        assert seconds == pytest.approx(10 * 3600, abs=1.0)

    def test_exactly_now(self) -> None:
        """When exactly at target hour, schedules for next day (~24 hours)."""
        collector = _make_collector(hour=6)
        # Mock: it's exactly 06:00:00 UTC
        mock_now = datetime(2026, 3, 9, 6, 0, 0, tzinfo=UTC)
        with patch(
            "options_arena.services.outcome_collector.datetime",
        ) as mock_dt:
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            seconds = collector._seconds_until_next_run()

        # Exactly at target hour -> next day = 24 hours = 86400 seconds
        assert seconds == pytest.approx(24 * 3600, abs=1.0)


# ---------------------------------------------------------------------------
# TestRunScheduler
# ---------------------------------------------------------------------------


_SLEEP_PATCH = "options_arena.services.outcome_collector.asyncio.sleep"


class TestRunScheduler:
    """Validate run_scheduler() loop behavior."""

    @pytest.mark.asyncio
    async def test_single_cycle(self) -> None:
        """Scheduler calls collect_outcomes once, then stops on CancelledError."""
        collector = _make_collector(hour=6)
        collector.collect_outcomes = AsyncMock(return_value=[])  # type: ignore[method-assign]
        collector._seconds_until_next_run = MagicMock(return_value=0.0)  # type: ignore[method-assign]

        call_count = 0

        async def fake_sleep(seconds: float) -> None:
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise asyncio.CancelledError

        with patch(_SLEEP_PATCH, side_effect=fake_sleep):
            await collector.run_scheduler()

        collector.collect_outcomes.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancellation(self) -> None:
        """Scheduler exits cleanly on CancelledError during sleep."""
        collector = _make_collector(hour=6)
        collector._seconds_until_next_run = MagicMock(return_value=0.0)  # type: ignore[method-assign]

        async def cancel_immediately(seconds: float) -> None:
            raise asyncio.CancelledError

        with patch(_SLEEP_PATCH, side_effect=cancel_immediately):
            # Should not raise — clean exit
            await collector.run_scheduler()

    @pytest.mark.asyncio
    async def test_error_recovery(self) -> None:
        """Scheduler continues after collect_outcomes raises an exception."""
        collector = _make_collector(hour=6)
        collector._seconds_until_next_run = MagicMock(return_value=0.0)  # type: ignore[method-assign]

        call_count = 0
        collect_call_count = 0

        async def fake_collect(
            holding_days: int | None = None,
        ) -> list[object]:
            nonlocal collect_call_count
            collect_call_count += 1
            if collect_call_count == 1:
                raise RuntimeError("simulated failure")
            return []

        collector.collect_outcomes = AsyncMock(side_effect=fake_collect)  # type: ignore[method-assign]

        async def fake_sleep(seconds: float) -> None:
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                raise asyncio.CancelledError

        with patch(_SLEEP_PATCH, side_effect=fake_sleep):
            await collector.run_scheduler()

        # collect_outcomes was called twice: first raises, second succeeds
        assert collect_call_count == 2

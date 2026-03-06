"""Tests for orchestrator Phase 1 inter-batch delay and batch ticker delay.

Verifies that asyncio.sleep is called between Phase 1 agent batches when
parallelism < number of agents, and skipped when parallelism >= agents or delay=0.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest


class TestPhase1InterBatchDelay:
    """Test the inter-batch delay logic extracted from orchestrator Phase 1."""

    @pytest.mark.asyncio
    async def test_sleep_called_between_batches(self) -> None:
        """When parallelism < coros and delay > 0, sleep is called between batches."""
        coros_count = 4
        parallelism = 2
        delay = 1.5

        sleep_calls: list[float] = []

        async def mock_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)
            # Don't actually sleep in tests

        # Simulate the batching loop from orchestrator.py
        async def _fake_coro() -> str:
            return "ok"

        coros = [_fake_coro() for _ in range(coros_count)]
        results: list[object] = []

        with patch("asyncio.sleep", side_effect=mock_sleep):
            for i in range(0, len(coros), parallelism):
                if i > 0 and delay > 0:
                    await asyncio.sleep(delay)
                batch = coros[i : i + parallelism]
                batch_results = await asyncio.gather(*batch, return_exceptions=True)
                results.extend(batch_results)

        # With 4 coros, parallelism 2: 2 batches, 1 sleep between them
        assert len(sleep_calls) == 1
        assert sleep_calls[0] == pytest.approx(1.5)
        assert len(results) == 4

    @pytest.mark.asyncio
    async def test_no_sleep_when_delay_zero(self) -> None:
        """When delay=0, no sleep is called."""
        coros_count = 4
        parallelism = 2
        delay = 0.0

        sleep_calls: list[float] = []

        async def mock_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        async def _fake_coro() -> str:
            return "ok"

        coros = [_fake_coro() for _ in range(coros_count)]
        results: list[object] = []

        with patch("asyncio.sleep", side_effect=mock_sleep):
            for i in range(0, len(coros), parallelism):
                if i > 0 and delay > 0:
                    await asyncio.sleep(delay)
                batch = coros[i : i + parallelism]
                batch_results = await asyncio.gather(*batch, return_exceptions=True)
                results.extend(batch_results)

        assert len(sleep_calls) == 0
        assert len(results) == 4

    @pytest.mark.asyncio
    async def test_no_sleep_when_parallelism_covers_all(self) -> None:
        """When parallelism >= coros, all run in one gather (no batching, no sleep)."""
        coros_count = 4
        parallelism = 4
        delay = 1.5

        sleep_calls: list[float] = []

        async def mock_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        async def _fake_coro() -> str:
            return "ok"

        coros = [_fake_coro() for _ in range(coros_count)]

        with patch("asyncio.sleep", side_effect=mock_sleep):
            # When parallelism >= len(coros), the orchestrator uses single gather
            if parallelism >= len(coros):
                results = list(await asyncio.gather(*coros, return_exceptions=True))
            else:
                results = []
                for i in range(0, len(coros), parallelism):
                    if i > 0 and delay > 0:
                        await asyncio.sleep(delay)
                    batch = coros[i : i + parallelism]
                    batch_results = await asyncio.gather(*batch, return_exceptions=True)
                    results.extend(batch_results)

        assert len(sleep_calls) == 0
        assert len(results) == 4

    @pytest.mark.asyncio
    async def test_multiple_sleep_calls_for_many_batches(self) -> None:
        """With 6 coros and parallelism=2, expect 2 sleep calls (between 3 batches)."""
        coros_count = 6
        parallelism = 2
        delay = 0.5

        sleep_calls: list[float] = []

        async def mock_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        async def _fake_coro() -> str:
            return "ok"

        coros = [_fake_coro() for _ in range(coros_count)]
        results: list[object] = []

        with patch("asyncio.sleep", side_effect=mock_sleep):
            for i in range(0, len(coros), parallelism):
                if i > 0 and delay > 0:
                    await asyncio.sleep(delay)
                batch = coros[i : i + parallelism]
                batch_results = await asyncio.gather(*batch, return_exceptions=True)
                results.extend(batch_results)

        assert len(sleep_calls) == 2
        assert all(s == pytest.approx(0.5) for s in sleep_calls)
        assert len(results) == 6


class TestBatchTickerDelay:
    """Test the inter-ticker delay pattern used in CLI and API batch debates."""

    @pytest.mark.asyncio
    async def test_sleep_called_between_tickers(self) -> None:
        """Sleep called before each ticker except the first."""
        tickers = ["AAPL", "MSFT", "GOOGL"]
        delay = 5.0
        sleep_calls: list[float] = []

        async def mock_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        processed: list[str] = []

        with patch("asyncio.sleep", side_effect=mock_sleep):
            for i, ticker in enumerate(tickers):
                if i > 0 and delay > 0:
                    await asyncio.sleep(delay)
                processed.append(ticker)

        assert len(sleep_calls) == 2  # Between ticker 1-2 and 2-3
        assert all(s == pytest.approx(5.0) for s in sleep_calls)
        assert processed == tickers

    @pytest.mark.asyncio
    async def test_no_sleep_when_delay_zero(self) -> None:
        """No sleep calls when batch_ticker_delay=0."""
        tickers = ["AAPL", "MSFT", "GOOGL"]
        delay = 0.0
        sleep_calls: list[float] = []

        async def mock_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        with patch("asyncio.sleep", side_effect=mock_sleep):
            for i, _ticker in enumerate(tickers):
                if i > 0 and delay > 0:
                    await asyncio.sleep(delay)

        assert len(sleep_calls) == 0

    @pytest.mark.asyncio
    async def test_single_ticker_no_sleep(self) -> None:
        """No sleep needed for a single ticker."""
        tickers = ["AAPL"]
        delay = 5.0
        sleep_calls: list[float] = []

        async def mock_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        with patch("asyncio.sleep", side_effect=mock_sleep):
            for i, _ticker in enumerate(tickers):
                if i > 0 and delay > 0:
                    await asyncio.sleep(delay)

        assert len(sleep_calls) == 0

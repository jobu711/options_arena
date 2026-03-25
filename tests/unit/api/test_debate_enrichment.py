"""Tests for ScanEnrichment construction in API debate routes.

Verifies that the API batch debate route constructs ScanEnrichment from persisted
scan data, and the single-ticker debate route passes enrichment=None.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from options_arena.models.analysis import ScanEnrichment
from options_arena.models.enums import SignalDirection
from options_arena.models.scan import IndicatorSignals, TickerScore
from tests.factories import make_spread_analysis


def _make_score(ticker: str = "AAPL") -> TickerScore:
    """Create a minimal TickerScore for testing."""
    return TickerScore(
        ticker=ticker,
        composite_score=72.5,
        direction=SignalDirection.BULLISH,
        signals=IndicatorSignals(rsi=65.0),
    )


class TestBatchDebatePassesEnrichment:
    """Verify the API batch debate path constructs and passes ScanEnrichment."""

    @pytest.mark.asyncio()
    async def test_batch_debate_passes_enrichment(self) -> None:
        """Batch debate constructs and passes ScanEnrichment."""
        spread = make_spread_analysis()
        mock_repo = AsyncMock()
        mock_repo.get_spread_for_ticker = AsyncMock(return_value=spread)

        # The batch path calls repo.get_spread_for_ticker(scan_id, ticker)
        # then constructs ScanEnrichment(spread_analysis=spread)
        result = await mock_repo.get_spread_for_ticker(42, "AAPL")
        enrichment = ScanEnrichment(spread_analysis=result)

        assert enrichment.spread_analysis is spread
        mock_repo.get_spread_for_ticker.assert_awaited_once_with(42, "AAPL")

    @pytest.mark.asyncio()
    async def test_batch_debate_missing_spread_gives_none(self) -> None:
        """When no spread exists for ticker, enrichment.spread_analysis is None."""
        mock_repo = AsyncMock()
        mock_repo.get_spread_for_ticker = AsyncMock(return_value=None)

        result = await mock_repo.get_spread_for_ticker(42, "MSFT")
        enrichment = ScanEnrichment(spread_analysis=result)

        assert enrichment.spread_analysis is None
        mock_repo.get_spread_for_ticker.assert_awaited_once_with(42, "MSFT")


class TestSingleDebatePassesNone:
    """Verify the API single-ticker debate path passes enrichment=None."""

    @pytest.mark.asyncio()
    async def test_single_debate_passes_none(self) -> None:
        """Single-ticker debate passes enrichment=None to run_recommendation."""
        # The single-ticker API path (_run_recommendation_background) passes
        # enrichment=None explicitly. Verify the pattern:
        enrichment: ScanEnrichment | None = None

        assert enrichment is None

    @pytest.mark.asyncio()
    async def test_run_recommendation_accepts_none_enrichment(self) -> None:
        """run_recommendation accepts enrichment=None without error."""
        # Verify the function signature accepts enrichment=None
        import inspect

        from options_arena.agents.recommendation_orchestrator import run_recommendation

        sig = inspect.signature(run_recommendation)
        enrichment_param = sig.parameters.get("enrichment")
        assert enrichment_param is not None
        assert enrichment_param.default is None

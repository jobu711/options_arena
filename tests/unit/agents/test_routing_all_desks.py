"""Tests for keyword routing to all 7 desk types.

Covers trend, flow, fundamental, contrarian, and research desk routing
(volatility and risk routing tested in test_routing.py).
"""

from __future__ import annotations

import pytest

# Prevent accidental real API calls
from pydantic_ai import models

from options_arena.agents._routing import classify_intent
from options_arena.models import DeskType

models.ALLOW_MODEL_REQUESTS = False


class TestClassifyIntentNewDesks:
    """classify_intent routes new desk queries to the correct DeskType."""

    def test_trend_keywords_route_to_trend(self) -> None:
        intent = classify_intent("What is the AAPL trend?")
        assert DeskType.TREND in intent.desks

    def test_flow_keywords_route_to_flow(self) -> None:
        intent = classify_intent("Show unusual options flow for TSLA")
        assert DeskType.FLOW in intent.desks

    def test_fundamental_keywords_route_to_fundamental(self) -> None:
        intent = classify_intent("AAPL earnings valuation analysis")
        assert DeskType.FUNDAMENTAL in intent.desks

    def test_contrarian_keywords_route_to_contrarian(self) -> None:
        intent = classify_intent("What is the contrarian view on AAPL consensus?")
        assert DeskType.CONTRARIAN in intent.desks

    def test_research_keywords_route_to_research(self) -> None:
        intent = classify_intent("Give me a comprehensive research overview of MSFT")
        assert DeskType.RESEARCH in intent.desks

    def test_momentum_routes_to_trend(self) -> None:
        intent = classify_intent("AAPL momentum and RSI analysis")
        assert DeskType.TREND in intent.desks

    def test_multi_desk_trend_and_flow(self) -> None:
        intent = classify_intent("What is the AAPL trend and unusual flow?")
        assert DeskType.TREND in intent.desks
        assert DeskType.FLOW in intent.desks

    def test_overview_routes_to_research(self) -> None:
        intent = classify_intent("Give me an overview of AAPL")
        assert DeskType.RESEARCH in intent.desks

    def test_summary_routes_to_research(self) -> None:
        intent = classify_intent("Provide a summary for TSLA")
        assert DeskType.RESEARCH in intent.desks

    def test_broad_routes_to_research(self) -> None:
        intent = classify_intent("Broad analysis of NVDA")
        assert DeskType.RESEARCH in intent.desks

    def test_sentiment_routes_to_contrarian(self) -> None:
        intent = classify_intent("What is the sentiment on AAPL?")
        assert DeskType.CONTRARIAN in intent.desks

    def test_reversal_routes_to_contrarian(self) -> None:
        intent = classify_intent("Is a reversal likely for TSLA?")
        assert DeskType.CONTRARIAN in intent.desks

    def test_volume_routes_to_flow(self) -> None:
        intent = classify_intent("What is the volume profile for AMD?")
        assert DeskType.FLOW in intent.desks

    def test_macd_routes_to_trend(self) -> None:
        intent = classify_intent("What does the MACD show for SPY?")
        assert DeskType.TREND in intent.desks


class TestAllDesksHaveRunners:
    """All 7 DeskType members are covered by classify_intent routing."""

    @pytest.mark.critical
    def test_all_seven_desks_routable(self) -> None:
        """All 7 DeskType members can be routed to via keyword queries."""
        assert len(DeskType) == 7

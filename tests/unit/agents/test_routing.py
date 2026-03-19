"""Tests for intent classification and routing orchestrator.

Covers classify_intent keyword routing, ticker extraction, query type inference,
multi-desk routing, defaults, and run_agency_query orchestration.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai import models

from options_arena.models import (
    AgencyConfig,
    AgencyQuery,
    DeskResponse,
    DeskType,
    QueryType,
)

models.ALLOW_MODEL_REQUESTS = False


class TestClassifyIntentVolatility:
    """classify_intent routes volatility-related queries to VOLATILITY desk."""

    def test_iv_keyword(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("What's AAPL's IV rank?")
        assert DeskType.VOLATILITY in intent.desks

    def test_vega_keyword(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("Check vega exposure on SPY")
        assert DeskType.VOLATILITY in intent.desks

    def test_implied_vol_keyword(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("Is implied vol elevated for MSFT?")
        assert DeskType.VOLATILITY in intent.desks

    def test_vol_surface_keyword(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("Show me the vol surface for TSLA")
        assert DeskType.VOLATILITY in intent.desks

    def test_volatility_keyword(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("What is the volatility for AAPL?")
        assert DeskType.VOLATILITY in intent.desks

    def test_skew_keyword(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("What does the skew look like?")
        assert DeskType.VOLATILITY in intent.desks

    def test_term_structure_keyword(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("How's the term structure looking?")
        assert DeskType.VOLATILITY in intent.desks


class TestClassifyIntentRisk:
    """classify_intent routes risk-related queries to RISK desk."""

    def test_risk_keyword(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("Analyze risk for TSLA")
        assert DeskType.RISK in intent.desks

    def test_hedge_keyword(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("How should I hedge my AAPL position?")
        assert DeskType.RISK in intent.desks

    def test_exposure_keyword(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("What's my portfolio exposure?")
        assert DeskType.RISK in intent.desks

    def test_drawdown_keyword(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("What is the drawdown risk here?")
        assert DeskType.RISK in intent.desks

    def test_position_size_keyword(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("What position size should I use?")
        assert DeskType.RISK in intent.desks


class TestClassifyIntentOtherDesks:
    """classify_intent routes to trend, flow, fundamental, contrarian desks."""

    def test_trend_keyword(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("What's the trend for NVDA?")
        assert DeskType.TREND in intent.desks

    def test_momentum_keyword(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("Check momentum on QQQ")
        assert DeskType.TREND in intent.desks

    def test_macd_keyword(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("What does the MACD say?")
        assert DeskType.TREND in intent.desks

    def test_flow_keyword(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("Any unusual activity in AMD?")
        assert DeskType.FLOW in intent.desks

    def test_open_interest_keyword(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("Show open interest for AAPL")
        assert DeskType.FLOW in intent.desks

    def test_fundamental_keyword(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("What are GOOG's earnings looking like?")
        assert DeskType.FUNDAMENTAL in intent.desks

    def test_valuation_keyword(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("How is the valuation for META?")
        assert DeskType.FUNDAMENTAL in intent.desks

    def test_contrarian_keyword(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("Is the sentiment overcrowded on META?")
        assert DeskType.CONTRARIAN in intent.desks

    def test_reversal_keyword(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("Is a reversal coming?")
        assert DeskType.CONTRARIAN in intent.desks


class TestClassifyIntentTickerExtraction:
    """classify_intent extracts tickers from queries."""

    def test_dollar_sign_ticker(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("What's $AAPL IV rank?")
        assert "AAPL" in intent.tickers

    def test_standalone_uppercase_ticker(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("Analyze TSLA volatility")
        assert "TSLA" in intent.tickers

    def test_multiple_tickers(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("Compare $AAPL and $MSFT volatility")
        assert "AAPL" in intent.tickers
        assert "MSFT" in intent.tickers

    def test_excludes_common_words(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("What IV rank for AAPL?")
        assert "IV" not in intent.tickers
        assert "AAPL" in intent.tickers

    def test_no_tickers_in_query(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("How does volatility work?")
        assert intent.tickers == []

    def test_duplicate_dollar_tickers_deduplicated(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("$AAPL $AAPL volatility")
        assert intent.tickers.count("AAPL") == 1

    def test_excludes_rsi_as_ticker(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("What's the RSI for AAPL?")
        assert "RSI" not in intent.tickers
        assert "AAPL" in intent.tickers

    def test_excludes_adx_as_ticker(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("Check ADX for TSLA")
        assert "ADX" not in intent.tickers
        assert "TSLA" in intent.tickers


class TestClassifyIntentQueryType:
    """classify_intent infers query type from keywords."""

    def test_comparison_query(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("Compare AAPL vs MSFT")
        assert intent.query_type == QueryType.COMPARISON

    def test_versus_keyword(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("AAPL versus MSFT volatility")
        assert intent.query_type == QueryType.COMPARISON

    def test_strategy_query(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("Recommend a strategy for TSLA")
        assert intent.query_type == QueryType.STRATEGY

    def test_trade_keyword(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("How should I trade AAPL?")
        assert intent.query_type == QueryType.STRATEGY

    def test_risk_check_query(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("What's my risk exposure?")
        assert intent.query_type == QueryType.RISK_CHECK

    def test_analysis_query(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("Analyze AAPL volatility")
        assert intent.query_type == QueryType.ANALYSIS

    def test_what_keyword(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("What is AAPL's IV rank?")
        assert intent.query_type == QueryType.ANALYSIS

    def test_default_general(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("Hello world")
        assert intent.query_type == QueryType.GENERAL


class TestClassifyIntentMultiDesk:
    """classify_intent routes to multiple desks when multiple keywords match."""

    def test_volatility_and_risk(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("What's the volatility risk for AAPL?")
        assert DeskType.VOLATILITY in intent.desks
        assert DeskType.RISK in intent.desks

    def test_no_duplicate_desks(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("IV and volatility and vega for AAPL")
        # All map to VOLATILITY -- should not duplicate
        vol_count = sum(1 for d in intent.desks if d == DeskType.VOLATILITY)
        assert vol_count == 1

    def test_trend_and_flow(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("What's the trend and unusual activity?")
        assert DeskType.TREND in intent.desks
        assert DeskType.FLOW in intent.desks


class TestClassifyIntentDefaults:
    """classify_intent default behavior when no keywords match."""

    def test_default_desk_is_volatility(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("Tell me about AAPL")
        assert DeskType.VOLATILITY in intent.desks

    def test_default_query_type_is_general(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("Tell me about AAPL")
        assert intent.query_type == QueryType.GENERAL

    def test_empty_query_defaults(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("")
        assert DeskType.VOLATILITY in intent.desks
        assert intent.query_type == QueryType.GENERAL
        assert intent.tickers == []

    def test_iv_is_keyword_not_ticker(self) -> None:
        """IV matches volatility desk keyword but is excluded as ticker."""
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("IV")
        assert DeskType.VOLATILITY in intent.desks
        assert "IV" not in intent.tickers


class TestClassifyIntentEdgeCases:
    """Edge cases for classify_intent."""

    def test_case_insensitive_keywords(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("VOLATILITY analysis for AAPL")
        assert DeskType.VOLATILITY in intent.desks

    def test_mixed_case_keywords(self) -> None:
        from options_arena.agents._routing import classify_intent

        intent = classify_intent("Hedge my portfolio")
        assert DeskType.RISK in intent.desks


@pytest.mark.asyncio
class TestRunAgencyQuery:
    """run_agency_query orchestrator -- dispatch, synthesis, never-raises."""

    @pytest.mark.critical
    async def test_dispatches_to_vol_desk(self) -> None:
        """Implemented vol desk returns real DeskResponse."""
        from options_arena.agents._routing import run_agency_query

        query = AgencyQuery(
            query_id="test-581",
            query_text="What's AAPL IV rank?",
            created_at=datetime.now(UTC),
        )
        with patch(
            "options_arena.agents._routing.run_vol_desk_query",
            new_callable=AsyncMock,
        ) as mock_vol:
            mock_vol.return_value = DeskResponse(
                desk=DeskType.VOLATILITY,
                response="IV rank is 85.",
                tools_used=["fetch_quote"],
                confidence=0.75,
            )
            resp = await run_agency_query(
                query,
                market_data=MagicMock(),
                options_data=MagicMock(),
                fred=MagicMock(),
                repo=MagicMock(),
                model=None,
                config=AgencyConfig(),
            )
            assert resp.query_id == "test-581"
            assert len(resp.desk_responses) >= 1
            assert resp.confidence > 0.0

    async def test_dispatches_to_risk_desk(self) -> None:
        """Implemented risk desk returns real DeskResponse."""
        from options_arena.agents._routing import run_agency_query

        query = AgencyQuery(
            query_id="test-risk",
            query_text="Analyze risk for TSLA",
            created_at=datetime.now(UTC),
        )
        with patch(
            "options_arena.agents._routing.run_risk_desk_query",
            new_callable=AsyncMock,
        ) as mock_risk:
            mock_risk.return_value = DeskResponse(
                desk=DeskType.RISK,
                response="Risk is moderate.",
                tools_used=["fetch_correlation"],
                confidence=0.8,
            )
            resp = await run_agency_query(
                query,
                market_data=MagicMock(),
                options_data=MagicMock(),
                fred=MagicMock(),
                repo=MagicMock(),
                model=None,
                config=AgencyConfig(),
            )
            assert resp.query_id == "test-risk"
            risk_resps = [r for r in resp.desk_responses if r.desk == DeskType.RISK]
            assert len(risk_resps) >= 1

    async def test_trend_desk_no_model_returns_error(self) -> None:
        """Trend desk with no model returns error DeskResponse with confidence=0.0."""
        from options_arena.agents._routing import run_agency_query

        query = AgencyQuery(
            query_id="test-582",
            query_text="What's the trend for AAPL?",
            created_at=datetime.now(UTC),
            desk_override=DeskType.TREND,
        )
        resp = await run_agency_query(
            query,
            market_data=MagicMock(),
            options_data=MagicMock(),
            fred=MagicMock(),
            repo=MagicMock(),
            model=None,
            config=AgencyConfig(),
        )
        trend_resp = [r for r in resp.desk_responses if r.desk == DeskType.TREND]
        assert len(trend_resp) == 1
        assert trend_resp[0].confidence == pytest.approx(0.0)

    async def test_flow_desk_no_model_returns_error(self) -> None:
        """Flow desk with no model returns error DeskResponse with confidence=0.0."""
        from options_arena.agents._routing import run_agency_query

        query = AgencyQuery(
            query_id="test-flow",
            query_text="Show unusual activity",
            created_at=datetime.now(UTC),
            desk_override=DeskType.FLOW,
        )
        resp = await run_agency_query(
            query,
            market_data=MagicMock(),
            options_data=MagicMock(),
            fred=MagicMock(),
            repo=MagicMock(),
            model=None,
            config=AgencyConfig(),
        )
        flow_resp = [r for r in resp.desk_responses if r.desk == DeskType.FLOW]
        assert len(flow_resp) == 1
        assert flow_resp[0].confidence == pytest.approx(0.0)

    async def test_fundamental_desk_no_model(self) -> None:
        """Fundamental desk with no model returns error response (confidence=0.0)."""
        from options_arena.agents._routing import run_agency_query

        query = AgencyQuery(
            query_id="test-fund",
            query_text="Show earnings",
            created_at=datetime.now(UTC),
            desk_override=DeskType.FUNDAMENTAL,
        )
        resp = await run_agency_query(
            query,
            market_data=MagicMock(),
            options_data=MagicMock(),
            fred=MagicMock(),
            repo=MagicMock(),
            model=None,
            config=AgencyConfig(),
        )
        fund_resp = [r for r in resp.desk_responses if r.desk == DeskType.FUNDAMENTAL]
        assert len(fund_resp) == 1
        assert fund_resp[0].confidence == pytest.approx(0.0)

    async def test_contrarian_desk_no_model(self) -> None:
        """Contrarian desk with no model returns error response (confidence=0.0)."""
        from options_arena.agents._routing import run_agency_query

        query = AgencyQuery(
            query_id="test-contra",
            query_text="Is consensus wrong?",
            created_at=datetime.now(UTC),
            desk_override=DeskType.CONTRARIAN,
        )
        resp = await run_agency_query(
            query,
            market_data=MagicMock(),
            options_data=MagicMock(),
            fred=MagicMock(),
            repo=MagicMock(),
            model=None,
            config=AgencyConfig(),
        )
        contra_resp = [r for r in resp.desk_responses if r.desk == DeskType.CONTRARIAN]
        assert len(contra_resp) == 1
        assert contra_resp[0].confidence == pytest.approx(0.0)

    async def test_unimplemented_research_desk(self) -> None:
        """Research desk is not yet implemented."""
        from options_arena.agents._routing import run_agency_query

        query = AgencyQuery(
            query_id="test-research",
            query_text="Research AAPL",
            created_at=datetime.now(UTC),
            desk_override=DeskType.RESEARCH,
        )
        resp = await run_agency_query(
            query,
            market_data=MagicMock(),
            options_data=MagicMock(),
            fred=MagicMock(),
            repo=MagicMock(),
            model=None,
            config=AgencyConfig(),
        )
        research_resp = [r for r in resp.desk_responses if r.desk == DeskType.RESEARCH]
        assert len(research_resp) == 1
        assert research_resp[0].confidence == pytest.approx(0.0)

    async def test_never_raises_on_exception(self) -> None:
        """run_agency_query catches all exceptions and returns error AgencyResponse."""
        from options_arena.agents._routing import run_agency_query

        query = AgencyQuery(
            query_id="test-583",
            query_text="What's AAPL IV?",
            created_at=datetime.now(UTC),
        )
        with patch(
            "options_arena.agents._routing.classify_intent",
            side_effect=RuntimeError("boom"),
        ):
            resp = await run_agency_query(
                query,
                market_data=MagicMock(),
                options_data=MagicMock(),
                fred=MagicMock(),
                repo=MagicMock(),
                model=None,
                config=AgencyConfig(),
            )
            # Should not raise -- returns error response
            assert resp.confidence == pytest.approx(0.0)
            assert resp.query_id == "test-583"

    async def test_desk_override_respected(self) -> None:
        """desk_override on AgencyQuery overrides classify_intent result."""
        from options_arena.agents._routing import run_agency_query

        query = AgencyQuery(
            query_id="test-584",
            query_text="Tell me about AAPL",
            created_at=datetime.now(UTC),
            desk_override=DeskType.RISK,
        )
        with patch(
            "options_arena.agents._routing.run_risk_desk_query",
            new_callable=AsyncMock,
        ) as mock_risk:
            mock_risk.return_value = DeskResponse(
                desk=DeskType.RISK,
                response="Risk analysis complete.",
                tools_used=["fetch_correlation"],
                confidence=0.8,
            )
            resp = await run_agency_query(
                query,
                market_data=MagicMock(),
                options_data=MagicMock(),
                fred=MagicMock(),
                repo=MagicMock(),
                model=None,
                config=AgencyConfig(),
            )
            # Should have dispatched to RISK desk despite no risk keywords in query text
            risk_resps = [r for r in resp.desk_responses if r.desk == DeskType.RISK]
            assert len(risk_resps) == 1

    async def test_synthesis_contains_desk_name(self) -> None:
        """Synthesis text includes desk name labels."""
        from options_arena.agents._routing import run_agency_query

        query = AgencyQuery(
            query_id="test-synth",
            query_text="What's AAPL IV rank?",
            created_at=datetime.now(UTC),
        )
        with patch(
            "options_arena.agents._routing.run_vol_desk_query",
            new_callable=AsyncMock,
        ) as mock_vol:
            mock_vol.return_value = DeskResponse(
                desk=DeskType.VOLATILITY,
                response="IV rank is 85.",
                tools_used=["fetch_quote"],
                confidence=0.75,
            )
            resp = await run_agency_query(
                query,
                market_data=MagicMock(),
                options_data=MagicMock(),
                fred=MagicMock(),
                repo=MagicMock(),
                model=None,
                config=AgencyConfig(),
            )
            assert "VOLATILITY" in resp.synthesis

    async def test_response_has_valid_created_at(self) -> None:
        """AgencyResponse has a UTC created_at timestamp."""
        from options_arena.agents._routing import run_agency_query

        query = AgencyQuery(
            query_id="test-ts",
            query_text="What's the trend?",
            created_at=datetime.now(UTC),
            desk_override=DeskType.TREND,
        )
        resp = await run_agency_query(
            query,
            market_data=MagicMock(),
            options_data=MagicMock(),
            fred=MagicMock(),
            repo=MagicMock(),
            model=None,
            config=AgencyConfig(),
        )
        assert resp.created_at.tzinfo is not None
        assert resp.created_at.utcoffset() == timedelta(0)

    @pytest.mark.critical
    async def test_multi_desk_dispatch(self) -> None:
        """Query matching both vol and risk dispatches to both desks."""
        from options_arena.agents._routing import run_agency_query

        query = AgencyQuery(
            query_id="test-multi",
            query_text="What's the volatility risk for AAPL?",
            created_at=datetime.now(UTC),
        )
        with (
            patch(
                "options_arena.agents._routing.run_vol_desk_query",
                new_callable=AsyncMock,
            ) as mock_vol,
            patch(
                "options_arena.agents._routing.run_risk_desk_query",
                new_callable=AsyncMock,
            ) as mock_risk,
        ):
            mock_vol.return_value = DeskResponse(
                desk=DeskType.VOLATILITY,
                response="IV is elevated.",
                tools_used=[],
                confidence=0.7,
            )
            mock_risk.return_value = DeskResponse(
                desk=DeskType.RISK,
                response="Risk is moderate.",
                tools_used=[],
                confidence=0.6,
            )
            resp = await run_agency_query(
                query,
                market_data=MagicMock(),
                options_data=MagicMock(),
                fred=MagicMock(),
                repo=MagicMock(),
                model=None,
                config=AgencyConfig(),
            )
            desks_in_response = {r.desk for r in resp.desk_responses}
            assert DeskType.VOLATILITY in desks_in_response
            assert DeskType.RISK in desks_in_response
            assert resp.confidence == pytest.approx(0.65, abs=0.01)

"""Tests for AI agency desk system models, enums, and config.

Covers DeskType, QueryType, QueryIntent, DeskResponse, and AgencyConfig.
"""

from __future__ import annotations

import math
from enum import StrEnum

import pytest
from pydantic import ValidationError

from options_arena.models import (
    AgencyConfig,
    AppSettings,
    DeskResponse,
    DeskType,
    QueryIntent,
    QueryType,
)


class TestDeskType:
    """DeskType StrEnum — 7 desk specializations."""

    def test_member_count(self) -> None:
        assert len(DeskType) == 7

    def test_values_match(self) -> None:
        assert DeskType.TREND == "trend"
        assert DeskType.VOLATILITY == "volatility"
        assert DeskType.FLOW == "flow"
        assert DeskType.FUNDAMENTAL == "fundamental"
        assert DeskType.RISK == "risk"
        assert DeskType.CONTRARIAN == "contrarian"
        assert DeskType.RESEARCH == "research"

    def test_is_str_enum(self) -> None:
        assert issubclass(DeskType, StrEnum)


class TestQueryType:
    """QueryType StrEnum — 5 query intent classifications."""

    def test_member_count(self) -> None:
        assert len(QueryType) == 5

    def test_values_match(self) -> None:
        assert QueryType.ANALYSIS == "analysis"
        assert QueryType.COMPARISON == "comparison"
        assert QueryType.STRATEGY == "strategy"
        assert QueryType.RISK_CHECK == "risk_check"
        assert QueryType.GENERAL == "general"

    def test_is_str_enum(self) -> None:
        assert issubclass(QueryType, StrEnum)


class TestQueryIntent:
    """QueryIntent frozen model — parsed user query for desk routing."""

    def test_construction(self) -> None:
        intent = QueryIntent(
            desks=[DeskType.TREND, DeskType.VOLATILITY],
            query_type=QueryType.ANALYSIS,
            tickers=["AAPL", "MSFT"],
        )
        assert intent.desks == [DeskType.TREND, DeskType.VOLATILITY]
        assert intent.query_type == QueryType.ANALYSIS
        assert intent.tickers == ["AAPL", "MSFT"]

    def test_frozen_rejects_mutation(self) -> None:
        intent = QueryIntent(
            desks=[DeskType.RISK],
            query_type=QueryType.RISK_CHECK,
            tickers=["TSLA"],
        )
        with pytest.raises(ValidationError):
            intent.query_type = QueryType.GENERAL  # type: ignore[assignment]

    def test_empty_tickers_valid(self) -> None:
        intent = QueryIntent(
            desks=[DeskType.RESEARCH],
            query_type=QueryType.GENERAL,
            tickers=[],
        )
        assert intent.tickers == []

    def test_json_roundtrip(self) -> None:
        intent = QueryIntent(
            desks=[DeskType.FLOW, DeskType.FUNDAMENTAL],
            query_type=QueryType.COMPARISON,
            tickers=["GOOG"],
        )
        roundtripped = QueryIntent.model_validate_json(intent.model_dump_json())
        assert roundtripped == intent


class TestDeskResponse:
    """DeskResponse frozen model — output from a single desk agent."""

    def test_construction(self) -> None:
        resp = DeskResponse(
            desk=DeskType.TREND,
            response="Uptrend confirmed by ADX > 25.",
            tools_used=["sma_alignment", "adx"],
            confidence=0.85,
        )
        assert resp.desk == DeskType.TREND
        assert resp.response == "Uptrend confirmed by ADX > 25."
        assert resp.tools_used == ["sma_alignment", "adx"]
        assert resp.confidence == 0.85

    def test_confidence_zero_valid(self) -> None:
        resp = DeskResponse(
            desk=DeskType.RISK,
            response="No clear signal.",
            tools_used=[],
            confidence=0.0,
        )
        assert resp.confidence == 0.0

    def test_confidence_one_valid(self) -> None:
        resp = DeskResponse(
            desk=DeskType.VOLATILITY,
            response="IV crush expected.",
            tools_used=["iv_rank"],
            confidence=1.0,
        )
        assert resp.confidence == 1.0

    def test_confidence_nan_rejected(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            DeskResponse(
                desk=DeskType.FLOW,
                response="test",
                tools_used=[],
                confidence=float("nan"),
            )

    def test_confidence_inf_rejected(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            DeskResponse(
                desk=DeskType.FLOW,
                response="test",
                tools_used=[],
                confidence=float("inf"),
            )

    def test_confidence_neg_inf_rejected(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            DeskResponse(
                desk=DeskType.FLOW,
                response="test",
                tools_used=[],
                confidence=float("-inf"),
            )

    def test_confidence_below_zero_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must be in"):
            DeskResponse(
                desk=DeskType.FLOW,
                response="test",
                tools_used=[],
                confidence=-0.1,
            )

    def test_confidence_above_one_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must be in"):
            DeskResponse(
                desk=DeskType.FLOW,
                response="test",
                tools_used=[],
                confidence=1.01,
            )

    def test_frozen_rejects_mutation(self) -> None:
        resp = DeskResponse(
            desk=DeskType.FUNDAMENTAL,
            response="Strong earnings.",
            tools_used=["pe_ratio"],
            confidence=0.7,
        )
        with pytest.raises(ValidationError):
            resp.confidence = 0.9  # type: ignore[misc]

    def test_json_roundtrip(self) -> None:
        resp = DeskResponse(
            desk=DeskType.CONTRARIAN,
            response="Market overreacting to earnings miss.",
            tools_used=["sentiment", "rsi"],
            confidence=0.6,
        )
        roundtripped = DeskResponse.model_validate_json(resp.model_dump_json())
        assert roundtripped == resp

    def test_tools_used_preserved(self) -> None:
        tools = ["iv_surface", "skew_analysis", "term_structure"]
        resp = DeskResponse(
            desk=DeskType.VOLATILITY,
            response="Vol surface shows skew.",
            tools_used=tools,
            confidence=0.75,
        )
        assert resp.tools_used == tools


class TestAgencyConfig:
    """AgencyConfig BaseModel — desk system configuration."""

    def test_default_construction(self) -> None:
        config = AgencyConfig()
        assert config.agent_timeout == 60.0
        assert config.default_tool_budget == 3
        assert config.risk_tool_budget == 5
        assert config.research_tool_budget == 5

    def test_field_overrides(self) -> None:
        config = AgencyConfig(
            agent_timeout=90.0,
            default_tool_budget=5,
            risk_tool_budget=10,
            research_tool_budget=8,
        )
        assert config.agent_timeout == 90.0
        assert config.default_tool_budget == 5
        assert config.risk_tool_budget == 10
        assert config.research_tool_budget == 8

    def test_nested_on_app_settings_via_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ARENA_AGENCY__AGENT_TIMEOUT", "120.0")
        settings = AppSettings()
        assert settings.agency.agent_timeout == 120.0

    def test_default_agency_on_app_settings(self) -> None:
        settings = AppSettings()
        assert settings.agency.agent_timeout == 60.0
        assert settings.agency.default_tool_budget == 3

    def test_agent_timeout_nan_rejected(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            AgencyConfig(agent_timeout=float("nan"))

    def test_timeout_zero_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must be > 0"):
            AgencyConfig(agent_timeout=0.0)

    def test_tool_budget_zero_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must be in"):
            AgencyConfig(default_tool_budget=0)

    def test_tool_budget_too_high_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must be in"):
            AgencyConfig(risk_tool_budget=21)

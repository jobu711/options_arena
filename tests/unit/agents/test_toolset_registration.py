"""Tests for analysis tool registration on desk toolsets.

Verifies that the 5 new analysis tools (valuation, position sizing, correlation
matrix, risk-adjusted metrics, HV Yang-Zhang) are registered on the correct
desk toolsets and NOT on desks where they do not belong.
"""

from __future__ import annotations

import pytest
from pydantic_ai import models

from options_arena.agents._toolsets import (
    build_contrarian_toolset,
    build_flow_toolset,
    build_fundamental_toolset,
    build_research_toolset,
    build_risk_toolset,
    build_trend_toolset,
    build_volatility_toolset,
    compute_composite_valuation_tool,
    compute_correlation_matrix_tool,
    compute_hv_yang_zhang_tool,
    compute_position_size_tool,
    compute_risk_adjusted_metrics_tool,
)

models.ALLOW_MODEL_REQUESTS = False


class TestVolatilityToolset:
    """Volatility desk toolset registration."""

    @pytest.mark.critical
    def test_volatility_toolset_count(self) -> None:
        """build_volatility_toolset returns 4-5 tools (5 with [ml])."""
        tools = build_volatility_toolset()
        assert len(tools) in {4, 5}

    def test_volatility_toolset_includes_hv(self) -> None:
        """HV tool is in the volatility toolset."""
        tools = build_volatility_toolset()
        assert compute_hv_yang_zhang_tool in tools


class TestFundamentalToolset:
    """Fundamental desk toolset registration."""

    def test_fundamental_toolset_count(self) -> None:
        """build_fundamental_toolset returns 5 tools."""
        tools = build_fundamental_toolset()
        assert len(tools) == 5

    def test_fundamental_toolset_includes_valuation(self) -> None:
        """Valuation tool is in the fundamental toolset."""
        tools = build_fundamental_toolset()
        assert compute_composite_valuation_tool in tools


class TestRiskToolset:
    """Risk desk toolset registration."""

    def test_risk_toolset_count(self) -> None:
        """build_risk_toolset returns 7-8 tools (8 with [ml])."""
        tools = build_risk_toolset()
        assert len(tools) in {7, 8}

    def test_risk_toolset_includes_new_tools(self) -> None:
        """All 3 new tools are in risk toolset."""
        tools = build_risk_toolset()
        assert compute_correlation_matrix_tool in tools
        assert compute_risk_adjusted_metrics_tool in tools
        assert compute_position_size_tool in tools


class TestResearchToolset:
    """Research desk toolset registration."""

    def test_research_toolset_count(self) -> None:
        """build_research_toolset returns 11-13 tools (13 with [ml])."""
        tools = build_research_toolset()
        assert len(tools) in {11, 12, 13}

    def test_research_toolset_includes_new_tools(self) -> None:
        """All 3 new tools are in research toolset."""
        tools = build_research_toolset()
        assert compute_composite_valuation_tool in tools
        assert compute_position_size_tool in tools
        assert compute_hv_yang_zhang_tool in tools


class TestNoCrossDomainLeakage:
    """Analysis tools appear only on their target desks."""

    def test_valuation_not_on_wrong_desks(self) -> None:
        """Valuation tool is NOT on vol/trend/flow/contrarian desks."""
        vol_tools = build_volatility_toolset()
        trend_tools = build_trend_toolset()
        flow_tools = build_flow_toolset()
        contrarian_tools = build_contrarian_toolset()

        assert compute_composite_valuation_tool not in vol_tools
        assert compute_composite_valuation_tool not in trend_tools
        assert compute_composite_valuation_tool not in flow_tools
        assert compute_composite_valuation_tool not in contrarian_tools

    def test_hv_not_on_wrong_desks(self) -> None:
        """HV tool is NOT on fundamental/trend/flow/contrarian desks."""
        fund_tools = build_fundamental_toolset()
        trend_tools = build_trend_toolset()
        flow_tools = build_flow_toolset()
        contrarian_tools = build_contrarian_toolset()

        assert compute_hv_yang_zhang_tool not in fund_tools
        assert compute_hv_yang_zhang_tool not in trend_tools
        assert compute_hv_yang_zhang_tool not in flow_tools
        assert compute_hv_yang_zhang_tool not in contrarian_tools

    def test_position_size_not_on_wrong_desks(self) -> None:
        """Position size tool is NOT on vol/fundamental/trend/flow/contrarian desks."""
        vol_tools = build_volatility_toolset()
        fund_tools = build_fundamental_toolset()
        trend_tools = build_trend_toolset()
        flow_tools = build_flow_toolset()
        contrarian_tools = build_contrarian_toolset()

        assert compute_position_size_tool not in vol_tools
        assert compute_position_size_tool not in fund_tools
        assert compute_position_size_tool not in trend_tools
        assert compute_position_size_tool not in flow_tools
        assert compute_position_size_tool not in contrarian_tools

    def test_correlation_matrix_not_on_wrong_desks(self) -> None:
        """Correlation matrix tool is NOT on vol/fundamental/trend/flow/contrarian desks."""
        vol_tools = build_volatility_toolset()
        fund_tools = build_fundamental_toolset()
        trend_tools = build_trend_toolset()
        flow_tools = build_flow_toolset()
        contrarian_tools = build_contrarian_toolset()

        assert compute_correlation_matrix_tool not in vol_tools
        assert compute_correlation_matrix_tool not in fund_tools
        assert compute_correlation_matrix_tool not in trend_tools
        assert compute_correlation_matrix_tool not in flow_tools
        assert compute_correlation_matrix_tool not in contrarian_tools

    def test_risk_metrics_not_on_wrong_desks(self) -> None:
        """Risk-adjusted metrics tool is NOT on vol/fundamental/trend/flow/contrarian desks."""
        vol_tools = build_volatility_toolset()
        fund_tools = build_fundamental_toolset()
        trend_tools = build_trend_toolset()
        flow_tools = build_flow_toolset()
        contrarian_tools = build_contrarian_toolset()

        assert compute_risk_adjusted_metrics_tool not in vol_tools
        assert compute_risk_adjusted_metrics_tool not in fund_tools
        assert compute_risk_adjusted_metrics_tool not in trend_tools
        assert compute_risk_adjusted_metrics_tool not in flow_tools
        assert compute_risk_adjusted_metrics_tool not in contrarian_tools


class TestUnchangedToolsets:
    """Verify toolsets not targeted by this change remain unchanged."""

    def test_trend_toolset_count(self) -> None:
        """Trend toolset has 4-5 tools (5 with [ml])."""
        assert len(build_trend_toolset()) in {4, 5}

    def test_flow_toolset_count(self) -> None:
        """Flow toolset still has 3 tools."""
        assert len(build_flow_toolset()) == 3

    def test_contrarian_toolset_count(self) -> None:
        """Contrarian toolset still has 2 tools."""
        assert len(build_contrarian_toolset()) == 2

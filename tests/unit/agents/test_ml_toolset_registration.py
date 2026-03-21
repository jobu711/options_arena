"""Tests for conditional registration of ML tools in toolset builders.

Task #628: Verifies that GARCH and Markov tools are conditionally registered
based on [ml] extra availability, while macro and Hurst tools are always present.
Also tests render_available_tools().
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
    compute_garch_forecast_tool,
    compute_hurst_exponent_tool,
    compute_macro_regime_tool,
    compute_markov_regime_tool,
    render_available_tools,
)

models.ALLOW_MODEL_REQUESTS = False


# ---------------------------------------------------------------------------
# Helper: simulate missing packages by patching sys.modules
# ---------------------------------------------------------------------------


def _hide_package(
    monkeypatch: pytest.MonkeyPatch,
    package_name: str,
) -> None:
    """Make ``import <package_name>`` raise ImportError.

    Patches ``sys.modules`` to map the package to ``None`` and also
    patches ``builtins.__import__`` to raise ImportError for the package.
    """
    import builtins

    original_import = builtins.__import__

    def mock_import(name: str, *args: object, **kwargs: object) -> object:
        if name == package_name or name.startswith(package_name + "."):
            raise ImportError(f"Mocked: No module named {package_name!r}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)


# ---------------------------------------------------------------------------
# Conditional GARCH (arch dependency)
# ---------------------------------------------------------------------------


class TestConditionalGARCH:
    """Test GARCH tool conditional registration on volatility desk."""

    def test_volatility_includes_garch_when_arch_installed(self) -> None:
        """Verify GARCH tool in volatility toolset when arch available."""
        tools = build_volatility_toolset()
        # If arch is installed, GARCH should be present
        try:
            import arch  # noqa: F401

            assert compute_garch_forecast_tool in tools
        except ImportError:
            assert compute_garch_forecast_tool not in tools

    def test_volatility_excludes_garch_when_arch_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify GARCH tool omitted when arch ImportError."""
        _hide_package(monkeypatch, "arch")

        tools = build_volatility_toolset()

        assert compute_garch_forecast_tool not in tools

    def test_volatility_base_count_without_ml(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Volatility desk has exactly 4 tools without [ml]."""
        _hide_package(monkeypatch, "arch")

        tools = build_volatility_toolset()

        assert len(tools) == 4


# ---------------------------------------------------------------------------
# Conditional Markov (statsmodels dependency)
# ---------------------------------------------------------------------------


class TestConditionalMarkov:
    """Test Markov tool conditional registration on trend and risk desks."""

    def test_trend_includes_markov_when_statsmodels_installed(self) -> None:
        """Verify Markov tool in trend toolset when statsmodels available."""
        tools = build_trend_toolset()
        try:
            import statsmodels  # noqa: F401

            assert compute_markov_regime_tool in tools
        except ImportError:
            assert compute_markov_regime_tool not in tools

    def test_trend_excludes_markov_when_statsmodels_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify Markov tool omitted when statsmodels ImportError."""
        _hide_package(monkeypatch, "statsmodels")

        tools = build_trend_toolset()

        assert compute_markov_regime_tool not in tools

    def test_risk_includes_markov_when_available(self) -> None:
        """Verify Markov tool in risk toolset when available."""
        tools = build_risk_toolset()
        try:
            import statsmodels  # noqa: F401

            assert compute_markov_regime_tool in tools
        except ImportError:
            assert compute_markov_regime_tool not in tools

    def test_risk_excludes_markov_when_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify Markov tool omitted from risk when statsmodels missing."""
        _hide_package(monkeypatch, "statsmodels")

        tools = build_risk_toolset()

        assert compute_markov_regime_tool not in tools


# ---------------------------------------------------------------------------
# Always-registered tools
# ---------------------------------------------------------------------------


class TestAlwaysRegistered:
    """Test tools that are always registered (no optional deps)."""

    def test_trend_always_includes_hurst(self) -> None:
        """Verify Hurst tool always in trend toolset."""
        tools = build_trend_toolset()

        assert compute_hurst_exponent_tool in tools

    def test_fundamental_always_includes_macro(self) -> None:
        """Verify macro tool always in fundamental toolset."""
        tools = build_fundamental_toolset()

        assert compute_macro_regime_tool in tools

    def test_risk_always_includes_macro(self) -> None:
        """Verify macro tool always in risk toolset."""
        tools = build_risk_toolset()

        assert compute_macro_regime_tool in tools

    def test_research_always_includes_macro_and_hurst(self) -> None:
        """Verify macro and Hurst always in research toolset."""
        tools = build_research_toolset()

        assert compute_macro_regime_tool in tools
        assert compute_hurst_exponent_tool in tools


# ---------------------------------------------------------------------------
# Research desk: all tools
# ---------------------------------------------------------------------------


class TestResearchAllTools:
    """Test research desk gets all 4 new tools when [ml] available."""

    def test_research_includes_all_when_ml_installed(self) -> None:
        """Verify research has all 4 new tools when [ml] available."""
        tools = build_research_toolset()
        try:
            import arch  # noqa: F401
            import statsmodels  # noqa: F401

            assert compute_garch_forecast_tool in tools
            assert compute_markov_regime_tool in tools
            assert compute_macro_regime_tool in tools
            assert compute_hurst_exponent_tool in tools
        except ImportError:
            # At minimum, macro and hurst should be present
            assert compute_macro_regime_tool in tools
            assert compute_hurst_exponent_tool in tools

    def test_research_has_always_tools_without_ml(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify research still has macro + hurst without [ml]."""
        _hide_package(monkeypatch, "arch")
        _hide_package(monkeypatch, "statsmodels")

        tools = build_research_toolset()

        assert compute_macro_regime_tool in tools
        assert compute_hurst_exponent_tool in tools
        assert compute_garch_forecast_tool not in tools
        assert compute_markov_regime_tool not in tools

    def test_research_base_count_without_ml(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Research desk has 11 tools without [ml]."""
        _hide_package(monkeypatch, "arch")
        _hide_package(monkeypatch, "statsmodels")

        tools = build_research_toolset()

        assert len(tools) == 11


# ---------------------------------------------------------------------------
# Unaffected desks
# ---------------------------------------------------------------------------


class TestUnaffectedDesks:
    """Flow and contrarian desks are unaffected by ML tools."""

    def test_flow_unaffected_by_ml(self) -> None:
        """Flow desk has same tools with or without [ml]."""
        tools = build_flow_toolset()

        assert compute_garch_forecast_tool not in tools
        assert compute_markov_regime_tool not in tools
        assert compute_macro_regime_tool not in tools
        assert compute_hurst_exponent_tool not in tools
        assert len(tools) == 3

    def test_contrarian_unaffected_by_ml(self) -> None:
        """Contrarian desk has same tools with or without [ml]."""
        tools = build_contrarian_toolset()

        assert compute_garch_forecast_tool not in tools
        assert compute_markov_regime_tool not in tools
        assert compute_macro_regime_tool not in tools
        assert compute_hurst_exponent_tool not in tools
        assert len(tools) == 2


# ---------------------------------------------------------------------------
# render_available_tools
# ---------------------------------------------------------------------------


class TestRenderAvailableTools:
    """Test render_available_tools prompt block generation."""

    def test_render_formats_tool_names(self) -> None:
        """Verify render_available_tools produces correct block."""

        def my_tool() -> None:
            pass

        def another_tool() -> None:
            pass

        result = render_available_tools([my_tool, another_tool])

        assert "- my_tool" in result
        assert "- another_tool" in result

    def test_render_empty_toolset(self) -> None:
        """Verify render handles empty list."""
        result = render_available_tools([])

        assert "<<<AVAILABLE_TOOLS>>>" in result
        assert "<<<END_AVAILABLE_TOOLS>>>" in result

    def test_render_delimiter_format(self) -> None:
        """Verify <<<AVAILABLE_TOOLS>>> delimiters present."""

        def a_tool() -> None:
            pass

        result = render_available_tools([a_tool])

        assert result.startswith("<<<AVAILABLE_TOOLS>>>")
        assert result.endswith("<<<END_AVAILABLE_TOOLS>>>")

    def test_render_with_real_toolset(self) -> None:
        """Verify render works with an actual desk toolset."""
        tools = build_fundamental_toolset()
        result = render_available_tools(tools)

        assert "<<<AVAILABLE_TOOLS>>>" in result
        assert "compute_macro_regime_tool" in result
        assert "fetch_quote" in result

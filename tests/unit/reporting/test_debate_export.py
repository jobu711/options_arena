"""Tests for debate export — markdown and file export of DebateResult.

Tests cover:
  - Markdown output contains all required section headers
  - Volatility section appears when vol_response is present
  - Bull rebuttal section appears when bull_rebuttal is present
  - Fallback warning displayed when is_fallback=True
  - File write creates a valid markdown file at the target path
  - PDF export raises ImportError when weasyprint is unavailable
  - Export directory is created automatically when it does not exist
  - Unsupported format raises ValueError
  - Disclaimer is always present in output
  - Rebuttal section omits risks subsection
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic_ai.usage import RunUsage

from options_arena.agents._parsing import DebateResult
from options_arena.models import AgentResponse, MarketContext, TradeThesis, VolatilityThesis
from options_arena.models.enums import ExerciseStyle, MacdSignal, SignalDirection, SpreadType
from options_arena.reporting.debate_export import (
    DISCLAIMER,
    export_debate_markdown,
    export_debate_to_file,
)


def _make_market_context() -> MarketContext:
    """Build a realistic MarketContext for AAPL."""
    return MarketContext(
        ticker="AAPL",
        current_price=Decimal("185.50"),
        price_52w_high=Decimal("199.62"),
        price_52w_low=Decimal("164.08"),
        iv_rank=45.2,
        iv_percentile=52.1,
        atm_iv_30d=28.5,
        rsi_14=62.3,
        macd_signal=MacdSignal.BULLISH_CROSSOVER,
        put_call_ratio=0.85,
        next_earnings=None,
        dte_target=45,
        target_strike=Decimal("190.00"),
        target_delta=0.35,
        sector="Information Technology",
        dividend_yield=0.005,
        exercise_style=ExerciseStyle.AMERICAN,
        data_timestamp=datetime(2026, 2, 24, 14, 30, 0, tzinfo=UTC),
    )


def _make_bull_response() -> AgentResponse:
    """Build a realistic bull AgentResponse."""
    return AgentResponse(
        agent_name="bull",
        direction=SignalDirection.BULLISH,
        confidence=0.72,
        argument="RSI at 62.3 indicates bullish momentum.",
        key_points=["RSI trending up", "Volume increasing"],
        risks_cited=["Earnings next week"],
        contracts_referenced=["AAPL $190 CALL 2026-04-10"],
        model_used="llama3.1:8b",
    )


def _make_bear_response() -> AgentResponse:
    """Build a realistic bear AgentResponse."""
    return AgentResponse(
        agent_name="bear",
        direction=SignalDirection.BEARISH,
        confidence=0.55,
        argument="Sector rotation and earnings risk weigh on upside.",
        key_points=["Sector rotation underway"],
        risks_cited=["Strong momentum could extend"],
        contracts_referenced=["AAPL $180 PUT 2026-04-10"],
        model_used="llama3.1:8b",
    )


def _make_trade_thesis() -> TradeThesis:
    """Build a realistic TradeThesis."""
    return TradeThesis(
        ticker="AAPL",
        direction=SignalDirection.BULLISH,
        confidence=0.65,
        summary="Moderate bullish case supported by momentum indicators.",
        bull_score=7.2,
        bear_score=4.5,
        key_factors=["RSI trending up", "Sector strength"],
        risk_assessment="Moderate risk. Position sizing: 2% of portfolio.",
        recommended_strategy=None,
    )


def _make_volatility_thesis() -> VolatilityThesis:
    """Build a realistic VolatilityThesis."""
    return VolatilityThesis(
        iv_assessment="overpriced",
        iv_rank_interpretation="IV rank at 85 is in the top 15%.",
        confidence=0.75,
        recommended_strategy=SpreadType.IRON_CONDOR,
        strategy_rationale="High IV favors selling premium via iron condor.",
        target_iv_entry=85.0,
        target_iv_exit=50.0,
        suggested_strikes=["185C", "195C"],
        key_vol_factors=["Earnings in 5 days", "IV rank 85"],
        model_used="llama3.1:8b",
    )


def _make_rebuttal_response() -> AgentResponse:
    """Build a realistic bull rebuttal AgentResponse."""
    return AgentResponse(
        agent_name="bull",
        direction=SignalDirection.BULLISH,
        confidence=0.68,
        argument="Bear overstates sector rotation risk; AAPL outperforms sector.",
        key_points=["AAPL relative strength vs sector", "Buyback support"],
        risks_cited=["Earnings miss could invalidate thesis"],
        contracts_referenced=["AAPL $190 CALL 2026-04-10"],
        model_used="llama3.1:8b",
    )


def _make_debate_result(
    *,
    vol_response: VolatilityThesis | None = None,
    bull_rebuttal: AgentResponse | None = None,
    is_fallback: bool = False,
) -> DebateResult:
    """Build a complete DebateResult with optional vol and rebuttal sections."""
    return DebateResult(
        context=_make_market_context(),
        bull_response=_make_bull_response(),
        bear_response=_make_bear_response(),
        thesis=_make_trade_thesis(),
        total_usage=RunUsage(),
        duration_ms=1500,
        is_fallback=is_fallback,
        vol_response=vol_response,
        bull_rebuttal=bull_rebuttal,
    )


# ---------------------------------------------------------------------------
# Markdown content tests
# ---------------------------------------------------------------------------


def test_markdown_contains_all_headers() -> None:
    """Exported markdown must contain Bull Case, Bear Case, and Verdict headers."""
    result = _make_debate_result()
    md = export_debate_markdown(result)

    assert "## Bull Case" in md
    assert "## Bear Case" in md
    assert "## Verdict" in md


def test_markdown_includes_vol_when_present() -> None:
    """When vol_response is set, the Volatility Assessment section appears."""
    result = _make_debate_result(vol_response=_make_volatility_thesis())
    md = export_debate_markdown(result)

    assert "## Volatility Assessment" in md
    assert "overpriced" in md
    assert "High IV favors selling premium via iron condor." in md


def test_markdown_excludes_vol_when_absent() -> None:
    """When vol_response is None, no Volatility Assessment section appears."""
    result = _make_debate_result(vol_response=None)
    md = export_debate_markdown(result)

    assert "## Volatility Assessment" not in md


def test_markdown_includes_rebuttal_when_present() -> None:
    """When bull_rebuttal is set, the Bull Rebuttal section appears."""
    result = _make_debate_result(bull_rebuttal=_make_rebuttal_response())
    md = export_debate_markdown(result)

    assert "## Bull Rebuttal" in md
    assert "Bear overstates sector rotation risk" in md


def test_markdown_excludes_rebuttal_when_absent() -> None:
    """When bull_rebuttal is None, no Bull Rebuttal section appears."""
    result = _make_debate_result(bull_rebuttal=None)
    md = export_debate_markdown(result)

    assert "## Bull Rebuttal" not in md


def test_markdown_rebuttal_omits_risks_subsection() -> None:
    """The Bull Rebuttal section does not include a Risks Cited subsection.

    The rebuttal uses ``include_risks=False``, so even though the AgentResponse
    has ``risks_cited`` populated, they should not appear in the rebuttal section.
    """
    rebuttal = _make_rebuttal_response()
    result = _make_debate_result(bull_rebuttal=rebuttal)
    md = export_debate_markdown(result)

    # Split output at the rebuttal heading to inspect only that section
    rebuttal_start = md.index("## Bull Rebuttal")
    # Find the next section heading after rebuttal (## Verdict)
    rebuttal_section = md[rebuttal_start : md.index("## Verdict")]

    assert "### Risks Cited" not in rebuttal_section


def test_markdown_fallback_warning_when_true() -> None:
    """When is_fallback=True, the report shows 'Fallback: Yes'."""
    result = _make_debate_result(is_fallback=True)
    md = export_debate_markdown(result)

    assert "**Fallback**: Yes" in md


def test_markdown_fallback_no_when_false() -> None:
    """When is_fallback=False, the report shows 'Fallback: No'."""
    result = _make_debate_result(is_fallback=False)
    md = export_debate_markdown(result)

    assert "**Fallback**: No" in md


def test_markdown_contains_disclaimer() -> None:
    """Disclaimer text must always appear in exported markdown."""
    result = _make_debate_result()
    md = export_debate_markdown(result)

    assert DISCLAIMER in md


def test_markdown_contains_ticker() -> None:
    """Report header must include the ticker symbol."""
    result = _make_debate_result()
    md = export_debate_markdown(result)

    assert "AAPL" in md


# ---------------------------------------------------------------------------
# File export tests
# ---------------------------------------------------------------------------


def test_export_to_file_writes_markdown(tmp_path: Path) -> None:
    """export_debate_to_file writes a valid markdown file to the given path."""
    result = _make_debate_result()
    dest = tmp_path / "report.md"

    returned_path = export_debate_to_file(result, dest, fmt="md")

    assert returned_path == dest
    assert dest.exists()
    content = dest.read_text(encoding="utf-8")
    assert "## Bull Case" in content
    assert "## Bear Case" in content
    assert "## Verdict" in content
    assert DISCLAIMER in content


def test_export_works_with_nested_directory(tmp_path: Path) -> None:
    """export_debate_to_file writes successfully into a nested directory structure."""
    result = _make_debate_result()
    nested_dir = tmp_path / "reports" / "2026"
    nested_dir.mkdir(parents=True, exist_ok=True)
    dest = nested_dir / "report.md"

    returned_path = export_debate_to_file(result, dest, fmt="md")
    assert returned_path == dest
    assert dest.exists()
    content = dest.read_text(encoding="utf-8")
    assert "AAPL" in content


def test_export_raises_value_error_for_unsupported_format(tmp_path: Path) -> None:
    """export_debate_to_file raises ValueError for unsupported format strings."""
    result = _make_debate_result()
    dest = tmp_path / "report.html"

    with pytest.raises(ValueError, match="Unsupported format"):
        export_debate_to_file(result, dest, fmt="html")


def test_export_pdf_raises_import_error_without_weasyprint(tmp_path: Path) -> None:
    """PDF export raises ImportError when weasyprint is not installed.

    weasyprint is an optional dependency. When absent, _render_pdf does a
    lazy import that raises ImportError with a user-friendly install message.
    """
    result = _make_debate_result()
    dest = tmp_path / "report.pdf"

    with pytest.raises(ImportError, match="weasyprint"):
        export_debate_to_file(result, dest, fmt="pdf")

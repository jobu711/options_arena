"""Tests for spread analysis block rendering in synthesis and risk desk prompts.

Covers:
- Synthesis prompt: <<<SPREAD_ANALYSIS>>> block present/absent based on deps
- Block content: strategy type, P&L profile, risk/reward, P(profit)
- Risk desk prompt: <<<SPREAD_CONTEXT>>> block rendering
- Edge cases: risk_reward_ratio=None, empty strategy_rationale
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from pydantic_ai import models

from options_arena.agents.risk_desk import _render_risk_spread_block, _risk_recommend_prompt
from options_arena.agents.synthesis_agent import (
    SynthesisDeps,
    _render_spread_block,
    _synthesis_system_prompt,
)
from tests.factories import make_spread_analysis

models.ALLOW_MODEL_REQUESTS = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_minimal_synthesis_deps(
    *,
    spread_analysis: object = None,
) -> SynthesisDeps:
    """Build a minimal SynthesisDeps for prompt testing."""
    return SynthesisDeps(
        context=MagicMock(),
        assessments=[],
        contracts=[],
        ticker_score=MagicMock(),
        spread_analysis=spread_analysis,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Synthesis prompt -- spread analysis block
# ---------------------------------------------------------------------------


class TestSpreadPromptRendering:
    """Spread analysis block injection into synthesis prompt."""

    @pytest.mark.asyncio
    async def test_spread_block_present_when_data(self) -> None:
        """<<<SPREAD_ANALYSIS>>> block rendered when spread_analysis provided."""
        spread = make_spread_analysis()
        deps = _make_minimal_synthesis_deps(spread_analysis=spread)

        ctx = MagicMock()
        ctx.deps = deps

        prompt = await _synthesis_system_prompt(ctx)
        assert "<<<SPREAD_ANALYSIS>>>" in prompt
        assert "<<<END_SPREAD_ANALYSIS>>>" in prompt

    @pytest.mark.asyncio
    async def test_spread_block_absent_when_none(self) -> None:
        """No SPREAD_ANALYSIS block when spread_analysis is None."""
        deps = _make_minimal_synthesis_deps(spread_analysis=None)

        ctx = MagicMock()
        ctx.deps = deps

        prompt = await _synthesis_system_prompt(ctx)
        assert "<<<END_SPREAD_ANALYSIS>>>" not in prompt

    @pytest.mark.asyncio
    async def test_spread_block_contains_strategy_type(self) -> None:
        """Block includes spread strategy type."""
        spread = make_spread_analysis()
        deps = _make_minimal_synthesis_deps(spread_analysis=spread)

        ctx = MagicMock()
        ctx.deps = deps

        prompt = await _synthesis_system_prompt(ctx)
        assert "vertical" in prompt

    @pytest.mark.asyncio
    async def test_spread_block_contains_pnl_profile(self) -> None:
        """Block includes net premium, max profit, max loss."""
        spread = make_spread_analysis(
            net_premium=Decimal("1.80"),
            max_profit=Decimal("3.20"),
            max_loss=Decimal("1.80"),
        )
        deps = _make_minimal_synthesis_deps(spread_analysis=spread)

        ctx = MagicMock()
        ctx.deps = deps

        prompt = await _synthesis_system_prompt(ctx)
        assert "1.80" in prompt
        assert "3.20" in prompt
        # max_loss value also present
        assert prompt.count("1.80") >= 2  # net_premium + max_loss

    @pytest.mark.asyncio
    async def test_spread_block_contains_risk_reward(self) -> None:
        """Block includes risk/reward ratio and P(profit)."""
        spread = make_spread_analysis(
            risk_reward_ratio=1.75,
            pop_estimate=0.62,
        )
        deps = _make_minimal_synthesis_deps(spread_analysis=spread)

        ctx = MagicMock()
        ctx.deps = deps

        prompt = await _synthesis_system_prompt(ctx)
        assert "1.75" in prompt
        assert "62%" in prompt

    @pytest.mark.asyncio
    async def test_spread_block_risk_reward_none(self) -> None:
        """risk_reward_ratio=None renders as '--' in the block."""
        spread = make_spread_analysis(risk_reward_ratio=None)
        block = _render_spread_block(spread)
        assert "Risk/reward ratio: --" in block

    @pytest.mark.asyncio
    async def test_spread_block_empty_rationale(self) -> None:
        """Empty strategy_rationale renders as 'N/A'."""
        spread = make_spread_analysis(strategy_rationale="")
        block = _render_spread_block(spread)
        assert "Rationale: N/A" in block

    @pytest.mark.asyncio
    async def test_spread_block_with_rationale(self) -> None:
        """Non-empty strategy_rationale is included verbatim."""
        spread = make_spread_analysis(strategy_rationale="High IV favors selling premium")
        block = _render_spread_block(spread)
        assert "High IV favors selling premium" in block


# ---------------------------------------------------------------------------
# Risk desk prompt -- spread context block
# ---------------------------------------------------------------------------


class TestRiskDeskSpreadContext:
    """Spread context block injection into risk desk recommendation prompt."""

    @pytest.mark.asyncio
    async def test_risk_desk_includes_spread(self) -> None:
        """Risk desk prompt includes spread context when available."""
        spread = make_spread_analysis(
            max_loss=Decimal("2.50"),
            pop_estimate=0.55,
            risk_reward_ratio=1.0,
        )
        ctx = MagicMock()
        ctx.deps = MagicMock()
        ctx.deps.learned_patterns = ""
        ctx.deps.spread_analysis = spread

        prompt = await _risk_recommend_prompt(ctx)
        assert "<<<SPREAD_CONTEXT>>>" in prompt
        assert "<<<END_SPREAD_CONTEXT>>>" in prompt
        assert "2.50" in prompt
        assert "55%" in prompt

    @pytest.mark.asyncio
    async def test_risk_desk_no_spread_when_none(self) -> None:
        """Risk desk prompt omits spread context when None."""
        ctx = MagicMock()
        ctx.deps = MagicMock()
        ctx.deps.learned_patterns = ""
        ctx.deps.spread_analysis = None

        prompt = await _risk_recommend_prompt(ctx)
        assert "<<<SPREAD_CONTEXT>>>" not in prompt
        assert "<<<END_SPREAD_CONTEXT>>>" not in prompt

    def test_risk_spread_block_contains_max_loss(self) -> None:
        """Risk spread block includes max loss value."""
        spread = make_spread_analysis(max_loss=Decimal("3.75"))
        block = _render_risk_spread_block(spread)
        assert "3.75" in block

    def test_risk_spread_block_contains_pop(self) -> None:
        """Risk spread block includes P(profit)."""
        spread = make_spread_analysis(pop_estimate=0.42)
        block = _render_risk_spread_block(spread)
        assert "42%" in block

    def test_risk_spread_block_risk_reward_none(self) -> None:
        """risk_reward_ratio=None renders as '--' in risk desk block."""
        spread = make_spread_analysis(risk_reward_ratio=None)
        block = _render_risk_spread_block(spread)
        assert "Risk/reward ratio: --" in block

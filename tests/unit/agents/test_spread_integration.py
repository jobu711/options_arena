"""Tests for spread data integration into debate agents and prompts.

Verifies:
- DebateDeps accepts spread_analysis field
- MarketContext accepts flat spread fields (all optional, default None)
- Volatility prompt renders spread section when data present, omits when None
- Risk prompt (full context block) renders spread risk profile when data present
- TradeThesis.recommended_strategy set from algorithmic SpreadAnalysis
- Algorithmic strategy takes priority over LLM suggestion
- No spread preserves LLM's recommended_strategy
"""

from __future__ import annotations

from decimal import Decimal

from pydantic_ai import models

from options_arena.agents._parsing import (
    DebateDeps,
    render_context_block,
    render_volatility_context,
)
from options_arena.models import (
    MarketContext,
    SignalDirection,
    SpreadType,
)
from tests.factories import (
    make_market_context,
    make_spread_analysis,
    make_ticker_score,
    make_trade_thesis,
)

# Prevent accidental real API calls in test suite
models.ALLOW_MODEL_REQUESTS = False


def _make_context_with_spread(**overrides: object) -> MarketContext:
    """Build a MarketContext with spread fields populated."""
    defaults: dict[str, object] = {
        "spread_type": SpreadType.VERTICAL,
        "spread_net_premium": Decimal("2.50"),
        "spread_max_profit": Decimal("2.50"),
        "spread_max_loss": Decimal("2.50"),
        "spread_pop": 0.55,
        "spread_risk_reward": 1.0,
    }
    defaults.update(overrides)
    return make_market_context(**defaults)


class TestDebateDepsSpread:
    """Tests for DebateDeps.spread_analysis field."""

    def test_debate_deps_accepts_spread(self) -> None:
        """Verify DebateDeps constructs with spread_analysis field."""
        sa = make_spread_analysis()
        ctx = make_market_context()
        score = make_ticker_score()
        deps = DebateDeps(
            context=ctx,
            ticker_score=score,
            contracts=[],
            spread_analysis=sa,
        )
        assert deps.spread_analysis is sa

    def test_debate_deps_spread_none_by_default(self) -> None:
        """Verify DebateDeps.spread_analysis defaults to None."""
        ctx = make_market_context()
        score = make_ticker_score()
        deps = DebateDeps(
            context=ctx,
            ticker_score=score,
            contracts=[],
        )
        assert deps.spread_analysis is None


class TestMarketContextSpreadFields:
    """Tests for spread fields on MarketContext."""

    def test_market_context_spread_fields(self) -> None:
        """Verify MarketContext accepts all 6 spread fields."""
        ctx = _make_context_with_spread()
        assert ctx.spread_type == SpreadType.VERTICAL
        assert ctx.spread_net_premium == Decimal("2.50")
        assert ctx.spread_max_profit == Decimal("2.50")
        assert ctx.spread_max_loss == Decimal("2.50")
        assert ctx.spread_pop == 0.55
        assert ctx.spread_risk_reward == 1.0

    def test_market_context_spread_none_by_default(self) -> None:
        """Verify all spread fields default to None."""
        ctx = make_market_context()
        assert ctx.spread_type is None
        assert ctx.spread_net_premium is None
        assert ctx.spread_max_profit is None
        assert ctx.spread_max_loss is None
        assert ctx.spread_pop is None
        assert ctx.spread_risk_reward is None

    def test_market_context_spread_json_roundtrip(self) -> None:
        """Verify spread Decimal fields survive JSON serialization."""
        ctx = _make_context_with_spread()
        dumped = ctx.model_dump_json()
        restored = MarketContext.model_validate_json(dumped)
        assert restored.spread_net_premium == Decimal("2.50")
        assert restored.spread_max_profit == Decimal("2.50")
        assert restored.spread_max_loss == Decimal("2.50")
        assert restored.spread_type == SpreadType.VERTICAL

    def test_market_context_spread_none_json_roundtrip(self) -> None:
        """Verify None spread fields survive JSON serialization."""
        ctx = make_market_context()
        dumped = ctx.model_dump_json()
        restored = MarketContext.model_validate_json(dumped)
        assert restored.spread_type is None
        assert restored.spread_net_premium is None


class TestVolatilityPromptSpread:
    """Tests for spread section in volatility agent context rendering."""

    def test_volatility_prompt_includes_spread(self) -> None:
        """Verify volatility prompt renders spread section when data present."""
        ctx = _make_context_with_spread()
        rendered = render_volatility_context(ctx)

        assert "## Algorithmic Strategy Recommendation" in rendered
        assert "STRATEGY: vertical" in rendered
        assert "NET PREMIUM: $2.50" in rendered
        assert "POP: 55.0%" in rendered

    def test_volatility_prompt_omits_spread_when_none(self) -> None:
        """Verify volatility prompt has no spread section when spread is None."""
        ctx = make_market_context()
        rendered = render_volatility_context(ctx)

        assert "## Algorithmic Strategy Recommendation" not in rendered
        assert "STRATEGY:" not in rendered
        assert "NET PREMIUM:" not in rendered

    def test_volatility_prompt_spread_with_nan_pop(self) -> None:
        """Verify _render_optional guards NaN pop_estimate."""
        ctx = _make_context_with_spread(spread_pop=None)
        rendered = render_volatility_context(ctx)

        assert "## Algorithmic Strategy Recommendation" in rendered
        assert "STRATEGY: vertical" in rendered
        # POP should be omitted when None
        assert "POP:" not in rendered


class TestRiskPromptSpread:
    """Tests for spread risk profile in full context block (used by Risk agent)."""

    def test_risk_prompt_includes_spread_risk(self) -> None:
        """Verify risk prompt renders max_loss, risk/reward, PoP."""
        ctx = _make_context_with_spread()
        rendered = render_context_block(ctx)

        assert "## Spread Risk Profile" in rendered
        assert "STRATEGY: vertical" in rendered
        assert "MAX LOSS: $2.50" in rendered
        assert "MAX PROFIT: $2.50" in rendered
        assert "RISK/REWARD: 1.00" in rendered
        assert "POP: 55.0%" in rendered

    def test_risk_prompt_omits_spread_when_none(self) -> None:
        """Verify risk prompt has no spread section when spread is None."""
        ctx = make_market_context()
        rendered = render_context_block(ctx)

        assert "## Spread Risk Profile" not in rendered
        assert "MAX LOSS:" not in rendered

    def test_risk_prompt_spread_partial_data(self) -> None:
        """Verify spread section renders with only some fields populated."""
        ctx = _make_context_with_spread(
            spread_risk_reward=None,
            spread_pop=None,
        )
        rendered = render_context_block(ctx)

        assert "## Spread Risk Profile" in rendered
        assert "STRATEGY: vertical" in rendered
        assert "MAX LOSS: $2.50" in rendered
        assert "MAX PROFIT: $2.50" in rendered
        # Optional fields should be omitted
        assert "RISK/REWARD:" not in rendered
        assert "POP:" not in rendered


class TestThesisRecommendedStrategy:
    """Tests for TradeThesis.recommended_strategy override from algorithmic engine."""

    def test_thesis_recommended_strategy_from_algorithmic(self) -> None:
        """Verify TradeThesis.recommended_strategy set from SpreadAnalysis."""
        thesis = make_trade_thesis(recommended_strategy=None)
        sa = make_spread_analysis()

        updated = thesis.model_copy(update={"recommended_strategy": sa.spread.spread_type})
        assert updated.recommended_strategy == SpreadType.VERTICAL

    def test_algorithmic_overrides_llm_suggestion(self) -> None:
        """Verify algorithmic strategy takes priority over LLM's suggestion."""
        # LLM suggested iron_condor, algorithmic suggests vertical
        thesis = make_trade_thesis(recommended_strategy=SpreadType.IRON_CONDOR)
        sa = make_spread_analysis()  # defaults to VERTICAL

        updated = thesis.model_copy(update={"recommended_strategy": sa.spread.spread_type})
        assert updated.recommended_strategy == SpreadType.VERTICAL
        assert updated.recommended_strategy != SpreadType.IRON_CONDOR

    def test_no_spread_preserves_llm_suggestion(self) -> None:
        """Verify when no spread, LLM's recommended_strategy is preserved."""
        thesis = make_trade_thesis(recommended_strategy=SpreadType.STRADDLE)
        # No spread_analysis -> no override
        assert thesis.recommended_strategy == SpreadType.STRADDLE

    def test_model_copy_preserves_other_fields(self) -> None:
        """Verify model_copy only changes recommended_strategy, not other fields."""
        thesis = make_trade_thesis(
            recommended_strategy=None,
            confidence=0.70,
            direction=SignalDirection.BULLISH,
        )
        sa = make_spread_analysis()

        updated = thesis.model_copy(update={"recommended_strategy": sa.spread.spread_type})
        assert updated.recommended_strategy == SpreadType.VERTICAL
        assert updated.confidence == 0.70
        assert updated.direction == SignalDirection.BULLISH
        assert updated.ticker == thesis.ticker
        assert updated.summary == thesis.summary

"""Complexity-based model routing for desk agents.

Assesses ticker analysis difficulty from MarketContext + TickerScore fields
and routes each desk agent to an appropriate LLM model tier (FAST, STANDARD,
PREMIUM). Risk desk always uses STANDARD+. Synthesis always uses PREMIUM
when routing is enabled.

When ``enable_model_routing`` is ``False`` (default), all desks use STANDARD.
"""

import logging
import math
from datetime import date

from pydantic_ai.models import Model

from options_arena.agents.model_config import build_debate_model
from options_arena.models import (
    DebateConfig,
    DeskType,
    ModelTier,
    RoutingConfig,
)
from options_arena.models.analysis import MarketContext
from options_arena.models.scan import TickerScore

logger = logging.getLogger(__name__)


def _assess_complexity(context: MarketContext, ticker_score: TickerScore) -> float:
    """Score ticker analysis difficulty from 0.0 (simple) to 1.0 (complex).

    Each heuristic adds a weighted contribution. All optional float fields are
    guarded with ``is not None and math.isfinite()`` before comparison (NaN defense).
    """
    score = 0.0

    # Low data completeness = more inference needed
    completeness = context.completeness_ratio()
    if math.isfinite(completeness) and completeness < 0.6:
        score += 0.2

    # Earnings within 7 days = event uncertainty
    if context.next_earnings is not None:
        days_to_earnings = (context.next_earnings - date.today()).days
        if days_to_earnings <= 7:
            score += 0.2

    signals = ticker_score.signals

    # RSI extremes (overbought/oversold)
    if (
        signals.rsi is not None
        and math.isfinite(signals.rsi)
        and (signals.rsi > 80 or signals.rsi < 20)
    ):
        score += 0.1

    # Extreme IV regime
    if signals.iv_rank is not None and math.isfinite(signals.iv_rank) and signals.iv_rank > 80:
        score += 0.15

    # Unusual flow
    if (
        signals.put_call_ratio is not None
        and math.isfinite(signals.put_call_ratio)
        and (signals.put_call_ratio > 2.0 or signals.put_call_ratio < 0.3)
    ):
        score += 0.1

    # No clear trend = harder to analyze
    if signals.adx is not None and math.isfinite(signals.adx) and signals.adx < 15:
        score += 0.1

    # Extreme composite scores are ambiguous
    cs = ticker_score.composite_score
    if math.isfinite(cs) and (cs < 30 or cs > 85):
        score += 0.15

    return min(1.0, max(0.0, score))


def route_model_tier(
    desk: DeskType,
    context: MarketContext,
    ticker_score: TickerScore,
    config: RoutingConfig,
) -> ModelTier:
    """Select the model tier for a desk agent based on complexity.

    When routing is disabled, returns STANDARD for all desks.
    Risk desk always returns STANDARD or higher (never FAST).
    """
    if not config.enable_model_routing:
        return ModelTier.STANDARD

    complexity = _assess_complexity(context, ticker_score)
    logger.debug("Complexity for %s (%s desk): %.3f", context.ticker, desk, complexity)

    if complexity < config.complexity_threshold_fast:
        tier = ModelTier.FAST
    elif complexity >= config.complexity_threshold_premium:
        tier = ModelTier.PREMIUM
    else:
        tier = ModelTier.STANDARD

    # Risk desk safety: never use FAST
    if desk == DeskType.RISK and tier == ModelTier.FAST:
        tier = ModelTier.STANDARD

    return tier


def build_model_for_tier(tier: ModelTier, config: DebateConfig) -> Model:
    """Construct a PydanticAI Model for the given tier.

    FAST overrides the model name to ``config.routing.fast_model``.
    STANDARD uses the default model from ``config.model``.
    PREMIUM uses ``config.routing.premium_model`` if set, otherwise the default.
    """
    match tier:
        case ModelTier.FAST:
            # Temporarily override model name for fast tier
            override = config.model_copy(update={"model": config.routing.fast_model})
            return build_debate_model(override)
        case ModelTier.STANDARD:
            return build_debate_model(config)
        case ModelTier.PREMIUM:
            if config.routing.premium_model:
                override = config.model_copy(update={"model": config.routing.premium_model})
                return build_debate_model(override)
            return build_debate_model(config)

"""Reusable context-building and prediction-extraction functions.

Extracted from ``orchestrator.py`` so that both the debate orchestrator and the
recommendation orchestrator can share the same logic without circular imports.

All functions are **pure** — no I/O, no API calls, no side effects beyond logging.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from datetime import UTC, date, datetime
from enum import StrEnum

from pydantic_ai.models.anthropic import AnthropicModelSettings
from pydantic_ai.settings import ModelSettings

from options_arena.agents._parsing import DebateResult
from options_arena.models import (
    AgentPrediction,
    DebateConfig,
    ExerciseStyle,
    LLMProvider,
    MacdSignal,
    MacroRegime,
    MarketContext,
    OptionContract,
    Quote,
    SignalDirection,
    TickerInfo,
    TickerScore,
)
from options_arena.models.financial_datasets import FinancialDatasetsPackage
from options_arena.models.intelligence import IntelligencePackage

logger = logging.getLogger(__name__)


def should_debate(ticker_score: TickerScore, config: DebateConfig) -> bool:
    """Return False if signal is too weak for meaningful AI debate.

    Pure function — no side effects, no I/O, no logging. Score comparison
    uses ``<`` so that a score exactly at ``min_recommendation_score`` returns True.
    """
    if ticker_score.direction == SignalDirection.NEUTRAL:
        return False
    return ticker_score.composite_score >= config.min_recommendation_score


def should_recommend(ticker_score: TickerScore, config: DebateConfig) -> bool:
    """Return True if signal is strong enough for a recommendation.

    Reads ``config.min_recommendation_score`` — unified gate for both
    debate and recommendation pipelines.
    """
    if ticker_score.direction == SignalDirection.NEUTRAL:
        return False
    return ticker_score.composite_score >= config.min_recommendation_score


def classify_macd_signal(macd_value: float | None) -> MacdSignal:
    """Classify a centered MACD value into a signal.

    The scan pipeline stores MACD as a normalized 0-100 percentile on
    ``IndicatorSignals.macd``.  The caller centres the value by subtracting
    50 before passing it here so that the sign indicates histogram direction:

    * positive  -> ``BULLISH_CROSSOVER``
    * negative  -> ``BEARISH_CROSSOVER``
    * zero / ``None`` / non-finite  -> ``NEUTRAL``

    Parameters
    ----------
    macd_value
        Centered MACD value (normalized - 50), or ``None`` when the
        indicator was not computed.

    Returns
    -------
    MacdSignal
        Classification based on histogram sign.
    """
    if macd_value is None or not math.isfinite(macd_value):
        return MacdSignal.NEUTRAL
    if macd_value > 0:
        return MacdSignal.BULLISH_CROSSOVER
    if macd_value < 0:
        return MacdSignal.BEARISH_CROSSOVER
    return MacdSignal.NEUTRAL


def build_market_context(
    ticker_score: TickerScore,
    quote: Quote,
    ticker_info: TickerInfo,
    contracts: list[OptionContract],
    next_earnings: date | None = None,
    intelligence: IntelligencePackage | None = None,
    fd_package: FinancialDatasetsPackage | None = None,
    macro_regime: MacroRegime | None = None,
    macro_yield_spread: float | None = None,
    macro_fed_funds_rate: float | None = None,
    macro_vix_level: float | None = None,
    prob_profit_neural: float | None = None,
) -> MarketContext:
    """Map scan pipeline output to ``MarketContext`` for agent consumption.

    Passes ``None`` through for optional float fields so that
    ``MarketContext.completeness_ratio()`` accurately reflects data availability.
    Options-specific indicators (``iv_rank``, ``iv_percentile``,
    ``put_call_ratio``) may be ``None`` on ``TickerScore.signals``.

    Parameters
    ----------
    ticker_score
        Scored ticker from the scan pipeline with indicator signals.
    quote
        Real-time price snapshot.
    ticker_info
        Fundamental data including dividend yield and 52-week range.
    contracts
        Recommended option contracts (may be empty).
    next_earnings
        Next earnings date for the ticker, or ``None`` if unknown.

    Returns
    -------
    MarketContext
        Flat snapshot of ticker state for agent consumption.
    """
    signals = ticker_score.signals

    # Classify MACD from real indicator signal (normalized 0-100, centred to sign)
    _raw_macd = (signals.macd - 50.0) if signals.macd is not None else None
    macd_signal = classify_macd_signal(_raw_macd)

    # Contract-derived fields with safe defaults
    first_contract = contracts[0] if contracts else None
    dte_target = first_contract.dte if first_contract is not None else 45
    target_strike = first_contract.strike if first_contract is not None else quote.price
    target_delta: float
    if first_contract is not None and first_contract.greeks is not None:
        target_delta = first_contract.greeks.delta
    else:
        target_delta = 0.35

    return MarketContext(
        ticker=ticker_score.ticker,
        current_price=quote.price,
        price_52w_high=ticker_info.fifty_two_week_high,
        price_52w_low=ticker_info.fifty_two_week_low,
        iv_rank=signals.iv_rank,
        iv_percentile=signals.iv_percentile,
        atm_iv_30d=(
            first_contract.market_iv
            if first_contract is not None
            and math.isfinite(first_contract.market_iv)
            and first_contract.market_iv > 0
            else None
        ),
        rsi_14=signals.rsi if signals.rsi is not None else 50.0,
        macd_signal=macd_signal,
        put_call_ratio=signals.put_call_ratio,
        next_earnings=next_earnings,
        dte_target=dte_target,
        target_strike=target_strike,
        target_delta=target_delta,
        sector=ticker_info.sector,
        dividend_yield=ticker_info.dividend_yield,
        exercise_style=ExerciseStyle.AMERICAN,
        data_timestamp=datetime.now(UTC),
        # Scoring context
        composite_score=ticker_score.composite_score,
        direction_signal=ticker_score.direction,
        # Key indicators (pass through from signals — already float | None)
        adx=signals.adx,
        sma_alignment=signals.sma_alignment,
        bb_width=signals.bb_width,
        atr_pct=signals.atr_pct,
        stochastic_rsi=signals.stochastic_rsi,
        relative_volume=signals.relative_volume,
        # Greeks beyond delta (None-safe access)
        target_gamma=(
            first_contract.greeks.gamma if first_contract and first_contract.greeks else None
        ),
        target_theta=(
            first_contract.greeks.theta if first_contract and first_contract.greeks else None
        ),
        target_vega=(
            first_contract.greeks.vega if first_contract and first_contract.greeks else None
        ),
        target_rho=(
            first_contract.greeks.rho if first_contract and first_contract.greeks else None
        ),
        # Options-specific indicators
        max_pain_distance=signals.max_pain_distance,
        # Contract pricing
        contract_mid=first_contract.mid if first_contract else None,
        # Short interest
        short_ratio=ticker_info.short_ratio,
        short_pct_of_float=ticker_info.short_pct_of_float,
        # --- Arena Recon: Intelligence fields ---
        analyst_target_mean=(
            intelligence.analyst.target_mean if intelligence and intelligence.analyst else None
        ),
        analyst_target_upside_pct=(
            intelligence.analyst.target_upside_pct
            if intelligence and intelligence.analyst
            else None
        ),
        analyst_consensus_score=(
            intelligence.analyst.consensus_score if intelligence and intelligence.analyst else None
        ),
        analyst_upgrades_30d=(
            intelligence.analyst_activity.upgrades_30d
            if intelligence and intelligence.analyst_activity
            else None
        ),
        analyst_downgrades_30d=(
            intelligence.analyst_activity.downgrades_30d
            if intelligence and intelligence.analyst_activity
            else None
        ),
        insider_net_buys_90d=(
            intelligence.insider.net_insider_buys_90d
            if intelligence and intelligence.insider
            else None
        ),
        insider_buy_ratio=(
            intelligence.insider.insider_buy_ratio
            if intelligence and intelligence.insider
            else None
        ),
        institutional_pct=(
            intelligence.institutional.institutional_pct
            if intelligence and intelligence.institutional
            else None
        ),
        # --- DSE: Dimensional scores (from TickerScore.dimensional_scores) ---
        dim_trend=(
            ticker_score.dimensional_scores.trend if ticker_score.dimensional_scores else None
        ),
        dim_iv_vol=(
            ticker_score.dimensional_scores.iv_vol if ticker_score.dimensional_scores else None
        ),
        dim_hv_vol=(
            ticker_score.dimensional_scores.hv_vol if ticker_score.dimensional_scores else None
        ),
        dim_flow=(
            ticker_score.dimensional_scores.flow if ticker_score.dimensional_scores else None
        ),
        dim_microstructure=(
            ticker_score.dimensional_scores.microstructure
            if ticker_score.dimensional_scores
            else None
        ),
        dim_fundamental=(
            ticker_score.dimensional_scores.fundamental
            if ticker_score.dimensional_scores
            else None
        ),
        dim_regime=(
            ticker_score.dimensional_scores.regime if ticker_score.dimensional_scores else None
        ),
        dim_risk=(
            ticker_score.dimensional_scores.risk if ticker_score.dimensional_scores else None
        ),
        # --- DSE: High-signal individual indicators (from TickerScore.signals) ---
        vol_regime=signals.vol_regime,
        iv_hv_spread=signals.iv_hv_spread,
        gex=signals.gex,
        unusual_activity_score=signals.unusual_activity_score,
        skew_ratio=signals.skew_ratio,
        vix_term_structure=signals.vix_term_structure,
        market_regime=signals.market_regime,
        rsi_divergence=signals.rsi_divergence,
        expected_move=signals.expected_move,
        expected_move_ratio=signals.expected_move_ratio,
        # --- DSE: Second-order Greeks (from recommended contract) ---
        target_vanna=(
            first_contract.greeks.vanna if first_contract and first_contract.greeks else None
        ),
        target_charm=(
            first_contract.greeks.charm if first_contract and first_contract.greeks else None
        ),
        target_vomma=(
            first_contract.greeks.vomma if first_contract and first_contract.greeks else None
        ),
        # --- Native Quant: HV & Vol Surface ---
        hv_yang_zhang=signals.hv_yang_zhang,
        skew_25d=signals.skew_25d,
        smile_curvature=signals.smile_curvature,
        prob_above_current=signals.prob_above_current,
        # --- ML Volatility Forecasts ---
        vol_forecast_garch=signals.vol_forecast_garch,
        iv_vs_forecast_spread=signals.iv_vs_forecast_spread,
        # --- Volatility Intelligence: Surface Mispricing ---
        iv_surface_residual=signals.iv_surface_residual,
        surface_fit_r2=signals.surface_fit_r2,
        surface_is_1d=(
            bool(signals.surface_is_1d >= 0.5) if signals.surface_is_1d is not None else None
        ),
        # --- DSE: Direction confidence ---
        direction_confidence=ticker_score.direction_confidence,
        # --- Financial Datasets enrichment (fd_* fields) ---
        fd_revenue=(
            fd_package.income.revenue
            if fd_package and fd_package.income and fd_package.income.revenue is not None
            else None
        ),
        fd_net_income=(
            fd_package.income.net_income
            if fd_package and fd_package.income and fd_package.income.net_income is not None
            else None
        ),
        fd_gross_profit=(
            fd_package.income.gross_profit
            if fd_package and fd_package.income and fd_package.income.gross_profit is not None
            else None
        ),
        fd_operating_income=(
            fd_package.income.operating_income
            if fd_package and fd_package.income and fd_package.income.operating_income is not None
            else None
        ),
        fd_eps_diluted=(
            fd_package.income.eps_diluted
            if fd_package and fd_package.income and fd_package.income.eps_diluted is not None
            else (
                fd_package.metrics.eps_diluted
                if fd_package and fd_package.metrics and fd_package.metrics.eps_diluted is not None
                else None
            )
        ),
        fd_gross_margin=(
            fd_package.income.gross_margin
            if fd_package and fd_package.income and fd_package.income.gross_margin is not None
            else (
                fd_package.metrics.gross_margin
                if fd_package
                and fd_package.metrics
                and fd_package.metrics.gross_margin is not None
                else None
            )
        ),
        fd_operating_margin=(
            fd_package.income.operating_margin
            if fd_package and fd_package.income and fd_package.income.operating_margin is not None
            else (
                fd_package.metrics.operating_margin
                if fd_package
                and fd_package.metrics
                and fd_package.metrics.operating_margin is not None
                else None
            )
        ),
        fd_net_margin=(
            fd_package.income.net_margin
            if fd_package and fd_package.income and fd_package.income.net_margin is not None
            else (
                fd_package.metrics.net_margin
                if fd_package and fd_package.metrics and fd_package.metrics.net_margin is not None
                else None
            )
        ),
        fd_total_debt=(
            fd_package.balance_sheet.total_debt
            if fd_package
            and fd_package.balance_sheet
            and fd_package.balance_sheet.total_debt is not None
            else None
        ),
        fd_total_cash=(
            fd_package.balance_sheet.total_cash
            if fd_package
            and fd_package.balance_sheet
            and fd_package.balance_sheet.total_cash is not None
            else None
        ),
        fd_total_assets=(
            fd_package.balance_sheet.total_assets
            if fd_package
            and fd_package.balance_sheet
            and fd_package.balance_sheet.total_assets is not None
            else None
        ),
        fd_current_ratio=(
            fd_package.metrics.current_ratio
            if fd_package and fd_package.metrics and fd_package.metrics.current_ratio is not None
            else None
        ),
        fd_revenue_growth=(
            fd_package.metrics.revenue_growth
            if fd_package and fd_package.metrics and fd_package.metrics.revenue_growth is not None
            else None
        ),
        fd_earnings_growth=(
            fd_package.metrics.earnings_growth
            if fd_package and fd_package.metrics and fd_package.metrics.earnings_growth is not None
            else None
        ),
        fd_ev_to_ebitda=(
            fd_package.metrics.enterprise_value_to_ebitda
            if fd_package
            and fd_package.metrics
            and fd_package.metrics.enterprise_value_to_ebitda is not None
            else None
        ),
        fd_free_cash_flow_yield=(
            fd_package.metrics.free_cash_flow_yield
            if fd_package
            and fd_package.metrics
            and fd_package.metrics.free_cash_flow_yield is not None
            else None
        ),
        # --- Financial Datasets enrichment: valuation model inputs ---
        # NOTE: capex, D&A, absolute FCF, and book_value_per_share are not yet on
        # the FD models — they will be added by FinancialDatasets epic #393.
        # For now these remain None; shares_outstanding and ROE are available.
        fd_shares_outstanding=(
            float(fd_package.balance_sheet.shares_outstanding)
            if fd_package
            and fd_package.balance_sheet
            and fd_package.balance_sheet.shares_outstanding is not None
            else None
        ),
        fd_roe=(
            fd_package.metrics.return_on_equity
            if fd_package
            and fd_package.metrics
            and fd_package.metrics.return_on_equity is not None
            else None
        ),
        # --- Macro Context (FRED) ---
        macro_regime=macro_regime,
        yield_spread=macro_yield_spread,
        fed_funds_rate=macro_fed_funds_rate,
        vix_level=macro_vix_level,
        # --- Neural Trajectory ---
        prob_profit_neural=prob_profit_neural,
    )


def _log_completeness_breakdown(context: MarketContext, ratio: float) -> None:
    """Log which MarketContext fields are populated vs missing for diagnostics."""
    field_checks: list[tuple[str, float | None]] = [
        ("iv_rank", context.iv_rank),
        ("iv_percentile", context.iv_percentile),
        ("atm_iv_30d", context.atm_iv_30d),
        ("put_call_ratio", context.put_call_ratio),
        ("max_pain_distance", context.max_pain_distance),
        ("adx", context.adx),
        ("sma_alignment", context.sma_alignment),
        ("bb_width", context.bb_width),
        ("atr_pct", context.atr_pct),
        ("stochastic_rsi", context.stochastic_rsi),
        ("relative_volume", context.relative_volume),
    ]
    if context.contract_mid is not None:
        field_checks.extend(
            [
                ("target_gamma", context.target_gamma),
                ("target_theta", context.target_theta),
                ("target_vega", context.target_vega),
                ("target_rho", context.target_rho),
            ]
        )

    populated = [name for name, val in field_checks if val is not None]
    missing = [name for name, val in field_checks if val is None]

    logger.info(
        "MarketContext completeness for %s: %.0f%% (%d/%d) — populated=[%s], missing=[%s]",
        context.ticker,
        ratio * 100,
        len(populated),
        len(field_checks),
        ", ".join(populated),
        ", ".join(missing),
    )


def extract_agent_predictions(
    debate_id: int,
    result: DebateResult,
    recommended_contract_id: int | None = None,
) -> list[AgentPrediction]:
    """Extract per-agent predictions from a DebateResult for accuracy tracking.

    Each agent response type is handled individually because they have different
    field names for direction and confidence (e.g. ``dissent_direction`` on
    ``ContrarianThesis``, no direction on ``RiskAssessment``).

    ``bull_response`` holds the trend agent output (backward-compat shim).
    Extract as "trend" to avoid conflating with the retired bull agent.
    ``bear_response`` is a static fallback — skip it to avoid misleading data.

    Args:
        debate_id: Database ID of the persisted debate.
        result: Completed debate result with agent responses.
        recommended_contract_id: Matching contract from ``recommended_contracts``
            table.  Needed for accuracy queries that JOIN predictions to outcomes.

    Returns a list of ``AgentPrediction`` — empty if all agents failed.
    """
    now = datetime.now(UTC)
    predictions: list[AgentPrediction] = []

    # bull_response holds the trend agent output (backward-compat shim).
    if result.bull_response is not None:
        predictions.append(
            AgentPrediction(
                debate_id=debate_id,
                recommended_contract_id=recommended_contract_id,
                agent_name="trend",
                direction=result.bull_response.direction,
                confidence=result.bull_response.confidence,
                created_at=now,
            )
        )

    # Flow response (FlowThesis — has direction + confidence)
    if result.flow_response is not None:
        predictions.append(
            AgentPrediction(
                debate_id=debate_id,
                recommended_contract_id=recommended_contract_id,
                agent_name="flow",
                direction=result.flow_response.direction,
                confidence=result.flow_response.confidence,
                created_at=now,
            )
        )

    # Fundamental response (FundamentalThesis — has direction + confidence)
    if result.fundamental_response is not None:
        predictions.append(
            AgentPrediction(
                debate_id=debate_id,
                recommended_contract_id=recommended_contract_id,
                agent_name="fundamental",
                direction=result.fundamental_response.direction,
                confidence=result.fundamental_response.confidence,
                created_at=now,
            )
        )

    # Volatility response (VolatilityThesis — has direction + confidence)
    if result.vol_response is not None:
        predictions.append(
            AgentPrediction(
                debate_id=debate_id,
                recommended_contract_id=recommended_contract_id,
                agent_name="volatility",
                direction=result.vol_response.direction,
                confidence=result.vol_response.confidence,
                created_at=now,
            )
        )

    # Risk response (RiskAssessment — has confidence, no direction field)
    if result.risk_response is not None:
        predictions.append(
            AgentPrediction(
                debate_id=debate_id,
                recommended_contract_id=recommended_contract_id,
                agent_name="risk",
                direction=None,
                confidence=result.risk_response.confidence,
                created_at=now,
            )
        )

    # Contrarian response (ContrarianThesis — has dissent_direction + dissent_confidence)
    if result.contrarian_response is not None:
        predictions.append(
            AgentPrediction(
                debate_id=debate_id,
                recommended_contract_id=recommended_contract_id,
                agent_name="contrarian",
                direction=result.contrarian_response.dissent_direction,
                confidence=result.contrarian_response.dissent_confidence,
                created_at=now,
            )
        )

    return predictions


def _build_model_settings(config: DebateConfig) -> ModelSettings:
    """Build provider-appropriate ``ModelSettings`` for agent runs.

    When provider is Anthropic and extended thinking is enabled, returns
    ``AnthropicModelSettings`` with ``anthropic_thinking`` configured and
    temperature forced to ``1.0`` (required by the Anthropic thinking API).
    Otherwise returns standard ``ModelSettings`` with the configured temperature.

    Groq ignores ``enable_extended_thinking`` — thinking is Anthropic-only.
    """
    if config.provider == LLMProvider.ANTHROPIC and config.enable_extended_thinking:
        return AnthropicModelSettings(
            temperature=1.0,
            anthropic_thinking={
                "type": "enabled",
                "budget_tokens": config.thinking_budget_tokens,
            },
        )
    return ModelSettings(temperature=config.temperature)


# ---------------------------------------------------------------------------
# Debate-era progress types — kept for backward-compat WebSocket bridges
# ---------------------------------------------------------------------------


class DebatePhase(StrEnum):
    """Phases of the AI debate pipeline, reported via progress callback."""

    TREND = "trend"
    VOLATILITY = "volatility"
    FLOW = "flow"
    FUNDAMENTAL = "fundamental"
    RISK = "risk"
    CONTRARIAN = "contrarian"


type DebateProgressCallback = Callable[[DebatePhase, str, float | None], None]
"""Callback for debate progress: ``(phase, status, confidence_or_none)``."""


# ---------------------------------------------------------------------------
# Provider-aware batch delay — moved from orchestrator.py
# ---------------------------------------------------------------------------

_GROQ_DEFAULT_BATCH_TICKER_DELAY = 5.0
_ANTHROPIC_SAFE_BATCH_TICKER_DELAY = 30.0


def effective_batch_ticker_delay(config: DebateConfig) -> float:
    """Return inter-ticker batch delay, auto-adjusted for Anthropic provider.

    When the provider is Anthropic and the stored ``batch_ticker_delay`` is the
    Groq default (5 s), substitute 30 s to stay within the 8K output-tokens/min
    Tier 1 limit (~1.8 debates/min safe throughput).  User overrides via
    ``ARENA_DEBATE__BATCH_TICKER_DELAY`` are respected.
    """
    delay = config.batch_ticker_delay

    if config.provider != LLMProvider.ANTHROPIC:
        return delay

    if delay == _GROQ_DEFAULT_BATCH_TICKER_DELAY:
        delay = _ANTHROPIC_SAFE_BATCH_TICKER_DELAY
        logger.info(
            "Anthropic provider: batch_ticker_delay=%.1fs (auto-adjusted for rate limits)",
            delay,
        )
    return delay

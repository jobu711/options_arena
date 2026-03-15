"""Orchestrator for the Options Arena AI debate system.

Coordinates six specialized agents (trend, volatility, flow, fundamental, risk,
contrarian) via Groq cloud API. Accumulates token usage, computes weighted verdict,
and returns a ``DebateResult``. On ANY failure (connection error, timeout, invalid
LLM output, etc.), returns a data-driven fallback — ``run_debate()`` never raises.

Protocol flow:
  Phase 1 (parallel): trend + volatility (always), flow + fundamental (when enrichment exists)
  Phase 2 (sequential): risk agent with all Phase 1 outputs
  Phase 3 (sequential): contrarian with all prior outputs (skip if >=3 Phase 1 failures)
  Phase 4 (algorithmic): synthesize_verdict -> ExtendedTradeThesis

Architecture rules:
- Every ``agent.run()`` is wrapped in ``asyncio.wait_for(timeout=...)``.
- The orchestrator does NOT fetch data — all inputs are pre-fetched by the caller.
- ``time.monotonic()`` for duration measurement, never ``time.time()``.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import cast

from pydantic_ai import AgentRunResult
from pydantic_ai.models.anthropic import AnthropicModelSettings
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import RunUsage

from options_arena.agents._parsing import (
    DebateDeps,
    DebateResult,
    compute_citation_density,
    render_context_block,
    render_flow_context,
    render_fundamental_context,
    render_trend_context,
    render_volatility_context,
)
from options_arena.agents.constraints import (
    check_contract_constraints,
    render_constraint_warnings,
)
from options_arena.agents.contrarian_agent import contrarian_agent
from options_arena.agents.flow_agent import flow_agent
from options_arena.agents.fundamental_agent import fundamental_agent
from options_arena.agents.model_config import build_debate_model
from options_arena.agents.risk import risk_agent
from options_arena.agents.trend_agent import trend_agent
from options_arena.agents.volatility import volatility_agent
from options_arena.analysis.position_sizing import compute_position_size
from options_arena.analysis.valuation import FDData, compute_composite_valuation
from options_arena.data.repository import Repository
from options_arena.models import (
    AgentAccuracyReport,
    AgentPrediction,
    AgentResponse,
    AgentWeightsComparison,
    ContrarianThesis,
    DebateConfig,
    DimensionalScores,
    ExerciseStyle,
    ExtendedTradeThesis,
    FlowThesis,
    FundamentalSnapshot,
    FundamentalThesis,
    LLMProvider,
    MacdSignal,
    MarketContext,
    NewsSentimentSnapshot,
    OptionContract,
    OptionsFilters,
    Quote,
    RiskAssessment,
    SignalDirection,
    SpreadAnalysis,
    TickerInfo,
    TickerScore,
    TradeThesis,
    UnusualFlowSnapshot,
    VolatilityThesis,
)
from options_arena.models.financial_datasets import FinancialDatasetsPackage
from options_arena.models.intelligence import IntelligencePackage

logger = logging.getLogger(__name__)


class DebatePhase(StrEnum):
    """Phases of the AI debate pipeline, reported via progress callback."""

    BULL = "bull"
    BEAR = "bear"
    REBUTTAL = "rebuttal"
    VOLATILITY = "volatility"
    RISK = "risk"


type DebateProgressCallback = Callable[[DebatePhase, str, float | None], None]
"""Callback for debate progress: ``(phase, status, confidence_or_none)``."""


def should_debate(ticker_score: TickerScore, config: DebateConfig) -> bool:
    """Return False if signal is too weak for meaningful AI debate.

    Pure function — no side effects, no I/O, no logging. Score comparison
    uses ``<`` so that a score exactly at ``min_debate_score`` returns True.
    """
    if ticker_score.direction == SignalDirection.NEUTRAL:
        return False
    return ticker_score.composite_score >= config.min_debate_score


def build_market_context(
    ticker_score: TickerScore,
    quote: Quote,
    ticker_info: TickerInfo,
    contracts: list[OptionContract],
    next_earnings: date | None = None,
    fundamentals: FundamentalSnapshot | None = None,
    flow: UnusualFlowSnapshot | None = None,
    sentiment: NewsSentimentSnapshot | None = None,
    intelligence: IntelligencePackage | None = None,
    fd_package: FinancialDatasetsPackage | None = None,
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
            if first_contract is not None and first_contract.market_iv > 0
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
        # Fundamental ratios — FD > OpenBB > None priority for 7 overlapping fields
        pe_ratio=(
            fd_package.metrics.pe_ratio
            if fd_package and fd_package.metrics and fd_package.metrics.pe_ratio is not None
            else (fundamentals.pe_ratio if fundamentals else None)
        ),
        forward_pe=(
            fd_package.metrics.forward_pe
            if fd_package and fd_package.metrics and fd_package.metrics.forward_pe is not None
            else (fundamentals.forward_pe if fundamentals else None)
        ),
        peg_ratio=(
            fd_package.metrics.peg_ratio
            if fd_package and fd_package.metrics and fd_package.metrics.peg_ratio is not None
            else (fundamentals.peg_ratio if fundamentals else None)
        ),
        price_to_book=(
            fd_package.metrics.price_to_book
            if fd_package and fd_package.metrics and fd_package.metrics.price_to_book is not None
            else (fundamentals.price_to_book if fundamentals else None)
        ),
        debt_to_equity=(
            fd_package.metrics.debt_to_equity
            if fd_package and fd_package.metrics and fd_package.metrics.debt_to_equity is not None
            else (fundamentals.debt_to_equity if fundamentals else None)
        ),
        revenue_growth=(
            fd_package.metrics.revenue_growth
            if fd_package and fd_package.metrics and fd_package.metrics.revenue_growth is not None
            else (fundamentals.revenue_growth if fundamentals else None)
        ),
        profit_margin=(
            fd_package.metrics.profit_margin
            if fd_package and fd_package.metrics and fd_package.metrics.profit_margin is not None
            else (fundamentals.profit_margin if fundamentals else None)
        ),
        # OpenBB enrichment — unusual flow
        net_call_premium=flow.net_call_premium if flow else None,
        net_put_premium=flow.net_put_premium if flow else None,
        options_put_call_ratio=flow.put_call_ratio if flow else None,
        # OpenBB enrichment — news sentiment
        news_sentiment=sentiment.aggregate_sentiment if sentiment else None,
        news_sentiment_label=(sentiment.sentiment_label if sentiment else None),
        recent_headlines=(
            [h.title for h in sentiment.headlines[:5]]
            if sentiment and sentiment.headlines
            else None
        ),
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


def _build_fallback_result(
    context: MarketContext,
    ticker_score: TickerScore,
    contracts: list[OptionContract],
    config: DebateConfig,
    start_time: float,
) -> DebateResult:
    """Build a data-driven fallback result when AI debate fails.

    Synthesizes ``AgentResponse`` for bull and bear from quantitative data,
    and a ``TradeThesis`` from the composite score and direction.
    """
    elapsed_ms = int((time.monotonic() - start_time) * 1000)

    # Gather top non-None indicator signals for key_points
    key_points = _extract_top_signals(ticker_score)

    # Contract descriptions for contracts_referenced
    contract_refs = _format_contract_refs(contracts)

    # --- Bull fallback ---
    cap = config.fallback_confidence
    bull_confidence = min(ticker_score.composite_score / 100.0 * cap, cap)
    bull_response = AgentResponse(
        agent_name="bull",
        direction=SignalDirection.BULLISH,
        confidence=bull_confidence,
        argument=(
            f"Data-driven analysis for {context.ticker}. "
            f"Composite score: {ticker_score.composite_score:.1f}/100. "
            f"Signal direction: {ticker_score.direction.value}. "
            f"RSI: {context.rsi_14:.1f}."
        ),
        key_points=key_points[:3] if key_points else ["Composite score available"],
        risks_cited=["AI analysis unavailable -- limited qualitative assessment"],
        contracts_referenced=contract_refs[:3],
        model_used="data-driven-fallback",
    )

    # --- Bear fallback ---
    bear_confidence = min((100.0 - ticker_score.composite_score) / 100.0 * cap, cap)
    bear_response = AgentResponse(
        agent_name="bear",
        direction=SignalDirection.BEARISH,
        confidence=bear_confidence,
        argument=(
            f"Data-driven bearish assessment for {context.ticker}. "
            f"Composite score: {ticker_score.composite_score:.1f}/100. "
            f"Inverse signal strength: {100.0 - ticker_score.composite_score:.1f}/100."
        ),
        key_points=key_points[:3] if key_points else ["Inverse composite score available"],
        risks_cited=["AI analysis unavailable -- limited qualitative assessment"],
        contracts_referenced=contract_refs[:3],
        model_used="data-driven-fallback",
    )

    # --- Thesis fallback ---
    thesis = TradeThesis(
        ticker=context.ticker,
        direction=ticker_score.direction,
        confidence=config.fallback_confidence,
        summary=(
            f"Data-driven analysis (AI unavailable). Based on composite score "
            f"{ticker_score.composite_score:.1f}/100, {ticker_score.direction.value} signal."
        ),
        bull_score=ticker_score.composite_score / 10.0,
        bear_score=(100.0 - ticker_score.composite_score) / 10.0,
        key_factors=key_points[:5] if key_points else ["Composite score only"],
        risk_assessment=(
            "Limited analysis -- AI debate unavailable. Exercise additional caution."
        ),
        recommended_strategy=None,
    )

    logger.info(
        "Data-driven fallback for %s: direction=%s, confidence=%.2f, duration=%dms",
        context.ticker,
        thesis.direction.value,
        thesis.confidence,
        elapsed_ms,
    )

    return DebateResult(
        context=context,
        bull_response=bull_response,
        bear_response=bear_response,
        thesis=thesis,
        total_usage=RunUsage(),
        duration_ms=elapsed_ms,
        is_fallback=True,
        bull_rebuttal=None,
        vol_response=None,
    )


def _build_screening_fallback(
    context: MarketContext,
    ticker_score: TickerScore,
    contracts: list[OptionContract],
    config: DebateConfig,
    start_time: float,
) -> DebateResult:
    """Build fallback for tickers that fail pre-debate screening.

    Wraps ``_build_fallback_result()`` with a screening-specific thesis summary
    indicating the debate was skipped due to weak signal.
    """
    result = _build_fallback_result(context, ticker_score, contracts, config, start_time)
    screening_summary = (
        f"Signal too weak for meaningful debate "
        f"(composite: {ticker_score.composite_score:.1f}/100, "
        f"direction: {ticker_score.direction.value})."
    )
    # Override thesis with screening-specific summary and no strategy recommendation
    screening_thesis = TradeThesis(
        ticker=result.thesis.ticker,
        direction=result.thesis.direction,
        confidence=result.thesis.confidence,
        summary=screening_summary,
        bull_score=result.thesis.bull_score,
        bear_score=result.thesis.bear_score,
        key_factors=result.thesis.key_factors,
        risk_assessment=result.thesis.risk_assessment,
        recommended_strategy=None,
    )
    return DebateResult(
        context=result.context,
        bull_response=result.bull_response,
        bear_response=result.bear_response,
        thesis=screening_thesis,
        total_usage=result.total_usage,
        duration_ms=result.duration_ms,
        is_fallback=True,
        bull_rebuttal=None,
        vol_response=None,
    )


def _extract_top_signals(ticker_score: TickerScore) -> list[str]:
    """Extract the top non-None indicator signals as human-readable strings."""
    signals = ticker_score.signals
    items: list[str] = []

    # Map field names to readable labels
    signal_labels: list[tuple[str, str]] = [
        ("rsi", "RSI"),
        ("adx", "ADX"),
        ("sma_alignment", "SMA Alignment"),
        ("bb_width", "Bollinger Band Width"),
        ("atr_pct", "ATR %"),
        ("obv", "OBV"),
        ("relative_volume", "Relative Volume"),
        ("stochastic_rsi", "Stochastic RSI"),
        ("supertrend", "SuperTrend"),
        ("roc", "Rate of Change"),
        ("keltner_width", "Keltner Width"),
        ("vwap_deviation", "VWAP Deviation"),
        ("iv_rank", "IV Rank"),
        ("iv_percentile", "IV Percentile"),
        ("put_call_ratio", "Put/Call Ratio"),
        ("williams_r", "Williams %R"),
        ("ad", "Accumulation/Distribution"),
        ("max_pain_distance", "Max Pain Distance"),
    ]

    for field_name, label in signal_labels:
        value = getattr(signals, field_name, None)
        if value is not None and math.isfinite(value):
            items.append(f"{label}: {value:.1f}")
        if len(items) >= 5:
            break

    return items


def _format_contract_refs(contracts: list[OptionContract]) -> list[str]:
    """Format option contracts as human-readable reference strings."""
    refs: list[str] = []
    for contract in contracts[:3]:
        strike_str = f"${contract.strike}"
        type_str = contract.option_type.value.upper()
        expiry_str = contract.expiration.isoformat()
        refs.append(f"{contract.ticker} {strike_str} {type_str} {expiry_str}")
    return refs


def _opposite_direction(direction: SignalDirection) -> SignalDirection:
    """Return the opposite direction, or NEUTRAL if NEUTRAL."""
    if direction == SignalDirection.BULLISH:
        return SignalDirection.BEARISH
    if direction == SignalDirection.BEARISH:
        return SignalDirection.BULLISH
    return SignalDirection.NEUTRAL


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


async def _persist_result(
    result: DebateResult,
    ticker_score: TickerScore,
    config: DebateConfig,
    repository: Repository,
) -> None:
    """Persist debate result to the database. Never raises -- logs on failure."""
    try:
        total_tokens = result.total_usage.input_tokens + result.total_usage.output_tokens
        model_name = (
            config.anthropic_model if config.provider == LLMProvider.ANTHROPIC else config.model
        )

        # Compute debate_mode for A/B logging
        if result.is_fallback:
            debate_mode = "fallback"
        elif config.enable_rebuttal and config.enable_volatility_agent:
            debate_mode = "full"
        elif config.enable_rebuttal:
            debate_mode = "rebuttal-only"
        elif config.enable_volatility_agent:
            debate_mode = "vol-only"
        else:
            debate_mode = "base"

        debate_id = await repository.save_debate(
            scan_run_id=ticker_score.scan_run_id,
            ticker=result.context.ticker,
            bull_json=result.bull_response.model_dump_json(),
            bear_json=result.bear_response.model_dump_json(),
            risk_json=None,  # Risk output is TradeThesis, stored in verdict_json
            verdict_json=result.thesis.model_dump_json(),
            total_tokens=total_tokens,
            model_name=model_name,
            duration_ms=result.duration_ms,
            is_fallback=result.is_fallback,
            vol_json=(
                result.vol_response.model_dump_json() if result.vol_response is not None else None
            ),
            rebuttal_json=(
                result.bull_rebuttal.model_dump_json()
                if result.bull_rebuttal is not None
                else None
            ),
            debate_mode=debate_mode,
            citation_density=result.citation_density,
            market_context_json=result.context.model_dump_json(),
            flow_thesis=result.flow_response,
            fundamental_thesis=result.fundamental_response,
            risk_assessment=result.risk_response,
            contrarian_thesis=result.contrarian_response,
        )

        # Look up the recommended contract for this debate's scan+ticker pair.
        # This links agent predictions to contract outcomes for accuracy tracking.
        contract_id = await repository.get_recommended_contract_id(
            ticker_score.scan_run_id,
            result.context.ticker,
        )

        # Persist per-agent predictions for accuracy tracking (FR-8)
        predictions = extract_agent_predictions(debate_id, result, contract_id)
        if predictions:
            await repository.save_agent_predictions(predictions)

        logger.debug(
            "Persisted debate for %s (tokens=%d, fallback=%s, mode=%s, predictions=%d)",
            result.context.ticker,
            total_tokens,
            result.is_fallback,
            debate_mode,
            len(predictions),
        )
    except Exception:
        logger.warning(
            "Failed to persist debate result for %s",
            result.context.ticker,
            exc_info=True,
        )


# ---------------------------------------------------------------------------
# 6-Agent Debate Protocol
# ---------------------------------------------------------------------------

# Mapping from agent name to its directional vote weight.
type VoteWeights = dict[str, float]

# Agent vote weights for verdict synthesis.
# Directional weights sum to 0.85 — unnormalized weights are correct for
# Bordley 1982 log-odds pooling.
AGENT_VOTE_WEIGHTS: VoteWeights = {
    "trend": 0.25,
    "volatility": 0.20,
    "flow": 0.20,
    "fundamental": 0.15,
    "contrarian": 0.05,
    "risk": 0.0,  # Risk agent is advisory-only — informs but doesn't vote on direction
}


def compute_auto_tune_weights(
    accuracy: list[AgentAccuracyReport],
) -> VoteWeights:
    """Compute auto-tuned vote weights from agent accuracy data.

    Uses inverse Brier score, clamped to [0.05, 0.35], normalized to sum=0.85.
    Agents with <10 samples keep manual weights. Risk is always 0.0.
    """
    weights = dict(AGENT_VOTE_WEIGHTS)
    agents_with_data = {r.agent_name: r for r in accuracy if r.sample_size >= 10}

    for name in weights:
        if name == "risk":
            weights[name] = 0.0
            continue
        if name in agents_with_data:
            raw = 1.0 - agents_with_data[name].brier_score
            if not math.isfinite(raw):
                continue
            weights[name] = raw

    for name in weights:
        if name == "risk":
            continue
        weights[name] = max(0.05, min(0.35, weights[name]))

    directional = {k: v for k, v in weights.items() if k != "risk"}
    total = sum(directional.values())
    if total > 0:
        for name in directional:
            weights[name] = (directional[name] / total) * 0.85

    return weights


async def auto_tune_weights(
    repo: Repository,
    window_days: int = 90,
    dry_run: bool = False,
) -> list[AgentWeightsComparison]:
    """Orchestrate end-to-end auto-tune: accuracy -> weights -> compare -> persist.

    Connects existing primitives into a working flow:
    1. Fetch per-agent accuracy from the repository.
    2. Compute auto-tuned weights via ``compute_auto_tune_weights()``.
    3. Build ``AgentWeightsComparison`` for each agent (manual vs auto).
    4. Optionally persist the results (skipped when *dry_run* is ``True``).

    Args:
        repo: Repository instance for DB access.
        window_days: Calendar-day lookback window passed to accuracy query.
        dry_run: When ``True``, skip persistence and return comparisons only.

    Returns:
        List of ``AgentWeightsComparison`` — one per agent with tuned weights.
        Empty list when no accuracy data meets the minimum sample threshold.
    """
    accuracy = await repo.get_agent_accuracy(window_days=window_days)

    # Skip persistence when no agent has enough scored outcomes
    has_eligible = any(
        r.agent_name != "risk" and r.sample_size >= 10 and math.isfinite(r.brier_score)
        for r in accuracy
    )
    if not has_eligible:
        logger.info(
            "Auto-tune skipped: no directional agent has enough scored outcomes (window=%d)",
            window_days,
        )
        return []

    tuned = compute_auto_tune_weights(accuracy)

    comparisons = [
        AgentWeightsComparison(
            agent_name=name,
            manual_weight=AGENT_VOTE_WEIGHTS.get(name, 0.0),
            auto_weight=tuned.get(name, 0.0),
            brier_score=next((a.brier_score for a in accuracy if a.agent_name == name), None),
            sample_size=next((a.sample_size for a in accuracy if a.agent_name == name), 0),
        )
        for name in tuned
    ]

    if not dry_run:
        await repo.save_auto_tune_weights(comparisons, window_days=window_days)

    logger.info(
        "Auto-tune weights computed for %d agents (window=%d, dry_run=%s)",
        len(comparisons),
        window_days,
        dry_run,
    )
    return comparisons


def compute_agreement_score(agent_directions: dict[str, SignalDirection]) -> float:
    """Compute fraction of directional agents agreeing with the majority.

    NEUTRAL agents are excluded from the denominator so they don't dilute
    agreement among agents that actually took a directional stance.

    Returns a float in [0.0, 1.0]. With 0 agents or all NEUTRAL, returns 0.0.

    Parameters
    ----------
    agent_directions
        Mapping of agent name to their direction call.

    Returns
    -------
    float
        Fraction of directional agents agreeing with the majority direction.
    """
    if not agent_directions:
        return 0.0

    bullish_count = sum(1 for d in agent_directions.values() if d == SignalDirection.BULLISH)
    bearish_count = sum(1 for d in agent_directions.values() if d == SignalDirection.BEARISH)

    directional_count = bullish_count + bearish_count
    if directional_count == 0:
        return 0.0  # All NEUTRAL — no directional consensus

    majority = max(bullish_count, bearish_count)
    return majority / directional_count


def _get_majority_direction(agent_directions: dict[str, SignalDirection]) -> SignalDirection:
    """Determine the majority direction from agent directions.

    Returns the direction with the most votes. Ties return NEUTRAL.
    """
    if not agent_directions:
        return SignalDirection.NEUTRAL

    bullish_count = sum(1 for d in agent_directions.values() if d == SignalDirection.BULLISH)
    bearish_count = sum(1 for d in agent_directions.values() if d == SignalDirection.BEARISH)

    if bullish_count > bearish_count:
        return SignalDirection.BULLISH
    if bearish_count > bullish_count:
        return SignalDirection.BEARISH
    return SignalDirection.NEUTRAL


def _vote_entropy(agent_directions: dict[str, SignalDirection]) -> float:
    """Shannon entropy of directional vote distribution.

    Measures ensemble diversity: 0.0 = unanimous, 1.0 = perfect two-way split.
    NEUTRAL agents are excluded (consistent with :func:`compute_agreement_score`).

    Parameters
    ----------
    agent_directions
        Mapping of agent name to their direction call.

    Returns
    -------
    float
        Shannon entropy in bits. 0.0 when empty, all NEUTRAL, or unanimous.
    """
    if not agent_directions:
        return 0.0
    # Exclude NEUTRAL agents — consistent with compute_agreement_score
    directional = {k: v for k, v in agent_directions.items() if v != SignalDirection.NEUTRAL}
    if not directional:
        return 0.0
    counts: dict[SignalDirection, int] = {}
    for d in directional.values():
        counts[d] = counts.get(d, 0) + 1
    total = len(directional)
    entropy = 0.0
    for count in counts.values():
        p = count / total
        if p > 0:
            entropy -= p * math.log2(p)
    return entropy


def _log_odds_pool(probabilities: list[float], weights: list[float]) -> float:
    """Pool probabilities using weighted log-odds (Bordley 1982).

    Properly compounds independent agreement: three agents at 0.9 produce
    a combined probability of ~0.997, unlike linear averaging which yields 0.9.

    Weights are NOT normalized — each agent's weight scales how much its
    opinion shifts the pooled result. This is what enables compounding:
    multiple agreeing agents produce higher confidence than any single agent.

    Clamps inputs to [0.01, 0.99] to prevent ``log(0)`` / ``log(inf)``.

    Parameters
    ----------
    probabilities
        List of agent confidence values (each in [0.0, 1.0]).
    weights
        Corresponding importance weights. NOT normalized — each weight
        scales the agent's contribution to the pooled log-odds sum.

    Returns
    -------
    float
        Pooled probability in (0.0, 1.0). Returns 0.5 if inputs are empty
        or total weight is zero (neutral prior).
    """
    if not probabilities:
        return 0.5  # no data -> neutral

    # Clamp to avoid log(0) / log(inf)
    clamped = [max(0.01, min(0.99, p)) for p in probabilities]

    total_weight = sum(weights)
    if total_weight == 0:
        return 0.5

    # Weighted sum in log-odds space (NOT divided by total_weight —
    # this compounds independent opinions rather than averaging them)
    log_odds_sum = sum(w * math.log(p / (1 - p)) for p, w in zip(clamped, weights, strict=True))

    # Convert back to probability
    return 1.0 / (1.0 + math.exp(-log_odds_sum))


def _vol_strategy_str(vol: VolatilityThesis) -> str:
    """Return the volatility strategy as a string, or 'none'."""
    return vol.recommended_strategy.value if vol.recommended_strategy else "none"


def _format_prior_outputs(
    trend_output: AgentResponse | None,
    vol_output: VolatilityThesis | None,
    flow_output: FlowThesis | None,
    fund_output: FundamentalThesis | None,
    risk_output: RiskAssessment | None,
) -> str:
    """Format all prior agent outputs as text for the Contrarian agent prompt."""
    sections: list[str] = []
    if trend_output is not None:
        sections.append(
            f"TREND AGENT:\n"
            f"  Direction: {trend_output.direction.value}\n"
            f"  Confidence: {trend_output.confidence}\n"
            f"  Argument: {trend_output.argument}"
        )
    if vol_output is not None:
        sections.append(
            f"VOLATILITY AGENT:\n"
            f"  IV Assessment: {vol_output.iv_assessment}\n"
            f"  Confidence: {vol_output.confidence}\n"
            f"  Strategy: {_vol_strategy_str(vol_output)}"
        )
    if flow_output is not None:
        sections.append(
            f"FLOW AGENT:\n"
            f"  Direction: {flow_output.direction.value}\n"
            f"  Confidence: {flow_output.confidence}\n"
            f"  GEX: {flow_output.gex_interpretation}"
        )
    if fund_output is not None:
        sections.append(
            f"FUNDAMENTAL AGENT:\n"
            f"  Direction: {fund_output.direction.value}\n"
            f"  Confidence: {fund_output.confidence}\n"
            f"  Catalyst: {fund_output.catalyst_impact.value}"
        )
    if risk_output is not None:
        sections.append(
            f"RISK AGENT:\n"
            f"  Risk Level: {risk_output.risk_level.value}\n"
            f"  Confidence: {risk_output.confidence}\n"
            f"  Max Loss: {risk_output.max_loss_estimate}"
        )
    return "\n\n".join(sections) if sections else "No prior agent outputs available."


def synthesize_verdict(
    agent_outputs: dict[str, AgentResponse | FlowThesis | FundamentalThesis | VolatilityThesis],
    risk_assessment: RiskAssessment | None,
    contrarian: ContrarianThesis | None,
    dimensional_scores: DimensionalScores | None,
    ticker: str,
    config: DebateConfig,
    vote_weights: VoteWeights | None = None,
) -> ExtendedTradeThesis:
    """Algorithmic verdict synthesis from all agent outputs.

    Pure function -- no LLM calls. Computes weighted direction, agreement score,
    and synthesizes a final verdict.

    Parameters
    ----------
    agent_outputs
        Mapping of agent name to their structured output.
    risk_assessment
        Expanded risk assessment from Phase 2, or None.
    contrarian
        Contrarian thesis from Phase 3, or None.
    dimensional_scores
        Dimensional scores from the scan pipeline, or None.
    ticker
        Ticker symbol for the verdict.
    config
        Debate configuration.
    vote_weights
        Optional custom vote weights. When None, uses AGENT_VOTE_WEIGHTS.

    Returns
    -------
    ExtendedTradeThesis
        Synthesized verdict with agreement scoring and contrarian context.
    """
    active_weights = vote_weights if vote_weights is not None else AGENT_VOTE_WEIGHTS

    # --- Collect agent directions ---
    agent_directions: dict[str, SignalDirection] = {}
    for name, output in agent_outputs.items():
        if hasattr(output, "direction"):
            agent_directions[name] = output.direction

    # --- Compute agreement score and vote entropy ---
    agreement = compute_agreement_score(agent_directions)
    majority_direction = _get_majority_direction(agent_directions)
    entropy = _vote_entropy(agent_directions)

    # --- Log-odds confidence pooling (Bordley 1982) ---
    probabilities: list[float] = []
    weights: list[float] = []
    for name, output in agent_outputs.items():
        weight = active_weights.get(name, 0.1)
        if hasattr(output, "confidence"):
            probabilities.append(output.confidence)
            weights.append(weight)
    if probabilities:
        weighted_confidence = _log_odds_pool(probabilities, weights)
    else:
        weighted_confidence = config.fallback_confidence

    # Cap confidence when agreement is low
    if agreement < 0.4:
        weighted_confidence = min(weighted_confidence, 0.4)
        logger.info(
            "Capping confidence for %s: agreement=%.2f < 0.4 -> confidence capped at 0.4",
            ticker,
            agreement,
        )

    # Ensure confidence is within bounds
    weighted_confidence = max(0.0, min(1.0, weighted_confidence))

    # --- Collect key factors ---
    key_factors: list[str] = []
    for _name, output in agent_outputs.items():
        if isinstance(output, AgentResponse) and output.key_points:
            key_factors.extend(output.key_points[:2])
        elif isinstance(output, FlowThesis) and output.key_flow_factors:
            key_factors.extend(output.key_flow_factors[:2])
        elif isinstance(output, FundamentalThesis) and output.key_fundamental_factors:
            key_factors.extend(output.key_fundamental_factors[:2])
        elif isinstance(output, VolatilityThesis) and output.key_vol_factors:
            key_factors.extend(output.key_vol_factors[:2])
    if not key_factors:
        key_factors = [f"Composite analysis for {ticker}"]

    # --- Dissenting agents ---
    dissenting: list[str] = [
        name
        for name, direction in agent_directions.items()
        if direction != majority_direction and direction != SignalDirection.NEUTRAL
    ]

    # --- Risk assessment text ---
    risk_text = "No expanded risk assessment available."
    if risk_assessment is not None:
        risk_text = (
            f"Risk level: {risk_assessment.risk_level.value}. "
            f"Max loss: {risk_assessment.max_loss_estimate}. "
            f"Key risks: {', '.join(risk_assessment.key_risks[:3])}."
        )

    # --- Summary ---
    agents_completed = len(agent_outputs)
    if risk_assessment is not None:
        agents_completed += 1
    if contrarian is not None:
        agents_completed += 1

    summary = (
        f"6-agent protocol: {agents_completed} agents completed. "
        f"Majority direction: {majority_direction.value} "
        f"(agreement: {agreement:.0%}). "
        f"Weighted confidence: {weighted_confidence:.2f}."
    )

    # --- Bull/bear scores (derived from direction votes) ---
    bullish_count = sum(1 for d in agent_directions.values() if d == SignalDirection.BULLISH)
    bearish_count = sum(1 for d in agent_directions.values() if d == SignalDirection.BEARISH)
    total_dir_agents = max(bullish_count + bearish_count, 1)
    bull_score = (bullish_count / total_dir_agents) * 10.0
    bear_score = (bearish_count / total_dir_agents) * 10.0

    # --- Contrarian dissent text ---
    contrarian_text: str | None = None
    if contrarian is not None:
        contrarian_text = (
            f"Contrarian ({contrarian.dissent_direction.value}, "
            f"confidence={contrarian.dissent_confidence:.2f}): "
            f"{contrarian.primary_challenge}"
        )

    return ExtendedTradeThesis(
        ticker=ticker,
        direction=majority_direction,
        confidence=weighted_confidence,
        summary=summary,
        bull_score=bull_score,
        bear_score=bear_score,
        key_factors=key_factors[:10],
        risk_assessment=risk_text,
        recommended_strategy=None,
        contrarian_dissent=contrarian_text,
        agent_agreement_score=agreement,
        ensemble_entropy=entropy,
        dissenting_agents=dissenting,
        dimensional_scores=dimensional_scores,
        agents_completed=agents_completed,
    )


async def run_debate(
    ticker_score: TickerScore,
    contracts: list[OptionContract],
    quote: Quote,
    ticker_info: TickerInfo,
    config: DebateConfig,
    repository: Repository | None = None,
    progress: DebateProgressCallback | None = None,
    dimensional_scores: DimensionalScores | None = None,
    flow_output: FlowThesis | None = None,
    fundamental_output: FundamentalThesis | None = None,
    fundamentals: FundamentalSnapshot | None = None,
    flow: UnusualFlowSnapshot | None = None,
    sentiment: NewsSentimentSnapshot | None = None,
    intelligence: IntelligencePackage | None = None,
    fd_package: FinancialDatasetsPackage | None = None,
    spread_analysis: SpreadAnalysis | None = None,
    options_filters: OptionsFilters | None = None,
) -> DebateResult:
    """Run 6-agent debate protocol. Falls back to data-driven on failure — never raises.

    Protocol flow:
      Phase 1 (parallel): trend, volatility, [flow, fundamental if enrichment exists]
      Phase 2 (sequential): risk agent with all Phase 1 outputs
      Phase 3 (sequential): contrarian with all prior outputs (skip if >= 3 failures)
      Phase 4 (algorithmic): synthesize_verdict -> ExtendedTradeThesis

    Flow and Fundamental agents run locally in Phase 1 when enrichment data
    exists (enrichment_ratio > 0) and the caller hasn't provided them externally.
    If neither condition is met, they count as Phase 1 failures.

    Parameters
    ----------
    ticker_score
        Scored ticker from the scan pipeline.
    contracts
        Recommended option contracts for this ticker.
    quote
        Real-time price snapshot.
    ticker_info
        Fundamental data (sector, dividend yield, 52-week range).
    config
        Debate configuration (model, timeouts).
    repository
        Optional persistence layer.
    progress
        Optional callback for real-time progress reporting.
    dimensional_scores
        Optional dimensional scores from the scan pipeline.
    flow_output
        Optional pre-computed FlowThesis from a flow agent.
    fundamental_output
        Optional pre-computed FundamentalThesis from a fundamental agent.
    spread_analysis
        Optional algorithmic spread recommendation from the spread engine.
    options_filters
        Optional option chain filters for constraint pre-check. When provided,
        contracts are validated against hard/soft constraint rules and warnings
        are injected into agent context.

    Returns
    -------
    DebateResult
        Complete debate output. ``is_fallback=True`` if all agents failed.
    """
    start_time = time.monotonic()
    context = build_market_context(
        ticker_score,
        quote,
        ticker_info,
        contracts,
        next_earnings=ticker_score.next_earnings,
        fundamentals=fundamentals,
        flow=flow,
        sentiment=sentiment,
        intelligence=intelligence,
        fd_package=fd_package,
    )

    # Populate flat spread fields on MarketContext from SpreadAnalysis
    if spread_analysis is not None:
        context.spread_type = spread_analysis.spread.spread_type
        context.spread_net_premium = spread_analysis.net_premium
        context.spread_max_profit = spread_analysis.max_profit
        context.spread_max_loss = spread_analysis.max_loss
        context.spread_pop = spread_analysis.pop_estimate
        context.spread_risk_reward = spread_analysis.risk_reward_ratio

    # --- Position Sizing (FR-C5): vol-regime-aware allocation guidance ---
    iv_for_sizing = context.atm_iv_30d or context.hv_yang_zhang
    if iv_for_sizing is not None:
        sizing_result = compute_position_size(iv_for_sizing)
        context.position_size_pct = sizing_result.final_allocation_pct
        context.position_size_rationale = sizing_result.rationale

    # --- Multi-Methodology Valuation (FR-C6) ---
    if context.fd_net_income is not None or context.fd_free_cash_flow is not None:
        try:
            fd_data = FDData(
                net_income=context.fd_net_income,
                depreciation_amortization=context.fd_depreciation_amortization,
                capex=context.fd_capex,
                free_cash_flow=context.fd_free_cash_flow,
                revenue_growth=context.fd_revenue_growth,
                earnings_growth=context.fd_earnings_growth,
                ev_to_ebitda=context.fd_ev_to_ebitda,
                book_value_per_share=context.fd_book_value_per_share,
                roe=context.fd_roe,
                shares_outstanding=context.fd_shares_outstanding,
            )
            valuation = compute_composite_valuation(
                ticker=context.ticker,
                current_price=float(context.current_price),
                fd=fd_data,
            )
            context.valuation_signal = valuation.valuation_signal
            context.valuation_margin_of_safety = valuation.composite_margin_of_safety
            context.valuation_fair_value = valuation.composite_fair_value
            logger.info(
                "Valuation for %s: signal=%s, MoS=%.1f%%, fair_value=$%.2f",
                context.ticker,
                valuation.valuation_signal or "N/A",
                (valuation.composite_margin_of_safety or 0.0) * 100,
                valuation.composite_fair_value or 0.0,
            )
        except Exception:
            logger.warning("Valuation computation failed for %s", context.ticker, exc_info=True)

    # --- Constraint pre-check (FR-C4) ---
    constraint_warnings_text: str | None = None
    if options_filters is not None and contracts:
        constraint_violations = check_contract_constraints(contracts, options_filters)
        if constraint_violations:
            constraint_warnings_text = render_constraint_warnings(constraint_violations)
            hard_count = sum(1 for v in constraint_violations if v.severity.value == "hard")
            soft_count = len(constraint_violations) - hard_count
            logger.info(
                "Constraint pre-check for %s: %d hard, %d soft violations",
                context.ticker,
                hard_count,
                soft_count,
            )

    completeness = context.completeness_ratio()
    _log_completeness_breakdown(context, completeness)

    if not should_debate(ticker_score, config):
        logger.info("Skipping debate for %s: signal too weak", ticker_score.ticker)
        return _build_screening_fallback(context, ticker_score, contracts, config, start_time)

    if completeness < 0.4:
        logger.warning(
            "MarketContext completeness %.0f%% < 40%% for %s — data-driven fallback",
            completeness * 100,
            context.ticker,
        )
        return _build_fallback_result(context, ticker_score, contracts, config, start_time)

    if completeness < 0.6:
        logger.warning(
            "MarketContext completeness %.0f%% < 60%% for %s — proceeding with caution",
            completeness * 100,
            context.ticker,
        )

    # Load auto-tuned weights if enabled and repository available
    vote_weights: VoteWeights | None = None
    if config.auto_tune_weights and repository is not None:
        try:
            weight_records = await repository.get_latest_auto_tune_weights()
            if weight_records:
                vote_weights = {r.agent_name: r.auto_weight for r in weight_records}
                logger.info("Using auto-tuned vote weights for %s", context.ticker)
        except Exception:
            logger.warning("Failed to load auto-tuned weights, using manual")

    try:
        result = await asyncio.wait_for(
            _run_debate_pipeline(
                context,
                ticker_score,
                contracts,
                config,
                start_time,
                progress,
                dimensional_scores,
                flow_output,
                fundamental_output,
                vote_weights=vote_weights,
                spread_analysis=spread_analysis,
                constraint_warnings=constraint_warnings_text,
            ),
            timeout=config.max_total_duration,
        )
    except Exception as e:
        logger.warning(
            "Debate failed for %s (%s: %s), using data-driven fallback",
            context.ticker,
            type(e).__name__,
            e,
        )
        result = _build_fallback_result(context, ticker_score, contracts, config, start_time)

    if repository is not None:
        await _persist_result(result, ticker_score, config, repository)

    return result


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


# Anthropic models are slower than Groq; extended thinking adds more latency.
_ANTHROPIC_TIMEOUT_MULTIPLIER = 2.0
_ANTHROPIC_THINKING_TIMEOUT_MULTIPLIER = 3.0

# Provider-aware rate limiting defaults.
# Groq defaults (from DebateConfig) are too aggressive for Anthropic Tier 1 limits
# (50 RPM, 30K input/min, 8K output/min).  Helpers below substitute safe values only
# when the user hasn't explicitly overridden via env vars.
_GROQ_DEFAULT_PHASE1_PARALLELISM = 2
_GROQ_DEFAULT_PHASE1_BATCH_DELAY = 1.0
_GROQ_DEFAULT_BATCH_TICKER_DELAY = 5.0
_ANTHROPIC_SAFE_PHASE1_PARALLELISM = 1
_ANTHROPIC_SAFE_PHASE1_BATCH_DELAY = 3.0
_ANTHROPIC_SAFE_BATCH_TICKER_DELAY = 30.0


def _effective_phase1_settings(config: DebateConfig) -> tuple[int, float]:
    """Return ``(parallelism, batch_delay)`` auto-adjusted for Anthropic provider.

    When the provider is Anthropic and the user has NOT overridden the Groq-tuned
    defaults (via ``ARENA_DEBATE__PHASE1_PARALLELISM`` etc.), substitute Anthropic-safe
    values that respect the 8K output-tokens/min rate limit.
    """
    parallelism = config.phase1_parallelism
    batch_delay = config.phase1_batch_delay

    if config.provider != LLMProvider.ANTHROPIC:
        return parallelism, batch_delay

    adjusted = False
    if parallelism == _GROQ_DEFAULT_PHASE1_PARALLELISM:
        parallelism = _ANTHROPIC_SAFE_PHASE1_PARALLELISM
        adjusted = True
    if batch_delay == _GROQ_DEFAULT_PHASE1_BATCH_DELAY:
        batch_delay = _ANTHROPIC_SAFE_PHASE1_BATCH_DELAY
        adjusted = True

    if adjusted:
        logger.info(
            "Anthropic provider: phase1_parallelism=%d, phase1_batch_delay=%.1fs "
            "(auto-adjusted for rate limits)",
            parallelism,
            batch_delay,
        )
    return parallelism, batch_delay


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


def _effective_agent_timeout(config: DebateConfig) -> float:
    """Return per-agent timeout, auto-adjusted for Anthropic provider.

    Groq cloud inference is fast (default 60s is fine). Anthropic models are
    slower, and extended thinking adds further latency. Multipliers ensure
    the configured ``agent_timeout`` is scaled appropriately.
    """
    if config.provider != LLMProvider.ANTHROPIC:
        return config.agent_timeout
    if config.enable_extended_thinking:
        return config.agent_timeout * _ANTHROPIC_THINKING_TIMEOUT_MULTIPLIER
    return config.agent_timeout * _ANTHROPIC_TIMEOUT_MULTIPLIER


async def _run_debate_pipeline(
    context: MarketContext,
    ticker_score: TickerScore,
    contracts: list[OptionContract],
    config: DebateConfig,
    start_time: float,
    _progress: DebateProgressCallback | None,
    dimensional_scores: DimensionalScores | None,
    flow_output: FlowThesis | None,
    fundamental_output: FundamentalThesis | None,
    vote_weights: VoteWeights | None = None,
    spread_analysis: SpreadAnalysis | None = None,
    constraint_warnings: str | None = None,
) -> DebateResult:
    """Run the 6-agent pipeline. Raises on total failure."""
    model = build_debate_model(config)
    settings = _build_model_settings(config)
    per_agent_timeout = _effective_agent_timeout(config)

    # Partitioned context: each Phase 1 agent sees only domain-specific fields.
    # Risk (Phase 2) and Contrarian (Phase 3) keep the full context block.
    trend_context = render_trend_context(context)
    vol_context = render_volatility_context(context)
    flow_context = render_flow_context(context)
    fund_context = render_fundamental_context(context)
    full_context = render_context_block(context, constraint_warnings=constraint_warnings)

    # ---------------------------------------------------------------
    # Phase 1: parallel — trend + volatility always; flow + fundamental
    # when enrichment data exists and not provided externally
    # ---------------------------------------------------------------
    base_deps = DebateDeps(
        context=context,
        ticker_score=ticker_score,
        contracts=contracts,
        constraint_warnings=constraint_warnings,
    )

    # Build coroutines for local Phase 1 agents
    trend_coro = asyncio.wait_for(
        trend_agent.run(
            f"Analyze trend and momentum for {context.ticker}.\n\n{trend_context}",
            model=model,
            deps=base_deps,
            model_settings=settings,
        ),
        timeout=per_agent_timeout,
    )

    vol_deps = DebateDeps(
        context=context,
        ticker_score=ticker_score,
        contracts=contracts,
        constraint_warnings=constraint_warnings,
    )
    vol_coro = asyncio.wait_for(
        volatility_agent.run(
            f"Assess implied volatility for {context.ticker}.\n\n{vol_context}",
            model=model,
            deps=vol_deps,
            model_settings=settings,
        ),
        timeout=per_agent_timeout,
    )

    # Build optional Phase 1 agent coroutines for flow/fundamental.
    # Always run when not provided externally — agents handle missing enrichment.
    has_enrichment = context.enrichment_ratio() > 0.0
    if not has_enrichment:
        logger.info(
            "Running flow/fundamental agents without enrichment data for %s",
            context.ticker,
        )

    phase1_coros: list[Awaitable[object]] = [trend_coro, vol_coro]
    phase1_labels = ["trend", "volatility"]

    flow_coro = None
    if flow_output is None:
        flow_deps = DebateDeps(
            context=context,
            ticker_score=ticker_score,
            contracts=contracts,
            constraint_warnings=constraint_warnings,
        )
        flow_coro = asyncio.wait_for(
            flow_agent.run(
                f"Analyze options flow for {context.ticker}.\n\n{flow_context}",
                model=model,
                deps=flow_deps,
                model_settings=settings,
            ),
            timeout=per_agent_timeout,
        )
        phase1_coros.append(flow_coro)
        phase1_labels.append("flow")

    fundamental_coro = None
    if fundamental_output is None:
        fund_deps = DebateDeps(
            context=context,
            ticker_score=ticker_score,
            contracts=contracts,
            constraint_warnings=constraint_warnings,
        )
        fundamental_coro = asyncio.wait_for(
            fundamental_agent.run(
                f"Assess fundamental catalysts for {context.ticker}.\n\n{fund_context}",
                model=model,
                deps=fund_deps,
                model_settings=settings,
            ),
            timeout=per_agent_timeout,
        )
        phase1_coros.append(fundamental_coro)
        phase1_labels.append("fundamental")

    logger.info(
        "Phase 1: running %s in parallel for %s",
        " + ".join(phase1_labels),
        context.ticker,
    )

    # Respect phase1_parallelism — batch if needed (auto-adjusted for Anthropic)
    parallelism, batch_delay = _effective_phase1_settings(config)
    phase1_results: list[object | BaseException]
    if parallelism >= len(phase1_coros):
        phase1_results = list(await asyncio.gather(*phase1_coros, return_exceptions=True))
    else:
        # Run in batches with optional inter-batch delay for rate-limit avoidance
        phase1_results = []
        for i in range(0, len(phase1_coros), parallelism):
            if i > 0 and batch_delay > 0:
                logger.debug(
                    "Phase 1 inter-batch delay: %.1fs before batch %d",
                    batch_delay,
                    i // parallelism + 1,
                )
                await asyncio.sleep(batch_delay)
            batch = phase1_coros[i : i + parallelism]
            batch_results = await asyncio.gather(*batch, return_exceptions=True)
            phase1_results.extend(batch_results)

    # Extract Phase 1 outputs
    trend_output: AgentResponse | None = None
    vol_thesis: VolatilityThesis | None = None
    total_usage = RunUsage()
    phase1_failures = 0

    # --- Trend ---
    trend_raw = phase1_results[0]
    if isinstance(trend_raw, BaseException):
        logger.warning("Trend agent failed for %s: %s", context.ticker, trend_raw)
        phase1_failures += 1
    else:
        trend_run = cast(AgentRunResult[AgentResponse], trend_raw)
        trend_output = trend_run.output
        total_usage = total_usage + trend_run.usage()
        logger.info(
            "Trend agent complete for %s: direction=%s, confidence=%.2f",
            context.ticker,
            trend_output.direction.value,
            trend_output.confidence,
        )

    # --- Volatility ---
    vol_raw = phase1_results[1]
    if isinstance(vol_raw, BaseException):
        logger.warning("Volatility agent failed for %s: %s", context.ticker, vol_raw)
        phase1_failures += 1
    else:
        vol_run = cast(AgentRunResult[VolatilityThesis], vol_raw)
        vol_thesis = vol_run.output
        total_usage = total_usage + vol_run.usage()
        logger.info(
            "Volatility agent complete for %s: iv=%s, confidence=%.2f",
            context.ticker,
            vol_thesis.iv_assessment,
            vol_thesis.confidence,
        )

    # --- Flow (locally-run or externally-provided) ---
    if "flow" in phase1_labels:
        flow_idx = phase1_labels.index("flow")
        flow_raw = phase1_results[flow_idx]
        if isinstance(flow_raw, BaseException):
            logger.warning("Flow agent failed for %s: %s", context.ticker, flow_raw)
            phase1_failures += 1
        else:
            flow_run = cast(AgentRunResult[FlowThesis], flow_raw)
            flow_output = flow_run.output
            total_usage = total_usage + flow_run.usage()
            logger.info(
                "Flow agent complete for %s: direction=%s, confidence=%.2f",
                context.ticker,
                flow_output.direction.value,
                flow_output.confidence,
            )
    elif flow_output is None:
        phase1_failures += 1

    # --- Fundamental (locally-run or externally-provided) ---
    if "fundamental" in phase1_labels:
        fund_idx = phase1_labels.index("fundamental")
        fund_raw = phase1_results[fund_idx]
        if isinstance(fund_raw, BaseException):
            logger.warning("Fundamental agent failed for %s: %s", context.ticker, fund_raw)
            phase1_failures += 1
        else:
            fund_run = cast(AgentRunResult[FundamentalThesis], fund_raw)
            fundamental_output = fund_run.output
            total_usage = total_usage + fund_run.usage()
            logger.info(
                "Fundamental agent complete for %s: direction=%s, confidence=%.2f",
                context.ticker,
                fundamental_output.direction.value,
                fundamental_output.confidence,
            )
    elif fundamental_output is None:
        phase1_failures += 1

    logger.info(
        "Phase 1 complete for %s: %d failures out of 4 agents",
        context.ticker,
        phase1_failures,
    )

    # Full data-driven fallback if all 4 Phase 1 agents failed
    if phase1_failures >= 4:
        logger.warning(
            "All Phase 1 agents failed for %s — full data-driven fallback",
            context.ticker,
        )
        return _build_fallback_result(context, ticker_score, contracts, config, start_time)

    # ---------------------------------------------------------------
    # Phase 2: Risk agent (sequential, receives Phase 1 outputs)
    # ---------------------------------------------------------------
    logger.info("Phase 2: running risk agent for %s", context.ticker)
    risk_output: RiskAssessment | None = None
    try:
        risk_deps = DebateDeps(
            context=context,
            ticker_score=ticker_score,
            contracts=contracts,
            trend_response=trend_output,
            volatility_thesis=vol_thesis,
            flow_thesis=flow_output,
            fundamental_thesis=fundamental_output,
            constraint_warnings=constraint_warnings,
        )
        risk_result = await asyncio.wait_for(
            risk_agent.run(
                f"Assess risk for {context.ticker} based on all agent outputs.\n\n{full_context}",
                model=model,
                deps=risk_deps,
                model_settings=settings,
            ),
            timeout=per_agent_timeout,
        )
        risk_output = risk_result.output
        total_usage = total_usage + risk_result.usage()
        logger.info(
            "Risk agent complete for %s: level=%s, confidence=%.2f",
            context.ticker,
            risk_output.risk_level.value,
            risk_output.confidence,
        )
    except Exception as e:
        logger.warning("Risk agent failed for %s: %s", context.ticker, e)

    # ---------------------------------------------------------------
    # Phase 3: Contrarian (sequential, skip if >= 3 Phase 1 failures)
    # ---------------------------------------------------------------
    contrarian_output: ContrarianThesis | None = None
    if phase1_failures < 3:
        logger.info("Phase 3: running contrarian agent for %s", context.ticker)
        try:
            prior_text = _format_prior_outputs(
                trend_output,
                vol_thesis,
                flow_output,
                fundamental_output,
                risk_output,
            )
            contrarian_deps = DebateDeps(
                context=context,
                ticker_score=ticker_score,
                contracts=contracts,
                trend_response=trend_output,
                volatility_thesis=vol_thesis,
                flow_thesis=flow_output,
                fundamental_thesis=fundamental_output,
                risk_assessment=risk_output,
                all_prior_outputs=prior_text,
                constraint_warnings=constraint_warnings,
            )
            contrarian_result = await asyncio.wait_for(
                contrarian_agent.run(
                    f"Challenge the consensus for {context.ticker}.\n\n{full_context}",
                    model=model,
                    deps=contrarian_deps,
                    model_settings=settings,
                ),
                timeout=per_agent_timeout,
            )
            contrarian_output = contrarian_result.output
            total_usage = total_usage + contrarian_result.usage()
            logger.info(
                "Contrarian agent complete for %s: dissent=%s, confidence=%.2f",
                context.ticker,
                contrarian_output.dissent_direction.value,
                contrarian_output.dissent_confidence,
            )
        except Exception as e:
            logger.warning("Contrarian agent failed for %s: %s", context.ticker, e)
    else:
        logger.info(
            "Phase 3 skipped for %s: %d Phase 1 failures (>= 3)",
            context.ticker,
            phase1_failures,
        )

    # ---------------------------------------------------------------
    # Phase 4: Algorithmic verdict synthesis (no LLM)
    # ---------------------------------------------------------------
    logger.info("Phase 4: synthesizing verdict for %s", context.ticker)
    agent_outputs: dict[
        str, AgentResponse | FlowThesis | FundamentalThesis | VolatilityThesis
    ] = {}
    if trend_output is not None:
        agent_outputs["trend"] = trend_output
    if vol_thesis is not None:
        agent_outputs["volatility"] = vol_thesis
    if flow_output is not None:
        agent_outputs["flow"] = flow_output
    if fundamental_output is not None:
        agent_outputs["fundamental"] = fundamental_output

    thesis = synthesize_verdict(
        agent_outputs=agent_outputs,
        risk_assessment=risk_output,
        contrarian=contrarian_output,
        dimensional_scores=dimensional_scores,
        ticker=context.ticker,
        config=config,
        vote_weights=vote_weights,
    )

    # Override recommended_strategy from algorithmic spread engine (priority over LLM)
    if spread_analysis is not None:
        thesis = thesis.model_copy(
            update={"recommended_strategy": spread_analysis.spread.spread_type}
        )

    elapsed_ms = int((time.monotonic() - start_time) * 1000)

    # Citation density scoring
    agent_texts: list[str] = [thesis.summary, thesis.risk_assessment]
    if trend_output is not None:
        agent_texts.append(trend_output.argument)
    density = compute_citation_density(full_context, *agent_texts)

    logger.info(
        "Debate complete for %s in %dms (agents=%d, agreement=%.2f, citation=%.2f)",
        context.ticker,
        elapsed_ms,
        thesis.agents_completed,
        thesis.agent_agreement_score or 0.0,
        density,
    )

    # Build a bull/bear fallback response pair for backward-compatible DebateResult
    bull_compat = trend_output or _build_fallback_agent_response(
        "trend",
        SignalDirection.NEUTRAL,
        ticker_score,
        contracts,
        config,
    )
    bear_compat = _build_fallback_agent_response(
        "bear",
        SignalDirection.BEARISH,
        ticker_score,
        contracts,
        config,
    )

    return DebateResult(
        context=context,
        bull_response=bull_compat,
        bear_response=bear_compat,
        thesis=thesis,
        total_usage=total_usage,
        duration_ms=elapsed_ms,
        is_fallback=False,
        bull_rebuttal=None,
        vol_response=vol_thesis,
        citation_density=density,
        flow_response=flow_output,
        fundamental_response=fundamental_output,
        risk_response=risk_output,
        contrarian_response=contrarian_output,
    )


def _build_fallback_agent_response(
    agent_name: str,
    direction: SignalDirection,
    ticker_score: TickerScore,
    contracts: list[OptionContract],
    config: DebateConfig,
) -> AgentResponse:
    """Build a minimal AgentResponse for backward-compatible DebateResult fields."""
    key_points = _extract_top_signals(ticker_score)
    contract_refs = _format_contract_refs(contracts)
    cap = config.fallback_confidence
    confidence = min(ticker_score.composite_score / 100.0 * cap, cap)
    return AgentResponse(
        agent_name=agent_name,
        direction=direction,
        confidence=confidence,
        argument=(
            f"Data-driven {direction.value} assessment. "
            f"Composite: {ticker_score.composite_score:.1f}/100."
        ),
        key_points=key_points[:3] if key_points else ["Composite score available"],
        risks_cited=["Placeholder for protocol compat"],
        contracts_referenced=contract_refs[:3],
        model_used="protocol-compat",
    )

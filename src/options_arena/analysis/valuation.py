"""Multi-methodology equity valuation framework.

Four independent valuation models produce per-share fair value estimates:
  1. Owner Earnings DCF (Buffett/Damodaran) — 35% default weight
  2. Three-Stage DCF (Damodaran)            — 35% default weight
  3. EV/EBITDA Relative (Damodaran)         — 20% default weight
  4. Residual Income Model (Hull)           — 10% default weight

Each model returns ``None`` when required data is absent. The composite combiner
renormalizes weights across the models that produced valid estimates. When all
four return ``None``, the composite is ``None``.

Architecture rules:
- Pure computation — no API calls, no I/O, no service imports.
- Imports only from ``models/`` and stdlib ``math``/``datetime``.
- All floats checked with ``math.isfinite()`` at entry.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import UTC, datetime

from options_arena.models.enums import ValuationSignal
from options_arena.models.valuation import CompositeValuation, ValuationModelResult

logger = logging.getLogger(__name__)

# Default model weights — sum to 1.0
OWNER_EARNINGS_WEIGHT: float = 0.35
THREE_STAGE_WEIGHT: float = 0.35
EV_EBITDA_WEIGHT: float = 0.20
RESIDUAL_INCOME_WEIGHT: float = 0.10

# Valuation signal thresholds
UNDERVALUED_THRESHOLD: float = 0.15
OVERVALUED_THRESHOLD: float = -0.15

# DCF parameters
OWNER_EARNINGS_HAIRCUT: float = 0.25  # 25% margin of safety haircut
RESIDUAL_INCOME_HAIRCUT: float = 0.20  # 20% margin of safety haircut
TERMINAL_GROWTH_RATE: float = 0.025  # 2.5% long-term GDP growth
MAX_GROWTH_RATE: float = 0.30  # cap at 30% to prevent explosion
DCF_PROJECTION_YEARS: int = 10  # 5yr high growth + 5yr transition
HIGH_GROWTH_YEARS: int = 5
TRANSITION_YEARS: int = 5

# Three-stage DCF scenario weights
SCENARIO_BULL_WEIGHT: float = 0.25
SCENARIO_BASE_WEIGHT: float = 0.50
SCENARIO_BEAR_WEIGHT: float = 0.25

# Bull/bear scenario multipliers on the base growth rate
BULL_GROWTH_MULTIPLIER: float = 1.3
BEAR_GROWTH_MULTIPLIER: float = 0.7

# EV/EBITDA sector average fallback
DEFAULT_SECTOR_EV_EBITDA: float = 15.0  # median S&P 500


@dataclass
class FDData:
    """Financial Datasets data slice for valuation models.

    Plain dataclass — not a Pydantic model. Constructed by the caller from
    ``MarketContext.fd_*`` fields. All fields are ``float | None``.
    """

    net_income: float | None = None
    depreciation_amortization: float | None = None
    capex: float | None = None
    free_cash_flow: float | None = None
    revenue_growth: float | None = None
    earnings_growth: float | None = None
    ev_to_ebitda: float | None = None
    book_value_per_share: float | None = None
    roe: float | None = None
    shares_outstanding: float | None = None
    sector_ev_ebitda: float | None = None  # sector average, if known


def _is_valid(v: float | None) -> bool:
    """Check that a value is not None and is a finite number."""
    return v is not None and math.isfinite(v)


def _safe_positive(v: float | None) -> float | None:
    """Return v if valid and positive, else None."""
    if _is_valid(v) and v is not None and v > 0.0:
        return v
    return None


def _clamp_growth(rate: float) -> float:
    """Clamp a growth rate to [-MAX, +MAX] to prevent DCF explosion."""
    return max(-MAX_GROWTH_RATE, min(MAX_GROWTH_RATE, rate))


def _margin_of_safety(fair_value: float, current_price: float) -> float | None:
    """Compute margin of safety: (fair - price) / fair.

    Returns None if fair_value is zero or non-positive (undefined ratio).
    """
    if fair_value <= 0.0:
        return None
    return (fair_value - current_price) / fair_value


def _classify_signal(margin: float | None) -> ValuationSignal | None:
    """Classify a margin of safety into a ValuationSignal."""
    if margin is None:
        return None
    if margin > UNDERVALUED_THRESHOLD:
        return ValuationSignal.UNDERVALUED
    if margin < OVERVALUED_THRESHOLD:
        return ValuationSignal.OVERVALUED
    return ValuationSignal.FAIRLY_VALUED


# ---------------------------------------------------------------------------
# Model 1: Owner Earnings DCF (Buffett method, Damodaran reference)
# ---------------------------------------------------------------------------


def compute_owner_earnings_dcf(
    fd: FDData,
    risk_free_rate: float,
    current_price: float,
) -> ValuationModelResult:
    """Owner Earnings DCF: net_income + D&A - capex, discounted at WACC with 25% haircut.

    Owner earnings = net_income + depreciation_amortization - capex.
    Discount stream at WACC (approximated as risk_free_rate + equity risk premium).
    Apply 25% haircut to final value for conservatism.
    """
    notes: list[str] = []

    # Validate required inputs
    if not _is_valid(fd.net_income):
        notes.append("net_income unavailable")
    if not _is_valid(fd.depreciation_amortization):
        notes.append("depreciation_amortization unavailable")
    if not _is_valid(fd.capex):
        notes.append("capex unavailable")
    if not _is_valid(fd.shares_outstanding) or (
        fd.shares_outstanding is not None and fd.shares_outstanding <= 0.0
    ):
        notes.append("shares_outstanding unavailable or non-positive")

    # Need at minimum net_income and shares_outstanding
    if (
        not _is_valid(fd.net_income)
        or not _is_valid(fd.shares_outstanding)
        or fd.shares_outstanding is None
        or fd.shares_outstanding <= 0.0
        or fd.net_income is None
    ):
        return ValuationModelResult(
            methodology="owner_earnings_dcf",
            fair_value=None,
            margin_of_safety=None,
            confidence=0.0,
            data_quality_notes=notes or ["insufficient data"],
        )

    # Compute owner earnings
    da = fd.depreciation_amortization if _is_valid(fd.depreciation_amortization) else 0.0
    assert da is not None  # mypy narrowing after _is_valid check
    capex = fd.capex if _is_valid(fd.capex) else 0.0
    assert capex is not None
    assert fd.net_income is not None

    owner_earnings = fd.net_income + da - abs(capex)

    if owner_earnings <= 0.0:
        notes.append("owner_earnings non-positive")
        return ValuationModelResult(
            methodology="owner_earnings_dcf",
            fair_value=None,
            margin_of_safety=None,
            confidence=0.1,
            data_quality_notes=notes,
        )

    # WACC approximation: risk-free + 5% equity risk premium
    wacc = risk_free_rate + 0.05
    if wacc <= TERMINAL_GROWTH_RATE:
        wacc = TERMINAL_GROWTH_RATE + 0.02  # guard against negative denominator

    # Growth rate from earnings growth if available, else conservative
    _raw_growth: float = 0.03
    if fd.earnings_growth is not None and _is_valid(fd.earnings_growth):
        _raw_growth = fd.earnings_growth
    growth_rate = _clamp_growth(_raw_growth)

    # Discount 10 years of growing owner earnings
    total_pv = 0.0
    for year in range(1, DCF_PROJECTION_YEARS + 1):
        projected = owner_earnings * (1.0 + growth_rate) ** year
        total_pv += projected / (1.0 + wacc) ** year

    # Terminal value (Gordon Growth Model)
    terminal_oe = owner_earnings * (1.0 + growth_rate) ** DCF_PROJECTION_YEARS
    terminal_value = terminal_oe * (1.0 + TERMINAL_GROWTH_RATE) / (wacc - TERMINAL_GROWTH_RATE)
    terminal_pv = terminal_value / (1.0 + wacc) ** DCF_PROJECTION_YEARS
    total_pv += terminal_pv

    # Per-share with haircut
    fair_value_raw = total_pv / fd.shares_outstanding
    fair_value = fair_value_raw * (1.0 - OWNER_EARNINGS_HAIRCUT)

    if not math.isfinite(fair_value) or fair_value <= 0.0:
        notes.append("computed fair value non-positive or non-finite")
        return ValuationModelResult(
            methodology="owner_earnings_dcf",
            fair_value=None,
            margin_of_safety=None,
            confidence=0.1,
            data_quality_notes=notes,
        )

    # Data quality confidence
    confidence = 0.5
    if _is_valid(fd.depreciation_amortization):
        confidence += 0.15
    if _is_valid(fd.capex):
        confidence += 0.15
    if _is_valid(fd.earnings_growth):
        confidence += 0.2

    margin = _margin_of_safety(fair_value, current_price)

    return ValuationModelResult(
        methodology="owner_earnings_dcf",
        fair_value=round(fair_value, 2),
        margin_of_safety=round(margin, 4) if margin is not None else None,
        confidence=min(confidence, 1.0),
        data_quality_notes=notes if notes else ["all required data present"],
    )


# ---------------------------------------------------------------------------
# Model 2: Three-Stage DCF (Damodaran reference)
# ---------------------------------------------------------------------------


def compute_three_stage_dcf(
    fd: FDData,
    risk_free_rate: float,
    current_price: float,
) -> ValuationModelResult:
    """Three-Stage DCF: high growth (5yr) -> transition (5yr) -> terminal value.

    Scenario-weighted: bull (25%), base (50%), bear (25%) growth assumptions.
    Uses FCF as the cash flow metric.
    """
    notes: list[str] = []

    fcf = _safe_positive(fd.free_cash_flow)
    shares = _safe_positive(fd.shares_outstanding)

    if fcf is None:
        notes.append("free_cash_flow unavailable or non-positive")
    if shares is None:
        notes.append("shares_outstanding unavailable or non-positive")

    if fcf is None or shares is None:
        return ValuationModelResult(
            methodology="three_stage_dcf",
            fair_value=None,
            margin_of_safety=None,
            confidence=0.0,
            data_quality_notes=notes or ["insufficient data"],
        )

    # WACC approximation
    wacc = risk_free_rate + 0.05
    if wacc <= TERMINAL_GROWTH_RATE:
        wacc = TERMINAL_GROWTH_RATE + 0.02

    # Base growth rate
    _raw_rev_growth: float = 0.05
    if fd.revenue_growth is not None and _is_valid(fd.revenue_growth):
        _raw_rev_growth = fd.revenue_growth
    base_growth = _clamp_growth(_raw_rev_growth)

    scenarios: list[tuple[float, float]] = [
        (SCENARIO_BULL_WEIGHT, base_growth * BULL_GROWTH_MULTIPLIER),
        (SCENARIO_BASE_WEIGHT, base_growth),
        (SCENARIO_BEAR_WEIGHT, base_growth * BEAR_GROWTH_MULTIPLIER),
    ]

    weighted_fair_value = 0.0
    for scenario_weight, growth in scenarios:
        growth = _clamp_growth(growth)
        total_pv = 0.0

        # Phase 1: High growth (years 1-5)
        for year in range(1, HIGH_GROWTH_YEARS + 1):
            projected = fcf * (1.0 + growth) ** year
            total_pv += projected / (1.0 + wacc) ** year

        # Phase 2: Transition (years 6-10) — linear decay to terminal growth
        for i, year in enumerate(
            range(HIGH_GROWTH_YEARS + 1, HIGH_GROWTH_YEARS + TRANSITION_YEARS + 1)
        ):
            blend = (TRANSITION_YEARS - i) / TRANSITION_YEARS
            transition_growth = growth * blend + TERMINAL_GROWTH_RATE * (1.0 - blend)
            projected = fcf * (1.0 + growth) ** HIGH_GROWTH_YEARS
            for _t in range(i + 1):
                projected *= 1.0 + transition_growth
            total_pv += projected / (1.0 + wacc) ** year

        # Phase 3: Terminal value
        # Recompute last year FCF for terminal
        last_fcf = fcf * (1.0 + growth) ** HIGH_GROWTH_YEARS
        for _t in range(TRANSITION_YEARS):
            blend_t = (TRANSITION_YEARS - _t) / TRANSITION_YEARS
            tg = growth * blend_t + TERMINAL_GROWTH_RATE * (1.0 - blend_t)
            last_fcf *= 1.0 + tg

        if wacc > TERMINAL_GROWTH_RATE:
            terminal_value = (
                last_fcf * (1.0 + TERMINAL_GROWTH_RATE) / (wacc - TERMINAL_GROWTH_RATE)
            )
            terminal_pv = terminal_value / (1.0 + wacc) ** DCF_PROJECTION_YEARS
            total_pv += terminal_pv

        scenario_fv = total_pv / shares
        weighted_fair_value += scenario_weight * scenario_fv

    if not math.isfinite(weighted_fair_value) or weighted_fair_value <= 0.0:
        notes.append("computed fair value non-positive or non-finite")
        return ValuationModelResult(
            methodology="three_stage_dcf",
            fair_value=None,
            margin_of_safety=None,
            confidence=0.1,
            data_quality_notes=notes,
        )

    # Confidence
    confidence = 0.5
    if _is_valid(fd.revenue_growth):
        confidence += 0.25
    if _is_valid(fd.earnings_growth):
        confidence += 0.15
    if _is_valid(fd.free_cash_flow):
        confidence += 0.1

    margin = _margin_of_safety(weighted_fair_value, current_price)

    return ValuationModelResult(
        methodology="three_stage_dcf",
        fair_value=round(weighted_fair_value, 2),
        margin_of_safety=round(margin, 4) if margin is not None else None,
        confidence=min(confidence, 1.0),
        data_quality_notes=notes if notes else ["all required data present"],
    )


# ---------------------------------------------------------------------------
# Model 3: EV/EBITDA Relative Valuation (Damodaran reference)
# ---------------------------------------------------------------------------


def compute_ev_ebitda_relative(
    fd: FDData,
    current_price: float,
) -> ValuationModelResult:
    """EV/EBITDA relative: compare ticker EV/EBITDA to sector average.

    Derives implied fair value by dividing current price by the ratio
    of (ticker EV/EBITDA / sector average EV/EBITDA).
    """
    notes: list[str] = []

    ev_ebitda = fd.ev_to_ebitda
    if not _is_valid(ev_ebitda) or ev_ebitda is None or ev_ebitda <= 0.0:
        notes.append("ev_to_ebitda unavailable or non-positive")
        return ValuationModelResult(
            methodology="ev_ebitda_relative",
            fair_value=None,
            margin_of_safety=None,
            confidence=0.0,
            data_quality_notes=notes,
        )

    sector_avg = (
        fd.sector_ev_ebitda
        if _is_valid(fd.sector_ev_ebitda)
        and fd.sector_ev_ebitda is not None
        and fd.sector_ev_ebitda > 0.0
        else DEFAULT_SECTOR_EV_EBITDA
    )

    if sector_avg <= 0.0:
        notes.append("sector_ev_ebitda non-positive")
        return ValuationModelResult(
            methodology="ev_ebitda_relative",
            fair_value=None,
            margin_of_safety=None,
            confidence=0.0,
            data_quality_notes=notes,
        )

    if current_price <= 0.0:
        notes.append("current_price non-positive")
        return ValuationModelResult(
            methodology="ev_ebitda_relative",
            fair_value=None,
            margin_of_safety=None,
            confidence=0.0,
            data_quality_notes=notes,
        )

    # Implied fair value: price * (sector_avg / ticker_ev_ebitda)
    fair_value = current_price * (sector_avg / ev_ebitda)

    if not math.isfinite(fair_value) or fair_value <= 0.0:
        notes.append("computed fair value non-positive or non-finite")
        return ValuationModelResult(
            methodology="ev_ebitda_relative",
            fair_value=None,
            margin_of_safety=None,
            confidence=0.1,
            data_quality_notes=notes,
        )

    # Confidence based on data availability
    confidence = 0.5
    if _is_valid(fd.sector_ev_ebitda):
        confidence += 0.3  # sector-specific average is much better than default
        notes.append("using sector-specific EV/EBITDA average")
    else:
        notes.append("using S&P 500 median EV/EBITDA as fallback")

    margin = _margin_of_safety(fair_value, current_price)

    return ValuationModelResult(
        methodology="ev_ebitda_relative",
        fair_value=round(fair_value, 2),
        margin_of_safety=round(margin, 4) if margin is not None else None,
        confidence=min(confidence, 1.0),
        data_quality_notes=notes if notes else ["all required data present"],
    )


# ---------------------------------------------------------------------------
# Model 4: Residual Income Model (Hull reference)
# ---------------------------------------------------------------------------


def compute_residual_income(
    fd: FDData,
    risk_free_rate: float,
    current_price: float,
) -> ValuationModelResult:
    """Residual Income Model: excess ROE * book value, discounted with 20% haircut.

    Residual income = (ROE - cost_of_equity) * book_value_per_share.
    Fair value = book_value + PV(residual income stream).
    Apply 20% haircut for conservatism.
    """
    notes: list[str] = []

    bvps = fd.book_value_per_share
    roe = fd.roe

    if not _is_valid(bvps) or bvps is None or bvps <= 0.0:
        notes.append("book_value_per_share unavailable or non-positive")
    if not _is_valid(roe) or roe is None:
        notes.append("roe unavailable")

    if not _is_valid(bvps) or bvps is None or bvps <= 0.0 or not _is_valid(roe) or roe is None:
        return ValuationModelResult(
            methodology="residual_income",
            fair_value=None,
            margin_of_safety=None,
            confidence=0.0,
            data_quality_notes=notes or ["insufficient data"],
        )

    # Cost of equity approximation: risk-free + 5% ERP
    cost_of_equity = risk_free_rate + 0.05

    # Excess ROE
    excess_roe = roe - cost_of_equity

    # If ROE does not exceed cost of equity, the stock has no excess return —
    # fair value is just book value (with haircut)
    if excess_roe <= 0.0:
        fair_value_raw = bvps
        notes.append("ROE does not exceed cost of equity — fair value equals book value")
    else:
        # Discount 10 years of residual income
        ri_pv = 0.0
        discount_rate = cost_of_equity if cost_of_equity > 0.0 else 0.08
        for year in range(1, DCF_PROJECTION_YEARS + 1):
            residual_income = excess_roe * bvps
            ri_pv += residual_income / (1.0 + discount_rate) ** year

        # Terminal residual income (fade to zero — conservative)
        terminal_ri = (
            excess_roe * bvps / (discount_rate - TERMINAL_GROWTH_RATE)
            if (discount_rate > TERMINAL_GROWTH_RATE)
            else 0.0
        )
        terminal_pv = terminal_ri / (1.0 + discount_rate) ** DCF_PROJECTION_YEARS
        ri_pv += terminal_pv

        fair_value_raw = bvps + ri_pv

    # Apply haircut
    fair_value = fair_value_raw * (1.0 - RESIDUAL_INCOME_HAIRCUT)

    if not math.isfinite(fair_value) or fair_value <= 0.0:
        notes.append("computed fair value non-positive or non-finite")
        return ValuationModelResult(
            methodology="residual_income",
            fair_value=None,
            margin_of_safety=None,
            confidence=0.1,
            data_quality_notes=notes,
        )

    # Confidence
    confidence = 0.5
    if _is_valid(fd.roe):
        confidence += 0.25
    if _is_valid(fd.book_value_per_share):
        confidence += 0.25

    margin = _margin_of_safety(fair_value, current_price)

    return ValuationModelResult(
        methodology="residual_income",
        fair_value=round(fair_value, 2),
        margin_of_safety=round(margin, 4) if margin is not None else None,
        confidence=min(confidence, 1.0),
        data_quality_notes=notes if notes else ["all required data present"],
    )


# ---------------------------------------------------------------------------
# Composite Combiner
# ---------------------------------------------------------------------------


def compute_composite_valuation(
    ticker: str,
    current_price: float,
    fd: FDData,
    risk_free_rate: float = 0.04,
) -> CompositeValuation:
    """Compute composite valuation from four independent models.

    Renormalizes weights across models that produced valid fair values.
    When all four return None, the composite fair value is None.

    Parameters
    ----------
    ticker
        Stock ticker symbol.
    current_price
        Current market price per share.
    fd
        Financial data inputs for the valuation models.
    risk_free_rate
        Current risk-free rate (decimal). Default 4%.

    Returns
    -------
    CompositeValuation
        Aggregated valuation with signal classification.
    """
    if current_price <= 0.0 or not math.isfinite(current_price):
        # Cannot compute valuation without a valid price
        return CompositeValuation(
            ticker=ticker,
            current_price=max(current_price, 0.0) if math.isfinite(current_price) else 0.0,
            composite_fair_value=None,
            composite_margin_of_safety=None,
            valuation_signal=None,
            models=[],
            weights_used={},
            computed_at=datetime.now(UTC),
        )

    # Run all four models
    model_results: list[tuple[str, float, ValuationModelResult]] = []
    oe = compute_owner_earnings_dcf(fd, risk_free_rate, current_price)
    ts = compute_three_stage_dcf(fd, risk_free_rate, current_price)
    ev = compute_ev_ebitda_relative(fd, current_price)
    ri = compute_residual_income(fd, risk_free_rate, current_price)

    all_results = [oe, ts, ev, ri]
    raw_weights = {
        "owner_earnings_dcf": OWNER_EARNINGS_WEIGHT,
        "three_stage_dcf": THREE_STAGE_WEIGHT,
        "ev_ebitda_relative": EV_EBITDA_WEIGHT,
        "residual_income": RESIDUAL_INCOME_WEIGHT,
    }

    # Collect models with valid fair values
    for result in all_results:
        if result.fair_value is not None and result.fair_value > 0.0:
            model_results.append((result.methodology, raw_weights[result.methodology], result))

    # Renormalize weights
    weights_used: dict[str, float] = {}
    if model_results:
        total_weight = sum(w for _, w, _ in model_results)
        if total_weight > 0.0:
            for methodology, weight, _ in model_results:
                weights_used[methodology] = round(weight / total_weight, 4)

    # Compute weighted average fair value
    composite_fv: float | None = None
    composite_mos: float | None = None
    signal: ValuationSignal | None = None

    if weights_used and model_results:
        weighted_sum = 0.0
        for methodology, _, result in model_results:
            assert result.fair_value is not None
            weighted_sum += weights_used[methodology] * result.fair_value
        composite_fv = round(weighted_sum, 2)

        if composite_fv > 0.0:
            composite_mos = round((composite_fv - current_price) / composite_fv, 4)
            signal = _classify_signal(composite_mos)

    return CompositeValuation(
        ticker=ticker,
        current_price=current_price,
        composite_fair_value=composite_fv,
        composite_margin_of_safety=composite_mos,
        valuation_signal=signal,
        models=all_results,
        weights_used=weights_used,
        computed_at=datetime.now(UTC),
    )

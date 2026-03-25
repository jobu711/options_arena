"""Risk-adjusted performance metric computation.

Pure computation module — takes lists of returns and holding days, returns
a typed ``RiskAdjustedMetrics`` model. No I/O, no API calls, no database access.

Formulas:
- Sharpe = sqrt(252 / avg_holding_days) * mean(excess_returns) / std(excess_returns)
- Sortino = sqrt(252 / avg_holding_days) * mean(excess_returns) / downside_std
- Max Drawdown = walk *position-sized* equity curve tracking peak-to-trough
- excess_returns = returns - (risk_free_rate * holding_days / 365)

Equity-curve methodology:
    Each trade impacts the portfolio proportionally to ``position_size_fraction``
    (default 5%). A -100% option expiry with 5% sizing reduces the portfolio by 5%,
    not 100%. This prevents a single worthless expiry from zeroing the entire curve.
"""

from __future__ import annotations

import math
import statistics
from datetime import date, timedelta

from options_arena.models.analytics import RiskAdjustedMetrics

# Minimum number of trades required for ratio computation
_MIN_TRADES_DEFAULT = 30

# Trading days per year for annualization
_TRADING_DAYS_PER_YEAR = 252

# Default position size: 5% of portfolio per trade
_DEFAULT_POSITION_SIZE_FRACTION = 0.05


def compute_risk_adjusted_metrics(
    returns: list[float],
    holding_days: list[int],
    risk_free_rate: float = 0.05,
    min_trades: int = _MIN_TRADES_DEFAULT,
    position_size_fraction: float = _DEFAULT_POSITION_SIZE_FRACTION,
) -> RiskAdjustedMetrics:
    """Compute risk-adjusted performance metrics from trade returns.

    Args:
        returns: List of trade return fractions (e.g. 0.05 = 5% gain).
        holding_days: List of holding periods in calendar days, parallel to returns.
        risk_free_rate: Annualized risk-free rate (default 5%).
        min_trades: Minimum number of trades required for Sharpe/Sortino computation.
        position_size_fraction: Fraction of portfolio allocated per trade for equity
            curve computation (default 0.05 = 5%). Each trade's portfolio impact is
            ``position_size_fraction * trade_return``. Sharpe/Sortino use raw per-trade
            returns (unaffected by this parameter).

    Returns:
        ``RiskAdjustedMetrics`` with computed ratios. Ratios are ``None`` when
        data is insufficient (< min_trades), standard deviation is zero, or
        downside deviation is zero.

    Raises:
        ValueError: If any return or holding_days value is non-finite, if
            the lists have mismatched lengths, or if position_size_fraction
            is not in (0, 1].
    """
    if len(returns) != len(holding_days):
        msg = (
            f"returns and holding_days must have the same length, "
            f"got {len(returns)} and {len(holding_days)}"
        )
        raise ValueError(msg)

    if not math.isfinite(position_size_fraction):
        raise ValueError(f"position_size_fraction must be finite, got {position_size_fraction}")
    if position_size_fraction <= 0 or position_size_fraction > 1.0:
        raise ValueError(
            f"position_size_fraction must be in (0, 1], got {position_size_fraction}"
        )

    # Validate inputs: reject NaN/Inf
    for i, r in enumerate(returns):
        if not math.isfinite(r):
            raise ValueError(f"returns[{i}] must be finite, got {r}")
    for i, hd in enumerate(holding_days):
        if hd < 0:
            raise ValueError(f"holding_days[{i}] must be >= 0, got {hd}")

    total_trades = len(returns)
    position_size_pct = position_size_fraction * 100.0

    if total_trades == 0:
        return RiskAdjustedMetrics(
            lookback_days=365,
            total_trades=0,
            sharpe_ratio=None,
            sortino_ratio=None,
            max_drawdown_pct=None,
            max_drawdown_date=None,
            annualized_return_pct=None,
            risk_free_rate=risk_free_rate,
            position_size_pct=position_size_pct,
        )

    # Compute excess returns: return - (risk_free_rate * holding_days / 365)
    excess_returns: list[float] = []
    for r, hd in zip(returns, holding_days, strict=True):
        # Guard against division by zero when holding_days is 0
        rf_adj = risk_free_rate * hd / 365 if hd > 0 else 0.0
        excess_returns.append(r - rf_adj)

    # Average holding period for annualization
    avg_hd = sum(holding_days) / total_trades
    # Guard against zero or very small average holding days
    if avg_hd < 1:
        avg_hd = 1.0

    annualization_factor = math.sqrt(_TRADING_DAYS_PER_YEAR / avg_hd)

    # Compute Sharpe ratio (uses raw per-trade returns, not position-sized)
    sharpe_ratio: float | None = None
    if total_trades >= min_trades:
        mean_excess = statistics.mean(excess_returns)
        if total_trades >= 2:
            std_excess = statistics.stdev(excess_returns)
            if std_excess > 0:
                sharpe_ratio = annualization_factor * mean_excess / std_excess

    # Compute Sortino ratio (uses raw per-trade returns, not position-sized)
    sortino_ratio: float | None = None
    if total_trades >= min_trades:
        mean_excess = statistics.mean(excess_returns)
        downside_returns = [min(er, 0.0) for er in excess_returns]
        if total_trades >= 2:
            # Downside deviation: std of negative excess returns (including zeros for
            # positive returns treated as 0 contribution to downside risk)
            downside_sq_sum = sum(dr * dr for dr in downside_returns)
            downside_std = math.sqrt(downside_sq_sum / (total_trades - 1))
            if downside_std > 0:
                sortino_ratio = annualization_factor * mean_excess / downside_std

    # Compute max drawdown by walking the position-sized equity curve.
    # Each trade's portfolio impact: position_size_fraction * trade_return.
    # A -100% option expiry with 5% sizing -> portfolio drops 5%, not 100%.
    max_drawdown_pct: float | None = None
    max_drawdown_date: date | None = None

    if total_trades > 0:
        equity = 1.0
        peak = 1.0
        worst_dd = 0.0
        worst_dd_idx = 0

        for i, r in enumerate(returns):
            equity *= 1.0 + position_size_fraction * r
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak if peak > 0 else 0.0
            if dd > worst_dd:
                worst_dd = dd
                worst_dd_idx = i

        max_drawdown_pct = worst_dd * 100.0  # Convert to percentage

        # Approximate the drawdown date using the trade index
        # Use today minus cumulative holding days as a rough date
        days_from_start = sum(holding_days[: worst_dd_idx + 1])
        max_drawdown_date = date.today() - timedelta(days=sum(holding_days) - days_from_start)

    # Compute annualized return using position-sized equity curve
    annualized_return_pct: float | None = None
    if total_trades > 0:
        cumulative = 1.0
        for r in returns:
            cumulative *= 1.0 + position_size_fraction * r
        total_days = sum(holding_days)
        if total_days > 0:
            years = total_days / 365.0
            if years > 0 and cumulative > 0:
                annualized_return_pct = (cumulative ** (1.0 / years) - 1.0) * 100.0
            else:
                annualized_return_pct = (cumulative - 1.0) * 100.0
        else:
            annualized_return_pct = (cumulative - 1.0) * 100.0

    # Determine lookback from total holding days
    lookback = sum(holding_days) if holding_days else 365

    return RiskAdjustedMetrics(
        lookback_days=max(lookback, 1),
        total_trades=total_trades,
        sharpe_ratio=sharpe_ratio,
        sortino_ratio=sortino_ratio,
        max_drawdown_pct=max_drawdown_pct,
        max_drawdown_date=max_drawdown_date,
        annualized_return_pct=annualized_return_pct,
        risk_free_rate=risk_free_rate,
        position_size_pct=position_size_pct,
    )

"""Tool wrappers and toolset builders for desk agents.

Each tool function wraps a service call, formats the result as a string for
LLM consumption, and appends its name to ``ctx.deps.tools_used`` for
observability.  Tools never raise — all exceptions are caught and returned
as ``"Error: ..."`` strings.

Builder functions return lists of tool callables suitable for passing to
``Agent(tools=...)``.
"""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import date

from pydantic_ai import RunContext

from options_arena.agents._desk_deps import DeskDeps
from options_arena.models.enums import TICKER_RE
from options_arena.models.options import OptionContract

logger = logging.getLogger(__name__)

# Maximum number of comparison tickers in fetch_correlation to bound resource usage.
_MAX_CORRELATION_TICKERS = 5

# Default confidence for successful desk responses.  Placeholder until
# confidence is derived from observable quality signals.
DESK_SUCCESS_CONFIDENCE = 0.7


def _validate_ticker(ticker: str) -> str | None:
    """Return an error string if *ticker* fails ``TICKER_RE``, else ``None``."""
    if not TICKER_RE.match(ticker.upper()):
        return f"Error: invalid ticker format: {ticker!r}"
    return None


# ---------------------------------------------------------------------------
# Tool: fetch_quote
# ---------------------------------------------------------------------------


async def fetch_quote(ctx: RunContext[DeskDeps], ticker: str) -> str:
    """Fetch a real-time quote for *ticker*.

    Returns a formatted string with price, bid/ask, volume, and 52-week
    range (fetched via ``TickerInfo`` for the range).
    """
    tool_name = "fetch_quote"
    if err := _validate_ticker(ticker):
        ctx.deps.tools_used.append(tool_name)
        return err
    try:
        quote = await ctx.deps.market_data.fetch_quote(ticker)
        lines: list[str] = [
            f"Quote for {ticker}:",
            f"  Price: ${quote.price}",
            f"  Bid: ${quote.bid}  Ask: ${quote.ask}",
            f"  Volume: {quote.volume:,}",
        ]
        # Attempt to get 52-week range from ticker_info
        try:
            info = await ctx.deps.market_data.fetch_ticker_info(ticker)
            lines.append(
                f"  52W High: ${info.fifty_two_week_high}  52W Low: ${info.fifty_two_week_low}"
            )
        except Exception:
            logger.debug("Could not fetch ticker_info for 52w range: %s", ticker)
        ctx.deps.tools_used.append(tool_name)
        return "\n".join(lines)
    except Exception as exc:
        logger.debug("fetch_quote failed for %s: %s", ticker, exc)
        ctx.deps.tools_used.append(tool_name)
        return f"Error: could not fetch quote for {ticker}"


# ---------------------------------------------------------------------------
# Tool: fetch_vol_surface_slice
# ---------------------------------------------------------------------------


async def fetch_vol_surface_slice(ctx: RunContext[DeskDeps], ticker: str) -> str:
    """Fetch a volatility surface slice showing IV by strike/expiry.

    Returns up to 10 contracts from the nearest expiration with their IV,
    strike, type, bid, ask, volume, and open interest.
    """
    tool_name = "fetch_vol_surface_slice"
    if err := _validate_ticker(ticker):
        ctx.deps.tools_used.append(tool_name)
        return err
    try:
        expirations = await ctx.deps.options_data.fetch_expirations(ticker)
        if not expirations:
            ctx.deps.tools_used.append(tool_name)
            return f"No option expirations found for {ticker}"

        # Find the nearest expiration with at least some DTE
        today = date.today()
        future_exps = [e for e in expirations if e > today]
        if not future_exps:
            ctx.deps.tools_used.append(tool_name)
            return f"No future expirations found for {ticker}"

        target_exp = future_exps[0]
        contracts = await ctx.deps.options_data.fetch_chain(ticker, target_exp)
        if not contracts:
            ctx.deps.tools_used.append(tool_name)
            return f"No contracts found for {ticker} exp {target_exp.isoformat()}"

        # Limit to 10 contracts, sorted by strike
        sorted_contracts = sorted(contracts, key=lambda c: c.strike)[:10]

        lines: list[str] = [
            f"Vol surface slice for {ticker} (exp {target_exp.isoformat()}):",
        ]
        for c in sorted_contracts:
            iv_str = f"{c.market_iv * 100:.1f}%" if math.isfinite(c.market_iv) else "N/A"
            lines.append(
                f"  {c.option_type.value.upper()} ${c.strike} "
                f"IV={iv_str} "
                f"Bid=${c.bid} Ask=${c.ask} "
                f"Vol={c.volume:,} OI={c.open_interest:,}"
            )

        ctx.deps.tools_used.append(tool_name)
        return "\n".join(lines)
    except Exception as exc:
        logger.debug("fetch_vol_surface_slice failed for %s: %s", ticker, exc)
        ctx.deps.tools_used.append(tool_name)
        return f"Error: could not fetch vol surface for {ticker}"


# ---------------------------------------------------------------------------
# Tool: compute_iv_for_strike
# ---------------------------------------------------------------------------


async def compute_iv_for_strike(
    ctx: RunContext[DeskDeps],
    ticker: str,
    strike: float,
    expiry: str,
) -> str:
    """Find the closest strike in the chain to *strike* and show IV details.

    Args:
        ticker: Underlying ticker symbol.
        strike: Target strike price.
        expiry: Expiration date as ISO 8601 string (``YYYY-MM-DD``).
    """
    tool_name = "compute_iv_for_strike"
    if err := _validate_ticker(ticker):
        ctx.deps.tools_used.append(tool_name)
        return err
    try:
        exp_date = date.fromisoformat(expiry)
        contracts = await ctx.deps.options_data.fetch_chain(ticker, exp_date)
        if not contracts:
            ctx.deps.tools_used.append(tool_name)
            return f"No contracts found for {ticker} exp {expiry}"

        # Find closest strike
        closest = min(contracts, key=lambda c: abs(float(c.strike) - strike))
        iv_str = f"{closest.market_iv * 100:.1f}%" if math.isfinite(closest.market_iv) else "N/A"

        result = (
            f"Closest match for {ticker} ${strike} exp {expiry}:\n"
            f"  {closest.option_type.value.upper()} ${closest.strike}\n"
            f"  IV: {iv_str}\n"
            f"  Bid: ${closest.bid}  Ask: ${closest.ask}\n"
            f"  Volume: {closest.volume:,}  OI: {closest.open_interest:,}"
        )
        ctx.deps.tools_used.append(tool_name)
        return result
    except Exception as exc:
        logger.debug("compute_iv_for_strike failed for %s: %s", ticker, exc)
        ctx.deps.tools_used.append(tool_name)
        return f"Error: could not compute IV for {ticker} ${strike} {expiry}"


# ---------------------------------------------------------------------------
# Tool: fetch_correlation
# ---------------------------------------------------------------------------


async def fetch_correlation(
    ctx: RunContext[DeskDeps],
    ticker: str,
    tickers: list[str],
) -> str:
    """Compute pairwise return correlations between *ticker* and each of *tickers*.

    Uses OHLCV close prices over the last year to compute daily return
    correlations.
    """
    tool_name = "fetch_correlation"
    if err := _validate_ticker(ticker):
        ctx.deps.tools_used.append(tool_name)
        return err
    try:
        import numpy as np

        # Cap comparison tickers to bound resource usage
        capped = [t for t in tickers if t != ticker][:_MAX_CORRELATION_TICKERS]
        all_tickers = [ticker] + capped

        # Validate all tickers before fetching
        for t in all_tickers:
            if not TICKER_RE.match(t.upper()):
                ctx.deps.tools_used.append(tool_name)
                return f"Error: invalid ticker format: {t!r}"

        # Fetch OHLCV in parallel with error isolation
        async def _fetch(t: str) -> tuple[str, list[float] | None]:
            try:
                ohlcv_list = await ctx.deps.market_data.fetch_ohlcv(t, period="1y")
                prices = [float(bar.close) for bar in ohlcv_list]
                # Guard zero/negative prices that cause division-by-zero
                if any(p <= 0.0 for p in prices):
                    logger.debug("Zero/negative prices in OHLCV for %s", t)
                    return (t, None)
                return (t, prices)
            except Exception:
                logger.debug("Could not fetch OHLCV for %s in correlation", t)
                return (t, None)

        results = await asyncio.gather(*[_fetch(t) for t in all_tickers], return_exceptions=True)
        close_series: dict[str, list[float]] = {
            t: prices
            for r in results
            if not isinstance(r, BaseException)
            for t, prices in [r]
            if prices is not None
        }

        if ticker not in close_series:
            ctx.deps.tools_used.append(tool_name)
            return f"Error: could not fetch price data for {ticker}"

        if len(close_series) < 2:  # noqa: PLR2004
            ctx.deps.tools_used.append(tool_name)
            return "Error: insufficient data for correlation (need at least 2 tickers)"

        # Compute daily returns and pairwise correlation
        base_prices = np.array(close_series[ticker])
        base_returns = np.diff(base_prices) / base_prices[:-1]

        lines: list[str] = [f"Correlations with {ticker} (1Y daily returns):"]
        for t in all_tickers:
            if t == ticker:
                continue
            if t not in close_series:
                lines.append(f"  {t}: N/A (no data)")
                continue

            other_prices = np.array(close_series[t])
            # Align to same length (shorter of the two)
            min_len = min(len(base_returns), max(0, len(other_prices) - 1))
            if min_len < 20:  # noqa: PLR2004
                lines.append(f"  {t}: N/A (insufficient overlap)")
                continue

            other_returns = np.diff(other_prices) / other_prices[:-1]
            corr_matrix = np.corrcoef(base_returns[-min_len:], other_returns[-min_len:])
            corr_val = float(corr_matrix[0, 1])
            if not math.isfinite(corr_val):
                lines.append(f"  {t}: N/A (unstable)")
                continue
            lines.append(f"  {t}: {corr_val:.3f}")

        ctx.deps.tools_used.append(tool_name)
        return "\n".join(lines)
    except Exception as exc:
        logger.debug("fetch_correlation failed for %s: %s", ticker, exc)
        ctx.deps.tools_used.append(tool_name)
        return f"Error: could not compute correlations for {ticker}"


# ---------------------------------------------------------------------------
# Tool: fetch_portfolio_exposure
# ---------------------------------------------------------------------------


async def fetch_portfolio_exposure(ctx: RunContext[DeskDeps], ticker: str) -> str:
    """Query repository for historical recommended contracts for *ticker*.

    Returns the most recent recommended contracts with their direction,
    strike, expiration, and scores.
    """
    tool_name = "fetch_portfolio_exposure"
    if err := _validate_ticker(ticker):
        ctx.deps.tools_used.append(tool_name)
        return err
    try:
        contracts = await ctx.deps.repo.get_contracts_for_ticker(ticker, limit=10)
        if not contracts:
            ctx.deps.tools_used.append(tool_name)
            return f"No historical recommended contracts found for {ticker}"

        lines: list[str] = [f"Recent recommended contracts for {ticker}:"]
        for c in contracts:
            lines.append(
                f"  {c.option_type.value.upper()} ${c.strike} "
                f"exp {c.expiration.isoformat()} "
                f"dir={c.direction.value} "
                f"score={c.composite_score:.1f} "
                f"mid=${c.entry_mid}"
            )

        ctx.deps.tools_used.append(tool_name)
        return "\n".join(lines)
    except Exception as exc:
        logger.debug("fetch_portfolio_exposure failed for %s: %s", ticker, exc)
        ctx.deps.tools_used.append(tool_name)
        return f"Error: could not fetch portfolio exposure for {ticker}"


# ---------------------------------------------------------------------------
# Toolset builders
# ---------------------------------------------------------------------------


def build_volatility_toolset() -> list[object]:
    """Return the tools for a Volatility Desk agent.

    Tools: ``fetch_quote``, ``fetch_vol_surface_slice``, ``compute_iv_for_strike``.
    """
    return [fetch_quote, fetch_vol_surface_slice, compute_iv_for_strike]


def build_risk_toolset() -> list[object]:
    """Return the tools for a Risk Desk agent.

    Tools: ``fetch_quote``, ``fetch_correlation``, ``fetch_portfolio_exposure``.
    """
    return [fetch_quote, fetch_correlation, fetch_portfolio_exposure]


# ---------------------------------------------------------------------------
# Tool: fetch_related_ohlcv (Trend desk)
# ---------------------------------------------------------------------------


async def fetch_related_ohlcv(
    ctx: RunContext[DeskDeps],
    ticker: str,
    period: str = "6mo",
) -> str:
    """Fetch recent OHLCV bars for *ticker*.

    Returns the last 5 bars with date, open, high, low, close, and volume.
    Useful for assessing recent price action and directional momentum.

    Args:
        ticker: Underlying ticker symbol.
        period: Data period — ``"6mo"`` (default), ``"1y"``, ``"3mo"``.
    """
    tool_name = "fetch_related_ohlcv"
    if err := _validate_ticker(ticker):
        ctx.deps.tools_used.append(tool_name)
        return err
    try:
        ohlcv_list = await ctx.deps.market_data.fetch_ohlcv(ticker, period=period)
        if not ohlcv_list:
            ctx.deps.tools_used.append(tool_name)
            return f"No OHLCV data found for {ticker} (period={period})"

        # Show last 5 bars
        recent = ohlcv_list[-5:]
        lines: list[str] = [f"Recent OHLCV for {ticker} (last {len(recent)} bars):"]
        for bar in recent:
            lines.append(
                f"  {bar.date.isoformat()} "
                f"O=${bar.open} H=${bar.high} L=${bar.low} C=${bar.close} "
                f"Vol={bar.volume:,}"
            )

        ctx.deps.tools_used.append(tool_name)
        return "\n".join(lines)
    except Exception as exc:
        logger.debug("fetch_related_ohlcv failed for %s: %s", ticker, exc)
        ctx.deps.tools_used.append(tool_name)
        return f"Error: could not fetch OHLCV for {ticker}"


# ---------------------------------------------------------------------------
# Tool: compute_indicator_on_demand (Trend desk)
# ---------------------------------------------------------------------------


async def compute_indicator_on_demand(
    ctx: RunContext[DeskDeps],
    ticker: str,
    indicator: str,
) -> str:
    """Compute a technical indicator on demand for *ticker*.

    Supported indicators: ``"rsi"``, ``"macd"``, ``"sma_alignment"``, ``"adx"``.

    Args:
        ticker: Underlying ticker symbol.
        indicator: Indicator name (case-insensitive).
    """
    tool_name = "compute_indicator_on_demand"
    if err := _validate_ticker(ticker):
        ctx.deps.tools_used.append(tool_name)
        return err

    supported = {"rsi", "macd", "sma_alignment", "adx"}
    indicator_lower = indicator.lower().strip()
    if indicator_lower not in supported:
        ctx.deps.tools_used.append(tool_name)
        return (
            f"Error: unsupported indicator {indicator!r}. "
            f"Supported: {', '.join(sorted(supported))}"
        )

    try:
        import pandas as pd

        from options_arena.indicators import adx as compute_adx
        from options_arena.indicators import macd as compute_macd
        from options_arena.indicators import rsi as compute_rsi
        from options_arena.indicators import sma_alignment as compute_sma_alignment

        ohlcv_list = await ctx.deps.market_data.fetch_ohlcv(ticker, period="1y")
        if not ohlcv_list:
            ctx.deps.tools_used.append(tool_name)
            return f"No OHLCV data found for {ticker}"

        close_series = pd.Series(
            [float(bar.close) for bar in ohlcv_list],
            index=[bar.date for bar in ohlcv_list],
        )

        result_str: str
        if indicator_lower == "rsi":
            rsi_series = compute_rsi(close_series)
            val = rsi_series.iloc[-1]
            if not math.isfinite(val):
                result_str = f"RSI for {ticker}: N/A (insufficient data)"
            else:
                interpretation = (
                    "overbought (>70)"
                    if val > 70  # noqa: PLR2004
                    else "oversold (<30)"
                    if val < 30  # noqa: PLR2004
                    else "neutral"
                )
                result_str = f"RSI(14) for {ticker}: {val:.1f} — {interpretation}"

        elif indicator_lower == "macd":
            histogram = compute_macd(close_series)
            val = histogram.iloc[-1]
            if not math.isfinite(val):
                result_str = f"MACD for {ticker}: N/A (insufficient data)"
            else:
                interpretation = "bullish (positive)" if val > 0 else "bearish (negative)"
                result_str = f"MACD histogram for {ticker}: {val:.4f} — {interpretation}"

        elif indicator_lower == "sma_alignment":
            alignment = compute_sma_alignment(close_series)
            val = alignment.iloc[-1]
            if not math.isfinite(val):
                result_str = f"SMA alignment for {ticker}: N/A (insufficient data)"
            else:
                interpretation = (
                    "strongly bullish"
                    if val > 0.5  # noqa: PLR2004
                    else "bullish"
                    if val > 0
                    else "strongly bearish"
                    if val < -0.5  # noqa: PLR2004
                    else "bearish"
                    if val < 0
                    else "neutral"
                )
                result_str = f"SMA alignment for {ticker}: {val:.2f} — {interpretation}"

        else:  # adx
            high_series = pd.Series(
                [float(bar.high) for bar in ohlcv_list],
                index=[bar.date for bar in ohlcv_list],
            )
            low_series = pd.Series(
                [float(bar.low) for bar in ohlcv_list],
                index=[bar.date for bar in ohlcv_list],
            )
            adx_series = compute_adx(high_series, low_series, close_series)
            val = adx_series.iloc[-1]
            if not math.isfinite(val):
                result_str = f"ADX for {ticker}: N/A (insufficient data)"
            else:
                interpretation = (
                    "strong trend (>25)"
                    if val > 25  # noqa: PLR2004
                    else "weak/no trend (<15)"
                    if val < 15  # noqa: PLR2004
                    else "moderate trend"
                )
                result_str = f"ADX(14) for {ticker}: {val:.1f} — {interpretation}"

        ctx.deps.tools_used.append(tool_name)
        return result_str
    except Exception as exc:
        logger.debug("compute_indicator_on_demand failed for %s/%s: %s", ticker, indicator, exc)
        ctx.deps.tools_used.append(tool_name)
        return f"Error: could not compute {indicator} for {ticker}"


# ---------------------------------------------------------------------------
# Tool: fetch_chain_summary (Flow desk)
# ---------------------------------------------------------------------------


async def fetch_chain_summary(ctx: RunContext[DeskDeps], ticker: str) -> str:
    """Fetch an option chain summary for *ticker*.

    Returns total calls/puts, total OI, total volume, put/call OI ratio,
    and put/call volume ratio for the nearest future expiration.
    """
    tool_name = "fetch_chain_summary"
    if err := _validate_ticker(ticker):
        ctx.deps.tools_used.append(tool_name)
        return err
    try:
        expirations = await ctx.deps.options_data.fetch_expirations(ticker)
        if not expirations:
            ctx.deps.tools_used.append(tool_name)
            return f"No option expirations found for {ticker}"

        today = date.today()
        future_exps = [e for e in expirations if e > today]
        if not future_exps:
            ctx.deps.tools_used.append(tool_name)
            return f"No future expirations found for {ticker}"

        target_exp = future_exps[0]
        contracts = await ctx.deps.options_data.fetch_chain(ticker, target_exp)
        if not contracts:
            ctx.deps.tools_used.append(tool_name)
            return f"No contracts found for {ticker} exp {target_exp.isoformat()}"

        call_count = 0
        put_count = 0
        call_oi = 0
        put_oi = 0
        call_vol = 0
        put_vol = 0

        for c in contracts:
            if c.option_type.value == "call":
                call_count += 1
                call_oi += c.open_interest
                call_vol += c.volume
            else:
                put_count += 1
                put_oi += c.open_interest
                put_vol += c.volume

        # Division-by-zero guards
        pc_oi_ratio = put_oi / call_oi if call_oi > 0 else float("nan")
        pc_vol_ratio = put_vol / call_vol if call_vol > 0 else float("nan")

        lines: list[str] = [
            f"Chain summary for {ticker} (exp {target_exp.isoformat()}):",
            f"  Calls: {call_count} contracts, OI={call_oi:,}, Vol={call_vol:,}",
            f"  Puts: {put_count} contracts, OI={put_oi:,}, Vol={put_vol:,}",
            f"  Total OI: {call_oi + put_oi:,}",
            f"  Total Volume: {call_vol + put_vol:,}",
        ]
        if math.isfinite(pc_oi_ratio):
            lines.append(f"  Put/Call OI Ratio: {pc_oi_ratio:.2f}")
        else:
            lines.append("  Put/Call OI Ratio: N/A (no call OI)")
        if math.isfinite(pc_vol_ratio):
            lines.append(f"  Put/Call Volume Ratio: {pc_vol_ratio:.2f}")
        else:
            lines.append("  Put/Call Volume Ratio: N/A (no call volume)")

        ctx.deps.tools_used.append(tool_name)
        return "\n".join(lines)
    except Exception as exc:
        logger.debug("fetch_chain_summary failed for %s: %s", ticker, exc)
        ctx.deps.tools_used.append(tool_name)
        return f"Error: could not fetch chain summary for {ticker}"


# ---------------------------------------------------------------------------
# Tool: fetch_unusual_activity (Flow desk)
# ---------------------------------------------------------------------------


async def fetch_unusual_activity(ctx: RunContext[DeskDeps], ticker: str) -> str:
    """Detect unusual options activity for *ticker*.

    Identifies contracts where volume exceeds 3x open interest — a signal of
    unusual activity that may indicate institutional positioning. Returns up
    to 5 contracts sorted by volume/OI ratio descending.
    """
    tool_name = "fetch_unusual_activity"
    if err := _validate_ticker(ticker):
        ctx.deps.tools_used.append(tool_name)
        return err
    try:
        expirations = await ctx.deps.options_data.fetch_expirations(ticker)
        if not expirations:
            ctx.deps.tools_used.append(tool_name)
            return f"No option expirations found for {ticker}"

        today = date.today()
        future_exps = [e for e in expirations if e > today]
        if not future_exps:
            ctx.deps.tools_used.append(tool_name)
            return f"No future expirations found for {ticker}"

        target_exp = future_exps[0]
        contracts = await ctx.deps.options_data.fetch_chain(ticker, target_exp)
        if not contracts:
            ctx.deps.tools_used.append(tool_name)
            return f"No contracts found for {ticker} exp {target_exp.isoformat()}"

        # Unusual activity: volume > 3x open interest
        _UNUSUAL_THRESHOLD = 3.0
        unusual: list[tuple[float, OptionContract]] = []
        for c in contracts:
            if c.open_interest > 0 and c.volume > 0:
                ratio = c.volume / c.open_interest
                if ratio > _UNUSUAL_THRESHOLD:
                    unusual.append((ratio, c))

        if not unusual:
            ctx.deps.tools_used.append(tool_name)
            return (
                f"No unusual activity detected for {ticker} "
                f"(exp {target_exp.isoformat()}). "
                f"No contracts with volume > 3x open interest."
            )

        # Sort by ratio descending, take top 5
        unusual.sort(key=lambda x: x[0], reverse=True)
        top = unusual[:5]

        lines: list[str] = [
            f"Unusual activity for {ticker} (exp {target_exp.isoformat()}):",
        ]
        for ratio, c in top:
            lines.append(
                f"  {c.option_type.value.upper()} ${c.strike} "
                f"Vol={c.volume:,} OI={c.open_interest:,} "
                f"Ratio={ratio:.1f}x "
                f"Bid=${c.bid} Ask=${c.ask}"
            )

        ctx.deps.tools_used.append(tool_name)
        return "\n".join(lines)
    except Exception as exc:
        logger.debug("fetch_unusual_activity failed for %s: %s", ticker, exc)
        ctx.deps.tools_used.append(tool_name)
        return f"Error: could not detect unusual activity for {ticker}"


# ---------------------------------------------------------------------------
# Trend and Flow toolset builders
# ---------------------------------------------------------------------------


def build_trend_toolset() -> list[object]:
    """Return the tools for a Trend Desk agent.

    Tools: ``fetch_quote``, ``fetch_related_ohlcv``, ``compute_indicator_on_demand``.
    """
    return [fetch_quote, fetch_related_ohlcv, compute_indicator_on_demand]


def build_flow_toolset() -> list[object]:
    """Return the tools for a Flow Desk agent.

    Tools: ``fetch_quote``, ``fetch_chain_summary``, ``fetch_unusual_activity``.
    """
    return [fetch_quote, fetch_chain_summary, fetch_unusual_activity]

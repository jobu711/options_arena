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
import re
from datetime import date

from pydantic_ai import RunContext

from options_arena.agents._desk_deps import DeskDeps
from options_arena.models.enums import TICKER_RE, ToolStatus
from options_arena.models.options import OptionContract
from options_arena.models.tool_response import ToolResponse

logger = logging.getLogger(__name__)

# Maximum number of comparison tickers in fetch_correlation to bound resource usage.
_MAX_CORRELATION_TICKERS = 5

# Default confidence for successful desk responses.  Placeholder until
# confidence is derived from observable quality signals.
DESK_SUCCESS_CONFIDENCE = 0.7


def _sanitize_error(exc: Exception, max_len: int = 120) -> str:
    """Extract a safe, truncated error message from an exception.

    Redacts sensitive tokens (API keys, passwords) and truncates to *max_len*
    characters so agent context windows are not polluted with stack traces.
    """
    msg = str(exc)
    msg = re.sub(r"(key|token|secret|password)=\S+", r"\1=***", msg, flags=re.IGNORECASE)
    if len(msg) > max_len:
        msg = msg[:max_len] + "..."
    return msg


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
        return ToolResponse[str](
            status=ToolStatus.ERROR,
            summary=err,
            next_actions=["skip exposure analysis", "note data gap"],
        ).model_dump_json()
    try:
        contracts = await ctx.deps.repo.get_contracts_for_ticker(ticker, limit=10)
        if not contracts:
            ctx.deps.tools_used.append(tool_name)
            return ToolResponse[str](
                status=ToolStatus.WARNING,
                summary=f"No prior recommendations found for {ticker}",
                data=f"No historical recommended contracts found for {ticker}.",
                next_actions=["no prior positions to assess", "treat as fresh entry"],
            ).model_dump_json()

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
        return ToolResponse[str](
            status=ToolStatus.SUCCESS,
            summary=f"{ticker}: {len(contracts)} prior recommendations found",
            data="\n".join(lines),
            next_actions=["assess existing exposure overlap", "note concentration risk"],
        ).model_dump_json()
    except Exception as exc:
        logger.debug("fetch_portfolio_exposure failed for %s: %s", ticker, exc)
        ctx.deps.tools_used.append(tool_name)
        return ToolResponse[str](
            status=ToolStatus.ERROR,
            summary=f"Portfolio exposure unavailable for {ticker}: {_sanitize_error(exc)}",
            next_actions=["skip exposure analysis", "note data gap"],
        ).model_dump_json()


# ---------------------------------------------------------------------------
# Toolset builders
# ---------------------------------------------------------------------------


def build_volatility_toolset() -> list[object]:
    """Return the tools for a Volatility Desk agent.

    Base tools: ``fetch_quote``, ``fetch_vol_surface_slice``,
    ``compute_iv_for_strike``, ``compute_hv_yang_zhang_tool``.
    Conditional: ``compute_garch_forecast_tool`` (requires ``arch``).
    """
    tools: list[object] = [
        fetch_quote,
        fetch_vol_surface_slice,
        compute_iv_for_strike,
        compute_hv_yang_zhang_tool,
    ]
    try:
        import arch  # noqa: F401

        tools.append(compute_garch_forecast_tool)
    except ImportError:
        pass  # [ml] not installed — vol desk works without GARCH
    return tools


def build_risk_toolset() -> list[object]:
    """Return the tools for a Risk Desk agent.

    Base tools: ``fetch_quote``, ``fetch_correlation``,
    ``fetch_portfolio_exposure``, ``compute_correlation_matrix_tool``,
    ``compute_risk_adjusted_metrics_tool``, ``compute_position_size_tool``,
    ``compute_macro_regime_tool``.
    Conditional: ``compute_markov_regime_tool`` (requires ``statsmodels``).
    """
    tools: list[object] = [
        fetch_quote,
        fetch_correlation,
        fetch_portfolio_exposure,
        compute_correlation_matrix_tool,
        compute_risk_adjusted_metrics_tool,
        compute_position_size_tool,
        compute_macro_regime_tool,
    ]
    try:
        import statsmodels  # noqa: F401

        tools.append(compute_markov_regime_tool)
    except ImportError:
        pass  # [ml] not installed — risk desk works without Markov
    return tools


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
    _ALLOWED_PERIODS = {"3mo", "6mo", "1y"}
    if period not in _ALLOWED_PERIODS:
        ctx.deps.tools_used.append(tool_name)
        return (
            f"Error: unsupported period {period!r}. "
            f"Supported: {', '.join(sorted(_ALLOWED_PERIODS))}"
        )
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
        return ToolResponse[str](
            status=ToolStatus.ERROR,
            summary=err,
            next_actions=["skip indicator analysis", "rely on context indicators only"],
        ).model_dump_json()

    supported = {"rsi", "macd", "sma_alignment", "adx"}
    indicator_lower = indicator.lower().strip()
    if indicator_lower not in supported:
        ctx.deps.tools_used.append(tool_name)
        return ToolResponse[str](
            status=ToolStatus.ERROR,
            summary=(
                f"Unsupported indicator {indicator!r}. Supported: {', '.join(sorted(supported))}"
            ),
            next_actions=["skip indicator analysis", "rely on context indicators only"],
        ).model_dump_json()

    try:
        import pandas as pd

        from options_arena.indicators import adx as compute_adx
        from options_arena.indicators import macd as compute_macd
        from options_arena.indicators import rsi as compute_rsi
        from options_arena.indicators import sma_alignment as compute_sma_alignment

        ohlcv_list = await ctx.deps.market_data.fetch_ohlcv(ticker, period="1y")
        if not ohlcv_list:
            ctx.deps.tools_used.append(tool_name)
            return ToolResponse[str](
                status=ToolStatus.ERROR,
                summary=f"No OHLCV data found for {ticker}",
                next_actions=["skip indicator analysis", "rely on context indicators only"],
            ).model_dump_json()

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

        # Determine status: warning if indicator returned N/A, else success
        is_warning = "N/A" in result_str
        if is_warning:
            status = ToolStatus.WARNING
            next_actions = [
                "note insufficient data for this indicator",
                "rely on context indicators only",
            ]
        else:
            status = ToolStatus.SUCCESS
            next_actions = [
                "assess trend strength via ADX",
                "check RSI for overbought/oversold",
            ]

        ctx.deps.tools_used.append(tool_name)
        return ToolResponse[str](
            status=status,
            summary=result_str,
            data=result_str,
            next_actions=next_actions,
        ).model_dump_json()
    except Exception as exc:
        logger.debug("compute_indicator_on_demand failed for %s/%s: %s", ticker, indicator, exc)
        ctx.deps.tools_used.append(tool_name)
        return ToolResponse[str](
            status=ToolStatus.ERROR,
            summary=f"Indicator {indicator} failed for {ticker}: {_sanitize_error(exc)}",
            next_actions=["skip indicator analysis", "rely on context indicators only"],
        ).model_dump_json()


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
        return ToolResponse[str](
            status=ToolStatus.ERROR,
            summary=err,
            next_actions=["skip chain analysis", "use context IV data only", "reduce confidence"],
        ).model_dump_json()
    try:
        expirations = await ctx.deps.options_data.fetch_expirations(ticker)
        if not expirations:
            ctx.deps.tools_used.append(tool_name)
            return ToolResponse[str](
                status=ToolStatus.ERROR,
                summary=f"No option expirations found for {ticker}",
                next_actions=[
                    "skip chain analysis",
                    "use context IV data only",
                    "reduce confidence",
                ],
            ).model_dump_json()

        today = date.today()
        future_exps = [e for e in expirations if e > today]
        if not future_exps:
            ctx.deps.tools_used.append(tool_name)
            return ToolResponse[str](
                status=ToolStatus.ERROR,
                summary=f"No future expirations found for {ticker}",
                next_actions=[
                    "skip chain analysis",
                    "use context IV data only",
                    "reduce confidence",
                ],
            ).model_dump_json()

        target_exp = future_exps[0]
        contracts = await ctx.deps.options_data.fetch_chain(ticker, target_exp)
        if not contracts:
            ctx.deps.tools_used.append(tool_name)
            return ToolResponse[str](
                status=ToolStatus.ERROR,
                summary=f"No contracts found for {ticker} exp {target_exp.isoformat()}",
                next_actions=[
                    "skip chain analysis",
                    "use context IV data only",
                    "reduce confidence",
                ],
            ).model_dump_json()

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

        # Warn if some expected data is missing (e.g. zero OI on one side)
        has_missing = (call_oi == 0 and put_count > 0) or (put_oi == 0 and call_count > 0)
        if has_missing:
            status = ToolStatus.WARNING
            next_actions = [
                "assess put/call ratio with caution",
                "note incomplete chain data on one side",
            ]
        else:
            status = ToolStatus.SUCCESS
            next_actions = ["assess put/call ratio", "compare volume vs OI for flow signal"]

        ctx.deps.tools_used.append(tool_name)
        return ToolResponse[str](
            status=status,
            summary=(
                f"{ticker} chain: {call_count} calls, {put_count} puts, OI={call_oi + put_oi:,}"
            ),
            data="\n".join(lines),
            next_actions=next_actions,
        ).model_dump_json()
    except Exception as exc:
        logger.debug("fetch_chain_summary failed for %s: %s", ticker, exc)
        ctx.deps.tools_used.append(tool_name)
        return ToolResponse[str](
            status=ToolStatus.ERROR,
            summary=f"Chain summary unavailable for {ticker}: {_sanitize_error(exc)}",
            next_actions=["skip chain analysis", "use context IV data only", "reduce confidence"],
        ).model_dump_json()


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
        return ToolResponse[str](
            status=ToolStatus.ERROR,
            summary=err,
            next_actions=["skip flow analysis", "note data gap"],
        ).model_dump_json()
    try:
        expirations = await ctx.deps.options_data.fetch_expirations(ticker)
        if not expirations:
            ctx.deps.tools_used.append(tool_name)
            return ToolResponse[str](
                status=ToolStatus.ERROR,
                summary=f"No option expirations found for {ticker}",
                next_actions=["skip flow analysis", "note data gap"],
            ).model_dump_json()

        today = date.today()
        future_exps = [e for e in expirations if e > today]
        if not future_exps:
            ctx.deps.tools_used.append(tool_name)
            return ToolResponse[str](
                status=ToolStatus.ERROR,
                summary=f"No future expirations found for {ticker}",
                next_actions=["skip flow analysis", "note data gap"],
            ).model_dump_json()

        target_exp = future_exps[0]
        contracts = await ctx.deps.options_data.fetch_chain(ticker, target_exp)
        if not contracts:
            ctx.deps.tools_used.append(tool_name)
            return ToolResponse[str](
                status=ToolStatus.ERROR,
                summary=f"No contracts found for {ticker} exp {target_exp.isoformat()}",
                next_actions=["skip flow analysis", "note data gap"],
            ).model_dump_json()

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
            return ToolResponse[str](
                status=ToolStatus.WARNING,
                summary=f"No unusual activity for {ticker} (exp {target_exp.isoformat()})",
                data=(
                    f"No contracts with volume > 3x open interest for {ticker} "
                    f"(exp {target_exp.isoformat()}). Chain has {len(contracts)} contracts."
                ),
                next_actions=["note absence of unusual activity", "interpret as normal flow"],
            ).model_dump_json()

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
        return ToolResponse[str](
            status=ToolStatus.SUCCESS,
            summary=f"{ticker}: {len(top)} unusual contracts found",
            data="\n".join(lines),
            next_actions=["assess direction of unusual flow", "note large positions"],
        ).model_dump_json()
    except Exception as exc:
        logger.debug("fetch_unusual_activity failed for %s: %s", ticker, exc)
        ctx.deps.tools_used.append(tool_name)
        return ToolResponse[str](
            status=ToolStatus.ERROR,
            summary=f"Unusual activity unavailable for {ticker}: {_sanitize_error(exc)}",
            next_actions=["skip flow analysis", "note data gap"],
        ).model_dump_json()


# ---------------------------------------------------------------------------
# Tool: fetch_earnings_history (Fundamental desk)
# ---------------------------------------------------------------------------


async def fetch_earnings_history(ctx: RunContext[DeskDeps], ticker: str) -> str:
    """Fetch fundamental data and next earnings date for *ticker*.

    Returns sector, industry, market cap, dividend yield, 52-week range,
    and next earnings date.
    """
    tool_name = "fetch_earnings_history"
    if err := _validate_ticker(ticker):
        ctx.deps.tools_used.append(tool_name)
        return ToolResponse[str](
            status=ToolStatus.ERROR,
            summary=err,
            next_actions=["skip fundamental context", "reduce confidence"],
        ).model_dump_json()
    try:
        info = await ctx.deps.market_data.fetch_ticker_info(ticker)

        lines: list[str] = [f"Fundamentals for {ticker} ({info.company_name}):"]
        lines.append(f"  Sector: {info.sector}")
        lines.append(f"  Industry: {info.industry}")

        if info.market_cap is not None:
            lines.append(f"  Market Cap: ${info.market_cap:,}")
        else:
            lines.append("  Market Cap: N/A")

        if info.market_cap_tier is not None:
            lines.append(f"  Cap Tier: {info.market_cap_tier.value}")

        div_pct = info.dividend_yield * 100
        lines.append(f"  Dividend Yield: {div_pct:.2f}%")
        lines.append(f"  Current Price: ${info.current_price}")
        lines.append(f"  52W High: ${info.fifty_two_week_high}")
        lines.append(f"  52W Low: ${info.fifty_two_week_low}")

        if info.short_ratio is not None and math.isfinite(info.short_ratio):
            lines.append(f"  Short Ratio: {info.short_ratio:.2f}")
        if info.short_pct_of_float is not None and math.isfinite(info.short_pct_of_float):
            lines.append(f"  Short % of Float: {info.short_pct_of_float * 100:.1f}%")

        # Next earnings date
        try:
            earnings_date = await ctx.deps.market_data.fetch_earnings_date(ticker)
            if earnings_date is not None:
                lines.append(f"  Next Earnings: {earnings_date.isoformat()}")
            else:
                lines.append("  Next Earnings: N/A")
        except Exception:
            logger.debug("Could not fetch earnings date for %s", ticker)
            lines.append("  Next Earnings: N/A")

        ctx.deps.tools_used.append(tool_name)
        return ToolResponse[str](
            status=ToolStatus.SUCCESS,
            summary=f"{ticker} fundamentals: {info.sector}, div={div_pct:.2f}%",
            data="\n".join(lines),
            next_actions=["note upcoming earnings risk", "assess dividend impact"],
        ).model_dump_json()
    except Exception as exc:
        logger.debug("fetch_earnings_history failed for %s: %s", ticker, exc)
        ctx.deps.tools_used.append(tool_name)
        return ToolResponse[str](
            status=ToolStatus.ERROR,
            summary=f"Fundamentals unavailable for {ticker}: {_sanitize_error(exc)}",
            next_actions=["skip fundamental context", "reduce confidence"],
        ).model_dump_json()


# ---------------------------------------------------------------------------
# Tool: fetch_sector_comparison (Fundamental desk)
# ---------------------------------------------------------------------------


async def fetch_sector_comparison(ctx: RunContext[DeskDeps], ticker: str) -> str:
    """Fetch fundamental metrics for *ticker* with sector context.

    Returns the ticker's key metrics alongside its sector label for
    fundamental comparison.
    """
    tool_name = "fetch_sector_comparison"
    if err := _validate_ticker(ticker):
        ctx.deps.tools_used.append(tool_name)
        return ToolResponse[str](
            status=ToolStatus.ERROR,
            summary=err,
            next_actions=["skip sector comparison", "note data gap"],
        ).model_dump_json()
    try:
        info = await ctx.deps.market_data.fetch_ticker_info(ticker)

        lines: list[str] = [
            f"Sector comparison for {ticker} ({info.sector}):",
            f"  Company: {info.company_name}",
            f"  Industry: {info.industry}",
            f"  Current Price: ${info.current_price}",
        ]

        if info.market_cap is not None:
            lines.append(f"  Market Cap: ${info.market_cap:,}")
        else:
            lines.append("  Market Cap: N/A")

        if info.market_cap_tier is not None:
            lines.append(f"  Cap Tier: {info.market_cap_tier.value}")

        div_pct = info.dividend_yield * 100
        lines.append(f"  Dividend Yield: {div_pct:.2f}%")

        # 52-week range context
        high = float(info.fifty_two_week_high)
        low = float(info.fifty_two_week_low)
        current = float(info.current_price)
        if high > low:
            range_pct = (current - low) / (high - low) * 100
            lines.append(f"  Position in 52W Range: {range_pct:.1f}%")

        ctx.deps.tools_used.append(tool_name)
        return ToolResponse[str](
            status=ToolStatus.SUCCESS,
            summary=f"{ticker} sector: {info.sector}, price=${info.current_price}",
            data="\n".join(lines),
            next_actions=["compare vs sector peers", "assess relative valuation"],
        ).model_dump_json()
    except Exception as exc:
        logger.debug("fetch_sector_comparison failed for %s: %s", ticker, exc)
        ctx.deps.tools_used.append(tool_name)
        return ToolResponse[str](
            status=ToolStatus.ERROR,
            summary=f"Sector comparison unavailable for {ticker}: {_sanitize_error(exc)}",
            next_actions=["skip sector comparison", "note data gap"],
        ).model_dump_json()


# ---------------------------------------------------------------------------
# Tool: fetch_debate_history (Contrarian desk)
# ---------------------------------------------------------------------------


async def fetch_debate_history(
    ctx: RunContext[DeskDeps],
    ticker: str,
    limit: int = 3,
) -> str:
    """Fetch prior AI debate history for *ticker*.

    Returns direction, confidence, and summary from the most recent debates.

    Args:
        ticker: Underlying ticker symbol.
        limit: Maximum number of debates to return (default 3).
    """
    from options_arena.models import TradeThesis

    tool_name = "fetch_debate_history"
    # Clamp limit to prevent unbounded DB queries from LLM-controlled input
    limit = min(max(1, limit), 20)
    if err := _validate_ticker(ticker):
        ctx.deps.tools_used.append(tool_name)
        return ToolResponse[str](
            status=ToolStatus.ERROR,
            summary=err,
            next_actions=["skip historical context", "note data gap"],
        ).model_dump_json()
    try:
        debates = await ctx.deps.repo.get_debates_for_ticker(ticker, limit=limit)
        if not debates:
            ctx.deps.tools_used.append(tool_name)
            return ToolResponse[str](
                status=ToolStatus.WARNING,
                summary=f"No prior debate history found for {ticker}",
                data=f"No prior debates found for {ticker}.",
                next_actions=["no prior analysis to reference", "assess fresh"],
            ).model_dump_json()

        lines: list[str] = [f"Recent debate history for {ticker} ({len(debates)} debates):"]
        for debate in debates:
            date_str = debate.created_at.strftime("%Y-%m-%d %H:%M")
            fallback_label = " [FALLBACK]" if debate.is_fallback else ""

            direction = "N/A"
            confidence = "N/A"
            summary = "N/A"

            if debate.verdict_json is not None:
                try:
                    thesis = TradeThesis.model_validate_json(debate.verdict_json)
                    direction = thesis.direction
                    if math.isfinite(thesis.confidence):
                        confidence = f"{thesis.confidence:.0%}"
                    summary_text = thesis.summary or ""
                    # Truncate long summaries
                    if len(summary_text) > 120:  # noqa: PLR2004
                        summary = summary_text[:117] + "..."
                    elif summary_text:
                        summary = summary_text
                except (ValueError, TypeError):
                    logger.debug("Could not parse verdict_json for debate %d", debate.id)

            lines.append(
                f"  [{date_str}]{fallback_label} Direction: {direction} | Confidence: {confidence}"
            )
            if summary != "N/A":
                lines.append(f"    Summary: {summary}")

        ctx.deps.tools_used.append(tool_name)
        return ToolResponse[str](
            status=ToolStatus.SUCCESS,
            summary=f"{ticker}: {len(debates)} prior debates found",
            data="\n".join(lines),
            next_actions=["note prior consensus direction", "assess confidence trend"],
        ).model_dump_json()
    except Exception as exc:
        logger.debug("fetch_debate_history failed for %s: %s", ticker, exc)
        ctx.deps.tools_used.append(tool_name)
        return ToolResponse[str](
            status=ToolStatus.ERROR,
            summary=f"Debate history unavailable for {ticker}: {_sanitize_error(exc)}",
            next_actions=["skip historical context", "note data gap"],
        ).model_dump_json()


# ---------------------------------------------------------------------------
# Tool: compute_composite_valuation_tool (Analysis)
# ---------------------------------------------------------------------------


async def compute_composite_valuation_tool(
    ctx: RunContext[DeskDeps],
    ticker: str,
) -> str:
    """Run multi-methodology equity valuation for *ticker*.

    Returns a ``ToolResponse`` JSON string with fair value computed from up to
    four models (Owner Earnings DCF, Three-Stage DCF, EV/EBITDA Relative,
    Residual Income) and a composite valuation with margin of safety and signal.
    """
    tool_name = "compute_composite_valuation"
    if err := _validate_ticker(ticker):
        ctx.deps.tools_used.append(tool_name)
        return ToolResponse[str](
            status=ToolStatus.ERROR,
            summary=err,
            next_actions=["skip valuation analysis", "rely on technical signals"],
        ).model_dump_json()
    try:
        from options_arena.analysis.valuation import FDData, compute_composite_valuation

        info = await ctx.deps.market_data.fetch_ticker_info(ticker)
        current_price = float(info.current_price)

        # Fetch risk-free rate if FRED service is available
        risk_free_rate = 0.05
        if ctx.deps.fred is not None:
            try:
                risk_free_rate = await ctx.deps.fred.fetch_risk_free_rate()
            except Exception:
                logger.debug("FRED unavailable for valuation, using default rate")

        # Build FDData from available ticker_info — most fields will be None
        # since TickerInfo doesn't carry financial statement data.
        # TODO: Wire FinancialDatasetsService to populate FDData when available.
        fd = FDData()

        result = compute_composite_valuation(
            ticker=ticker,
            current_price=current_price,
            fd=fd,
            risk_free_rate=risk_free_rate,
        )

        lines: list[str] = [
            f"Composite Valuation for {ticker}:",
            f"  Current Price: ${result.current_price:.2f}",
        ]

        if result.composite_fair_value is not None:
            lines.append(f"  Fair Value: ${result.composite_fair_value:.2f}")
        else:
            lines.append(
                "  Fair Value: N/A (financial statement data not yet available "
                "— valuation requires net income, FCF, revenue, EBITDA)"
            )

        if result.composite_margin_of_safety is not None:
            lines.append(f"  Margin of Safety: {result.composite_margin_of_safety:.1%}")
        else:
            lines.append("  Margin of Safety: N/A")

        if result.valuation_signal is not None:
            lines.append(f"  Signal: {result.valuation_signal.value}")
        else:
            lines.append("  Signal: N/A")

        # Per-model results
        successful_models = 0
        for model_result in result.models:
            fv_str = (
                f"${model_result.fair_value:.2f}" if model_result.fair_value is not None else "N/A"
            )
            mos_str = (
                f"{model_result.margin_of_safety:.1%}"
                if model_result.margin_of_safety is not None
                else "N/A"
            )
            lines.append(
                f"  {model_result.methodology}: FV={fv_str} MoS={mos_str} "
                f"conf={model_result.confidence:.0%}"
            )
            if model_result.fair_value is not None:
                successful_models += 1

        # Determine status based on valuation coverage
        total_models = len(result.models)
        if successful_models == 0:
            status = ToolStatus.WARNING
            next_actions = ["assess available methods only", "note limited valuation scope"]
            summary = f"{ticker} valuation: no models produced fair value"
        elif successful_models < total_models:
            status = ToolStatus.WARNING
            next_actions = ["assess available methods only", "note limited valuation scope"]
            summary = f"{ticker} valuation: {successful_models}/{total_models} models computed"
        else:
            status = ToolStatus.SUCCESS
            next_actions = ["compare fair value to current price", "note valuation spread"]
            summary = f"{ticker} valuation: {successful_models} models computed"

        ctx.deps.tools_used.append(tool_name)
        return ToolResponse[str](
            status=status,
            summary=summary,
            data="\n".join(lines),
            next_actions=next_actions,
        ).model_dump_json()
    except Exception as exc:
        logger.debug("compute_composite_valuation failed for %s: %s", ticker, exc)
        ctx.deps.tools_used.append(tool_name)
        return ToolResponse[str](
            status=ToolStatus.ERROR,
            summary=f"Valuation failed for {ticker}: {_sanitize_error(exc)}",
            next_actions=["skip valuation analysis", "rely on technical signals"],
        ).model_dump_json()


# ---------------------------------------------------------------------------
# Tool: compute_position_size_tool (Analysis)
# ---------------------------------------------------------------------------


async def compute_position_size_tool(
    ctx: RunContext[DeskDeps],
    ticker: str,
    annualized_iv: float,
    correlation: float | None = None,
) -> str:
    """Compute volatility-regime-aware position size for *ticker*.

    Maps annualized IV to allocation tiers with linear interpolation
    and an optional correlation penalty.

    Args:
        ticker: Underlying ticker symbol (for labeling).
        annualized_iv: Annualized implied volatility as decimal (e.g. 0.25 = 25%).
        correlation: Optional correlation with portfolio for adjustment.
    """
    tool_name = "compute_position_size"
    if err := _validate_ticker(ticker):
        ctx.deps.tools_used.append(tool_name)
        return err
    try:
        from options_arena.analysis.position_sizing import compute_position_size

        # Guard non-finite inputs from LLM-controlled parameters
        if not math.isfinite(annualized_iv):
            ctx.deps.tools_used.append(tool_name)
            return f"Error: annualized_iv is not a finite number for {ticker}"
        if correlation is not None and not math.isfinite(correlation):
            correlation = None

        result = compute_position_size(
            annualized_iv=annualized_iv,
            correlation_with_portfolio=correlation,
        )

        iv_str = f"{annualized_iv:.1%}" if math.isfinite(annualized_iv) else "N/A"
        lines: list[str] = [
            f"Position Sizing for {ticker} (IV={iv_str}):",
            f"  Tier: {result.vol_regime_tier} ({result.vol_regime_label.value})",
            f"  Base Allocation: {result.base_allocation_pct:.1%}",
            f"  Correlation Adjustment: {result.correlation_adjustment:.0%}",
            f"  Final Allocation: {result.final_allocation_pct:.1%}",
            f"  Rationale: {result.rationale}",
        ]

        ctx.deps.tools_used.append(tool_name)
        return "\n".join(lines)
    except Exception as exc:
        logger.debug("compute_position_size failed for %s: %s", ticker, exc)
        ctx.deps.tools_used.append(tool_name)
        return f"Error: could not compute position size for {ticker}"


# ---------------------------------------------------------------------------
# Tool: compute_correlation_matrix_tool (Analysis)
# ---------------------------------------------------------------------------


async def compute_correlation_matrix_tool(
    ctx: RunContext[DeskDeps],
    ticker: str,
    comparison_tickers: list[str],
) -> str:
    """Compute pairwise correlation matrix between *ticker* and *comparison_tickers*.

    Uses log daily returns over the last year (Markowitz 1952).

    Args:
        ticker: Primary ticker symbol.
        comparison_tickers: List of tickers to compare against (max 5).
    """
    tool_name = "compute_correlation_matrix"
    if err := _validate_ticker(ticker):
        ctx.deps.tools_used.append(tool_name)
        return err
    try:
        import pandas as pd

        from options_arena.analysis.correlation import compute_correlation_matrix

        # Normalize, dedupe, and cap comparison tickers
        capped = list(
            dict.fromkeys(t.upper() for t in comparison_tickers if t.upper() != ticker.upper())
        )[:_MAX_CORRELATION_TICKERS]
        all_tickers = [ticker] + capped

        for t in all_tickers:
            if not TICKER_RE.match(t.upper()):
                ctx.deps.tools_used.append(tool_name)
                return f"Error: invalid ticker format: {t!r}"

        from options_arena.utils.exceptions import DataFetchError

        # Fetch OHLCV in parallel with error isolation
        async def _fetch(t: str) -> tuple[str, pd.DataFrame | None]:
            try:
                ohlcv_list = await ctx.deps.market_data.fetch_ohlcv(t, period="1y")
                if not ohlcv_list:
                    return (t, None)
                df = pd.DataFrame(
                    {"Close": [float(bar.close) for bar in ohlcv_list]},
                    index=[bar.date for bar in ohlcv_list],
                )
                return (t, df)
            except (DataFetchError, TimeoutError):
                logger.debug("Could not fetch OHLCV for %s in correlation matrix", t)
                return (t, None)

        results = await asyncio.gather(*[_fetch(t) for t in all_tickers], return_exceptions=True)
        price_data: dict[str, pd.DataFrame] = {}
        for r in results:
            if isinstance(r, BaseException):
                continue
            t, df = r
            if df is not None:
                price_data[t] = df

        if ticker not in price_data:
            ctx.deps.tools_used.append(tool_name)
            return f"Error: could not fetch price data for {ticker}"

        if len(price_data) < 2:  # noqa: PLR2004
            ctx.deps.tools_used.append(tool_name)
            return "Error: insufficient data for correlation matrix (need at least 2 tickers)"

        matrix = compute_correlation_matrix(price_data)

        lines: list[str] = ["Correlation Matrix (log returns, 1Y):"]
        if not matrix.pairs:
            lines.append("  No valid pairs with sufficient overlap.")
        else:
            for pair in matrix.pairs:
                lines.append(
                    f"  {pair.ticker_a} / {pair.ticker_b}: {pair.correlation:.3f} "
                    f"({pair.overlapping_days} overlapping days)"
                )
        if matrix.avg_correlation is not None and math.isfinite(matrix.avg_correlation):
            lines.append(f"  Average correlation: {matrix.avg_correlation:.3f}")

        ctx.deps.tools_used.append(tool_name)
        return "\n".join(lines)
    except Exception as exc:
        logger.debug("compute_correlation_matrix failed for %s: %s", ticker, exc)
        ctx.deps.tools_used.append(tool_name)
        return f"Error: could not compute correlation matrix for {ticker}"


# ---------------------------------------------------------------------------
# Tool: compute_risk_adjusted_metrics_tool (Analysis)
# ---------------------------------------------------------------------------


async def compute_risk_adjusted_metrics_tool(
    ctx: RunContext[DeskDeps],
    ticker: str,
) -> str:
    """Compute portfolio-wide risk-adjusted performance metrics.

    Queries historical outcomes from the repository and computes Sharpe,
    Sortino, max drawdown, and annualized return across ALL tickers.
    The *ticker* parameter is for API consistency — the returned metrics
    are portfolio-wide, not per-ticker.
    """
    tool_name = "compute_risk_adjusted_metrics"
    if err := _validate_ticker(ticker):
        ctx.deps.tools_used.append(tool_name)
        return err
    try:
        # Fetch risk-free rate
        risk_free_rate = 0.05
        if ctx.deps.fred is not None:
            try:
                risk_free_rate = await ctx.deps.fred.fetch_risk_free_rate()
            except Exception:
                logger.debug("FRED unavailable for risk metrics, using default rate")

        # Use the repo's built-in risk-adjusted metrics query which already
        # handles joining contracts with outcomes.
        result = await ctx.deps.repo.get_risk_adjusted_metrics(
            lookback_days=365,
            risk_free_rate=risk_free_rate,
        )

        if result.total_trades == 0:
            ctx.deps.tools_used.append(tool_name)
            return (
                f"No outcome data available for {ticker} — "
                f"run 'outcomes collect' to gather contract outcomes first"
            )

        lines: list[str] = [
            f"Risk-Adjusted Metrics (all tickers, {result.lookback_days}d lookback):",
            f"  Total Trades: {result.total_trades}",
        ]
        if result.sharpe_ratio is not None and math.isfinite(result.sharpe_ratio):
            lines.append(f"  Sharpe Ratio: {result.sharpe_ratio:.2f}")
        else:
            lines.append("  Sharpe Ratio: N/A (insufficient data)")
        if result.sortino_ratio is not None and math.isfinite(result.sortino_ratio):
            lines.append(f"  Sortino Ratio: {result.sortino_ratio:.2f}")
        else:
            lines.append("  Sortino Ratio: N/A (insufficient data)")
        if result.max_drawdown_pct is not None and math.isfinite(result.max_drawdown_pct):
            lines.append(f"  Max Drawdown: {result.max_drawdown_pct:.1f}%")
        else:
            lines.append("  Max Drawdown: N/A")
        if result.annualized_return_pct is not None and math.isfinite(
            result.annualized_return_pct
        ):
            lines.append(f"  Annualized Return: {result.annualized_return_pct:.1f}%")
        else:
            lines.append("  Annualized Return: N/A")

        ctx.deps.tools_used.append(tool_name)
        return "\n".join(lines)
    except Exception as exc:
        logger.debug("compute_risk_adjusted_metrics failed for %s: %s", ticker, exc)
        ctx.deps.tools_used.append(tool_name)
        return f"Error: could not compute risk metrics for {ticker}"


# ---------------------------------------------------------------------------
# Tool: compute_hv_yang_zhang_tool (Analysis)
# ---------------------------------------------------------------------------


async def compute_hv_yang_zhang_tool(
    ctx: RunContext[DeskDeps],
    ticker: str,
    period: int = 20,
) -> str:
    """Compute Yang-Zhang historical volatility for *ticker*.

    Yang-Zhang (2000) combines overnight, close-to-open, and
    Rogers-Satchell variance for a drift-independent HV estimate.

    Args:
        ticker: Underlying ticker symbol.
        period: Lookback window in trading days (default 20, clamped to [2, 60]).
    """
    tool_name = "compute_hv_yang_zhang"
    if err := _validate_ticker(ticker):
        ctx.deps.tools_used.append(tool_name)
        return err
    try:
        import pandas as pd

        from options_arena.indicators import compute_hv_yang_zhang

        # Clamp period to [2, 60]
        period = max(2, min(60, period))

        ohlcv_list = await ctx.deps.market_data.fetch_ohlcv(ticker, period="1y")
        if not ohlcv_list:
            ctx.deps.tools_used.append(tool_name)
            return f"No OHLCV data found for {ticker}"

        # Build 4 pandas Series with date index
        dates = [bar.date for bar in ohlcv_list]
        open_series = pd.Series([float(bar.open) for bar in ohlcv_list], index=dates)
        high_series = pd.Series([float(bar.high) for bar in ohlcv_list], index=dates)
        low_series = pd.Series([float(bar.low) for bar in ohlcv_list], index=dates)
        close_series = pd.Series([float(bar.close) for bar in ohlcv_list], index=dates)

        hv = compute_hv_yang_zhang(
            open_series, high_series, low_series, close_series, period=period
        )

        if hv is None:
            ctx.deps.tools_used.append(tool_name)
            return (
                f"Yang-Zhang HV({period}) for {ticker}: N/A "
                f"(insufficient data or non-finite result)"
            )

        # Interpret the volatility level
        if hv < 0.15:  # noqa: PLR2004
            interpretation = "low volatility"
        elif hv < 0.30:  # noqa: PLR2004
            interpretation = "moderate volatility"
        elif hv < 0.50:  # noqa: PLR2004
            interpretation = "elevated volatility"
        else:
            interpretation = "extreme volatility"

        ctx.deps.tools_used.append(tool_name)
        return f"Yang-Zhang HV({period}) for {ticker}: {hv:.1%} annualized — {interpretation}"
    except Exception as exc:
        logger.debug("compute_hv_yang_zhang failed for %s: %s", ticker, exc)
        ctx.deps.tools_used.append(tool_name)
        return f"Error: could not compute HV for {ticker}"


# ---------------------------------------------------------------------------
# Tool: compute_garch_forecast_tool (ML — requires [ml] extra)
# ---------------------------------------------------------------------------


async def compute_garch_forecast_tool(
    ctx: RunContext[DeskDeps],
    ticker: str,
) -> str:
    """Compute a GARCH(1,1) volatility forecast for *ticker*.

    Fits a GARCH(1,1) model to 1-year percentage log returns and returns
    the annualized volatility forecast.  Requires the ``arch`` and
    ``statsmodels`` optional dependencies (``[ml]`` extra).

    Args:
        ticker: Underlying ticker symbol.
    """
    tool_name = "compute_garch_forecast"
    if err := _validate_ticker(ticker):
        ctx.deps.tools_used.append(tool_name)
        return err
    try:
        import numpy as np
        import pandas as pd

        try:
            from options_arena.indicators.vol_forecast import compute_garch_forecast
        except ImportError:
            ctx.deps.tools_used.append(tool_name)
            return "GARCH unavailable: [ml] extra not installed"

        ohlcv_list = await ctx.deps.market_data.fetch_ohlcv(ticker, period="1y")
        if not ohlcv_list:
            ctx.deps.tools_used.append(tool_name)
            return f"No OHLCV data found for {ticker}"

        close_arr = np.array([float(bar.close) for bar in ohlcv_list], dtype=np.float64)

        if len(close_arr) < 2:  # noqa: PLR2004
            ctx.deps.tools_used.append(tool_name)
            return f"Insufficient OHLCV data for {ticker} (need >= 2 bars)"

        # GARCH expects percentage log returns: log(P_t / P_{t-1}) * 100
        pct_returns = np.log(close_arr[1:] / close_arr[:-1]) * 100
        returns_series = pd.Series(pct_returns, dtype=float)

        vol = compute_garch_forecast(returns_series)

        if vol is None:
            ctx.deps.tools_used.append(tool_name)
            return (
                f"GARCH(1,1) forecast for {ticker}: N/A "
                f"(insufficient data, non-stationarity, or convergence failure)"
            )

        # Interpret the volatility level
        if vol < 0.15:  # noqa: PLR2004
            interpretation = "low volatility regime"
        elif vol < 0.30:  # noqa: PLR2004
            interpretation = "moderate volatility"
        elif vol < 0.50:  # noqa: PLR2004
            interpretation = "elevated volatility"
        else:
            interpretation = "extreme volatility regime"

        ctx.deps.tools_used.append(tool_name)
        return f"GARCH(1,1) forecast for {ticker}: {vol:.1%} annualized — {interpretation}"
    except Exception as exc:
        logger.debug("compute_garch_forecast failed for %s: %s", ticker, exc)
        ctx.deps.tools_used.append(tool_name)
        return f"Error: could not compute GARCH forecast for {ticker}"


# ---------------------------------------------------------------------------
# Tool: compute_markov_regime_tool (ML — requires [ml] extra)
# ---------------------------------------------------------------------------


async def compute_markov_regime_tool(
    ctx: RunContext[DeskDeps],
    ticker: str,
) -> str:
    """Detect the current market regime for *ticker* using Markov-switching.

    Fits a Markov-switching regression model (Hamilton 1989) to 1-year
    log returns and classifies the current regime as ``low_vol``,
    ``normal``, or ``high_vol``.  Requires ``statsmodels`` (``[ml]`` extra).

    Args:
        ticker: Underlying ticker symbol.
    """
    tool_name = "compute_markov_regime"
    if err := _validate_ticker(ticker):
        ctx.deps.tools_used.append(tool_name)
        return err
    try:
        import numpy as np
        import pandas as pd

        try:
            from options_arena.indicators.regime_ml import compute_markov_regime
        except ImportError:
            ctx.deps.tools_used.append(tool_name)
            return "Markov regime unavailable: [ml] extra not installed"

        ohlcv_list = await ctx.deps.market_data.fetch_ohlcv(ticker, period="1y")
        if not ohlcv_list:
            ctx.deps.tools_used.append(tool_name)
            return f"No OHLCV data found for {ticker}"

        close_arr = np.array([float(bar.close) for bar in ohlcv_list], dtype=np.float64)

        if len(close_arr) < 2:  # noqa: PLR2004
            ctx.deps.tools_used.append(tool_name)
            return f"Insufficient OHLCV data for {ticker} (need >= 2 bars)"

        # Markov expects plain log returns (not percentage form)
        log_returns = np.log(close_arr[1:] / close_arr[:-1])
        returns_series = pd.Series(log_returns, dtype=float)

        result = compute_markov_regime(returns_series)

        if result is None:
            ctx.deps.tools_used.append(tool_name)
            return f"Markov regime for {ticker}: N/A (insufficient data or convergence failure)"

        # Format regime probabilities
        prob_str = ", ".join(f"{p:.1%}" for p in result.regime_probabilities)

        # Format transition matrix
        tm_lines: list[str] = []
        labels = ["low_vol", "normal", "high_vol"][: len(result.transition_matrix)]
        for i, row in enumerate(result.transition_matrix):
            row_str = " ".join(f"{v:.2f}" for v in row)
            label = labels[i] if i < len(labels) else f"regime_{i}"
            tm_lines.append(f"    {label}: [{row_str}]")

        lines: list[str] = [
            f"Markov regime for {ticker}: {result.regime_label} "
            f"(prob: {result.regime_probabilities[result.current_regime]:.1%})",
            f"  Regime probabilities: [{prob_str}]",
            "  Transition matrix:",
            *tm_lines,
        ]

        ctx.deps.tools_used.append(tool_name)
        return "\n".join(lines)
    except Exception as exc:
        logger.debug("compute_markov_regime failed for %s: %s", ticker, exc)
        ctx.deps.tools_used.append(tool_name)
        return f"Error: could not compute Markov regime for {ticker}"


# ---------------------------------------------------------------------------
# Tool: compute_macro_regime_tool (always available — no optional deps)
# ---------------------------------------------------------------------------


async def compute_macro_regime_tool(ctx: RunContext[DeskDeps]) -> str:
    """Classify the current macro-economic regime from FRED data.

    Uses yield spread (10Y-2Y), unemployment rate, and other FRED
    indicators to classify the macro regime as expansionary,
    contractionary, or transitional.  Ticker-independent — only
    requires FRED service access.
    """
    tool_name = "compute_macro_regime"
    try:
        from options_arena.indicators.macro import compute_macro_regime

        if ctx.deps.fred is None:
            ctx.deps.tools_used.append(tool_name)
            return "FRED service not available — cannot compute macro regime"

        macro_ctx = await ctx.deps.fred.fetch_macro_context()

        result = compute_macro_regime(
            yield_spread_10y2y=macro_ctx.yield_spread_10y2y,
            unemployment_rate=macro_ctx.unemployment_rate,
            fed_funds_rate=macro_ctx.fed_funds_rate,
            vix=macro_ctx.vix,
            cpi_yoy=macro_ctx.cpi_yoy,
            completeness_ratio=macro_ctx.completeness_ratio(),
        )

        if result is None:
            ctx.deps.tools_used.append(tool_name)
            return "Macro regime: N/A (insufficient FRED data)"

        lines: list[str] = [
            f"Macro regime: {result.regime.value} (confidence: {result.confidence:.0%})",
        ]
        if macro_ctx.yield_spread_10y2y is not None:
            lines.append(f"  Yield spread (10Y-2Y): {macro_ctx.yield_spread_10y2y:.4f}")
        if macro_ctx.unemployment_rate is not None:
            lines.append(f"  Unemployment: {macro_ctx.unemployment_rate:.1%}")
        if macro_ctx.fed_funds_rate is not None:
            lines.append(f"  Fed funds rate: {macro_ctx.fed_funds_rate:.2%}")
        if macro_ctx.vix is not None:
            lines.append(f"  VIX: {macro_ctx.vix:.1f}")

        ctx.deps.tools_used.append(tool_name)
        return "\n".join(lines)
    except Exception as exc:
        logger.debug("compute_macro_regime failed: %s", exc)
        ctx.deps.tools_used.append(tool_name)
        return "Error: could not compute macro regime"


# ---------------------------------------------------------------------------
# Tool: compute_hurst_exponent_tool (always available — no optional deps)
# ---------------------------------------------------------------------------


async def compute_hurst_exponent_tool(
    ctx: RunContext[DeskDeps],
    ticker: str,
) -> str:
    """Compute the Hurst exponent for *ticker* via rescaled range analysis.

    Classifies the series as trending (H > 0.55), mean-reverting
    (H < 0.45), or random walk (H ~ 0.5).  Requires at least 200
    daily close prices.

    Args:
        ticker: Underlying ticker symbol.
    """
    tool_name = "compute_hurst_exponent"
    if err := _validate_ticker(ticker):
        ctx.deps.tools_used.append(tool_name)
        return err
    try:
        import pandas as pd

        from options_arena.indicators.hurst import hurst_exponent

        ohlcv_list = await ctx.deps.market_data.fetch_ohlcv(ticker, period="1y")
        if not ohlcv_list:
            ctx.deps.tools_used.append(tool_name)
            return f"No OHLCV data found for {ticker}"

        dates = [bar.date for bar in ohlcv_list]
        close_series = pd.Series(
            [float(bar.close) for bar in ohlcv_list], index=dates, dtype=float
        )

        h = hurst_exponent(close_series)

        if h is None:
            ctx.deps.tools_used.append(tool_name)
            return f"Hurst exponent for {ticker}: N/A (insufficient data or unreliable fit)"

        # Interpret the Hurst exponent
        if h > 0.55:  # noqa: PLR2004
            interpretation = "trending (persistent)"
        elif h < 0.45:  # noqa: PLR2004
            interpretation = "mean-reverting (anti-persistent)"
        else:
            interpretation = "random walk"

        ctx.deps.tools_used.append(tool_name)
        return f"Hurst exponent for {ticker}: {h:.3f} — {interpretation}"
    except Exception as exc:
        logger.debug("compute_hurst_exponent failed for %s: %s", ticker, exc)
        ctx.deps.tools_used.append(tool_name)
        return f"Error: could not compute Hurst exponent for {ticker}"


# ---------------------------------------------------------------------------
# Helper: render_available_tools
# ---------------------------------------------------------------------------


def render_available_tools(toolset: list[object]) -> str:
    """Generate an ``<<<AVAILABLE_TOOLS>>>`` prompt block from *toolset*.

    Each tool is listed by its ``__name__`` attribute. Used to dynamically
    inform desk agents which tools are registered.

    Args:
        toolset: List of tool callables from a ``build_*_toolset()`` function.

    Returns:
        Formatted prompt block with tool names.
    """
    tool_names = [getattr(t, "__name__", str(t)) for t in toolset]
    lines = [
        "<<<AVAILABLE_TOOLS>>>",
        *[f"- {name}" for name in tool_names],
        "<<<END_AVAILABLE_TOOLS>>>",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Trend, Flow, Fundamental, and Contrarian toolset builders
# ---------------------------------------------------------------------------


def build_trend_toolset() -> list[object]:
    """Return the tools for a Trend Desk agent.

    Base tools: ``fetch_quote``, ``fetch_related_ohlcv``,
    ``compute_indicator_on_demand``, ``compute_hurst_exponent_tool``.
    Conditional: ``compute_markov_regime_tool`` (requires ``statsmodels``).
    """
    tools: list[object] = [
        fetch_quote,
        fetch_related_ohlcv,
        compute_indicator_on_demand,
        compute_hurst_exponent_tool,
    ]
    try:
        import statsmodels  # noqa: F401

        tools.append(compute_markov_regime_tool)
    except ImportError:
        pass  # [ml] not installed — trend desk works without Markov
    return tools


def build_flow_toolset() -> list[object]:
    """Return the tools for a Flow Desk agent.

    Tools: ``fetch_quote``, ``fetch_chain_summary``, ``fetch_unusual_activity``.
    """
    return [fetch_quote, fetch_chain_summary, fetch_unusual_activity]


def build_fundamental_toolset() -> list[object]:
    """Return the tools for a Fundamental Desk agent.

    Tools: ``fetch_quote``, ``fetch_earnings_history``, ``fetch_sector_comparison``,
    ``compute_composite_valuation_tool``, ``compute_macro_regime_tool``.
    """
    return [
        fetch_quote,
        fetch_earnings_history,
        fetch_sector_comparison,
        compute_composite_valuation_tool,
        compute_macro_regime_tool,
    ]


def build_contrarian_toolset() -> list[object]:
    """Return the tools for a Contrarian Desk agent.

    Tools: ``fetch_quote``, ``fetch_debate_history``.
    """
    return [fetch_quote, fetch_debate_history]


def build_research_toolset() -> list[object]:
    """Return the tools for a Research Desk agent.

    Base tools (11): ``fetch_quote``, ``fetch_vol_surface_slice``,
    ``fetch_chain_summary``, ``fetch_earnings_history``,
    ``compute_indicator_on_demand``, ``fetch_debate_history``,
    ``compute_composite_valuation_tool``, ``compute_position_size_tool``,
    ``compute_hv_yang_zhang_tool``, ``compute_macro_regime_tool``,
    ``compute_hurst_exponent_tool``.
    Conditional: ``compute_garch_forecast_tool`` (``arch``),
    ``compute_markov_regime_tool`` (``statsmodels``).
    """
    tools: list[object] = [
        fetch_quote,
        fetch_vol_surface_slice,
        fetch_chain_summary,
        fetch_earnings_history,
        compute_indicator_on_demand,
        fetch_debate_history,
        compute_composite_valuation_tool,
        compute_position_size_tool,
        compute_hv_yang_zhang_tool,
        compute_macro_regime_tool,
        compute_hurst_exponent_tool,
    ]
    try:
        import arch  # noqa: F401

        tools.append(compute_garch_forecast_tool)
    except ImportError:
        pass
    try:
        import statsmodels  # noqa: F401

        tools.append(compute_markov_regime_tool)
    except ImportError:
        pass
    return tools


# ---------------------------------------------------------------------------
# Synthesis toolset — lightweight lookup tools for synthesis agent
# ---------------------------------------------------------------------------

# The synthesis agent uses SynthesisDeps (not DeskDeps). These tools access
# the pre-fetched data already available in deps (MarketContext, contracts).
# RunContext is typed as object to avoid circular imports with synthesis_agent.py.


async def synth_fetch_current_quote(
    ctx: RunContext[object],
    ticker: str,
) -> str:
    """Fetch the current quote snapshot for *ticker* from the market context.

    Returns price, 52-week range, IV rank, RSI, and sector from the
    pre-fetched ``MarketContext`` in deps. Only the ticker matching the
    analysis context is available.
    """
    if err := _validate_ticker(ticker):
        return err
    try:
        context = ctx.deps.context  # type: ignore[attr-defined]
        upper = ticker.upper()
        if upper != context.ticker.upper():
            return f"Error: only {context.ticker} data is available in this session"

        lines: list[str] = [
            f"Quote for {context.ticker}:",
            f"  Price: ${context.current_price}",
            f"  52W High: ${context.price_52w_high}  52W Low: ${context.price_52w_low}",
            f"  RSI(14): {context.rsi_14:.1f}",
            f"  Sector: {context.sector}",
            f"  Dividend Yield: {context.dividend_yield * 100:.2f}%",
        ]
        if context.iv_rank is not None and math.isfinite(context.iv_rank):
            lines.append(f"  IV Rank: {context.iv_rank:.1f}")
        if context.iv_percentile is not None and math.isfinite(context.iv_percentile):
            lines.append(f"  IV Percentile: {context.iv_percentile:.1f}")
        if context.atm_iv_30d is not None and math.isfinite(context.atm_iv_30d):
            lines.append(f"  ATM IV 30D: {context.atm_iv_30d * 100:.1f}%")
        if context.put_call_ratio is not None and math.isfinite(context.put_call_ratio):
            lines.append(f"  Put/Call Ratio: {context.put_call_ratio:.2f}")

        return "\n".join(lines)
    except Exception as exc:
        logger.debug("synth_fetch_current_quote failed: %s", exc)
        return f"Error: could not fetch quote for {ticker}"


async def synth_fetch_chain_summary(
    ctx: RunContext[object],
    ticker: str,
) -> str:
    """Summarize the available option contracts for *ticker*.

    Returns total contracts, call/put breakdown, OI and volume totals,
    put/call ratios, and average bid-ask spread percentage from the
    pre-fetched contract list in deps.
    """
    if err := _validate_ticker(ticker):
        return err
    try:
        contracts: list[OptionContract] = ctx.deps.contracts  # type: ignore[attr-defined]
        if not contracts:
            return f"No contracts available for {ticker}"

        call_count = 0
        put_count = 0
        call_oi = 0
        put_oi = 0
        call_vol = 0
        put_vol = 0
        spread_pcts: list[float] = []

        for c in contracts:
            mid = float(c.mid)
            if mid > 0:
                spread_pct = float(c.spread) / mid
                if math.isfinite(spread_pct):
                    spread_pcts.append(spread_pct)

            if c.option_type.value == "call":
                call_count += 1
                call_oi += c.open_interest
                call_vol += c.volume
            else:
                put_count += 1
                put_oi += c.open_interest
                put_vol += c.volume

        pc_oi_ratio = put_oi / call_oi if call_oi > 0 else float("nan")
        pc_vol_ratio = put_vol / call_vol if call_vol > 0 else float("nan")
        avg_spread = sum(spread_pcts) / len(spread_pcts) if spread_pcts else float("nan")

        lines: list[str] = [
            f"Chain summary for {ticker} ({len(contracts)} contracts):",
            f"  Calls: {call_count}, OI={call_oi:,}, Vol={call_vol:,}",
            f"  Puts: {put_count}, OI={put_oi:,}, Vol={put_vol:,}",
            f"  Total OI: {call_oi + put_oi:,}",
            f"  Total Volume: {call_vol + put_vol:,}",
        ]
        if math.isfinite(pc_oi_ratio):
            lines.append(f"  Put/Call OI Ratio: {pc_oi_ratio:.2f}")
        else:
            lines.append("  Put/Call OI Ratio: N/A")
        if math.isfinite(pc_vol_ratio):
            lines.append(f"  Put/Call Volume Ratio: {pc_vol_ratio:.2f}")
        else:
            lines.append("  Put/Call Volume Ratio: N/A")
        if math.isfinite(avg_spread):
            lines.append(f"  Avg Bid-Ask Spread: {avg_spread * 100:.1f}%")
        else:
            lines.append("  Avg Bid-Ask Spread: N/A")

        # Show individual contract details
        for c in contracts:
            greeks_str = ""
            if c.greeks is not None:
                greeks_str = (
                    f" D={c.greeks.delta:.2f} G={c.greeks.gamma:.4f}"
                    f" T={c.greeks.theta:.4f} V={c.greeks.vega:.4f}"
                )
            iv_str = f"{c.market_iv * 100:.1f}%" if math.isfinite(c.market_iv) else "N/A"
            lines.append(
                f"  {c.option_type.value.upper()} ${c.strike} "
                f"exp {c.expiration.isoformat()} "
                f"Bid=${c.bid} Ask=${c.ask} IV={iv_str}"
                f" OI={c.open_interest:,} Vol={c.volume:,}{greeks_str}"
            )

        return "\n".join(lines)
    except Exception as exc:
        logger.debug("synth_fetch_chain_summary failed: %s", exc)
        return f"Error: could not summarize chain for {ticker}"


def build_synthesis_toolset() -> list[object]:
    """Return the tools for the Synthesis agent.

    Lightweight tools: ``synth_fetch_current_quote`` (market context summary),
    ``synth_fetch_chain_summary`` (contract list summary with Greeks).
    These operate on pre-fetched data in ``SynthesisDeps`` — no service calls.
    """
    return [synth_fetch_current_quote, synth_fetch_chain_summary]

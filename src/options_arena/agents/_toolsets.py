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
# Tool: fetch_earnings_history
# ---------------------------------------------------------------------------


async def fetch_earnings_history(ctx: RunContext[DeskDeps], ticker: str) -> str:
    """Fetch fundamental data and next earnings date for *ticker*.

    Returns sector, industry, market cap, dividend yield, 52-week range,
    and next earnings date.
    """
    tool_name = "fetch_earnings_history"
    if err := _validate_ticker(ticker):
        ctx.deps.tools_used.append(tool_name)
        return err
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
        return "\n".join(lines)
    except Exception as exc:
        logger.debug("fetch_earnings_history failed for %s: %s", ticker, exc)
        ctx.deps.tools_used.append(tool_name)
        return f"Error: could not fetch fundamentals for {ticker}"


# ---------------------------------------------------------------------------
# Tool: fetch_sector_comparison
# ---------------------------------------------------------------------------


async def fetch_sector_comparison(ctx: RunContext[DeskDeps], ticker: str) -> str:
    """Fetch fundamental metrics for *ticker* with sector context.

    Returns the ticker's key metrics alongside its sector label for
    fundamental comparison.
    """
    tool_name = "fetch_sector_comparison"
    if err := _validate_ticker(ticker):
        ctx.deps.tools_used.append(tool_name)
        return err
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
        return "\n".join(lines)
    except Exception as exc:
        logger.debug("fetch_sector_comparison failed for %s: %s", ticker, exc)
        ctx.deps.tools_used.append(tool_name)
        return f"Error: could not fetch sector comparison for {ticker}"


# ---------------------------------------------------------------------------
# Tool: fetch_debate_history
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
    import json as _json

    tool_name = "fetch_debate_history"
    if err := _validate_ticker(ticker):
        ctx.deps.tools_used.append(tool_name)
        return err
    try:
        debates = await ctx.deps.repo.get_debates_for_ticker(ticker, limit=limit)
        if not debates:
            ctx.deps.tools_used.append(tool_name)
            return f"No prior debate history found for {ticker}"

        lines: list[str] = [f"Recent debate history for {ticker} ({len(debates)} debates):"]
        for debate in debates:
            date_str = debate.created_at.strftime("%Y-%m-%d %H:%M")
            fallback_label = " [FALLBACK]" if debate.is_fallback else ""

            direction = "N/A"
            confidence = "N/A"
            summary = "N/A"

            if debate.verdict_json is not None:
                try:
                    verdict = _json.loads(debate.verdict_json)
                    direction = verdict.get("direction", "N/A")
                    raw_conf = verdict.get("confidence")
                    if raw_conf is not None and isinstance(raw_conf, (int, float)):
                        confidence = f"{float(raw_conf):.0%}"
                    summary_text = verdict.get("summary", "")
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
        return "\n".join(lines)
    except Exception as exc:
        logger.debug("fetch_debate_history failed for %s: %s", ticker, exc)
        ctx.deps.tools_used.append(tool_name)
        return f"Error: could not fetch debate history for {ticker}"


# ---------------------------------------------------------------------------
# Toolset builders (continued)
# ---------------------------------------------------------------------------


def build_fundamental_toolset() -> list[object]:
    """Return the tools for a Fundamental Desk agent.

    Tools: ``fetch_quote``, ``fetch_earnings_history``, ``fetch_sector_comparison``.
    """
    return [fetch_quote, fetch_earnings_history, fetch_sector_comparison]


def build_contrarian_toolset() -> list[object]:
    """Return the tools for a Contrarian Desk agent.

    Tools: ``fetch_quote``, ``fetch_debate_history``.
    """
    return [fetch_quote, fetch_debate_history]

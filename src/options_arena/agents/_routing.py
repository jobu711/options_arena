"""Intent classification and agency routing orchestrator.

Rule-based V1 routing: keyword matching + regex ticker extraction -> desk dispatch.
No LLM call for classification. The orchestrator dispatches to desk agents and
synthesizes responses into a single ``AgencyResponse``.

Public API:
  - ``classify_intent(query)`` -- pure function, returns ``QueryIntent``
  - ``run_agency_query(query, ...)`` -- async orchestrator, returns ``AgencyResponse``
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable
from datetime import UTC, datetime

from options_arena.agents._desk_deps import DeskDeps
from options_arena.agents.contrarian_desk import run_contrarian_desk_query
from options_arena.agents.flow_desk import run_flow_desk_query
from options_arena.agents.fundamental_desk import run_fundamental_desk_query
from options_arena.agents.research_desk import run_research_desk_query
from options_arena.agents.risk_desk import run_risk_desk_query
from options_arena.agents.trend_desk import run_trend_desk_query
from options_arena.agents.volatility_desk import run_vol_desk_query
from options_arena.data.repository import Repository
from options_arena.models import (
    AgencyConfig,
    AgencyQuery,
    AgencyResponse,
    Citation,
    DeskResponse,
    DeskType,
    QueryIntent,
    QueryType,
)
from options_arena.services.fred import FredService
from options_arena.services.market_data import MarketDataService
from options_arena.services.options_data import OptionsDataService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Keyword -> DeskType mapping (case-insensitive)
# ---------------------------------------------------------------------------

_DESK_KEYWORDS: dict[DeskType, list[str]] = {
    DeskType.VOLATILITY: [
        "volatility",
        "iv",
        "vega",
        "vol",
        "implied",
        "skew",
        "term structure",
        "vol surface",
        "implied vol",
    ],
    DeskType.RISK: [
        "risk",
        "hedge",
        "exposure",
        "portfolio",
        "position size",
        "drawdown",
        "var",
    ],
    DeskType.TREND: [
        "trend",
        "momentum",
        "moving average",
        "adx",
        "rsi",
        "sma",
        "macd",
        "ema",
    ],
    DeskType.FLOW: [
        "flow",
        "volume",
        "unusual",
        "put call ratio",
        "open interest",
        "unusual activity",
    ],
    DeskType.FUNDAMENTAL: [
        "fundamental",
        "earnings",
        "valuation",
        "p/e",
        "revenue",
        "dividend",
    ],
    DeskType.CONTRARIAN: [
        "contrarian",
        "consensus",
        "against",
        "dissent",
        "devil",
        "sentiment",
        "overcrowded",
        "reversal",
    ],
    DeskType.RESEARCH: [
        "research",
        "overview",
        "summary",
        "broad",
        "comprehensive",
        "multi",
        "cross",
    ],
}

# ---------------------------------------------------------------------------
# Query type keyword mapping
# ---------------------------------------------------------------------------

_QUERY_TYPE_KEYWORDS: dict[QueryType, list[str]] = {
    QueryType.COMPARISON: ["compare", "vs", "versus"],
    QueryType.STRATEGY: ["strategy", "recommend", "trade", "play"],
    QueryType.RISK_CHECK: ["risk", "hedge", "exposure"],
    QueryType.ANALYSIS: ["analyze", "analysis", "what"],
}

# ---------------------------------------------------------------------------
# Non-ticker common English words to exclude from ticker extraction
# ---------------------------------------------------------------------------

_NON_TICKER_WORDS: frozenset[str] = frozenset(
    {
        "I",
        "IV",
        "PE",
        "GDP",
        "CPI",
        "ATM",
        "OTM",
        "ITM",
        "DTE",
        "OI",
        "HV",
        "THE",
        "AND",
        "FOR",
        "ARE",
        "NOT",
        "BUT",
        "HAS",
        "HAD",
        "WAS",
        "ALL",
        "CAN",
        "HER",
        "ONE",
        "OUR",
        "OUT",
        "YOU",
        "HIS",
        "HOW",
        "ITS",
        "MAY",
        "NEW",
        "NOW",
        "OLD",
        "SEE",
        "WAY",
        "WHO",
        "BOY",
        "DID",
        "GET",
        "LET",
        "SAY",
        "SHE",
        "TOO",
        "USE",
        "DAD",
        "MOM",
        "RUN",
        "SET",
        "TRY",
        "ASK",
        "MEN",
        "PUT",
        "ANY",
        "BIG",
        "FEW",
        "YOY",
        "VAR",
        "EMA",
        "SMA",
        "RSI",
        "ADX",
        "ATR",
    }
)

# Regex for $TICKER extraction (case-insensitive to capture $aapl -> AAPL)
_DOLLAR_TICKER_RE = re.compile(r"\$([A-Za-z]{1,5})\b")

# Regex for standalone uppercase words (potential tickers)
_STANDALONE_TICKER_RE = re.compile(r"\b([A-Z][A-Z0-9.\-]{0,4})\b")

# Citation labels to scan for in desk responses
_CITATION_LABELS: list[str] = [
    "IV Rank",
    "IV Percentile",
    "RSI",
    "ADX",
    "MACD",
    "SMA",
    "ATR",
    "Vega",
    "Delta",
    "Gamma",
    "Theta",
    "Rho",
    "P/E",
    "Volume",
    "Open Interest",
    "Put/Call Ratio",
    "Bollinger",
    "VIX",
    "Sharpe",
    "Max Drawdown",
    "Price",
    "Strike",
    "Expiration",
    "DTE",
]


def classify_intent(query: str) -> QueryIntent:
    """Classify a natural-language query into desk routing intent.

    Rule-based V1 -- keyword matching + regex ticker extraction.
    No LLM call. Returns ``QueryIntent`` with desk(s), query type, and tickers.

    Parameters
    ----------
    query
        Natural-language user query string.

    Returns
    -------
    QueryIntent
        Classified intent with target desks, query type, and extracted tickers.
    """
    query_lower = query.lower()

    # --- Desk matching (word-boundary to prevent "vol" matching "volume") ---
    matched_desks: list[DeskType] = []
    for desk, keywords in _DESK_KEYWORDS.items():
        for kw in keywords:
            if re.search(rf"\b{re.escape(kw)}\b", query_lower):
                if desk not in matched_desks:
                    matched_desks.append(desk)
                break  # one keyword match per desk is sufficient

    # Default to VOLATILITY if no keywords match
    if not matched_desks:
        matched_desks = [DeskType.VOLATILITY]

    # --- Query type classification ---
    query_type = QueryType.GENERAL
    # Check in priority order (COMPARISON > STRATEGY > RISK_CHECK > ANALYSIS)
    for qt in (QueryType.COMPARISON, QueryType.STRATEGY, QueryType.RISK_CHECK, QueryType.ANALYSIS):
        keywords = _QUERY_TYPE_KEYWORDS[qt]
        for kw in keywords:
            if kw in query_lower:
                query_type = qt
                break
        if query_type != QueryType.GENERAL:
            break

    # --- Ticker extraction ---
    tickers: list[str] = []

    # Extract $TICKER format (uppercase to normalize $aapl -> AAPL)
    for match in _DOLLAR_TICKER_RE.finditer(query):
        ticker = match.group(1).upper()
        if ticker not in tickers:
            tickers.append(ticker)

    # Extract standalone uppercase words
    for match in _STANDALONE_TICKER_RE.finditer(query):
        word = match.group(1)
        if word not in _NON_TICKER_WORDS and word not in tickers:
            tickers.append(word)

    return QueryIntent(
        desks=matched_desks,
        query_type=query_type,
        tickers=tickers,
    )


# ---------------------------------------------------------------------------
# Desk dispatch
# ---------------------------------------------------------------------------


async def _run_vol(
    query: str,
    deps: DeskDeps,
    *,
    model: object | None,
    config: AgencyConfig,
) -> DeskResponse:
    """Delegate to run_vol_desk_query."""
    return await run_vol_desk_query(query, deps, model=model, config=config)


async def _run_risk(
    query: str,
    deps: DeskDeps,
    *,
    model: object | None,
    config: AgencyConfig,
) -> DeskResponse:
    """Delegate to run_risk_desk_query."""
    return await run_risk_desk_query(query, deps, model=model, config=config)


async def _run_trend(
    query: str,
    deps: DeskDeps,
    *,
    model: object | None,
    config: AgencyConfig,
) -> DeskResponse:
    """Delegate to run_trend_desk_query."""
    return await run_trend_desk_query(query, deps, model=model, config=config)


async def _run_flow(
    query: str,
    deps: DeskDeps,
    *,
    model: object | None,
    config: AgencyConfig,
) -> DeskResponse:
    """Delegate to run_flow_desk_query."""
    return await run_flow_desk_query(query, deps, model=model, config=config)


async def _run_fundamental(
    query: str,
    deps: DeskDeps,
    *,
    model: object | None,
    config: AgencyConfig,
) -> DeskResponse:
    """Delegate to run_fundamental_desk_query."""
    return await run_fundamental_desk_query(query, deps, model=model, config=config)


async def _run_contrarian(
    query: str,
    deps: DeskDeps,
    *,
    model: object | None,
    config: AgencyConfig,
) -> DeskResponse:
    """Delegate to run_contrarian_desk_query."""
    return await run_contrarian_desk_query(query, deps, model=model, config=config)


async def _run_research(
    query: str,
    deps: DeskDeps,
    *,
    model: object | None,
    config: AgencyConfig,
) -> DeskResponse:
    """Delegate to run_research_desk_query."""
    return await run_research_desk_query(query, deps, model=model, config=config)


async def _run_unimplemented(
    desk: DeskType,
) -> DeskResponse:
    """Return an error DeskResponse for desks not yet implemented."""
    return DeskResponse(
        desk=desk,
        response="All desks are available. Supported: volatility, risk, trend, flow, "
        "fundamental, contrarian, research.",
        tools_used=[],
        confidence=0.0,
    )


# Map implemented desks to their runners
_IMPLEMENTED_DESKS: frozenset[DeskType] = frozenset(
    {
        DeskType.VOLATILITY,
        DeskType.RISK,
        DeskType.TREND,
        DeskType.FLOW,
        DeskType.FUNDAMENTAL,
        DeskType.CONTRARIAN,
        DeskType.RESEARCH,
    }
)


def _extract_citations(
    desk_responses: list[DeskResponse],
) -> list[Citation]:
    """Extract citations from desk response text by scanning for known labels.

    Parameters
    ----------
    desk_responses
        List of desk responses to scan for citation labels.

    Returns
    -------
    list[Citation]
        Extracted citations with source, content snippet, and originating desk.
    """
    citations: list[Citation] = []
    for resp in desk_responses:
        if resp.confidence <= 0.0:
            continue
        for label in _CITATION_LABELS:
            if label.lower() in resp.response.lower():
                citations.append(
                    Citation(
                        source=label,
                        content=label,
                        desk=resp.desk,
                    )
                )
    return citations


def _synthesize_text(
    desk_responses: list[DeskResponse],
) -> str:
    """Combine desk response texts into a synthesis string.

    Parameters
    ----------
    desk_responses
        List of desk responses to synthesize.

    Returns
    -------
    str
        Combined synthesis text.
    """
    parts: list[str] = []
    for resp in desk_responses:
        parts.append(f"[{resp.desk.value.upper()}] {resp.response}")
    return "\n\n".join(parts) if parts else "No desk responses available."


def _average_confidence(desk_responses: list[DeskResponse]) -> float:
    """Compute average confidence across desk responses.

    Parameters
    ----------
    desk_responses
        List of desk responses.

    Returns
    -------
    float
        Average confidence, or 0.0 if no responses.
    """
    if not desk_responses:
        return 0.0
    total = sum(r.confidence for r in desk_responses)
    return total / len(desk_responses)


async def run_agency_query(
    query: AgencyQuery,
    *,
    market_data: MarketDataService,
    options_data: OptionsDataService,
    fred: FredService,
    repo: Repository,
    model: object | None,
    config: AgencyConfig,
    tickers_override: list[str] | None = None,
) -> AgencyResponse:
    """Route a user query to desk agent(s) and synthesize the response.

    Orchestration flow:
    1. Classify intent (or use desk_override if set).
    2. Dispatch to desk(s) via asyncio.gather with return_exceptions=True.
    3. For implemented desks (all 7): call desk runners.
    4. For unrecognized desks: return error DeskResponse(confidence=0.0).
    5. Synthesize AgencyResponse with merged citations and averaged confidence.
    6. Never raises -- catches all exceptions, returns error AgencyResponse.

    Parameters
    ----------
    query
        The agency query to process.
    market_data
        Market data service instance.
    options_data
        Options data service instance.
    fred
        FRED service instance.
    repo
        Database repository instance.
    model
        PydanticAI model for desk agents (None triggers model-not-configured errors).
    config
        Agency configuration.

    Returns
    -------
    AgencyResponse
        Synthesized response from desk agents. Never raises.
    """
    try:
        # 1. Classify intent
        intent = classify_intent(query.query_text)

        # 2. Override desk if desk_override is set
        if query.desk_override is not None:
            intent = QueryIntent(
                desks=[query.desk_override],
                query_type=intent.query_type,
                tickers=intent.tickers,
            )

        # 2b. Override tickers if explicitly provided by caller
        if tickers_override:
            intent = QueryIntent(
                desks=intent.desks,
                query_type=intent.query_type,
                tickers=tickers_override,
            )

        # 3. Build coroutines for each desk
        tickers = intent.tickers or [""]
        primary_ticker = tickers[0] if tickers else ""

        # Dispatch table: DeskType -> runner coroutine factory
        _desk_runners = {
            DeskType.VOLATILITY: _run_vol,
            DeskType.RISK: _run_risk,
            DeskType.TREND: _run_trend,
            DeskType.FLOW: _run_flow,
            DeskType.FUNDAMENTAL: _run_fundamental,
            DeskType.CONTRARIAN: _run_contrarian,
            DeskType.RESEARCH: _run_research,
        }

        awaitables: list[Awaitable[DeskResponse]] = []
        desk_order: list[DeskType] = []

        for desk in intent.desks:
            desk_order.append(desk)
            runner = _desk_runners.get(desk)
            if runner is not None:
                deps = DeskDeps(
                    query=query.query_text,
                    ticker=primary_ticker,
                    market_data=market_data,
                    options_data=options_data,
                    fred=fred,
                    repo=repo,
                )
                awaitables.append(runner(query.query_text, deps, model=model, config=config))
            else:
                awaitables.append(_run_unimplemented(desk))

        # 4. Dispatch atomically — no orphan risk from ensure_future
        results = await asyncio.gather(*awaitables, return_exceptions=True)

        # 5. Collect responses (handle exceptions from gather)
        desk_responses: list[DeskResponse] = []
        for i, result in enumerate(results):
            if isinstance(result, BaseException):
                logger.warning(
                    "Desk %s raised %s: %s",
                    desk_order[i].value,
                    type(result).__name__,
                    result,
                )
                desk_responses.append(
                    DeskResponse(
                        desk=desk_order[i],
                        response=f"Desk error: {type(result).__name__}",
                        tools_used=[],
                        confidence=0.0,
                    )
                )
            else:
                desk_responses.append(result)

        # 6. Synthesize
        citations = _extract_citations(desk_responses)
        synthesis = _synthesize_text(desk_responses)
        confidence = _average_confidence(desk_responses)

        return AgencyResponse(
            query_id=query.query_id,
            query_text=query.query_text,
            intent=intent,
            desk_responses=desk_responses,
            synthesis=synthesis,
            citations=citations,
            confidence=confidence,
            created_at=datetime.now(UTC),
        )

    except Exception as exc:
        logger.warning("run_agency_query failed: %s: %s", type(exc).__name__, exc)
        # Build a minimal error response
        error_intent = QueryIntent(
            desks=[DeskType.VOLATILITY],
            query_type=QueryType.GENERAL,
            tickers=[],
        )
        return AgencyResponse(
            query_id=query.query_id,
            query_text=query.query_text,
            intent=error_intent,
            desk_responses=[],
            synthesis=f"Error processing query: {type(exc).__name__}",
            citations=[],
            confidence=0.0,
            created_at=datetime.now(UTC),
        )

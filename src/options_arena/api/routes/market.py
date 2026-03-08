"""Market data endpoints — heatmap."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request

from options_arena.api.app import limiter
from options_arena.api.deps import get_market_data, get_repo, get_universe
from options_arena.api.schemas import HeatmapTicker
from options_arena.data import Repository
from options_arena.models.enums import MarketCapTier
from options_arena.services import MarketDataService, UniverseService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/market", tags=["market"])

# Market-cap tier → treemap weight mapping.
# Larger companies get proportionally larger tiles in the heatmap.
MARKET_CAP_WEIGHTS: dict[MarketCapTier, float] = {
    MarketCapTier.MEGA: 100.0,
    MarketCapTier.LARGE: 50.0,
    MarketCapTier.MID: 20.0,
    MarketCapTier.SMALL: 8.0,
    MarketCapTier.MICRO: 3.0,
}

_DEFAULT_WEIGHT: float = 10.0


@router.get("/heatmap")
@limiter.limit("10/minute")
async def get_heatmap(
    request: Request,
    market_data: MarketDataService = Depends(get_market_data),
    universe: UniverseService = Depends(get_universe),
    repo: Repository = Depends(get_repo),
) -> list[HeatmapTicker]:
    """Return S&P 500 heatmap data: daily changes joined with metadata.

    The endpoint is a thin join — no business logic:
    1. Fetch S&P 500 constituents (source of truth for ticker list).
    2. Fetch batch daily changes for those tickers.
    3. Fetch cached ticker metadata for enrichment.
    4. Join into ``HeatmapTicker`` response models.

    Tickers without a ``BatchQuote`` are omitted. Missing metadata
    falls back to ``sector="Unknown"``, ``company_name=ticker``, ``weight=10``.
    """
    # 1. Get S&P 500 tickers
    constituents = await universe.fetch_sp500_constituents()
    if not constituents:
        return []

    tickers = [c.ticker for c in constituents]
    constituent_map = {c.ticker: c for c in constituents}

    # 2. Fetch batch daily changes
    quotes = await market_data.fetch_batch_daily_changes(tickers)
    quote_map = {q.ticker: q for q in quotes}

    # 3. Fetch metadata for enrichment
    all_metadata = await repo.get_all_ticker_metadata()
    meta_map = {m.ticker: m for m in all_metadata}

    # 4. Join — only include tickers that have a quote
    result: list[HeatmapTicker] = []
    for ticker in tickers:
        quote = quote_map.get(ticker)
        if quote is None:
            continue

        meta = meta_map.get(ticker)
        constituent = constituent_map[ticker]

        # Determine sector: metadata > constituent > fallback
        if meta and meta.sector is not None:
            sector = meta.sector.value
        elif constituent.sector:
            sector = constituent.sector
        else:
            sector = "Unknown"

        # Determine company_name: metadata > ticker
        company_name = meta.company_name if meta and meta.company_name else ticker

        # Determine industry_group: metadata > "Unknown"
        industry_group = (
            meta.industry_group.value if meta and meta.industry_group is not None else "Unknown"
        )

        # Determine weight from market-cap tier
        weight = _DEFAULT_WEIGHT
        if meta and meta.market_cap_tier is not None:
            weight = MARKET_CAP_WEIGHTS.get(meta.market_cap_tier, _DEFAULT_WEIGHT)

        result.append(
            HeatmapTicker(
                ticker=ticker,
                company_name=company_name,
                sector=sector,
                industry_group=industry_group,
                market_cap_weight=weight,
                change_pct=quote.change_pct,
                price=quote.price,
                volume=quote.volume,
            )
        )

    return result

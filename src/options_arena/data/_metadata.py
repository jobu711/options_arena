"""MetadataMixin — ticker metadata persistence."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from sqlite3 import Row

from options_arena.models import (
    GICSIndustryGroup,
    GICSSector,
    MarketCapTier,
    MetadataCoverage,
    TickerMetadata,
)

from ._base import RepositoryBase

logger = logging.getLogger(__name__)


class MetadataMixin(RepositoryBase):
    """Ticker metadata CRUD operations."""

    async def upsert_ticker_metadata(self, metadata: TickerMetadata) -> None:
        """INSERT OR REPLACE a single ticker_metadata row.

        Enum fields are stored as their ``.value`` strings (or ``NULL`` for ``None``).
        ``last_updated`` is stored as ISO 8601 text.
        """
        conn = self._db.conn
        await conn.execute(
            "INSERT OR REPLACE INTO ticker_metadata "
            "(ticker, sector, industry_group, market_cap_tier, company_name, "
            "raw_sector, raw_industry, last_updated) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                metadata.ticker.upper(),
                metadata.sector.value if metadata.sector is not None else None,
                metadata.industry_group.value if metadata.industry_group is not None else None,
                metadata.market_cap_tier.value if metadata.market_cap_tier is not None else None,
                metadata.company_name,
                metadata.raw_sector,
                metadata.raw_industry,
                metadata.last_updated.isoformat(),
            ),
        )
        await conn.commit()
        logger.debug("Upserted ticker_metadata for %s", metadata.ticker.upper())

    async def upsert_ticker_metadata_batch(
        self, items: list[TickerMetadata], *, commit: bool = True
    ) -> None:
        """Batch upsert ticker_metadata rows via ``executemany``.

        Args:
            items: List of ``TickerMetadata`` models to persist.
            commit: Whether to commit immediately (default ``True``).
                Pass ``False`` when batching multiple saves for atomic persistence.
        """
        if not items:
            return
        conn = self._db.conn
        await conn.executemany(
            "INSERT OR REPLACE INTO ticker_metadata "
            "(ticker, sector, industry_group, market_cap_tier, company_name, "
            "raw_sector, raw_industry, last_updated) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    m.ticker.upper(),
                    m.sector.value if m.sector is not None else None,
                    m.industry_group.value if m.industry_group is not None else None,
                    m.market_cap_tier.value if m.market_cap_tier is not None else None,
                    m.company_name,
                    m.raw_sector,
                    m.raw_industry,
                    m.last_updated.isoformat(),
                )
                for m in items
            ],
        )
        if commit:
            await conn.commit()
        logger.debug("Batch-upserted %d ticker_metadata rows", len(items))

    async def get_ticker_metadata(self, ticker: str) -> TickerMetadata | None:
        """Lookup a single ``TickerMetadata`` by ticker (uppercased).

        Returns ``None`` if the ticker is not in the table.
        """
        conn = self._db.conn
        async with conn.execute(
            "SELECT * FROM ticker_metadata WHERE ticker = ?", (ticker.upper(),)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_ticker_metadata(row)

    async def get_all_ticker_metadata(self) -> list[TickerMetadata]:
        """Return all rows from ``ticker_metadata`` as a list of ``TickerMetadata``."""
        conn = self._db.conn
        async with conn.execute("SELECT * FROM ticker_metadata ORDER BY ticker ASC") as cursor:
            rows = await cursor.fetchall()
        results = [self._row_to_ticker_metadata(row) for row in rows]
        logger.debug("Retrieved %d ticker_metadata rows", len(results))
        return results

    async def get_stale_tickers(self, max_age_days: int = 30) -> list[str]:
        """Return tickers whose ``last_updated`` is older than *max_age_days*.

        Compares ``last_updated`` against ``datetime.now(UTC) - timedelta(days=max_age_days)``.
        """
        conn = self._db.conn
        cutoff = (datetime.now(UTC) - timedelta(days=max_age_days)).isoformat()
        async with conn.execute(
            "SELECT ticker FROM ticker_metadata WHERE last_updated < ? ORDER BY ticker ASC",
            (cutoff,),
        ) as cursor:
            rows = await cursor.fetchall()
        tickers = [str(row["ticker"]) for row in rows]
        logger.debug("Found %d stale tickers (max_age=%d days)", len(tickers), max_age_days)
        return tickers

    async def get_metadata_coverage(self) -> MetadataCoverage:
        """Return coverage statistics for the ``ticker_metadata`` table.

        Uses SQL ``COUNT`` for efficiency — does not load all rows into memory.
        """
        conn = self._db.conn
        async with conn.execute(
            "SELECT "
            "COUNT(*) AS total, "
            "COUNT(sector) AS with_sector, "
            "COUNT(industry_group) AS with_industry_group "
            "FROM ticker_metadata"
        ) as cursor:
            row = await cursor.fetchone()
        assert row is not None  # COUNT always returns a row
        total = int(row["total"])
        with_sector = int(row["with_sector"])
        with_industry_group = int(row["with_industry_group"])
        coverage = with_sector / total if total > 0 else 0.0
        return MetadataCoverage(
            total=total,
            with_sector=with_sector,
            with_industry_group=with_industry_group,
            coverage=coverage,
        )

    @staticmethod
    def _row_to_ticker_metadata(row: Row) -> TickerMetadata:
        """Reconstruct a ``TickerMetadata`` from an ``aiosqlite.Row``."""
        return TickerMetadata(
            ticker=str(row["ticker"]),
            sector=GICSSector(row["sector"]) if row["sector"] is not None else None,
            industry_group=(
                GICSIndustryGroup(row["industry_group"])
                if row["industry_group"] is not None
                else None
            ),
            market_cap_tier=(
                MarketCapTier(row["market_cap_tier"])
                if row["market_cap_tier"] is not None
                else None
            ),
            company_name=str(row["company_name"]) if row["company_name"] is not None else None,
            raw_sector=str(row["raw_sector"]),
            raw_industry=str(row["raw_industry"]),
            last_updated=datetime.fromisoformat(row["last_updated"]),
        )

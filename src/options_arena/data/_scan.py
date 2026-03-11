"""ScanMixin — scan and score persistence."""

from __future__ import annotations

import logging
from datetime import date, datetime
from sqlite3 import Row

from options_arena.models import (
    DimensionalScores,
    GICSIndustryGroup,
    GICSSector,
    HistoryPoint,
    IndicatorSignals,
    MarketRegime,
    ScanPreset,
    ScanRun,
    ScanSource,
    SignalDirection,
    TickerScore,
    TrendingTicker,
)

from ._base import RepositoryBase

logger = logging.getLogger(__name__)


class ScanMixin(RepositoryBase):
    """Scan run and ticker score CRUD operations."""

    async def save_scan_run(self, scan_run: ScanRun, *, commit: bool = True) -> int:
        """Persist a ScanRun.  Returns the database-assigned ID (lastrowid).

        Args:
            scan_run: The scan run to persist.
            commit: Whether to commit immediately (default ``True``).
                Pass ``False`` when batching multiple saves for atomic persistence.
        """
        conn = self._db.conn
        cursor = await conn.execute(
            "INSERT INTO scan_runs "
            "(started_at, completed_at, preset, source, "
            "tickers_scanned, tickers_scored, recommendations, filter_spec_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                scan_run.started_at.isoformat(),
                scan_run.completed_at.isoformat() if scan_run.completed_at is not None else None,
                scan_run.preset.value,
                scan_run.source.value,
                scan_run.tickers_scanned,
                scan_run.tickers_scored,
                scan_run.recommendations,
                scan_run.filter_spec_json,
            ),
        )
        if commit:
            await conn.commit()
        assert cursor.lastrowid is not None
        row_id: int = cursor.lastrowid
        logger.debug("Saved scan run id=%d", row_id)
        return row_id

    async def save_ticker_scores(
        self, scan_id: int, scores: list[TickerScore], *, commit: bool = True
    ) -> None:
        """Batch-insert TickerScores for a scan run.

        Args:
            scan_id: Database ID of the parent scan run.
            scores: List of ticker scores to persist.
            commit: Whether to commit immediately (default ``True``).
                Pass ``False`` when batching multiple saves for atomic persistence.
        """
        conn = self._db.conn
        await conn.executemany(
            "INSERT INTO ticker_scores "
            "(scan_run_id, ticker, composite_score, direction, signals_json, "
            "next_earnings, sector, company_name, "
            "dimensional_scores_json, direction_confidence, market_regime, "
            "industry_group) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    scan_id,
                    score.ticker,
                    score.composite_score,
                    score.direction.value,
                    score.signals.model_dump_json(),
                    score.next_earnings.isoformat() if score.next_earnings is not None else None,
                    score.sector.value if score.sector is not None else None,
                    score.company_name,
                    score.dimensional_scores.model_dump_json()
                    if score.dimensional_scores is not None
                    else None,
                    score.direction_confidence,
                    score.market_regime.value if score.market_regime is not None else None,
                    score.industry_group.value if score.industry_group is not None else None,
                )
                for score in scores
            ],
        )
        if commit:
            await conn.commit()
        logger.debug("Saved %d ticker scores for scan %d", len(scores), scan_id)

    async def get_latest_scan(self) -> ScanRun | None:
        """Get the most recent ScanRun, or None if no scans exist."""
        conn = self._db.conn
        async with conn.execute("SELECT * FROM scan_runs ORDER BY id DESC LIMIT 1") as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_scan_run(row)

    async def get_scan_by_id(self, scan_id: int) -> ScanRun | None:
        """Get a ScanRun by its ID, or None if not found."""
        conn = self._db.conn
        async with conn.execute("SELECT * FROM scan_runs WHERE id = ?", (scan_id,)) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_scan_run(row)

    async def get_scores_for_scan(self, scan_id: int) -> list[TickerScore]:
        """Get all TickerScores for a scan run.  Returns empty list if none."""
        conn = self._db.conn
        async with conn.execute(
            "SELECT * FROM ticker_scores WHERE scan_run_id = ? ORDER BY id ASC",
            (scan_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        scores = [self._row_to_ticker_score(row) for row in rows]
        logger.debug("Retrieved %d scores for scan %d", len(scores), scan_id)
        return scores

    async def get_recent_scans(self, limit: int = 10) -> list[ScanRun]:
        """Get the N most recent ScanRuns, newest first."""
        conn = self._db.conn
        async with conn.execute(
            "SELECT * FROM scan_runs ORDER BY id DESC LIMIT ?", (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
        return [self._row_to_scan_run(row) for row in rows]

    @staticmethod
    def _row_to_scan_run(row: Row) -> ScanRun:
        """Reconstruct a ScanRun from an aiosqlite.Row."""
        completed_at_raw: str | None = row["completed_at"]
        # sqlite3.Row ``in`` checks values, not columns — must use .keys()
        source_raw: str | None = row["source"] if "source" in row.keys() else None  # noqa: SIM118
        # filter_spec_json may not exist in legacy databases before migration 031;
        # sqlite3.Row does not support ``"col" in row`` — use ``.keys()`` instead.
        row_keys = row.keys()
        filter_spec_raw: str | None = (
            row["filter_spec_json"] if "filter_spec_json" in row_keys else None
        )  # noqa: E501
        return ScanRun(
            id=int(row["id"]),
            started_at=datetime.fromisoformat(row["started_at"]),
            completed_at=(
                datetime.fromisoformat(completed_at_raw) if completed_at_raw is not None else None
            ),
            preset=ScanPreset(row["preset"]),
            source=ScanSource(source_raw) if source_raw else ScanSource.MANUAL,
            tickers_scanned=int(row["tickers_scanned"]),
            tickers_scored=int(row["tickers_scored"]),
            recommendations=int(row["recommendations"]),
            filter_spec_json=filter_spec_raw,
        )

    @staticmethod
    def _row_to_ticker_score(row: Row) -> TickerScore:
        """Reconstruct a TickerScore from an aiosqlite.Row."""
        raw_earnings: str | None = row["next_earnings"]
        raw_sector: str | None = row["sector"]
        raw_dim_json: str | None = row["dimensional_scores_json"]
        raw_confidence: float | None = row["direction_confidence"]
        raw_regime: str | None = row["market_regime"]
        raw_industry_group: str | None = row["industry_group"]
        return TickerScore(
            ticker=str(row["ticker"]),
            composite_score=float(row["composite_score"]),
            direction=SignalDirection(row["direction"]),
            signals=IndicatorSignals.model_validate_json(row["signals_json"]),
            next_earnings=date.fromisoformat(raw_earnings) if raw_earnings is not None else None,
            sector=GICSSector(raw_sector) if raw_sector is not None else None,
            company_name=row["company_name"],
            scan_run_id=int(row["scan_run_id"]),
            dimensional_scores=(
                DimensionalScores.model_validate_json(raw_dim_json)
                if raw_dim_json is not None
                else None
            ),
            direction_confidence=(float(raw_confidence) if raw_confidence is not None else None),
            market_regime=(MarketRegime(raw_regime) if raw_regime is not None else None),
            industry_group=(
                GICSIndustryGroup(raw_industry_group) if raw_industry_group is not None else None
            ),
        )

    # ------------------------------------------------------------------
    # Score history
    # ------------------------------------------------------------------

    async def get_score_history(self, ticker: str, limit: int = 20) -> list[HistoryPoint]:
        """Get score history for a ticker across recent scans.

        Joins ``ticker_scores`` with ``scan_runs`` to produce chronological
        score data.  Returns newest first, limited to *limit* entries.
        """
        conn = self._db.conn
        async with conn.execute(
            "SELECT ts.scan_run_id, sr.started_at, ts.composite_score, "
            "ts.direction, sr.preset "
            "FROM ticker_scores ts "
            "JOIN scan_runs sr ON ts.scan_run_id = sr.id "
            "WHERE ts.ticker = ? "
            "ORDER BY sr.started_at DESC "
            "LIMIT ?",
            (ticker.upper(), limit),
        ) as cursor:
            rows = await cursor.fetchall()
        history = [
            HistoryPoint(
                scan_id=int(row["scan_run_id"]),
                scan_date=datetime.fromisoformat(row["started_at"]),
                composite_score=float(row["composite_score"]),
                direction=SignalDirection(row["direction"]),
                preset=ScanPreset(row["preset"]),
            )
            for row in rows
        ]
        logger.debug("Retrieved %d history points for ticker=%s", len(history), ticker.upper())
        return history

    async def get_trending_tickers(
        self, direction: str, min_scans: int = 3
    ) -> list[TrendingTicker]:
        """Find tickers with consistent direction over consecutive recent scans.

        1. Get all tickers from the latest scan.
        2. For each, fetch last N score entries ordered by scan date descending.
        3. Count consecutive entries matching *direction* from the most recent.
        4. Filter to those with ``consecutive_scans >= min_scans``.
        5. Sort by consecutive_scans descending.
        """
        conn = self._db.conn

        # Step 1: find latest scan
        async with conn.execute("SELECT id FROM scan_runs ORDER BY id DESC LIMIT 1") as cursor:
            latest_row = await cursor.fetchone()
        if latest_row is None:
            return []
        latest_scan_id = int(latest_row["id"])

        # Step 2: get tickers from latest scan that match the requested direction
        async with conn.execute(
            "SELECT ticker, composite_score FROM ticker_scores "
            "WHERE scan_run_id = ? AND direction = ?",
            (latest_scan_id, direction),
        ) as cursor:
            candidate_rows = await cursor.fetchall()

        if not candidate_rows:
            return []

        # Step 3: for each candidate, check consecutive scans with same direction
        trending: list[TrendingTicker] = []
        # Pre-fetch a reasonable lookback depth to avoid per-ticker queries
        lookback = min_scans + 10  # enough depth to count streaks

        for cand_row in candidate_rows:
            ticker_name = str(cand_row["ticker"])
            latest_score = float(cand_row["composite_score"])

            async with conn.execute(
                "SELECT ts.composite_score, ts.direction "
                "FROM ticker_scores ts "
                "JOIN scan_runs sr ON ts.scan_run_id = sr.id "
                "WHERE ts.ticker = ? "
                "ORDER BY sr.started_at DESC "
                "LIMIT ?",
                (ticker_name, lookback),
            ) as cursor:
                history_rows = list(await cursor.fetchall())

            # Count consecutive matching direction from the most recent
            consecutive = 0
            for h_row in history_rows:
                if str(h_row["direction"]) == direction:
                    consecutive += 1
                else:
                    break

            if consecutive < min_scans:
                continue

            # Compute score_change: latest - oldest in the streak
            oldest_score = float(history_rows[consecutive - 1]["composite_score"])
            score_change = latest_score - oldest_score

            trending.append(
                TrendingTicker(
                    ticker=ticker_name,
                    direction=SignalDirection(direction),
                    consecutive_scans=consecutive,
                    latest_score=latest_score,
                    score_change=score_change,
                )
            )

        # Sort by consecutive_scans descending
        trending.sort(key=lambda t: t.consecutive_scans, reverse=True)
        logger.debug(
            "Found %d trending tickers for direction=%s min_scans=%d",
            len(trending),
            direction,
            min_scans,
        )
        return trending

    async def get_last_debate_dates(self, tickers: list[str]) -> dict[str, datetime]:
        """Get the most recent debate date for each ticker in a single query."""
        if not tickers:
            return {}
        conn = self._db.conn
        placeholders = ", ".join("?" for _ in tickers)
        async with conn.execute(
            "SELECT ticker, MAX(created_at) as last_debate "
            "FROM ai_theses "
            f"WHERE ticker IN ({placeholders}) "
            "GROUP BY ticker",
            tuple(tickers),
        ) as cursor:
            rows = await cursor.fetchall()
        result: dict[str, datetime] = {
            str(row["ticker"]): datetime.fromisoformat(row["last_debate"]) for row in rows
        }
        logger.debug("Retrieved last debate dates for %d tickers", len(result))
        return result

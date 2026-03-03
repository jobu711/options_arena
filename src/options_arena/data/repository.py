"""Typed CRUD operations for ScanRun, TickerScore, and debate results.

Every public method accepts and returns Pydantic models or dataclasses — never raw dicts,
tuples, or Row objects.  Uses parameterized queries exclusively.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from sqlite3 import Row

from options_arena.data.database import Database
from options_arena.models import (
    ExerciseStyle,
    GICSSector,
    GreeksSource,
    HistoryPoint,
    IndicatorSignals,
    MarketContext,
    NormalizationStats,
    OptionType,
    PricingModel,
    RecommendedContract,
    ScanPreset,
    ScanRun,
    SignalDirection,
    TickerScore,
    TrendingTicker,
    Watchlist,
    WatchlistTicker,
)

logger = logging.getLogger(__name__)


@dataclass
class DebateRow:
    """Row from ai_theses table.

    Kept in repository (not models/) because it contains raw JSON strings,
    not typed models.
    """

    id: int
    scan_run_id: int | None
    ticker: str
    bull_json: str | None
    bear_json: str | None
    risk_json: str | None
    verdict_json: str | None
    vol_json: str | None
    rebuttal_json: str | None
    total_tokens: int
    model_name: str
    duration_ms: int
    is_fallback: bool
    created_at: datetime
    debate_mode: str = "full"
    citation_density: float = 0.0
    market_context: MarketContext | None = None


class Repository:
    """Typed CRUD for ScanRun and TickerScore.

    Parameters
    ----------
    db
        A connected ``Database`` instance.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    async def save_scan_run(self, scan_run: ScanRun) -> int:
        """Persist a ScanRun.  Returns the database-assigned ID (lastrowid)."""
        conn = self._db.conn
        cursor = await conn.execute(
            "INSERT INTO scan_runs "
            "(started_at, completed_at, preset, tickers_scanned, tickers_scored, recommendations) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                scan_run.started_at.isoformat(),
                scan_run.completed_at.isoformat() if scan_run.completed_at is not None else None,
                scan_run.preset.value,
                scan_run.tickers_scanned,
                scan_run.tickers_scored,
                scan_run.recommendations,
            ),
        )
        await conn.commit()
        row_id: int = cursor.lastrowid  # type: ignore[assignment]
        logger.debug("Saved scan run id=%d", row_id)
        return row_id

    async def save_ticker_scores(self, scan_id: int, scores: list[TickerScore]) -> None:
        """Batch-insert TickerScores for a scan run."""
        conn = self._db.conn
        await conn.executemany(
            "INSERT INTO ticker_scores "
            "(scan_run_id, ticker, composite_score, direction, signals_json, "
            "next_earnings, sector, company_name) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
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
                )
                for score in scores
            ],
        )
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
        return ScanRun(
            id=int(row["id"]),
            started_at=datetime.fromisoformat(row["started_at"]),
            completed_at=(
                datetime.fromisoformat(completed_at_raw) if completed_at_raw is not None else None
            ),
            preset=ScanPreset(row["preset"]),
            tickers_scanned=int(row["tickers_scanned"]),
            tickers_scored=int(row["tickers_scored"]),
            recommendations=int(row["recommendations"]),
        )

    @staticmethod
    def _row_to_ticker_score(row: Row) -> TickerScore:
        """Reconstruct a TickerScore from an aiosqlite.Row."""
        raw_earnings: str | None = row["next_earnings"]
        raw_sector: str | None = row["sector"]
        return TickerScore(
            ticker=str(row["ticker"]),
            composite_score=float(row["composite_score"]),
            direction=SignalDirection(row["direction"]),
            signals=IndicatorSignals.model_validate_json(row["signals_json"]),
            next_earnings=date.fromisoformat(raw_earnings) if raw_earnings is not None else None,
            sector=GICSSector(raw_sector) if raw_sector is not None else None,
            company_name=row["company_name"],
            scan_run_id=int(row["scan_run_id"]),
        )

    # ------------------------------------------------------------------
    # Debate persistence
    # ------------------------------------------------------------------

    async def save_debate(
        self,
        scan_run_id: int | None,
        ticker: str,
        bull_json: str | None,
        bear_json: str | None,
        risk_json: str | None,
        verdict_json: str | None,
        total_tokens: int,
        model_name: str,
        duration_ms: int,
        is_fallback: bool,
        vol_json: str | None = None,
        rebuttal_json: str | None = None,
        debate_mode: str = "full",
        citation_density: float = 0.0,
        market_context_json: str | None = None,
    ) -> int:
        """Persist a debate result.  Returns the database-assigned ID."""
        conn = self._db.conn
        created_at = datetime.now(UTC).isoformat()
        cursor = await conn.execute(
            "INSERT INTO ai_theses "
            "(scan_run_id, ticker, bull_json, bear_json, risk_json, verdict_json, "
            "vol_json, rebuttal_json, total_tokens, model_name, duration_ms, is_fallback, "
            "created_at, debate_mode, citation_density, market_context_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                scan_run_id,
                ticker,
                bull_json,
                bear_json,
                risk_json,
                verdict_json,
                vol_json,
                rebuttal_json,
                total_tokens,
                model_name,
                duration_ms,
                int(is_fallback),
                created_at,
                debate_mode,
                citation_density,
                market_context_json,
            ),
        )
        await conn.commit()
        row_id: int = cursor.lastrowid  # type: ignore[assignment]
        logger.debug("Saved debate id=%d for ticker=%s", row_id, ticker)
        return row_id

    async def get_debate_by_id(self, debate_id: int) -> DebateRow | None:
        """Get a single debate by its primary key, or None if not found."""
        conn = self._db.conn
        async with conn.execute("SELECT * FROM ai_theses WHERE id = ?", (debate_id,)) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_debate_row(row)

    async def get_recent_debates(self, limit: int = 20) -> list[DebateRow]:
        """Get the N most recent debates across all tickers, newest first."""
        conn = self._db.conn
        async with conn.execute(
            "SELECT * FROM ai_theses ORDER BY id DESC LIMIT ?", (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
        debates = [self._row_to_debate_row(row) for row in rows]
        logger.debug("Retrieved %d recent debates", len(debates))
        return debates

    async def get_debates_for_ticker(self, ticker: str, limit: int = 5) -> list[DebateRow]:
        """Get recent debates for a ticker, newest first."""
        conn = self._db.conn
        async with conn.execute(
            "SELECT * FROM ai_theses WHERE ticker = ? ORDER BY id DESC LIMIT ?",
            (ticker, limit),
        ) as cursor:
            rows = await cursor.fetchall()
        debates = [self._row_to_debate_row(row) for row in rows]
        logger.debug("Retrieved %d debates for ticker=%s", len(debates), ticker)
        return debates

    @staticmethod
    def _row_to_debate_row(row: Row) -> DebateRow:
        """Reconstruct a DebateRow from an aiosqlite.Row."""
        raw_scan_run_id = row["scan_run_id"]
        raw_market_context: str | None = row["market_context_json"]
        return DebateRow(
            id=int(row["id"]),
            scan_run_id=int(raw_scan_run_id) if raw_scan_run_id is not None else None,
            ticker=str(row["ticker"]),
            bull_json=row["bull_json"],
            bear_json=row["bear_json"],
            risk_json=row["risk_json"],
            verdict_json=row["verdict_json"],
            vol_json=row["vol_json"],
            rebuttal_json=row["rebuttal_json"],
            total_tokens=int(row["total_tokens"]),
            model_name=str(row["model_name"]),
            duration_ms=int(row["duration_ms"]),
            is_fallback=bool(row["is_fallback"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            debate_mode=str(row["debate_mode"]) if row["debate_mode"] is not None else "full",
            citation_density=(
                float(row["citation_density"]) if row["citation_density"] is not None else 0.0
            ),
            market_context=(
                MarketContext.model_validate_json(raw_market_context)
                if raw_market_context is not None
                else None
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

    # ------------------------------------------------------------------
    # Watchlist persistence
    # ------------------------------------------------------------------

    async def create_watchlist(self, name: str) -> Watchlist:
        """Create a new watchlist.  Returns the created model with DB-assigned ID.

        Raises ``sqlite3.IntegrityError`` if a watchlist with this name already exists
        (UNIQUE constraint on ``watchlists.name``).
        """
        conn = self._db.conn
        created_at = datetime.now(UTC).isoformat()
        cursor = await conn.execute(
            "INSERT INTO watchlists (name, created_at) VALUES (?, ?)",
            (name, created_at),
        )
        await conn.commit()
        row_id: int = cursor.lastrowid  # type: ignore[assignment]
        logger.debug("Created watchlist id=%d name=%s", row_id, name)
        return Watchlist(
            id=row_id,
            name=name,
            created_at=datetime.fromisoformat(created_at),
        )

    async def delete_watchlist(self, watchlist_id: int) -> None:
        """Delete a watchlist and all its ticker memberships (cascade via FK).

        Silently succeeds even if the watchlist does not exist.
        """
        conn = self._db.conn
        # Delete tickers first (foreign key may not cascade without ON DELETE CASCADE)
        await conn.execute("DELETE FROM watchlist_tickers WHERE watchlist_id = ?", (watchlist_id,))
        await conn.execute("DELETE FROM watchlists WHERE id = ?", (watchlist_id,))
        await conn.commit()
        logger.debug("Deleted watchlist id=%d", watchlist_id)

    async def add_ticker_to_watchlist(self, watchlist_id: int, ticker: str) -> None:
        """Add a ticker to a watchlist.

        Raises ``sqlite3.IntegrityError`` if the ticker is already in the watchlist
        (UNIQUE constraint on ``(watchlist_id, ticker)``).
        """
        conn = self._db.conn
        added_at = datetime.now(UTC).isoformat()
        await conn.execute(
            "INSERT INTO watchlist_tickers (watchlist_id, ticker, added_at) VALUES (?, ?, ?)",
            (watchlist_id, ticker.upper(), added_at),
        )
        await conn.commit()
        logger.debug("Added ticker %s to watchlist id=%d", ticker.upper(), watchlist_id)

    async def remove_ticker_from_watchlist(self, watchlist_id: int, ticker: str) -> None:
        """Remove a ticker from a watchlist.

        Silently succeeds even if the ticker is not in the watchlist.
        """
        conn = self._db.conn
        await conn.execute(
            "DELETE FROM watchlist_tickers WHERE watchlist_id = ? AND ticker = ?",
            (watchlist_id, ticker.upper()),
        )
        await conn.commit()
        logger.debug("Removed ticker %s from watchlist id=%d", ticker.upper(), watchlist_id)

    async def get_watchlists(self) -> list[Watchlist]:
        """Get all watchlists, ordered by name."""
        conn = self._db.conn
        async with conn.execute("SELECT * FROM watchlists ORDER BY name ASC") as cursor:
            rows = await cursor.fetchall()
        watchlists = [self._row_to_watchlist(row) for row in rows]
        logger.debug("Retrieved %d watchlists", len(watchlists))
        return watchlists

    async def get_watchlist_by_id(self, watchlist_id: int) -> Watchlist | None:
        """Get a single watchlist by ID, or None if not found."""
        conn = self._db.conn
        async with conn.execute(
            "SELECT * FROM watchlists WHERE id = ?", (watchlist_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_watchlist(row)

    async def get_watchlist_by_name(self, name: str) -> Watchlist | None:
        """Get a single watchlist by name, or None if not found."""
        conn = self._db.conn
        async with conn.execute("SELECT * FROM watchlists WHERE name = ?", (name,)) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_watchlist(row)

    async def get_tickers_for_watchlist(self, watchlist_id: int) -> list[WatchlistTicker]:
        """Get all tickers in a watchlist, ordered by ticker name."""
        conn = self._db.conn
        async with conn.execute(
            "SELECT * FROM watchlist_tickers WHERE watchlist_id = ? ORDER BY ticker ASC",
            (watchlist_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        tickers = [self._row_to_watchlist_ticker(row) for row in rows]
        logger.debug("Retrieved %d tickers for watchlist %d", len(tickers), watchlist_id)
        return tickers

    @staticmethod
    def _row_to_watchlist(row: Row) -> Watchlist:
        """Reconstruct a Watchlist from an aiosqlite.Row."""
        return Watchlist(
            id=int(row["id"]),
            name=str(row["name"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _row_to_watchlist_ticker(row: Row) -> WatchlistTicker:
        """Reconstruct a WatchlistTicker from an aiosqlite.Row."""
        return WatchlistTicker(
            id=int(row["id"]),
            watchlist_id=int(row["watchlist_id"]),
            ticker=str(row["ticker"]),
            added_at=datetime.fromisoformat(row["added_at"]),
        )

    # ------------------------------------------------------------------
    # Analytics: Contracts & Normalization
    # ------------------------------------------------------------------

    async def save_recommended_contracts(
        self,
        scan_id: int,
        contracts: list[RecommendedContract],
    ) -> None:
        """Batch-insert recommended contracts for a scan run.

        Decimal fields are stored as TEXT to preserve precision.
        Uses ``executemany()`` for efficient batch insertion.

        Args:
            scan_id: Database ID of the parent scan run.
            contracts: List of recommended contracts to persist.
        """
        if not contracts:
            return
        conn = self._db.conn
        await conn.executemany(
            "INSERT INTO recommended_contracts "
            "(scan_run_id, ticker, option_type, strike, expiration, bid, ask, last, "
            "volume, open_interest, market_iv, exercise_style, "
            "delta, gamma, theta, vega, rho, pricing_model, greeks_source, "
            "entry_stock_price, entry_mid, direction, composite_score, "
            "risk_free_rate, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    scan_id,
                    c.ticker,
                    c.option_type.value,
                    str(c.strike),
                    c.expiration.isoformat(),
                    str(c.bid),
                    str(c.ask),
                    str(c.last) if c.last is not None else None,
                    c.volume,
                    c.open_interest,
                    c.market_iv,
                    c.exercise_style.value,
                    c.delta,
                    c.gamma,
                    c.theta,
                    c.vega,
                    c.rho,
                    c.pricing_model.value if c.pricing_model is not None else None,
                    c.greeks_source.value if c.greeks_source is not None else None,
                    str(c.entry_stock_price),
                    str(c.entry_mid),
                    c.direction.value,
                    c.composite_score,
                    c.risk_free_rate,
                    c.created_at.isoformat(),
                )
                for c in contracts
            ],
        )
        await conn.commit()
        logger.debug("Saved %d recommended contracts for scan %d", len(contracts), scan_id)

    async def get_contracts_for_scan(self, scan_id: int) -> list[RecommendedContract]:
        """Get all recommended contracts for a scan run.

        Args:
            scan_id: Database ID of the scan run.

        Returns:
            List of ``RecommendedContract`` models (empty if none found).
        """
        conn = self._db.conn
        async with conn.execute(
            "SELECT * FROM recommended_contracts WHERE scan_run_id = ? ORDER BY id ASC",
            (scan_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        contracts = [self._row_to_recommended_contract(row) for row in rows]
        logger.debug("Retrieved %d contracts for scan %d", len(contracts), scan_id)
        return contracts

    async def get_contracts_for_ticker(
        self, ticker: str, limit: int = 50
    ) -> list[RecommendedContract]:
        """Get recent recommended contracts for a ticker.

        Returns most recent contracts first, limited to *limit* entries.

        Args:
            ticker: Ticker symbol (case-sensitive as stored).
            limit: Maximum number of contracts to return.

        Returns:
            List of ``RecommendedContract`` models (empty if none found).
        """
        conn = self._db.conn
        async with conn.execute(
            "SELECT * FROM recommended_contracts WHERE ticker = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (ticker, limit),
        ) as cursor:
            rows = await cursor.fetchall()
        contracts = [self._row_to_recommended_contract(row) for row in rows]
        logger.debug("Retrieved %d contracts for ticker=%s", len(contracts), ticker)
        return contracts

    async def save_normalization_stats(
        self,
        scan_id: int,
        stats: list[NormalizationStats],
    ) -> None:
        """Batch-insert normalization stats for a scan run.

        Uses ``executemany()`` for efficient batch insertion.

        Args:
            scan_id: Database ID of the parent scan run.
            stats: List of normalization stats to persist.
        """
        if not stats:
            return
        conn = self._db.conn
        await conn.executemany(
            "INSERT INTO normalization_metadata "
            "(scan_run_id, indicator_name, ticker_count, "
            "min_value, max_value, median_value, mean_value, std_dev, "
            "p25, p75, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    scan_id,
                    s.indicator_name,
                    s.ticker_count,
                    s.min_value,
                    s.max_value,
                    s.median_value,
                    s.mean_value,
                    s.std_dev,
                    s.p25,
                    s.p75,
                    s.created_at.isoformat(),
                )
                for s in stats
            ],
        )
        await conn.commit()
        logger.debug("Saved %d normalization stats for scan %d", len(stats), scan_id)

    async def get_normalization_stats(self, scan_id: int) -> list[NormalizationStats]:
        """Get normalization stats for a scan run.

        Args:
            scan_id: Database ID of the scan run.

        Returns:
            List of ``NormalizationStats`` models (empty if none found).
        """
        conn = self._db.conn
        async with conn.execute(
            "SELECT * FROM normalization_metadata WHERE scan_run_id = ? ORDER BY id ASC",
            (scan_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        stats = [self._row_to_normalization_stats(row) for row in rows]
        logger.debug("Retrieved %d normalization stats for scan %d", len(stats), scan_id)
        return stats

    @staticmethod
    def _row_to_recommended_contract(row: Row) -> RecommendedContract:
        """Reconstruct a RecommendedContract from an aiosqlite.Row.

        Decimal fields are stored as TEXT and reconstructed via ``Decimal()``.
        Enum fields are reconstructed via their constructor.
        Optional fields (Greeks, pricing_model, greeks_source, last) handle NULL.
        """
        raw_last: str | None = row["last"]
        raw_pricing_model: str | None = row["pricing_model"]
        raw_greeks_source: str | None = row["greeks_source"]
        return RecommendedContract(
            id=int(row["id"]),
            scan_run_id=int(row["scan_run_id"]),
            ticker=str(row["ticker"]),
            option_type=OptionType(row["option_type"]),
            strike=Decimal(row["strike"]),
            expiration=date.fromisoformat(row["expiration"]),
            bid=Decimal(row["bid"]),
            ask=Decimal(row["ask"]),
            last=Decimal(raw_last) if raw_last is not None else None,
            volume=int(row["volume"]),
            open_interest=int(row["open_interest"]),
            market_iv=float(row["market_iv"]),
            exercise_style=ExerciseStyle(row["exercise_style"]),
            delta=float(row["delta"]) if row["delta"] is not None else None,
            gamma=float(row["gamma"]) if row["gamma"] is not None else None,
            theta=float(row["theta"]) if row["theta"] is not None else None,
            vega=float(row["vega"]) if row["vega"] is not None else None,
            rho=float(row["rho"]) if row["rho"] is not None else None,
            pricing_model=(
                PricingModel(raw_pricing_model) if raw_pricing_model is not None else None
            ),
            greeks_source=(
                GreeksSource(raw_greeks_source) if raw_greeks_source is not None else None
            ),
            entry_stock_price=Decimal(row["entry_stock_price"]),
            entry_mid=Decimal(row["entry_mid"]),
            direction=SignalDirection(row["direction"]),
            composite_score=float(row["composite_score"]),
            risk_free_rate=float(row["risk_free_rate"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _row_to_normalization_stats(row: Row) -> NormalizationStats:
        """Reconstruct a NormalizationStats from an aiosqlite.Row.

        Optional float stats handle NULL values from the database.
        """
        return NormalizationStats(
            id=int(row["id"]),
            scan_run_id=int(row["scan_run_id"]),
            indicator_name=str(row["indicator_name"]),
            ticker_count=int(row["ticker_count"]),
            min_value=(float(row["min_value"]) if row["min_value"] is not None else None),
            max_value=(float(row["max_value"]) if row["max_value"] is not None else None),
            median_value=(float(row["median_value"]) if row["median_value"] is not None else None),
            mean_value=(float(row["mean_value"]) if row["mean_value"] is not None else None),
            std_dev=(float(row["std_dev"]) if row["std_dev"] is not None else None),
            p25=float(row["p25"]) if row["p25"] is not None else None,
            p75=float(row["p75"]) if row["p75"] is not None else None,
            created_at=datetime.fromisoformat(row["created_at"]),
        )

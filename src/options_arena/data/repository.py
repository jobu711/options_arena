"""Typed CRUD operations for ScanRun, TickerScore, and debate results.

Every public method accepts and returns Pydantic models or dataclasses — never raw dicts,
tuples, or Row objects.  Uses parameterized queries exclusively.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from sqlite3 import Row

from options_arena.data.database import Database
from options_arena.models import (
    DebateTrendPoint,
    ExerciseStyle,
    IndicatorSignals,
    OptionContract,
    OptionGreeks,
    OptionType,
    PricingModel,
    ScanDiffResult,
    ScanPreset,
    ScanRun,
    ScoreChange,
    SignalDirection,
    TickerScore,
    TradeThesis,
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
            "(scan_run_id, ticker, composite_score, direction, signals_json) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (
                    scan_id,
                    score.ticker,
                    score.composite_score,
                    score.direction.value,
                    score.signals.model_dump_json(),
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
        return TickerScore(
            ticker=str(row["ticker"]),
            composite_score=float(row["composite_score"]),
            direction=SignalDirection(row["direction"]),
            signals=IndicatorSignals.model_validate_json(row["signals_json"]),
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
    ) -> int:
        """Persist a debate result.  Returns the database-assigned ID."""
        conn = self._db.conn
        created_at = datetime.now(UTC).isoformat()
        cursor = await conn.execute(
            "INSERT INTO ai_theses "
            "(scan_run_id, ticker, bull_json, bear_json, risk_json, verdict_json, "
            "vol_json, rebuttal_json, total_tokens, model_name, duration_ms, is_fallback, "
            "created_at, debate_mode, citation_density) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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

    async def get_debate_trend_for_ticker(
        self, ticker: str, limit: int = 20
    ) -> list[DebateTrendPoint]:
        """Get debate confidence trend for a ticker, chronological (oldest first).

        Parses ``verdict_json`` from each ``ai_theses`` row to extract direction and
        confidence.  Rows with ``NULL`` or unparseable ``verdict_json`` are silently
        skipped (with a warning log).

        Parameters
        ----------
        ticker
            Uppercase ticker symbol.
        limit
            Maximum number of trend points to return.

        Returns
        -------
        list[DebateTrendPoint]
            Chronologically ordered (ASC by created_at).
        """
        conn = self._db.conn
        async with conn.execute(
            "SELECT id, ticker, verdict_json, is_fallback, created_at "
            "FROM ai_theses WHERE ticker = ? ORDER BY created_at ASC LIMIT ?",
            (ticker, limit),
        ) as cursor:
            rows = await cursor.fetchall()

        points: list[DebateTrendPoint] = []
        for row in rows:
            verdict_json: str | None = row["verdict_json"]
            if verdict_json is None:
                logger.warning("Skipping debate id=%d for trend: verdict_json is NULL", row["id"])
                continue
            try:
                thesis = TradeThesis.model_validate_json(verdict_json)
            except Exception:
                logger.warning(
                    "Skipping debate id=%d for trend: invalid verdict_json",
                    row["id"],
                    exc_info=True,
                )
                continue

            points.append(
                DebateTrendPoint(
                    ticker=str(row["ticker"]),
                    direction=thesis.direction,
                    confidence=thesis.confidence,
                    is_fallback=bool(row["is_fallback"]),
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
            )

        logger.debug("Retrieved %d trend points for ticker=%s", len(points), ticker)
        return points

    @staticmethod
    def _row_to_debate_row(row: Row) -> DebateRow:
        """Reconstruct a DebateRow from an aiosqlite.Row."""
        raw_scan_run_id = row["scan_run_id"]
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
        )

    # ------------------------------------------------------------------
    # Recommended contracts persistence
    # ------------------------------------------------------------------

    async def save_recommended_contracts(
        self,
        scan_id: int,
        ticker: str,
        contracts: list[OptionContract],
    ) -> None:
        """Batch-insert recommended OptionContracts for a ticker in a scan run.

        Parameters
        ----------
        scan_id
            The database-assigned scan run ID.
        ticker
            Uppercase ticker symbol.
        contracts
            List of recommended OptionContract instances to persist.
        """
        conn = self._db.conn
        created_at = datetime.now(UTC).isoformat()
        await conn.executemany(
            "INSERT INTO recommended_contracts "
            "(scan_run_id, ticker, option_type, strike, expiration, bid, ask, "
            "volume, open_interest, implied_volatility, delta, gamma, theta, vega, "
            "score, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    scan_id,
                    ticker,
                    contract.option_type.value,
                    str(contract.strike),
                    contract.expiration.isoformat(),
                    str(contract.bid),
                    str(contract.ask),
                    contract.volume,
                    contract.open_interest,
                    contract.market_iv,
                    contract.greeks.delta if contract.greeks else None,
                    contract.greeks.gamma if contract.greeks else None,
                    contract.greeks.theta if contract.greeks else None,
                    contract.greeks.vega if contract.greeks else None,
                    None,  # score — not used yet
                    created_at,
                )
                for contract in contracts
            ],
        )
        await conn.commit()
        logger.debug(
            "Saved %d recommended contracts for ticker=%s scan=%d",
            len(contracts),
            ticker,
            scan_id,
        )

    async def get_recommended_contracts(
        self,
        scan_id: int,
        ticker: str,
    ) -> list[OptionContract]:
        """Get recommended contracts for a specific ticker in a scan.

        Parameters
        ----------
        scan_id
            The scan run ID to query.
        ticker
            Uppercase ticker symbol.

        Returns
        -------
        list[OptionContract]
            Reconstructed contracts ordered by insertion order (id ASC).
            Empty list if no recommendations exist.
        """
        conn = self._db.conn
        async with conn.execute(
            "SELECT * FROM recommended_contracts "
            "WHERE scan_run_id = ? AND ticker = ? ORDER BY id ASC",
            (scan_id, ticker),
        ) as cursor:
            rows = await cursor.fetchall()
        contracts = [self._row_to_option_contract(row) for row in rows]
        logger.debug(
            "Retrieved %d contracts for ticker=%s scan=%d",
            len(contracts),
            ticker,
            scan_id,
        )
        return contracts

    async def get_all_recommendations_for_scan(
        self,
        scan_id: int,
    ) -> dict[str, list[OptionContract]]:
        """Get all recommended contracts for a scan, grouped by ticker.

        Parameters
        ----------
        scan_id
            The scan run ID to query.

        Returns
        -------
        dict[str, list[OptionContract]]
            Ticker -> contracts mapping. Empty dict if no recommendations exist.
        """
        conn = self._db.conn
        async with conn.execute(
            "SELECT * FROM recommended_contracts WHERE scan_run_id = ? ORDER BY id ASC",
            (scan_id,),
        ) as cursor:
            rows = await cursor.fetchall()

        result: dict[str, list[OptionContract]] = defaultdict(list)
        for row in rows:
            contract = self._row_to_option_contract(row)
            result[str(row["ticker"])].append(contract)

        logger.debug(
            "Retrieved recommendations for %d tickers in scan %d",
            len(result),
            scan_id,
        )
        return dict(result)

    @staticmethod
    def _row_to_option_contract(row: Row) -> OptionContract:
        """Reconstruct an OptionContract from a recommended_contracts row."""
        greeks: OptionGreeks | None = None
        if row["delta"] is not None:
            greeks = OptionGreeks(
                delta=float(row["delta"]),
                gamma=float(row["gamma"]),
                theta=float(row["theta"]),
                vega=float(row["vega"]),
                rho=0.0,  # rho not stored in recommended_contracts table
                pricing_model=PricingModel.BAW,
            )

        bid_raw = row["bid"]
        ask_raw = row["ask"]
        return OptionContract(
            ticker=str(row["ticker"]),
            option_type=OptionType(row["option_type"]),
            strike=Decimal(row["strike"]),
            expiration=date.fromisoformat(row["expiration"]),
            bid=Decimal(bid_raw) if bid_raw is not None else Decimal("0"),
            ask=Decimal(ask_raw) if ask_raw is not None else Decimal("0"),
            last=Decimal("0"),  # not stored — zero placeholder
            volume=int(row["volume"]) if row["volume"] is not None else 0,
            open_interest=int(row["open_interest"]) if row["open_interest"] is not None else 0,
            exercise_style=ExerciseStyle.AMERICAN,
            market_iv=float(row["implied_volatility"]) if row["implied_volatility"] else 0.0,
            greeks=greeks,
        )

    # ------------------------------------------------------------------
    # Scan diff
    # ------------------------------------------------------------------

    async def get_scan_diff(
        self,
        old_scan_id: int,
        new_scan_id: int,
    ) -> ScanDiffResult:
        """Compute a diff between two scan runs based on ticker scores.

        Uses a UNION ALL query pattern to work around SQLite's lack of
        FULL OUTER JOIN.

        Parameters
        ----------
        old_scan_id
            The earlier scan run ID.
        new_scan_id
            The later scan run ID.

        Returns
        -------
        ScanDiffResult
            Contains score changes, new entries, and removed entries.
        """
        conn = self._db.conn

        # Query tickers from both scans using LEFT JOIN + UNION ALL
        # First part: all tickers in old scan (with or without match in new)
        # Second part: tickers only in new scan (no match in old)
        async with conn.execute(
            "SELECT o.ticker, o.composite_score AS old_score, "
            "o.direction AS old_direction, "
            "n.composite_score AS new_score, n.direction AS new_direction "
            "FROM ticker_scores o "
            "LEFT JOIN ticker_scores n ON o.ticker = n.ticker AND n.scan_run_id = ? "
            "WHERE o.scan_run_id = ? "
            "UNION ALL "
            "SELECT n.ticker, NULL, NULL, n.composite_score, n.direction "
            "FROM ticker_scores n "
            "LEFT JOIN ticker_scores o ON n.ticker = o.ticker AND o.scan_run_id = ? "
            "WHERE n.scan_run_id = ? AND o.ticker IS NULL",
            (new_scan_id, old_scan_id, old_scan_id, new_scan_id),
        ) as cursor:
            rows = await cursor.fetchall()

        changes: list[ScoreChange] = []
        new_entries: list[str] = []
        removed_entries: list[str] = []

        for row in rows:
            ticker = str(row["ticker"])
            old_score_raw = row["old_score"]
            new_score_raw = row["new_score"]

            if old_score_raw is None:
                # Ticker only in new scan
                new_entries.append(ticker)
            elif new_score_raw is None:
                # Ticker only in old scan
                removed_entries.append(ticker)
            else:
                # Ticker in both scans
                old_score = float(old_score_raw)
                new_score = float(new_score_raw)
                old_direction = SignalDirection(row["old_direction"])
                new_direction = SignalDirection(row["new_direction"])
                changes.append(
                    ScoreChange(
                        ticker=ticker,
                        old_score=old_score,
                        new_score=new_score,
                        old_direction=old_direction,
                        new_direction=new_direction,
                        direction_changed=old_direction != new_direction,
                        score_delta=new_score - old_score,
                    )
                )

        logger.debug(
            "Scan diff %d->%d: %d changes, %d new, %d removed",
            old_scan_id,
            new_scan_id,
            len(changes),
            len(new_entries),
            len(removed_entries),
        )

        return ScanDiffResult(
            old_scan_id=old_scan_id,
            new_scan_id=new_scan_id,
            changes=changes,
            new_entries=new_entries,
            removed_entries=removed_entries,
            created_at=datetime.now(UTC),
        )

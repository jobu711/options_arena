"""Typed CRUD operations for ScanRun, TickerScore, and debate results.

Every public method accepts and returns Pydantic models or dataclasses — never raw dicts,
tuples, or Row objects.  Uses parameterized queries exclusively.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from sqlite3 import Row

from options_arena.data.database import Database
from options_arena.models import (
    IndicatorSignals,
    ScanPreset,
    ScanRun,
    SignalDirection,
    TickerScore,
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
    total_tokens: int
    model_name: str
    duration_ms: int
    is_fallback: bool
    created_at: datetime


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
    ) -> int:
        """Persist a debate result.  Returns the database-assigned ID."""
        conn = self._db.conn
        created_at = datetime.now(UTC).isoformat()
        cursor = await conn.execute(
            "INSERT INTO ai_theses "
            "(scan_run_id, ticker, bull_json, bear_json, risk_json, verdict_json, "
            "total_tokens, model_name, duration_ms, is_fallback, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                scan_run_id,
                ticker,
                bull_json,
                bear_json,
                risk_json,
                verdict_json,
                total_tokens,
                model_name,
                duration_ms,
                int(is_fallback),
                created_at,
            ),
        )
        await conn.commit()
        row_id: int = cursor.lastrowid  # type: ignore[assignment]
        logger.debug("Saved debate id=%d for ticker=%s", row_id, ticker)
        return row_id

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
        return DebateRow(
            id=int(row["id"]),
            scan_run_id=int(raw_scan_run_id) if raw_scan_run_id is not None else None,
            ticker=str(row["ticker"]),
            bull_json=row["bull_json"],
            bear_json=row["bear_json"],
            risk_json=row["risk_json"],
            verdict_json=row["verdict_json"],
            total_tokens=int(row["total_tokens"]),
            model_name=str(row["model_name"]),
            duration_ms=int(row["duration_ms"]),
            is_fallback=bool(row["is_fallback"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

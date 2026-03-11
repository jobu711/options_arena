"""DebateMixin — debate persistence and agent calibration queries."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from sqlite3 import Row

from options_arena.models import (
    AgentAccuracyReport,
    AgentCalibrationData,
    AgentPrediction,
    AgentWeightsComparison,
    CalibrationBucket,
    ContrarianThesis,
    FlowThesis,
    FundamentalThesis,
    MarketContext,
    RiskAssessment,
    WeightSnapshot,
)

from ._base import RepositoryBase

logger = logging.getLogger(__name__)


@dataclass
class DebateRow:
    """Row from ai_theses table.

    Kept in the data layer (not models/) because it contains raw JSON strings,
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
    flow_json: str | None = None
    fundamental_json: str | None = None
    risk_assessment_json: str | None = None
    contrarian_json: str | None = None


class DebateMixin(RepositoryBase):
    """Debate persistence and agent calibration CRUD operations."""

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
        flow_thesis: FlowThesis | None = None,
        fundamental_thesis: FundamentalThesis | None = None,
        risk_assessment: RiskAssessment | None = None,
        contrarian_thesis: ContrarianThesis | None = None,
    ) -> int:
        """Persist a debate result.  Returns the database-assigned ID."""
        conn = self._db.conn
        created_at = datetime.now(UTC).isoformat()

        # Serialize agent models to JSON strings
        flow_json = flow_thesis.model_dump_json() if flow_thesis else None
        fundamental_json = fundamental_thesis.model_dump_json() if fundamental_thesis else None
        risk_assessment_json = risk_assessment.model_dump_json() if risk_assessment else None
        contrarian_json = contrarian_thesis.model_dump_json() if contrarian_thesis else None

        cursor = await conn.execute(
            "INSERT INTO ai_theses "
            "(scan_run_id, ticker, bull_json, bear_json, risk_json, verdict_json, "
            "vol_json, rebuttal_json, total_tokens, model_name, duration_ms, is_fallback, "
            "created_at, debate_mode, citation_density, market_context_json, "
            "flow_json, fundamental_json, risk_assessment_json, contrarian_json, "
            "debate_protocol) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                flow_json,
                fundamental_json,
                risk_assessment_json,
                contrarian_json,
                "current",
            ),
        )
        await conn.commit()
        assert cursor.lastrowid is not None
        row_id: int = cursor.lastrowid
        logger.debug("Saved debate id=%d for ticker=%s", row_id, ticker)
        return row_id

    async def save_agent_predictions(self, predictions: list[AgentPrediction]) -> None:
        """Persist per-agent predictions for accuracy tracking.

        Uses ``INSERT OR IGNORE`` with ``UNIQUE(debate_id, agent_name)`` for idempotency.
        Skips empty prediction lists without touching the database.
        """
        if not predictions:
            return
        conn = self._db.conn
        await conn.executemany(
            "INSERT OR IGNORE INTO agent_predictions "
            "(debate_id, agent_name, recommended_contract_id, direction, confidence, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    p.debate_id,
                    p.agent_name,
                    p.recommended_contract_id,
                    p.direction.value if p.direction is not None else None,
                    p.confidence,
                    p.created_at.isoformat(),
                )
                for p in predictions
            ],
        )
        await conn.commit()
        logger.debug(
            "Saved %d agent predictions for debate_id=%d",
            len(predictions),
            predictions[0].debate_id,
        )

    async def get_recommended_contract_id(
        self,
        scan_run_id: int | None,
        ticker: str,
    ) -> int | None:
        """Look up the recommended_contracts.id for a scan_run + ticker pair.

        Returns the most recently inserted contract ID, or ``None`` if no match
        (e.g. standalone debates without a prior scan run).
        """
        if scan_run_id is None:
            return None
        conn = self._db.conn
        async with conn.execute(
            "SELECT id FROM recommended_contracts "
            "WHERE scan_run_id = ? AND ticker = ? "
            "ORDER BY id DESC LIMIT 1",
            (scan_run_id, ticker),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return int(row[0])

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
            flow_json=row["flow_json"],
            fundamental_json=row["fundamental_json"],
            risk_assessment_json=row["risk_assessment_json"],
            contrarian_json=row["contrarian_json"],
        )

    # ------------------------------------------------------------------
    # Agent calibration queries
    # ------------------------------------------------------------------

    async def get_agent_accuracy(
        self,
        window_days: int | None = None,
    ) -> list[AgentAccuracyReport]:
        """Per-agent direction accuracy and Brier scores.

        JOINs ``agent_predictions`` with ``contract_outcomes`` via
        ``recommended_contract_id`` at T+10 (``holding_days=10``).
        Agents with fewer than 10 matched outcomes are excluded.
        """
        conn = self._db.conn
        where_clauses = [
            "co.holding_days = 10",
            "ap.direction IN ('bullish', 'bearish')",
            "ap.recommended_contract_id IS NOT NULL",
        ]
        params: list[object] = []
        if window_days is not None:
            where_clauses.append("ap.created_at >= datetime('now', ?)")
            params.append(f"-{window_days} days")

        where_sql = " AND ".join(where_clauses)

        sql = (
            "SELECT "
            "ap.agent_name, "
            "AVG(CASE "
            "  WHEN ap.direction = 'bullish' AND co.stock_return_pct > 0 "
            "  THEN 1.0 "
            "  WHEN ap.direction = 'bearish' AND co.stock_return_pct < 0 "
            "  THEN 1.0 "
            "  ELSE 0.0 "
            "END) AS direction_hit_rate, "
            "AVG(ap.confidence) AS mean_confidence, "
            "AVG( "
            "  (ap.confidence - CASE "
            "    WHEN ap.direction = 'bullish' "
            "      AND co.stock_return_pct > 0 THEN 1.0 "
            "    WHEN ap.direction = 'bearish' "
            "      AND co.stock_return_pct < 0 THEN 1.0 "
            "    ELSE 0.0 "
            "  END) * (ap.confidence - CASE "
            "    WHEN ap.direction = 'bullish' "
            "      AND co.stock_return_pct > 0 THEN 1.0 "
            "    WHEN ap.direction = 'bearish' "
            "      AND co.stock_return_pct < 0 THEN 1.0 "
            "    ELSE 0.0 "
            "  END) "
            ") AS brier_score, "
            "COUNT(*) AS sample_size "
            "FROM agent_predictions ap "
            "JOIN contract_outcomes co "
            "  ON ap.recommended_contract_id = co.recommended_contract_id "
            f"WHERE {where_sql} "
            "GROUP BY ap.agent_name "
            "HAVING COUNT(*) >= 10"
        )

        async with conn.execute(sql, params) as cursor:
            rows = await cursor.fetchall()

        results = [
            AgentAccuracyReport(
                agent_name=str(row["agent_name"]),
                direction_hit_rate=float(row["direction_hit_rate"]),
                mean_confidence=float(row["mean_confidence"]),
                brier_score=float(row["brier_score"]),
                sample_size=int(row["sample_size"]),
            )
            for row in rows
        ]
        logger.debug("Retrieved accuracy for %d agents", len(results))
        return results

    async def get_agent_calibration(
        self,
        agent_name: str | None = None,
    ) -> AgentCalibrationData:
        """Confidence calibration buckets.

        Bins predictions into 5 confidence buckets and computes
        mean confidence vs actual hit rate in each.
        """
        conn = self._db.conn

        bucket_defs = [
            ("0.0-0.2", 0.0, 0.2),
            ("0.2-0.4", 0.2, 0.4),
            ("0.4-0.6", 0.4, 0.6),
            ("0.6-0.8", 0.6, 0.8),
            ("0.8-1.0", 0.8, 1.01),  # inclusive upper for last bucket
        ]

        where_clauses = [
            "co.holding_days = 10",
            "ap.direction IS NOT NULL",
            "ap.recommended_contract_id IS NOT NULL",
        ]
        params: list[object] = []
        if agent_name is not None:
            where_clauses.append("ap.agent_name = ?")
            params.append(agent_name)

        where_sql = " AND ".join(where_clauses)

        sql = (
            "SELECT "
            "ap.confidence, "
            "CASE "
            "  WHEN ap.direction = 'bullish' AND co.stock_return_pct > 0 "
            "  THEN 1.0 "
            "  WHEN ap.direction = 'bearish' AND co.stock_return_pct < 0 "
            "  THEN 1.0 "
            "  ELSE 0.0 "
            "END AS direction_correct "
            "FROM agent_predictions ap "
            "JOIN contract_outcomes co "
            "  ON ap.recommended_contract_id = co.recommended_contract_id "
            f"WHERE {where_sql}"
        )

        async with conn.execute(sql, params) as cursor:
            rows = await cursor.fetchall()

        # Bin rows into buckets in Python for clarity
        buckets: list[CalibrationBucket] = []
        total_count = 0
        for label, low, high in bucket_defs:
            bucket_rows = [r for r in rows if low <= float(r["confidence"]) < high]
            count = len(bucket_rows)
            total_count += count
            if count > 0:
                mean_conf = sum(float(r["confidence"]) for r in bucket_rows) / count
                hit_rate = sum(float(r["direction_correct"]) for r in bucket_rows) / count
            else:
                mean_conf = (low + high) / 2
                hit_rate = 0.0
            buckets.append(
                CalibrationBucket(
                    bucket_label=label,
                    bucket_low=low,
                    bucket_high=min(high, 1.0),
                    mean_confidence=mean_conf,
                    actual_hit_rate=hit_rate,
                    count=count,
                )
            )

        logger.debug(
            "Built calibration data for agent=%s (%d total rows)",
            agent_name or "ALL",
            total_count,
        )
        return AgentCalibrationData(
            agent_name=agent_name,
            buckets=buckets,
            sample_size=total_count,
        )

    async def get_latest_auto_tune_weights(
        self,
    ) -> list[AgentWeightsComparison]:
        """Retrieve the most recently saved auto-tune weight set."""
        conn = self._db.conn

        async with conn.execute(
            "SELECT MAX(created_at) AS latest FROM auto_tune_weights"
        ) as cursor:
            row = await cursor.fetchone()

        if row is None or row["latest"] is None:
            return []

        latest_ts = row["latest"]

        async with conn.execute(
            "SELECT agent_name, manual_weight, auto_weight, "
            "brier_score, sample_size "
            "FROM auto_tune_weights "
            "WHERE created_at = ? "
            "ORDER BY agent_name",
            (latest_ts,),
        ) as cursor:
            rows = await cursor.fetchall()

        results = [
            AgentWeightsComparison(
                agent_name=str(r["agent_name"]),
                manual_weight=float(r["manual_weight"]),
                auto_weight=float(r["auto_weight"]),
                brier_score=(float(r["brier_score"]) if r["brier_score"] is not None else None),
                sample_size=int(r["sample_size"]),
            )
            for r in rows
        ]
        logger.debug("Retrieved %d auto-tune weights (latest set)", len(results))
        return results

    async def save_auto_tune_weights(
        self,
        weights: list[AgentWeightsComparison],
        window_days: int,
    ) -> None:
        """Persist a computed set of auto-tune weights."""
        if not weights:
            return
        conn = self._db.conn
        now_iso = datetime.now(UTC).isoformat()
        await conn.executemany(
            "INSERT INTO auto_tune_weights "
            "(agent_name, manual_weight, auto_weight, brier_score, "
            "sample_size, window_days, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    w.agent_name,
                    w.manual_weight,
                    w.auto_weight,
                    w.brier_score,
                    w.sample_size,
                    window_days,
                    now_iso,
                )
                for w in weights
            ],
        )
        await conn.commit()
        logger.debug(
            "Saved %d auto-tune weights (window=%d days)",
            len(weights),
            window_days,
        )

    async def get_weight_history(self, limit: int = 20) -> list[WeightSnapshot]:
        """Retrieve historical auto-tune weight snapshots, newest first.

        Groups ``auto_tune_weights`` rows by ``created_at`` timestamp.
        Each unique timestamp becomes a single ``WeightSnapshot`` containing
        all agent weights saved at that time.

        Args:
            limit: Maximum number of snapshots to return (default 20).

        Returns:
            List of ``WeightSnapshot`` objects ordered by ``computed_at``
            descending.  Returns an empty list when no auto-tune weights exist.
        """
        conn = self._db.conn

        # Single query: fetch all rows for the N most recent timestamps
        sql = (
            "SELECT agent_name, manual_weight, auto_weight, "
            "brier_score, sample_size, window_days, created_at "
            "FROM auto_tune_weights "
            "WHERE created_at IN ("
            "  SELECT DISTINCT created_at FROM auto_tune_weights "
            "  ORDER BY created_at DESC LIMIT ?"
            ") "
            "ORDER BY created_at DESC, agent_name"
        )
        async with conn.execute(sql, (limit,)) as cursor:
            rows = await cursor.fetchall()

        if not rows:
            return []

        # Group rows by created_at timestamp (Python-side)
        from itertools import groupby

        snapshots: list[WeightSnapshot] = []
        for ts_str, group in groupby(rows, key=lambda r: r["created_at"]):
            group_rows = list(group)
            weights = [
                AgentWeightsComparison(
                    agent_name=str(r["agent_name"]),
                    manual_weight=float(r["manual_weight"]),
                    auto_weight=float(r["auto_weight"]),
                    brier_score=(
                        float(r["brier_score"]) if r["brier_score"] is not None else None
                    ),
                    sample_size=int(r["sample_size"]),
                )
                for r in group_rows
            ]
            snapshots.append(
                WeightSnapshot(
                    computed_at=datetime.fromisoformat(ts_str),
                    window_days=int(group_rows[0]["window_days"]),
                    weights=weights,
                )
            )

        logger.debug("Retrieved %d weight snapshots", len(snapshots))
        return snapshots

"""RecommendationMixin — recommendation result persistence for Repository.

Provides save/get/list operations for ``RecommendationResult`` from the unified
agent system.  ``RecommendationRow`` is a plain dataclass holding raw DB values;
consumers deserialize JSON fields on demand.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from sqlite3 import Row

from options_arena.models import RecommendationResult

from ._base import RepositoryBase

logger = logging.getLogger(__name__)


@dataclass
class RecommendationRow:
    """Raw row from ``recommendation_results`` table.

    Kept in the data layer (not ``models/``) because it contains raw JSON
    strings, not typed models — mirrors the ``DebateRow`` pattern.
    """

    id: int
    ticker: str
    scan_run_id: int | None
    direction: str
    confidence: float
    recommended_contract: str
    entry_price: str  # Decimal as string
    entry_criteria: str
    exit_criteria: str
    stop_loss: str | None
    take_profit: str | None
    position_size_pct: float
    risk_reward_ratio: float
    recommended_strategy: str | None
    summary: str
    key_factors_json: str
    risk_assessment: str
    agent_agreement_score: float | None
    dissenting_desks_json: str
    assessments_json: str
    total_input_tokens: int
    total_output_tokens: int
    duration_ms: int
    is_fallback: bool
    citation_density: float
    position_rationale: str
    strategy_rationale: str
    max_loss_estimate: str
    model_used: str
    created_at: str


class RecommendationMixin(RepositoryBase):
    """Recommendation result CRUD operations.

    Methods
    -------
    save_recommendation
        Persist a ``RecommendationResult``. Returns the DB row ID.
    get_recommendation_by_id
        Retrieve a single recommendation by ID.
    get_recent_recommendations
        Retrieve most recent recommendations, newest first.
    get_recommendations_for_ticker
        Retrieve recommendations for a specific ticker, newest first.
    """

    async def save_recommendation(
        self,
        result: RecommendationResult,
        scan_run_id: int | None = None,
        *,
        commit: bool = True,
    ) -> int:
        """Persist a ``RecommendationResult``.  Returns the database-assigned ID."""
        conn = self._db.conn
        rec = result.recommendation
        created_at = datetime.now(UTC).isoformat()

        # Serialize complex fields to JSON — mode="json" produces JSON-safe types
        # natively (StrEnum → str, Decimal → str via field_serializer) without
        # the fragile default=str fallback.
        assessment_dicts = [a.model_dump(mode="json") for a in result.assessments]
        assessments_json = json.dumps(assessment_dicts)
        key_factors_json = json.dumps(rec.key_factors)
        dissenting_desks_json = json.dumps([d.value for d in rec.dissenting_desks])

        cursor = await conn.execute(
            "INSERT INTO recommendation_results "
            "(ticker, scan_run_id, direction, confidence, recommended_contract, "
            "entry_price, entry_criteria, exit_criteria, stop_loss, take_profit, "
            "position_size_pct, risk_reward_ratio, recommended_strategy, summary, "
            "key_factors_json, risk_assessment, agent_agreement_score, "
            "dissenting_desks_json, assessments_json, total_input_tokens, "
            "total_output_tokens, duration_ms, is_fallback, citation_density, "
            "position_rationale, strategy_rationale, max_loss_estimate, "
            "model_used, created_at) "
            "VALUES ("
            "?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
            "?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                rec.ticker,
                scan_run_id,
                rec.direction.value,
                rec.confidence,
                rec.recommended_contract,
                str(rec.entry_price),
                rec.entry_criteria,
                rec.exit_criteria,
                str(rec.stop_loss) if rec.stop_loss is not None else None,
                str(rec.take_profit) if rec.take_profit is not None else None,
                rec.position_size_pct,
                rec.risk_reward_ratio,
                rec.recommended_strategy.value if rec.recommended_strategy is not None else None,
                rec.summary,
                key_factors_json,
                rec.risk_assessment,
                rec.agent_agreement_score,
                dissenting_desks_json,
                assessments_json,
                result.total_usage.input_tokens,
                result.total_usage.output_tokens,
                result.duration_ms,
                int(result.is_fallback),
                result.citation_density,
                rec.position_rationale,
                rec.strategy_rationale,
                rec.max_loss_estimate,
                rec.model_used,
                created_at,
            ),
        )
        if commit:
            await conn.commit()
        if cursor.lastrowid is None:
            raise RuntimeError("INSERT into recommendation_results returned no lastrowid")
        row_id: int = cursor.lastrowid
        logger.debug("Saved recommendation id=%d for ticker=%s", row_id, rec.ticker)
        return row_id

    async def get_recommendation_by_id(self, rec_id: int) -> RecommendationRow | None:
        """Retrieve a single recommendation by ID, or ``None`` if not found."""
        conn = self._db.conn
        async with conn.execute(
            "SELECT * FROM recommendation_results WHERE id = ?", (rec_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_recommendation_row(row)

    async def get_recent_recommendations(self, limit: int = 20) -> list[RecommendationRow]:
        """Retrieve the *limit* most recent recommendations, newest first."""
        conn = self._db.conn
        async with conn.execute(
            "SELECT * FROM recommendation_results ORDER BY id DESC LIMIT ?",
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
        results = [self._row_to_recommendation_row(r) for r in rows]
        logger.debug("Retrieved %d recent recommendations", len(results))
        return results

    async def get_recommendations_for_ticker(
        self,
        ticker: str,
        limit: int = 5,
    ) -> list[RecommendationRow]:
        """Retrieve recommendations for a specific ticker, newest first."""
        conn = self._db.conn
        async with conn.execute(
            "SELECT * FROM recommendation_results WHERE ticker = ? ORDER BY id DESC LIMIT ?",
            (ticker, limit),
        ) as cursor:
            rows = await cursor.fetchall()
        results = [self._row_to_recommendation_row(r) for r in rows]
        logger.debug("Retrieved %d recommendations for ticker=%s", len(results), ticker)
        return results

    @staticmethod
    def _row_to_recommendation_row(row: Row) -> RecommendationRow:
        """Reconstruct a ``RecommendationRow`` from an ``aiosqlite.Row``."""
        raw_scan_run_id = row["scan_run_id"]
        raw_agreement = row["agent_agreement_score"]
        return RecommendationRow(
            id=int(row["id"]),
            ticker=str(row["ticker"]),
            scan_run_id=int(raw_scan_run_id) if raw_scan_run_id is not None else None,
            direction=str(row["direction"]),
            confidence=float(row["confidence"]),
            recommended_contract=str(row["recommended_contract"]),
            entry_price=str(row["entry_price"]),
            entry_criteria=str(row["entry_criteria"]),
            exit_criteria=str(row["exit_criteria"]),
            stop_loss=str(row["stop_loss"]) if row["stop_loss"] is not None else None,
            take_profit=str(row["take_profit"]) if row["take_profit"] is not None else None,
            position_size_pct=float(row["position_size_pct"]),
            risk_reward_ratio=float(row["risk_reward_ratio"]),
            recommended_strategy=(
                str(row["recommended_strategy"])
                if row["recommended_strategy"] is not None
                else None
            ),
            summary=str(row["summary"]),
            key_factors_json=str(row["key_factors_json"]),
            risk_assessment=str(row["risk_assessment"]),
            agent_agreement_score=float(raw_agreement) if raw_agreement is not None else None,
            dissenting_desks_json=str(row["dissenting_desks_json"]),
            assessments_json=str(row["assessments_json"]),
            total_input_tokens=int(row["total_input_tokens"]),
            total_output_tokens=int(row["total_output_tokens"]),
            duration_ms=int(row["duration_ms"]),
            is_fallback=bool(row["is_fallback"]),
            citation_density=float(row["citation_density"]),
            position_rationale=str(row["position_rationale"]),
            strategy_rationale=str(row["strategy_rationale"]),
            max_loss_estimate=str(row["max_loss_estimate"]),
            model_used=str(row["model_used"]),
            created_at=str(row["created_at"]),
        )

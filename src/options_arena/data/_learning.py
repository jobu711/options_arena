"""LearningMixin — strategy rule and prediction persistence for Repository.

Provides CRUD operations for strategy rules (mined patterns with human approval)
and predictions (intermediate directional decisions for attribution scoring).
All methods return typed Pydantic models from ``models/strategy.py`` and
``models/attribution.py``.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import UTC, datetime, timedelta
from sqlite3 import Row

from options_arena.models.attribution import (
    Prediction,
    PredictionAccuracy,
    PredictionSource,
)
from options_arena.models.enums import RuleStatus, SignalDirection
from options_arena.models.strategy import StrategyCondition, StrategyRule

from ._base import RepositoryBase

# Minimum scored predictions for a source to be considered statistically reliable.
_MIN_PREDICTION_SAMPLES: int = 10

logger = logging.getLogger(__name__)

_MIN_SAMPLE_SIZE = 10
"""Minimum scored predictions before ``sample_sufficient`` is ``True``."""


class LearningMixin(RepositoryBase):
    """CRUD operations for strategy rules and predictions.

    Methods
    -------
    save_strategy_rule
        Persist (upsert) a strategy rule.
    get_strategy_rules
        Retrieve strategy rules, optionally filtered by status.
    update_rule_status
        Transition a rule's status (candidate -> approved/rejected).
    update_rule_confidence
        Update confidence, last_validated, and validation_count for a rule.
    update_rule_status_and_confidence
        Atomically update both status and confidence for a rule.
    save_prediction
        Persist a single prediction.
    save_predictions_batch
        Persist multiple predictions in a single transaction.
    score_predictions
        Score all predictions for a recommendation_id.
    score_scan_predictions
        Score predictions for a scan_run_id + ticker.
    get_predictions
        Retrieve predictions within a time window, optionally by source.
    get_prediction_accuracy
        Compute per-source accuracy statistics over a time window.
    """

    async def save_strategy_rule(
        self,
        rule: StrategyRule,
        *,
        commit: bool = True,
    ) -> None:
        """Persist a strategy rule (upsert by rule_id).

        Parameters
        ----------
        rule
            The ``StrategyRule`` to save.
        commit
            Whether to commit immediately (default ``True``).
        """
        conn = self._db.conn
        conditions_json = json.dumps(
            [c.model_dump() for c in rule.conditions],
        )

        await conn.execute(
            "INSERT OR REPLACE INTO strategy_rules "
            "(rule_id, pattern, conditions_json, win_rate, avg_return, "
            "sample_size, status, created_at, confidence, last_validated, "
            "validation_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                rule.rule_id,
                rule.pattern,
                conditions_json,
                rule.win_rate,
                rule.avg_return,
                rule.sample_size,
                rule.status.value,
                rule.created_at.isoformat(),
                rule.confidence,
                rule.last_validated.isoformat() if rule.last_validated else None,
                rule.validation_count,
            ),
        )
        if commit:
            await conn.commit()
        logger.debug("Saved strategy rule %s", rule.rule_id)

    async def get_strategy_rules(
        self,
        status: RuleStatus | None = None,
        limit: int | None = None,
    ) -> list[StrategyRule]:
        """Retrieve strategy rules, optionally filtered by status.

        Parameters
        ----------
        status
            If provided, only return rules with this status.
        limit
            Maximum number of rules to return.  ``None`` returns all rows.

        Returns
        -------
        list[StrategyRule]
            Rules ordered by ``created_at`` DESC.
        """
        conn = self._db.conn
        params: tuple[str | int, ...] = ()

        if status is not None and limit is not None:
            query = (
                "SELECT * FROM strategy_rules WHERE status = ? ORDER BY created_at DESC LIMIT ?"
            )
            params = (status.value, limit)
        elif status is not None:
            query = "SELECT * FROM strategy_rules WHERE status = ? ORDER BY created_at DESC"
            params = (status.value,)
        elif limit is not None:
            query = "SELECT * FROM strategy_rules ORDER BY created_at DESC LIMIT ?"
            params = (limit,)
        else:
            query = "SELECT * FROM strategy_rules ORDER BY created_at DESC"

        async with conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()

        return [self._row_to_strategy_rule(row) for row in rows]

    async def update_rule_status(
        self,
        rule_id: str,
        status: RuleStatus,
        *,
        commit: bool = True,
    ) -> bool:
        """Update the status of a strategy rule.

        Parameters
        ----------
        rule_id
            The unique identifier of the rule.
        status
            The new status to set.
        commit
            Whether to commit immediately (default ``True``).

        Returns
        -------
        bool
            ``True`` if a row was updated, ``False`` if ``rule_id`` not found.
        """
        conn = self._db.conn
        cursor = await conn.execute(
            "UPDATE strategy_rules SET status = ? WHERE rule_id = ?",
            (status.value, rule_id),
        )
        if commit:
            await conn.commit()
        updated = cursor.rowcount > 0
        if updated:
            logger.debug("Updated rule %s status to %s", rule_id, status.value)
        return updated

    async def update_rule_confidence(
        self,
        rule_id: str,
        confidence: float,
        last_validated: datetime | None,
        validation_count: int,
        *,
        commit: bool = True,
    ) -> bool:
        """Update confidence, last_validated, and validation_count for a rule.

        Parameters
        ----------
        rule_id
            The unique identifier of the rule.
        confidence
            The new confidence value (0.0 to 1.0).
        last_validated
            When the rule was last validated (UTC datetime or ``None``).
        validation_count
            The cumulative number of validations.
        commit
            Whether to commit immediately (default ``True``).

        Returns
        -------
        bool
            ``True`` if a row was updated, ``False`` if ``rule_id`` not found.
        """
        if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
            raise ValueError(f"confidence must be finite in [0.0, 1.0], got {confidence}")
        conn = self._db.conn
        cursor = await conn.execute(
            "UPDATE strategy_rules "
            "SET confidence = ?, last_validated = ?, validation_count = ? "
            "WHERE rule_id = ?",
            (
                confidence,
                last_validated.isoformat() if last_validated else None,
                validation_count,
                rule_id,
            ),
        )
        if commit:
            await conn.commit()
        updated = cursor.rowcount > 0
        if updated:
            logger.debug(
                "Updated rule %s confidence to %.3f (validation_count=%d)",
                rule_id,
                confidence,
                validation_count,
            )
        return updated

    async def update_rule_status_and_confidence(
        self,
        rule_id: str,
        status: RuleStatus,
        confidence: float,
        *,
        commit: bool = True,
    ) -> bool:
        """Atomically update both status and confidence for a rule.

        Parameters
        ----------
        rule_id
            The unique identifier of the rule.
        status
            The new status to set.
        confidence
            The new confidence value (0.0 to 1.0).
        commit
            Whether to commit immediately (default ``True``).

        Returns
        -------
        bool
            ``True`` if a row was updated, ``False`` if ``rule_id`` not found.
        """
        if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
            raise ValueError(f"confidence must be finite in [0.0, 1.0], got {confidence}")
        conn = self._db.conn
        cursor = await conn.execute(
            "UPDATE strategy_rules SET status = ?, confidence = ? WHERE rule_id = ?",
            (status.value, confidence, rule_id),
        )
        if commit:
            await conn.commit()
        updated = cursor.rowcount > 0
        if updated:
            logger.debug(
                "Updated rule %s status to %s, confidence to %.3f",
                rule_id,
                status.value,
                confidence,
            )
        return updated

    async def get_prediction_accuracy(
        self,
        window_days: int | None = None,
    ) -> list[PredictionAccuracy]:
        """Per-source accuracy from the ``predictions`` table.

        Groups scored predictions (``was_correct IS NOT NULL``) by ``source``,
        computes accuracy = correct / total, and flags whether the sample count
        meets ``_MIN_PREDICTION_SAMPLES``.

        Parameters
        ----------
        window_days
            If provided, only include predictions created within this many days.

        Returns
        -------
        list[PredictionAccuracy]
            One entry per source with at least 1 scored prediction.
        """
        conn = self._db.conn

        where_clauses = ["was_correct IS NOT NULL"]
        params: list[object] = []
        if window_days is not None:
            where_clauses.append("created_at >= datetime('now', ?)")
            params.append(f"-{window_days} days")

        where_sql = " AND ".join(where_clauses)

        sql = (
            "SELECT "
            "source, "
            "COUNT(*) AS total, "
            "SUM(CASE WHEN was_correct = 1 THEN 1 ELSE 0 END) AS correct "
            f"FROM predictions WHERE {where_sql} "
            "GROUP BY source "
            "ORDER BY source"
        )

        async with conn.execute(sql, params) as cursor:
            rows = await cursor.fetchall()

        results: list[PredictionAccuracy] = []
        for row in rows:
            total = int(row["total"])
            correct = int(row["correct"])
            accuracy = correct / total if total > 0 else 0.0
            source = PredictionSource(str(row["source"]))
            results.append(
                PredictionAccuracy(
                    source=source,
                    total=total,
                    correct=correct,
                    accuracy=accuracy,
                    sample_sufficient=total >= _MIN_PREDICTION_SAMPLES,
                )
            )

        return results

    # ------------------------------------------------------------------
    # Prediction CRUD
    # ------------------------------------------------------------------

    async def save_prediction(
        self,
        prediction: Prediction,
        *,
        commit: bool = True,
    ) -> int:
        """Persist a single prediction.

        Parameters
        ----------
        prediction
            The ``Prediction`` to save.
        commit
            Whether to commit immediately (default ``True``).

        Returns
        -------
        int
            The database-assigned row ID.
        """
        conn = self._db.conn
        cursor = await conn.execute(
            "INSERT INTO predictions "
            "(recommendation_id, scan_run_id, ticker, source, predicted_direction, "
            "confidence, adx, iv_rank, atr_pct, rsi, was_correct, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                prediction.recommendation_id,
                prediction.scan_run_id,
                prediction.ticker,
                prediction.source.value,
                prediction.predicted_direction.value,
                prediction.confidence,
                prediction.adx,
                prediction.iv_rank,
                prediction.atr_pct,
                prediction.rsi,
                int(prediction.was_correct) if prediction.was_correct is not None else None,
                prediction.created_at.isoformat(),
            ),
        )
        if commit:
            await conn.commit()
        row_id = cursor.lastrowid or 0
        logger.debug("Saved prediction id=%d source=%s", row_id, prediction.source.value)
        return row_id

    async def save_predictions_batch(
        self,
        predictions: list[Prediction],
        *,
        commit: bool = True,
    ) -> list[int]:
        """Persist multiple predictions in a single transaction.

        Parameters
        ----------
        predictions
            The list of ``Prediction`` models to save.
        commit
            Whether to commit after all inserts (default ``True``).

        Returns
        -------
        list[int]
            The database-assigned row IDs (one per prediction).
        """
        if not predictions:
            return []
        conn = self._db.conn
        ids: list[int] = []
        try:
            for p in predictions:
                row_id = await self.save_prediction(p, commit=False)
                ids.append(row_id)
        except Exception:
            await conn.rollback()
            raise
        if commit:
            await conn.commit()
        logger.debug("Saved %d predictions in batch", len(ids))
        return ids

    async def score_predictions(
        self,
        recommendation_id: int,
        was_correct: bool,
        *,
        commit: bool = True,
    ) -> int:
        """Score all predictions for a recommendation.

        Parameters
        ----------
        recommendation_id
            The recommendation to score predictions for.
        was_correct
            Whether the predictions were correct.
        commit
            Whether to commit immediately (default ``True``).

        Returns
        -------
        int
            Number of rows updated.
        """
        conn = self._db.conn
        cursor = await conn.execute(
            "UPDATE predictions SET was_correct = ? WHERE recommendation_id = ?",
            (int(was_correct), recommendation_id),
        )
        if commit:
            await conn.commit()
        count = cursor.rowcount
        logger.debug(
            "Scored %d predictions for recommendation_id=%d was_correct=%s",
            count,
            recommendation_id,
            was_correct,
        )
        return count

    async def score_scan_predictions(
        self,
        scan_run_id: int,
        ticker: str,
        was_correct: bool,
        *,
        commit: bool = True,
    ) -> int:
        """Score predictions for a scan run + ticker.

        Parameters
        ----------
        scan_run_id
            The scan run to score predictions for.
        ticker
            The ticker symbol to filter by.
        was_correct
            Whether the predictions were correct.
        commit
            Whether to commit immediately (default ``True``).

        Returns
        -------
        int
            Number of rows updated.
        """
        conn = self._db.conn
        cursor = await conn.execute(
            "UPDATE predictions SET was_correct = ? WHERE scan_run_id = ? AND ticker = ?",
            (int(was_correct), scan_run_id, ticker),
        )
        if commit:
            await conn.commit()
        count = cursor.rowcount
        logger.debug(
            "Scored %d scan predictions for scan_run_id=%d ticker=%s",
            count,
            scan_run_id,
            ticker,
        )
        return count

    async def get_predictions(
        self,
        window_days: int,
        source: PredictionSource | None = None,
    ) -> list[Prediction]:
        """Retrieve predictions within a time window.

        Parameters
        ----------
        window_days
            Number of days to look back from now.
        source
            If provided, only return predictions from this source.

        Returns
        -------
        list[Prediction]
            Predictions ordered by ``created_at`` DESC.
        """
        if window_days < 0:
            raise ValueError(f"window_days must be >= 0, got {window_days}")
        conn = self._db.conn
        cutoff = (datetime.now(UTC) - timedelta(days=window_days)).isoformat()

        if source is not None:
            query = (
                "SELECT * FROM predictions "
                "WHERE created_at >= ? AND source = ? "
                "ORDER BY created_at DESC"
            )
            params: tuple[str, ...] = (cutoff, source.value)
        else:
            query = "SELECT * FROM predictions WHERE created_at >= ? ORDER BY created_at DESC"
            params = (cutoff,)

        async with conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()

        return [self._row_to_prediction(row) for row in rows]

    async def get_prediction_accuracy(
        self,
        window_days: int,
    ) -> list[PredictionAccuracy]:
        """Compute per-source accuracy statistics over a time window.

        Parameters
        ----------
        window_days
            Number of days to look back from now.

        Returns
        -------
        list[PredictionAccuracy]
            Accuracy statistics grouped by source.
        """
        if window_days < 0:
            raise ValueError(f"window_days must be >= 0, got {window_days}")
        conn = self._db.conn
        cutoff = (datetime.now(UTC) - timedelta(days=window_days)).isoformat()

        query = (
            "SELECT source, COUNT(*) as total, SUM(was_correct) as correct "
            "FROM predictions "
            "WHERE was_correct IS NOT NULL AND created_at >= ? "
            "GROUP BY source"
        )
        async with conn.execute(query, (cutoff,)) as cursor:
            rows = await cursor.fetchall()

        results: list[PredictionAccuracy] = []
        for row in rows:
            total = int(row["total"])
            raw_correct = row["correct"]
            correct = int(raw_correct) if raw_correct is not None else 0
            accuracy = correct / total if total > 0 else 0.0
            results.append(
                PredictionAccuracy(
                    source=PredictionSource(str(row["source"])),
                    total=total,
                    correct=correct,
                    accuracy=accuracy,
                    sample_sufficient=total >= _MIN_SAMPLE_SIZE,
                )
            )
        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_prediction(row: Row) -> Prediction:
        """Reconstruct a ``Prediction`` from a database row."""
        # Parse created_at with UTC defense
        created_at = datetime.fromisoformat(str(row["created_at"]))
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)

        # Map was_correct: NULL -> None, 0 -> False, 1 -> True
        raw_was_correct = row["was_correct"]
        was_correct: bool | None = None
        if raw_was_correct is not None:
            was_correct = bool(int(raw_was_correct))

        return Prediction(
            id=int(row["id"]) if row["id"] is not None else None,
            recommendation_id=(
                int(row["recommendation_id"]) if row["recommendation_id"] is not None else None
            ),
            scan_run_id=(int(row["scan_run_id"]) if row["scan_run_id"] is not None else None),
            ticker=str(row["ticker"]),
            source=PredictionSource(str(row["source"])),
            predicted_direction=SignalDirection(str(row["predicted_direction"])),
            confidence=float(row["confidence"]),
            adx=float(row["adx"]) if row["adx"] is not None else None,
            iv_rank=float(row["iv_rank"]) if row["iv_rank"] is not None else None,
            atr_pct=float(row["atr_pct"]) if row["atr_pct"] is not None else None,
            rsi=float(row["rsi"]) if row["rsi"] is not None else None,
            was_correct=was_correct,
            created_at=created_at,
        )

    @staticmethod
    def _row_to_strategy_rule(row: Row) -> StrategyRule:
        """Reconstruct a ``StrategyRule`` from a database row."""
        conditions_data = json.loads(str(row["conditions_json"]))
        conditions = [StrategyCondition(**c) for c in conditions_data]

        # Confidence columns added in migration 038 — fallback for pre-migration rows
        raw_confidence = row["confidence"]
        confidence = float(raw_confidence) if raw_confidence is not None else 0.5

        raw_last_validated = row["last_validated"]
        last_validated: datetime | None = None
        if raw_last_validated is not None:
            dt = datetime.fromisoformat(str(raw_last_validated))
            last_validated = dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)

        raw_validation_count = row["validation_count"]
        validation_count = int(raw_validation_count) if raw_validation_count is not None else 0

        # Ensure created_at is timezone-aware (defense against corrupt DB rows)
        created_at = datetime.fromisoformat(str(row["created_at"]))
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)

        return StrategyRule(
            rule_id=str(row["rule_id"]),
            pattern=str(row["pattern"]),
            conditions=conditions,
            win_rate=float(row["win_rate"]),
            avg_return=float(row["avg_return"]),
            sample_size=int(row["sample_size"]),
            status=RuleStatus(str(row["status"])),
            created_at=created_at,
            confidence=confidence,
            last_validated=last_validated,
            validation_count=validation_count,
        )

"""EvalMixin — eval definition and run persistence for Repository.

Provides CRUD operations for eval definitions (what to test) and eval runs
(execution history). All methods return typed Pydantic models from ``models/eval.py``.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from sqlite3 import Row

from options_arena.models.enums import (
    DeskType,
    EvalType,
    GraderType,
    SignalDirection,
)
from options_arena.models.eval import EvalDefinition, EvalRun

from ._base import RepositoryBase

logger = logging.getLogger(__name__)


class EvalMixin(RepositoryBase):
    """CRUD operations for eval definitions and runs.

    Methods
    -------
    save_eval_definition
        Persist (upsert) an eval definition.
    get_eval_definitions
        Retrieve all eval definitions.
    get_eval_definition
        Retrieve a single eval definition by name.
    save_eval_run
        Persist an eval run, returning the DB-assigned ID.
    get_eval_runs
        Retrieve eval runs, optionally filtered by eval name.
    get_latest_eval_runs
        Get the most recent run for each eval definition.
    """

    async def save_eval_definition(
        self,
        definition: EvalDefinition,
        *,
        commit: bool = True,
    ) -> None:
        """Persist an eval definition (upsert by name).

        Parameters
        ----------
        definition
            The ``EvalDefinition`` to save.
        commit
            Whether to commit immediately (default ``True``).
        """
        conn = self._db.conn
        custom_json = json.dumps(definition.custom_assertions)

        await conn.execute(
            "INSERT OR REPLACE INTO eval_definitions "
            "(name, eval_type, target_desk, description, grader_type, "
            "market_context_fixture, expected_direction, "
            "expected_confidence_min, expected_confidence_max, "
            "custom_assertions_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                definition.name,
                definition.eval_type.value,
                definition.target_desk.value if definition.target_desk else None,
                definition.description,
                definition.grader_type.value,
                definition.market_context_fixture,
                (
                    definition.expected_direction.value
                    if definition.expected_direction
                    else None
                ),
                definition.expected_confidence_min,
                definition.expected_confidence_max,
                custom_json,
                datetime.now(UTC).isoformat(),
            ),
        )
        if commit:
            await conn.commit()
        logger.debug("Saved eval definition %s", definition.name)

    async def get_eval_definitions(self) -> list[EvalDefinition]:
        """Retrieve all eval definitions.

        Returns
        -------
        list[EvalDefinition]
            All definitions ordered by name.
        """
        conn = self._db.conn
        async with conn.execute(
            "SELECT * FROM eval_definitions ORDER BY name"
        ) as cursor:
            rows = await cursor.fetchall()
        return [self._row_to_eval_definition(row) for row in rows]

    async def get_eval_definition(self, name: str) -> EvalDefinition | None:
        """Retrieve a single eval definition by name.

        Parameters
        ----------
        name
            The eval definition name.

        Returns
        -------
        EvalDefinition | None
            The definition, or ``None`` if not found.
        """
        conn = self._db.conn
        async with conn.execute(
            "SELECT * FROM eval_definitions WHERE name = ?", (name,)
        ) as cursor:
            row = await cursor.fetchone()
        return self._row_to_eval_definition(row) if row else None

    async def save_eval_run(
        self,
        run: EvalRun,
        *,
        commit: bool = True,
    ) -> int:
        """Persist an eval run.

        Parameters
        ----------
        run
            The ``EvalRun`` to save.
        commit
            Whether to commit immediately (default ``True``).

        Returns
        -------
        int
            The DB-assigned row ID.
        """
        conn = self._db.conn
        cursor = await conn.execute(
            "INSERT INTO eval_runs "
            "(eval_name, timestamp, passed, attempts, successes, "
            "model_used, duration_ms, details) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run.eval_name,
                run.timestamp.isoformat(),
                1 if run.passed else 0,
                run.attempts,
                run.successes,
                run.model_used,
                run.duration_ms,
                run.details,
            ),
        )
        if commit:
            await conn.commit()
        row_id = cursor.lastrowid or 0
        logger.debug("Saved eval run id=%d for %s", row_id, run.eval_name)
        return row_id

    async def get_eval_runs(
        self,
        eval_name: str | None = None,
        limit: int = 100,
    ) -> list[EvalRun]:
        """Retrieve eval runs, optionally filtered by eval name.

        Parameters
        ----------
        eval_name
            If provided, only return runs for this eval.
        limit
            Maximum number of runs to return.

        Returns
        -------
        list[EvalRun]
            Runs ordered by timestamp DESC.
        """
        conn = self._db.conn
        if eval_name is not None:
            query = (
                "SELECT * FROM eval_runs WHERE eval_name = ? "
                "ORDER BY timestamp DESC LIMIT ?"
            )
            params: tuple[str | int, ...] = (eval_name, limit)
        else:
            query = "SELECT * FROM eval_runs ORDER BY timestamp DESC LIMIT ?"
            params = (limit,)

        async with conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
        return [self._row_to_eval_run(row) for row in rows]

    async def get_latest_eval_runs(self) -> list[EvalRun]:
        """Get the most recent run for each eval definition.

        Returns
        -------
        list[EvalRun]
            One run per eval definition, the most recent.
        """
        conn = self._db.conn
        query = (
            "SELECT er.* FROM eval_runs er "
            "INNER JOIN ("
            "  SELECT eval_name, MAX(timestamp) AS max_ts "
            "  FROM eval_runs GROUP BY eval_name"
            ") latest ON er.eval_name = latest.eval_name "
            "AND er.timestamp = latest.max_ts "
            "ORDER BY er.eval_name"
        )
        async with conn.execute(query) as cursor:
            rows = await cursor.fetchall()
        return [self._row_to_eval_run(row) for row in rows]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_eval_definition(row: Row) -> EvalDefinition:
        """Reconstruct an ``EvalDefinition`` from a database row."""
        raw_desk = row["target_desk"]
        target_desk = DeskType(str(raw_desk)) if raw_desk is not None else None

        raw_direction = row["expected_direction"]
        expected_direction = (
            SignalDirection(str(raw_direction)) if raw_direction is not None else None
        )

        raw_assertions = row["custom_assertions_json"]
        custom_assertions: list[str] = json.loads(str(raw_assertions))

        return EvalDefinition(
            name=str(row["name"]),
            eval_type=EvalType(str(row["eval_type"])),
            target_desk=target_desk,
            description=str(row["description"]),
            grader_type=GraderType(str(row["grader_type"])),
            market_context_fixture=str(row["market_context_fixture"]),
            expected_direction=expected_direction,
            expected_confidence_min=(
                float(row["expected_confidence_min"])
                if row["expected_confidence_min"] is not None
                else None
            ),
            expected_confidence_max=(
                float(row["expected_confidence_max"])
                if row["expected_confidence_max"] is not None
                else None
            ),
            custom_assertions=custom_assertions,
        )

    @staticmethod
    def _row_to_eval_run(row: Row) -> EvalRun:
        """Reconstruct an ``EvalRun`` from a database row."""
        return EvalRun(
            id=int(row["id"]),
            eval_name=str(row["eval_name"]),
            timestamp=datetime.fromisoformat(str(row["timestamp"])),
            passed=bool(row["passed"]),
            attempts=int(row["attempts"]),
            successes=int(row["successes"]),
            model_used=str(row["model_used"]),
            duration_ms=int(row["duration_ms"]),
            details=str(row["details"]),
        )

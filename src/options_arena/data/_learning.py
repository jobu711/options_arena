"""LearningMixin — strategy rule and agent memory persistence for Repository.

Provides CRUD operations for strategy rules (mined patterns with human approval)
and agent memory (long-term knowledge entries).  All methods return typed Pydantic
models from ``models/strategy.py``.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from sqlite3 import Row

from options_arena.models.enums import RuleStatus
from options_arena.models.strategy import AgentMemory, StrategyCondition, StrategyRule

from ._base import RepositoryBase

logger = logging.getLogger(__name__)


class LearningMixin(RepositoryBase):
    """CRUD operations for strategy rules and agent memory.

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
    save_agent_memory
        Persist (upsert) an agent memory entry.
    get_agent_memories
        Retrieve agent memories, optionally filtered by agent or scope type.
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

    async def save_agent_memory(
        self,
        memory: AgentMemory,
        *,
        commit: bool = True,
    ) -> None:
        """Persist an agent memory entry (upsert by memory_id).

        Parameters
        ----------
        memory
            The ``AgentMemory`` to save.
        commit
            Whether to commit immediately (default ``True``).
        """
        conn = self._db.conn
        await conn.execute(
            "INSERT OR REPLACE INTO agent_memory "
            "(memory_id, agent_name, scope, scope_type, content, "
            "sample_size, win_rate, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                memory.memory_id,
                memory.agent_name,
                memory.scope,
                memory.scope_type,
                memory.content,
                memory.sample_size,
                memory.win_rate,
                memory.created_at.isoformat(),
            ),
        )
        if commit:
            await conn.commit()
        logger.debug("Saved agent memory %s", memory.memory_id)

    async def get_agent_memories(
        self,
        agent_name: str | None = None,
        scope_type: str | None = None,
        limit: int | None = None,
    ) -> list[AgentMemory]:
        """Retrieve agent memory entries, optionally filtered.

        Parameters
        ----------
        agent_name
            If provided, only return memories for this agent.
        scope_type
            If provided, only return memories with this scope type.
        limit
            Maximum number of memories to return.  ``None`` returns all rows.

        Returns
        -------
        list[AgentMemory]
            Memories ordered by ``created_at`` DESC.
        """
        conn = self._db.conn
        conditions: list[str] = []
        query_params: list[str | int] = []

        if agent_name is not None:
            conditions.append("agent_name = ?")
            query_params.append(agent_name)
        if scope_type is not None:
            conditions.append("scope_type = ?")
            query_params.append(scope_type)

        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"SELECT * FROM agent_memory{where} ORDER BY created_at DESC"
        if limit is not None:
            query += " LIMIT ?"
            query_params.append(limit)

        async with conn.execute(query, tuple(query_params)) as cursor:
            rows = await cursor.fetchall()

        return [self._row_to_agent_memory(row) for row in rows]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_strategy_rule(row: Row) -> StrategyRule:
        """Reconstruct a ``StrategyRule`` from a database row."""
        conditions_data = json.loads(str(row["conditions_json"]))
        conditions = [StrategyCondition(**c) for c in conditions_data]

        # Confidence columns added in migration 038 — fallback for pre-migration rows
        raw_confidence = row["confidence"]
        confidence = float(raw_confidence) if raw_confidence is not None else 0.5

        raw_last_validated = row["last_validated"]
        last_validated: datetime | None = (
            datetime.fromisoformat(str(raw_last_validated))
            if raw_last_validated is not None
            else None
        )

        raw_validation_count = row["validation_count"]
        validation_count = int(raw_validation_count) if raw_validation_count is not None else 0

        return StrategyRule(
            rule_id=str(row["rule_id"]),
            pattern=str(row["pattern"]),
            conditions=conditions,
            win_rate=float(row["win_rate"]),
            avg_return=float(row["avg_return"]),
            sample_size=int(row["sample_size"]),
            status=RuleStatus(str(row["status"])),
            created_at=datetime.fromisoformat(str(row["created_at"])),
            confidence=confidence,
            last_validated=last_validated,
            validation_count=validation_count,
        )

    @staticmethod
    def _row_to_agent_memory(row: Row) -> AgentMemory:
        """Reconstruct an ``AgentMemory`` from a database row."""
        return AgentMemory(
            memory_id=str(row["memory_id"]),
            agent_name=str(row["agent_name"]),
            scope=str(row["scope"]),
            scope_type=str(row["scope_type"]),
            content=str(row["content"]),
            sample_size=int(row["sample_size"]),
            win_rate=float(row["win_rate"]),
            created_at=datetime.fromisoformat(str(row["created_at"])),
        )

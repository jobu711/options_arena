"""AgencyMixin — agency query persistence for Repository.

Stores and retrieves agency routing queries, classified intents, and synthesized
responses.  Methods accept and return primitives / ``AgencyQueryRow`` dataclass
to avoid coupling to models that may be defined in parallel (task #581).
The routing layer handles serialization/deserialization of full Pydantic models.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from ._base import RepositoryBase

logger = logging.getLogger(__name__)


@dataclass
class AgencyQueryRow:
    """Raw row from the ``agency_queries`` table.

    Kept in the data layer (not ``models/``) because it contains raw JSON
    strings, not typed models — same pattern as ``DebateRow``.
    """

    id: int
    query_id: str
    query_text: str
    desk: str | None
    tickers_json: str
    intent_json: str
    response_json: str
    confidence: float
    created_at: str


class AgencyMixin(RepositoryBase):
    """CRUD operations for agency queries.

    Methods
    -------
    save_agency_query
        Persist a completed agency query with its intent and response.
    get_agency_query
        Retrieve a single agency query row by ``query_id``.
    list_agency_queries
        List recent agency queries, newest first.
    """

    async def save_agency_query(
        self,
        query_id: str,
        query_text: str,
        desk: str | None,
        tickers: list[str],
        intent_json: str,
        response_json: str,
        confidence: float,
        *,
        commit: bool = True,
    ) -> int:
        """Persist an agency query and its response.

        Parameters
        ----------
        query_id
            UUID4 string uniquely identifying the query.
        query_text
            The raw user query string.
        desk
            Comma-separated desk names dispatched to, or ``None``.
        tickers
            Extracted ticker symbols (serialized to JSON array).
        intent_json
            Full ``QueryIntent.model_dump_json()`` for reconstruction.
        response_json
            Full ``AgencyResponse.model_dump_json()`` for reconstruction.
        confidence
            Float confidence from the synthesized response.
        commit
            Whether to commit immediately (default ``True``).
            Set ``False`` for batched persistence.

        Returns
        -------
        int
            The database row ID of the inserted record.
        """
        conn = self._db.conn
        tickers_json = json.dumps(tickers)
        created_at = datetime.now(UTC).isoformat()

        cursor = await conn.execute(
            "INSERT INTO agency_queries "
            "(query_id, query_text, desk, tickers_json, intent_json, "
            "response_json, confidence, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                query_id,
                query_text,
                desk,
                tickers_json,
                intent_json,
                response_json,
                confidence,
                created_at,
            ),
        )
        if commit:
            await conn.commit()
        assert cursor.lastrowid is not None
        row_id: int = cursor.lastrowid
        logger.debug("Saved agency query id=%d query_id=%s", row_id, query_id)
        return row_id

    async def get_agency_query(self, query_id: str) -> AgencyQueryRow | None:
        """Retrieve a stored agency query by ``query_id``.

        Parameters
        ----------
        query_id
            The UUID4 string identifying the query.

        Returns
        -------
        AgencyQueryRow | None
            The raw row data, or ``None`` if not found.
        """
        conn = self._db.conn
        async with conn.execute(
            "SELECT * FROM agency_queries WHERE query_id = ?",
            (query_id,),
        ) as cursor:
            row = await cursor.fetchone()

        if row is None:
            return None

        return AgencyQueryRow(
            id=int(row["id"]),
            query_id=str(row["query_id"]),
            query_text=str(row["query_text"]),
            desk=str(row["desk"]) if row["desk"] is not None else None,
            tickers_json=str(row["tickers_json"]),
            intent_json=str(row["intent_json"]),
            response_json=str(row["response_json"]),
            confidence=float(row["confidence"]),
            created_at=str(row["created_at"]),
        )

    async def list_agency_queries(self, limit: int = 20) -> list[AgencyQueryRow]:
        """List recent agency queries, newest first.

        Parameters
        ----------
        limit
            Maximum number of results to return (default 20).

        Returns
        -------
        list[AgencyQueryRow]
            Raw rows ordered by ``created_at`` DESC.
        """
        conn = self._db.conn
        async with conn.execute(
            "SELECT * FROM agency_queries ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()

        return [
            AgencyQueryRow(
                id=int(row["id"]),
                query_id=str(row["query_id"]),
                query_text=str(row["query_text"]),
                desk=str(row["desk"]) if row["desk"] is not None else None,
                tickers_json=str(row["tickers_json"]),
                intent_json=str(row["intent_json"]),
                response_json=str(row["response_json"]),
                confidence=float(row["confidence"]),
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]

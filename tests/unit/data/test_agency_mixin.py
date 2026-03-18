"""Tests for AgencyMixin — agency query persistence."""

from __future__ import annotations

import json
import sqlite3

import pytest
import pytest_asyncio

from options_arena.data.database import Database
from options_arena.data.repository import AgencyQueryRow, Repository


@pytest_asyncio.fixture
async def db() -> Database:  # type: ignore[misc]
    database = Database(":memory:")
    await database.connect()
    yield database  # type: ignore[misc]
    await database.close()


@pytest_asyncio.fixture
async def repo(db: Database) -> Repository:
    return Repository(db)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_intent_json(tickers: list[str] | None = None) -> str:
    """Return a plausible intent JSON string."""
    return json.dumps(
        {
            "desks": ["volatility"],
            "query_type": "analysis",
            "tickers": tickers or ["AAPL"],
        }
    )


def _make_response_json(
    query_id: str = "test-q-582",
    confidence: float = 0.75,
) -> str:
    """Return a plausible response JSON string."""
    return json.dumps(
        {
            "query_id": query_id,
            "query_text": "What's AAPL IV?",
            "intent": {
                "desks": ["volatility"],
                "query_type": "analysis",
                "tickers": ["AAPL"],
            },
            "desk_responses": [
                {
                    "desk": "volatility",
                    "response": "IV rank is 85.",
                    "tools_used": ["fetch_quote"],
                    "confidence": 0.75,
                },
            ],
            "synthesis": "AAPL implied volatility is elevated.",
            "citations": [],
            "confidence": confidence,
            "created_at": "2026-03-18T12:00:00+00:00",
        }
    )


# ---------------------------------------------------------------------------
# save_agency_query
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSaveAgencyQuery:
    """save_agency_query persists all fields and returns row ID."""

    async def test_returns_row_id(self, repo: Repository) -> None:
        row_id = await repo.save_agency_query(
            query_id="test-q-582",
            query_text="What's AAPL IV?",
            desk="volatility",
            tickers=["AAPL"],
            intent_json=_make_intent_json(),
            response_json=_make_response_json(),
            confidence=0.75,
        )
        assert isinstance(row_id, int)
        assert row_id > 0

    async def test_duplicate_query_id_raises(self, repo: Repository) -> None:
        kwargs = {
            "query_id": "dup-582",
            "query_text": "What's AAPL IV?",
            "desk": "volatility",
            "tickers": ["AAPL"],
            "intent_json": _make_intent_json(),
            "response_json": _make_response_json(query_id="dup-582"),
            "confidence": 0.75,
        }
        await repo.save_agency_query(**kwargs)
        with pytest.raises(sqlite3.IntegrityError):
            await repo.save_agency_query(**kwargs)

    async def test_commit_false_defers_commit(self, repo: Repository) -> None:
        """With commit=False, data is available after explicit commit."""
        await repo.save_agency_query(
            query_id="deferred-582",
            query_text="Deferred query",
            desk="volatility",
            tickers=["AAPL"],
            intent_json=_make_intent_json(),
            response_json=_make_response_json(query_id="deferred-582"),
            confidence=0.5,
            commit=False,
        )
        # Explicitly commit
        await repo.commit()
        result = await repo.get_agency_query("deferred-582")
        assert result is not None

    async def test_null_desk(self, repo: Repository) -> None:
        """desk can be None."""
        row_id = await repo.save_agency_query(
            query_id="null-desk-582",
            query_text="General question",
            desk=None,
            tickers=[],
            intent_json=_make_intent_json(tickers=[]),
            response_json=_make_response_json(query_id="null-desk-582"),
            confidence=0.5,
        )
        assert row_id > 0
        result = await repo.get_agency_query("null-desk-582")
        assert result is not None
        assert result.desk is None

    async def test_empty_tickers(self, repo: Repository) -> None:
        """tickers can be an empty list."""
        row_id = await repo.save_agency_query(
            query_id="empty-tickers-582",
            query_text="General question",
            desk="volatility",
            tickers=[],
            intent_json=_make_intent_json(tickers=[]),
            response_json=_make_response_json(query_id="empty-tickers-582"),
            confidence=0.5,
        )
        assert row_id > 0
        result = await repo.get_agency_query("empty-tickers-582")
        assert result is not None
        assert json.loads(result.tickers_json) == []


# ---------------------------------------------------------------------------
# get_agency_query
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetAgencyQuery:
    """get_agency_query retrieves by query_id."""

    async def test_returns_none_on_empty_db(self, repo: Repository) -> None:
        result = await repo.get_agency_query("nonexistent")
        assert result is None

    async def test_returns_none_for_wrong_id(self, repo: Repository) -> None:
        await repo.save_agency_query(
            query_id="exists-582",
            query_text="What's AAPL IV?",
            desk="volatility",
            tickers=["AAPL"],
            intent_json=_make_intent_json(),
            response_json=_make_response_json(query_id="exists-582"),
            confidence=0.75,
        )
        result = await repo.get_agency_query("wrong-id")
        assert result is None

    async def test_round_trip_fidelity(self, repo: Repository) -> None:
        """Write then read — all fields match."""
        intent = _make_intent_json()
        response = _make_response_json(query_id="roundtrip-582", confidence=0.82)

        await repo.save_agency_query(
            query_id="roundtrip-582",
            query_text="What's AAPL IV?",
            desk="volatility",
            tickers=["AAPL"],
            intent_json=intent,
            response_json=response,
            confidence=0.82,
        )
        result = await repo.get_agency_query("roundtrip-582")
        assert result is not None
        assert isinstance(result, AgencyQueryRow)
        assert result.query_id == "roundtrip-582"
        assert result.query_text == "What's AAPL IV?"
        assert result.desk == "volatility"
        assert json.loads(result.tickers_json) == ["AAPL"]
        assert result.intent_json == intent
        assert result.response_json == response
        assert result.confidence == pytest.approx(0.82)
        assert result.created_at  # non-empty ISO timestamp

    async def test_confidence_preserved(self, repo: Repository) -> None:
        await repo.save_agency_query(
            query_id="conf-582",
            query_text="Check IV",
            desk="volatility",
            tickers=["AAPL"],
            intent_json=_make_intent_json(),
            response_json=_make_response_json(query_id="conf-582", confidence=0.42),
            confidence=0.42,
        )
        result = await repo.get_agency_query("conf-582")
        assert result is not None
        assert result.confidence == pytest.approx(0.42)


# ---------------------------------------------------------------------------
# list_agency_queries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestListAgencyQueries:
    """list_agency_queries returns recent queries newest first."""

    async def test_empty_db_returns_empty_list(self, repo: Repository) -> None:
        result = await repo.list_agency_queries()
        assert result == []

    async def test_returns_newest_first(self, repo: Repository) -> None:
        """Insert 3 queries with different created_at, verify ordering."""
        # We need to bypass the auto-generated created_at to control ordering.
        # Insert directly via SQL so we can set created_at explicitly.
        conn = repo._db.conn
        timestamps = [
            "2026-03-18T10:00:00+00:00",
            "2026-03-18T11:00:00+00:00",
            "2026-03-18T12:00:00+00:00",
        ]
        for i, ts in enumerate(timestamps, start=1):
            await conn.execute(
                "INSERT INTO agency_queries "
                "(query_id, query_text, desk, tickers_json, intent_json, "
                "response_json, confidence, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    f"order-{i:03d}",
                    "Query text",
                    "volatility",
                    "[]",
                    "{}",
                    "{}",
                    0.5,
                    ts,
                ),
            )
        await conn.commit()

        results = await repo.list_agency_queries()
        assert len(results) == 3
        assert results[0].query_id == "order-003"  # newest
        assert results[2].query_id == "order-001"  # oldest

    async def test_respects_limit(self, repo: Repository) -> None:
        for i in range(5):
            await repo.save_agency_query(
                query_id=f"limit-{i:03d}",
                query_text="Limit test",
                desk="volatility",
                tickers=["AAPL"],
                intent_json=_make_intent_json(),
                response_json=_make_response_json(query_id=f"limit-{i:03d}"),
                confidence=0.5,
            )

        results = await repo.list_agency_queries(limit=3)
        assert len(results) == 3

    async def test_default_limit_is_20(self, repo: Repository) -> None:
        """Default limit is 20 — verify with fewer records."""
        for i in range(5):
            await repo.save_agency_query(
                query_id=f"default-{i:03d}",
                query_text="Default limit test",
                desk="volatility",
                tickers=["AAPL"],
                intent_json=_make_intent_json(),
                response_json=_make_response_json(query_id=f"default-{i:03d}"),
                confidence=0.5,
            )

        results = await repo.list_agency_queries()
        assert len(results) == 5  # fewer than default limit

    async def test_limit_zero_returns_empty(self, repo: Repository) -> None:
        """LIMIT 0 returns empty list."""
        await repo.save_agency_query(
            query_id="lim0-582",
            query_text="Limit 0 test",
            desk="volatility",
            tickers=["AAPL"],
            intent_json=_make_intent_json(),
            response_json=_make_response_json(query_id="lim0-582"),
            confidence=0.5,
        )
        results = await repo.list_agency_queries(limit=0)
        assert results == []


# ---------------------------------------------------------------------------
# Repository composition
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAgencyMixinOnRepository:
    """AgencyMixin is properly composed on Repository."""

    async def test_repository_has_save_method(self, repo: Repository) -> None:
        assert hasattr(repo, "save_agency_query")

    async def test_repository_has_get_method(self, repo: Repository) -> None:
        assert hasattr(repo, "get_agency_query")

    async def test_repository_has_list_method(self, repo: Repository) -> None:
        assert hasattr(repo, "list_agency_queries")

    async def test_isolation_from_other_tables(self, repo: Repository) -> None:
        """Agency queries don't interfere with scan/debate tables."""
        await repo.save_agency_query(
            query_id="iso-582",
            query_text="Isolation test",
            desk="volatility",
            tickers=["AAPL"],
            intent_json=_make_intent_json(),
            response_json=_make_response_json(query_id="iso-582"),
            confidence=0.5,
        )
        # Verify other tables still work
        latest_scan = await repo.get_latest_scan()
        assert latest_scan is None  # no scans saved


# ---------------------------------------------------------------------------
# Migration verification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestMigration034:
    """Verify migration 034 creates the table and indexes."""

    async def test_table_exists(self, db: Database) -> None:
        """agency_queries table exists after connect."""
        async with db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='agency_queries'"
        ) as cursor:
            row = await cursor.fetchone()
        assert row is not None

    async def test_indexes_exist(self, db: Database) -> None:
        """Both indexes exist after connect."""
        sql = (
            "SELECT name FROM sqlite_master "
            "WHERE type='index' AND name LIKE 'idx_agency_queries_%'"
        )
        async with db.conn.execute(sql) as cursor:
            rows = await cursor.fetchall()
        index_names = {str(row["name"]) for row in rows}
        assert "idx_agency_queries_query_id" in index_names
        assert "idx_agency_queries_created_at" in index_names

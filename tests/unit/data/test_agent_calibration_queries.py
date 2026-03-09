"""Tests for agent calibration repository queries.

Covers:
  - get_agent_accuracy: basic accuracy, window filter, 10-sample minimum,
    NULL direction excluded, no matching outcomes
  - get_agent_calibration: aggregate, per-agent, empty buckets, boundary
  - get_latest_auto_tune_weights / save_auto_tune_weights: roundtrip,
    latest retrieval, empty table
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import pytest_asyncio

from options_arena.data.database import Database
from options_arena.data.repository import Repository
from options_arena.models import (
    AgentWeightsComparison,
    ScanPreset,
    ScanRun,
)

pytestmark = pytest.mark.db

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

NOW = datetime(2026, 3, 7, 12, 0, 0, tzinfo=UTC)
LONG_AGO = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)


@pytest_asyncio.fixture
async def db() -> Database:
    """Fresh in-memory database with all migrations applied."""
    database = Database(":memory:")
    await database.connect()
    yield database  # type: ignore[misc]
    await database.close()


@pytest_asyncio.fixture
async def repo(db: Database) -> Repository:
    """Repository wrapping the in-memory database."""
    return Repository(db)


async def _seed_scan_and_contract(repo: Repository) -> int:
    """Create a scan run + recommended contract, return contract ID."""
    scan = ScanRun(
        started_at=NOW,
        completed_at=NOW,
        preset=ScanPreset.SP500,
        tickers_scanned=500,
        tickers_scored=450,
        recommendations=5,
    )
    scan_id = await repo.save_scan_run(scan)

    conn = repo._db.conn
    await conn.execute(
        "INSERT INTO recommended_contracts "
        "(scan_run_id, ticker, option_type, strike, expiration, bid, ask, "
        "volume, open_interest, market_iv, exercise_style, "
        "entry_stock_price, entry_mid, direction, composite_score, "
        "risk_free_rate, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            scan_id,
            "AAPL",
            "call",
            "185.50",
            "2026-04-15",
            "5.20",
            "5.60",
            1200,
            5000,
            0.32,
            "american",
            "182.30",
            "5.40",
            "bullish",
            78.5,
            0.045,
            NOW.isoformat(),
        ),
    )
    await conn.commit()
    async with conn.execute(
        "SELECT id FROM recommended_contracts WHERE scan_run_id = ?",
        (scan_id,),
    ) as cursor:
        row = await cursor.fetchone()
    assert row is not None
    return int(row["id"])


_AP_INSERT = (
    "INSERT INTO agent_predictions "
    "(debate_id, recommended_contract_id, agent_name, "
    "direction, confidence, created_at) "
    "VALUES (?, ?, ?, ?, ?, ?)"
)

_THESIS_INSERT = (
    "INSERT INTO ai_theses "
    "(ticker, bull_json, bear_json, verdict_json, "
    "total_tokens, model_name, duration_ms, is_fallback, created_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
)

_OUTCOME_INSERT = (
    "INSERT OR IGNORE INTO contract_outcomes "
    "(recommended_contract_id, stock_return_pct, contract_return_pct, "
    "is_winner, holding_days, collection_method, collected_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?)"
)


async def _seed_predictions_and_outcomes(
    repo: Repository,
    contract_id: int,
    agent_name: str,
    count: int,
    *,
    direction: str = "bullish",
    confidence: float = 0.7,
    stock_return_pct: float = 5.0,
    created_at: datetime = NOW,
) -> None:
    """Seed N predictions with matching T+10 outcomes."""
    conn = repo._db.conn

    for _i in range(count):
        cursor = await conn.execute(
            _THESIS_INSERT,
            (
                "AAPL",
                "{}",
                "{}",
                "{}",
                100,
                "test",
                500,
                0,
                created_at.isoformat(),
            ),
        )
        debate_id = cursor.lastrowid
        await conn.execute(
            _AP_INSERT,
            (
                debate_id,
                contract_id,
                agent_name,
                direction,
                confidence,
                created_at.isoformat(),
            ),
        )
        await conn.execute(
            _OUTCOME_INSERT,
            (
                contract_id,
                stock_return_pct,
                10.0,
                1,
                10,
                "scheduled",
                created_at.isoformat(),
            ),
        )

    await conn.commit()


# ---------------------------------------------------------------------------
# get_agent_accuracy
# ---------------------------------------------------------------------------


class TestGetAgentAccuracy:
    """Tests for Repository.get_agent_accuracy()."""

    async def test_basic_accuracy(self, repo: Repository) -> None:
        """Verify accuracy computation with seeded data."""
        contract_id = await _seed_scan_and_contract(repo)
        await _seed_predictions_and_outcomes(
            repo,
            contract_id,
            "trend",
            15,
            direction="bullish",
            confidence=0.8,
            stock_return_pct=5.0,
        )

        results = await repo.get_agent_accuracy()
        assert len(results) >= 1
        trend = next(r for r in results if r.agent_name == "trend")
        assert trend.direction_hit_rate == pytest.approx(1.0, abs=0.01)
        assert trend.mean_confidence == pytest.approx(0.8, abs=0.01)
        assert trend.brier_score == pytest.approx(0.04, abs=0.01)
        assert trend.sample_size >= 10

    async def test_window_filter(self, repo: Repository) -> None:
        """Verify window_days filters to recent predictions only."""
        contract_id = await _seed_scan_and_contract(repo)
        conn = repo._db.conn

        for _i in range(12):
            cursor = await conn.execute(
                _THESIS_INSERT,
                (
                    "AAPL",
                    "{}",
                    "{}",
                    "{}",
                    100,
                    "test",
                    500,
                    0,
                    LONG_AGO.isoformat(),
                ),
            )
            debate_id = cursor.lastrowid
            await conn.execute(
                _AP_INSERT,
                (
                    debate_id,
                    contract_id,
                    "volatility",
                    "bullish",
                    0.9,
                    LONG_AGO.isoformat(),
                ),
            )
        await conn.commit()

        results = await repo.get_agent_accuracy(window_days=7)
        vol_agents = [r for r in results if r.agent_name == "volatility"]
        assert len(vol_agents) == 0

    async def test_ten_sample_minimum(self, repo: Repository) -> None:
        """Verify agents with < 10 outcomes excluded."""
        contract_id = await _seed_scan_and_contract(repo)
        await _seed_predictions_and_outcomes(
            repo,
            contract_id,
            "flow",
            5,
        )

        results = await repo.get_agent_accuracy()
        flow_agents = [r for r in results if r.agent_name == "flow"]
        assert len(flow_agents) == 0

    async def test_null_direction_excluded(self, repo: Repository) -> None:
        """Verify predictions with direction=NULL not counted."""
        contract_id = await _seed_scan_and_contract(repo)
        conn = repo._db.conn

        for _i in range(15):
            cursor = await conn.execute(
                _THESIS_INSERT,
                (
                    "AAPL",
                    "{}",
                    "{}",
                    "{}",
                    100,
                    "test",
                    500,
                    0,
                    NOW.isoformat(),
                ),
            )
            debate_id = cursor.lastrowid
            await conn.execute(
                _AP_INSERT,
                (
                    debate_id,
                    contract_id,
                    "risk",
                    None,
                    0.5,
                    NOW.isoformat(),
                ),
            )
        await conn.commit()

        results = await repo.get_agent_accuracy()
        risk_agents = [r for r in results if r.agent_name == "risk"]
        assert len(risk_agents) == 0

    async def test_no_matching_outcomes(self, repo: Repository) -> None:
        """Verify empty list when no outcomes match."""
        contract_id = await _seed_scan_and_contract(repo)
        conn = repo._db.conn

        for _i in range(15):
            cursor = await conn.execute(
                _THESIS_INSERT,
                (
                    "AAPL",
                    "{}",
                    "{}",
                    "{}",
                    100,
                    "test",
                    500,
                    0,
                    NOW.isoformat(),
                ),
            )
            debate_id = cursor.lastrowid
            await conn.execute(
                _AP_INSERT,
                (
                    debate_id,
                    contract_id,
                    "fundamental",
                    "bullish",
                    0.7,
                    NOW.isoformat(),
                ),
            )
        await conn.commit()

        results = await repo.get_agent_accuracy()
        assert len(results) == 0


# ---------------------------------------------------------------------------
# get_agent_calibration
# ---------------------------------------------------------------------------


class TestGetAgentCalibration:
    """Tests for Repository.get_agent_calibration()."""

    async def test_aggregate_calibration(self, repo: Repository) -> None:
        """Verify aggregate (agent_name=None) buckets all agents."""
        contract_id = await _seed_scan_and_contract(repo)
        await _seed_predictions_and_outcomes(
            repo,
            contract_id,
            "trend",
            15,
            confidence=0.7,
            stock_return_pct=5.0,
        )

        data = await repo.get_agent_calibration()
        assert data.agent_name is None
        assert len(data.buckets) == 5
        assert data.sample_size > 0

    async def test_per_agent_calibration(self, repo: Repository) -> None:
        """Verify per-agent filtering."""
        contract_id = await _seed_scan_and_contract(repo)
        await _seed_predictions_and_outcomes(
            repo,
            contract_id,
            "trend",
            15,
            confidence=0.7,
        )

        data = await repo.get_agent_calibration(agent_name="trend")
        assert data.agent_name == "trend"
        assert data.sample_size > 0

        data_none = await repo.get_agent_calibration(
            agent_name="nonexistent",
        )
        assert data_none.sample_size == 0

    async def test_empty_buckets(self, repo: Repository) -> None:
        """Verify buckets with 0 predictions have count=0."""
        data = await repo.get_agent_calibration()
        assert len(data.buckets) == 5
        for bucket in data.buckets:
            assert bucket.count == 0

    async def test_bucket_boundaries(self, repo: Repository) -> None:
        """Verify confidence 0.2 falls in [0.2, 0.4) bucket."""
        contract_id = await _seed_scan_and_contract(repo)
        await _seed_predictions_and_outcomes(
            repo,
            contract_id,
            "trend",
            15,
            confidence=0.2,
            stock_return_pct=5.0,
        )

        data = await repo.get_agent_calibration()
        bucket_02_04 = next(b for b in data.buckets if b.bucket_label == "0.2-0.4")
        bucket_00_02 = next(b for b in data.buckets if b.bucket_label == "0.0-0.2")
        assert bucket_02_04.count > 0
        assert bucket_00_02.count == 0


# ---------------------------------------------------------------------------
# Auto-tune weights CRUD
# ---------------------------------------------------------------------------


class TestAutoTuneWeightsCRUD:
    """Tests for save/get auto-tune weights."""

    def _make_weights(self) -> list[AgentWeightsComparison]:
        return [
            AgentWeightsComparison(
                agent_name="trend",
                manual_weight=0.17,
                auto_weight=0.22,
                brier_score=0.18,
                sample_size=50,
            ),
            AgentWeightsComparison(
                agent_name="volatility",
                manual_weight=0.17,
                auto_weight=0.15,
                brier_score=0.25,
                sample_size=30,
            ),
            AgentWeightsComparison(
                agent_name="risk",
                manual_weight=0.0,
                auto_weight=0.0,
                brier_score=None,
                sample_size=0,
            ),
        ]

    async def test_save_and_retrieve(self, repo: Repository) -> None:
        """Verify roundtrip."""
        weights = self._make_weights()
        await repo.save_auto_tune_weights(weights, window_days=90)

        retrieved = await repo.get_latest_auto_tune_weights()
        assert len(retrieved) == 3

        trend = next(r for r in retrieved if r.agent_name == "trend")
        assert trend.manual_weight == pytest.approx(0.17)
        assert trend.auto_weight == pytest.approx(0.22)
        assert trend.brier_score == pytest.approx(0.18)
        assert trend.sample_size == 50

        risk = next(r for r in retrieved if r.agent_name == "risk")
        assert risk.brier_score is None

    async def test_latest_returns_most_recent(
        self,
        repo: Repository,
    ) -> None:
        """Verify get_latest returns the most recent set."""
        old_weights = [
            AgentWeightsComparison(
                agent_name="trend",
                manual_weight=0.17,
                auto_weight=0.10,
                brier_score=0.40,
                sample_size=20,
            ),
        ]
        await repo.save_auto_tune_weights(old_weights, window_days=30)

        new_weights = [
            AgentWeightsComparison(
                agent_name="trend",
                manual_weight=0.17,
                auto_weight=0.25,
                brier_score=0.12,
                sample_size=80,
            ),
        ]
        await repo.save_auto_tune_weights(new_weights, window_days=90)

        retrieved = await repo.get_latest_auto_tune_weights()
        assert len(retrieved) == 1
        assert retrieved[0].auto_weight == pytest.approx(0.25)

    async def test_empty_table(self, repo: Repository) -> None:
        """Verify empty list when no weights saved yet."""
        results = await repo.get_latest_auto_tune_weights()
        assert results == []

    async def test_save_empty_list(self, repo: Repository) -> None:
        """Verify saving an empty list is a no-op."""
        await repo.save_auto_tune_weights([], window_days=90)
        results = await repo.get_latest_auto_tune_weights()
        assert results == []

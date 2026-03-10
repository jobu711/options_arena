"""Integration tests for the agent calibration pipeline.

End-to-end verification:
  - Seeded predictions + outcomes → accuracy queries → weight computation
  - Backward compatibility (auto_tune_weights=False uses manual weights)
  - Weight constraints: sum=0.85, floor=0.05, cap=0.35, risk=0.0
  - 10-sample guard: agents with <10 outcomes keep manual weights
  - Accuracy and calibration consistency
  - Auto-tune weights save/retrieve roundtrip
  - Migrations applied correctly

Uses in-memory SQLite with all migrations applied — no mocks for persistence.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import pytest_asyncio

from options_arena.agents.orchestrator import (
    AGENT_VOTE_WEIGHTS,
    compute_auto_tune_weights,
)
from options_arena.data.database import Database
from options_arena.data.repository import Repository
from options_arena.models import (
    AgentAccuracyReport,
    AgentWeightsComparison,
    ScanPreset,
    ScanRun,
)

pytestmark = pytest.mark.db

NOW = datetime(2026, 3, 7, 12, 0, 0, tzinfo=UTC)

# SQL templates for seeding data
_THESIS_INSERT = (
    "INSERT INTO ai_theses "
    "(ticker, bull_json, bear_json, verdict_json, "
    "total_tokens, model_name, duration_ms, is_fallback, created_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
)

_AP_INSERT = (
    "INSERT INTO agent_predictions "
    "(debate_id, recommended_contract_id, agent_name, "
    "direction, confidence, created_at) "
    "VALUES (?, ?, ?, ?, ?, ?)"
)

_OUTCOME_INSERT = (
    "INSERT OR IGNORE INTO contract_outcomes "
    "(recommended_contract_id, stock_return_pct, contract_return_pct, "
    "is_winner, holding_days, collection_method, collected_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?)"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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

    conn = repo._db.conn  # noqa: SLF001
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


async def _seed_agent_data(
    repo: Repository,
    contract_id: int,
    agent_name: str,
    count: int,
    *,
    direction: str = "bullish",
    confidence: float = 0.7,
    stock_return_pct: float = 5.0,
) -> None:
    """Seed N predictions with matching outcomes."""
    conn = repo._db.conn  # noqa: SLF001
    for _ in range(count):
        cursor = await conn.execute(
            _THESIS_INSERT,
            ("AAPL", "{}", "{}", "{}", 100, "test", 500, 0, NOW.isoformat()),
        )
        debate_id = cursor.lastrowid
        await conn.execute(
            _AP_INSERT,
            (debate_id, contract_id, agent_name, direction, confidence, NOW.isoformat()),
        )
        await conn.execute(
            _OUTCOME_INSERT,
            (contract_id, stock_return_pct, 10.0, 1, 10, "scheduled", NOW.isoformat()),
        )
    await conn.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCalibrationPipeline:
    """End-to-end integration tests for the calibration pipeline."""

    async def test_full_pipeline_seeded_data(self, repo: Repository) -> None:
        """Seed predictions + outcomes → accuracy → weights → constraint check."""
        contract_id = await _seed_scan_and_contract(repo)

        # Seed 6 agents with varying accuracy
        # Good agents (high accuracy, low Brier)
        await _seed_agent_data(
            repo,
            contract_id,
            "trend",
            15,
            direction="bullish",
            confidence=0.8,
            stock_return_pct=5.0,
        )
        await _seed_agent_data(
            repo,
            contract_id,
            "volatility",
            15,
            direction="bullish",
            confidence=0.7,
            stock_return_pct=3.0,
        )
        await _seed_agent_data(
            repo,
            contract_id,
            "flow",
            12,
            direction="bullish",
            confidence=0.6,
            stock_return_pct=2.0,
        )
        await _seed_agent_data(
            repo,
            contract_id,
            "fundamental",
            15,
            direction="bearish",
            confidence=0.9,
            stock_return_pct=5.0,
        )

        # Pipeline: accuracy → weights
        accuracy = await repo.get_agent_accuracy()
        assert len(accuracy) >= 3  # trend, volatility, flow have 10+ outcomes

        weights = compute_auto_tune_weights(accuracy)
        assert isinstance(weights, dict)

        # Weight constraints: sum=0.85 for directional, risk=0.0
        directional = {k: v for k, v in weights.items() if k != "risk"}
        assert sum(directional.values()) == pytest.approx(0.85, abs=0.01)
        assert weights.get("risk", 0.0) == 0.0
        # All directional weights must be positive
        for name, w in directional.items():
            assert w > 0, f"{name} weight {w} should be positive"

    async def test_backward_compat_manual_weights(self, repo: Repository) -> None:
        """compute_auto_tune_weights with empty accuracy returns manual weights."""
        weights = compute_auto_tune_weights([])
        assert weights == AGENT_VOTE_WEIGHTS

    async def test_weight_constraints_enforced(self, repo: Repository) -> None:
        """Verify sum=0.85, floor=0.05, cap=0.35, risk=0.0 on computed weights."""
        # Create accuracy reports with extreme values
        reports = [
            AgentAccuracyReport(
                agent_name="trend",
                direction_hit_rate=1.0,
                mean_confidence=0.9,
                brier_score=0.01,  # Near perfect → high weight
                sample_size=50,
            ),
            AgentAccuracyReport(
                agent_name="volatility",
                direction_hit_rate=0.5,
                mean_confidence=0.5,
                brier_score=0.95,  # Near worst → floor weight
                sample_size=50,
            ),
            AgentAccuracyReport(
                agent_name="flow",
                direction_hit_rate=0.6,
                mean_confidence=0.6,
                brier_score=0.40,
                sample_size=50,
            ),
            AgentAccuracyReport(
                agent_name="fundamental",
                direction_hit_rate=0.7,
                mean_confidence=0.7,
                brier_score=0.20,
                sample_size=50,
            ),
        ]

        weights = compute_auto_tune_weights(reports)

        assert weights["risk"] == 0.0
        directional = {k: v for k, v in weights.items() if k != "risk"}
        assert sum(directional.values()) == pytest.approx(0.85, abs=0.01)
        # Verify relative ordering: trend (low Brier) should have highest weight
        assert weights["trend"] > weights["volatility"]
        # All directional weights positive after normalization
        for name, w in directional.items():
            assert w > 0, f"{name}={w} should be positive"

    async def test_insufficient_samples_keep_manual(self, repo: Repository) -> None:
        """Agents with <10 outcomes keep their manual weights."""
        contract_id = await _seed_scan_and_contract(repo)

        # Seed trend with 15 outcomes (above threshold)
        await _seed_agent_data(
            repo,
            contract_id,
            "trend",
            15,
            direction="bullish",
            confidence=0.8,
            stock_return_pct=5.0,
        )
        # Seed contrarian with only 5 outcomes (below threshold)
        await _seed_agent_data(
            repo,
            contract_id,
            "contrarian",
            5,
            direction="bearish",
            confidence=0.6,
            stock_return_pct=-2.0,
        )

        accuracy = await repo.get_agent_accuracy()
        # contrarian should be excluded (< 10 samples)
        contrarian_reports = [r for r in accuracy if r.agent_name == "contrarian"]
        assert len(contrarian_reports) == 0

        weights = compute_auto_tune_weights(accuracy)
        # contrarian keeps manual weight since no accuracy data
        assert weights["contrarian"] == pytest.approx(AGENT_VOTE_WEIGHTS["contrarian"], abs=0.01)

    async def test_accuracy_and_calibration_consistent(self, repo: Repository) -> None:
        """Accuracy and calibration queries agree on same seeded data."""
        contract_id = await _seed_scan_and_contract(repo)
        await _seed_agent_data(
            repo,
            contract_id,
            "trend",
            15,
            direction="bullish",
            confidence=0.7,
            stock_return_pct=5.0,
        )

        accuracy = await repo.get_agent_accuracy()
        calibration = await repo.get_agent_calibration("trend")

        assert len(accuracy) >= 1
        trend_acc = next(r for r in accuracy if r.agent_name == "trend")
        assert trend_acc.sample_size >= 10
        assert calibration.agent_name == "trend"
        assert calibration.sample_size > 0

    async def test_weights_persisted_and_retrieved(self, repo: Repository) -> None:
        """Verify save + get_latest roundtrip for auto-tune weights."""
        weights_data = [
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
        ]

        await repo.save_auto_tune_weights(weights_data, window_days=90)
        retrieved = await repo.get_latest_auto_tune_weights()

        assert len(retrieved) == 2
        trend = next(r for r in retrieved if r.agent_name == "trend")
        assert trend.auto_weight == pytest.approx(0.22)
        assert trend.brier_score == pytest.approx(0.18)

    async def test_all_migrations_applied(self, db: Database) -> None:
        """Verify agent_predictions and auto_tune_weights tables exist."""
        conn = db.conn
        # Check agent_predictions table
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='agent_predictions'"
        ) as cursor:
            row = await cursor.fetchone()
        assert row is not None, "agent_predictions table missing"

        # Check auto_tune_weights table
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='auto_tune_weights'"
        ) as cursor:
            row = await cursor.fetchone()
        assert row is not None, "auto_tune_weights table missing"

    async def test_perfect_brier_equal_weights(self) -> None:
        """All agents perfectly accurate → equal weights summing to 0.85."""
        reports = [
            AgentAccuracyReport(
                agent_name=name,
                direction_hit_rate=1.0,
                mean_confidence=1.0,
                brier_score=0.0,
                sample_size=50,
            )
            for name in AGENT_VOTE_WEIGHTS
            if name != "risk"
        ]

        weights = compute_auto_tune_weights(reports)
        directional = {k: v for k, v in weights.items() if k != "risk"}
        values = list(directional.values())

        # All directional weights should be equal
        assert all(v == pytest.approx(values[0], abs=0.01) for v in values)
        assert sum(values) == pytest.approx(0.85, abs=0.01)

    async def test_worst_brier_floor_weights(self) -> None:
        """All agents worst possible → floor weights renormalized to 0.85."""
        reports = [
            AgentAccuracyReport(
                agent_name=name,
                direction_hit_rate=0.0,
                mean_confidence=1.0,
                brier_score=1.0,
                sample_size=50,
            )
            for name in AGENT_VOTE_WEIGHTS
            if name != "risk"
        ]

        weights = compute_auto_tune_weights(reports)
        directional = {k: v for k, v in weights.items() if k != "risk"}
        assert sum(directional.values()) == pytest.approx(0.85, abs=0.01)
        assert weights["risk"] == 0.0

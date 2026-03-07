"""Tests for repository dimensional score persistence (migration 015)."""

from datetime import UTC, datetime

import pytest
import pytest_asyncio

from options_arena.data.database import Database
from options_arena.data.repository import Repository
from options_arena.models import (
    IndicatorSignals,
    MarketRegime,
    ScanPreset,
    ScanRun,
    SignalDirection,
    TickerScore,
)
from options_arena.models.scoring import DimensionalScores

pytestmark = pytest.mark.db

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db() -> Database:
    """Fresh in-memory database for each test."""
    database = Database(":memory:")
    await database.connect()
    yield database  # type: ignore[misc]
    await database.close()


@pytest_asyncio.fixture
async def repo(db: Database) -> Repository:
    """Repository backed by the in-memory database."""
    return Repository(db)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_scan_run(**overrides: object) -> ScanRun:
    """Build a ScanRun with sensible defaults."""
    defaults: dict[str, object] = {
        "started_at": datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC),
        "completed_at": datetime(2026, 1, 15, 10, 35, 0, tzinfo=UTC),
        "preset": ScanPreset.SP500,
        "tickers_scanned": 500,
        "tickers_scored": 450,
        "recommendations": 8,
    }
    defaults.update(overrides)
    return ScanRun(**defaults)  # type: ignore[arg-type]


def _make_ticker_score(**overrides: object) -> TickerScore:
    """Build a TickerScore with sensible defaults."""
    defaults: dict[str, object] = {
        "ticker": "AAPL",
        "composite_score": 78.5,
        "direction": SignalDirection.BULLISH,
        "signals": IndicatorSignals(rsi=65.2, adx=28.4, bb_width=42.1),
    }
    defaults.update(overrides)
    return TickerScore(**defaults)  # type: ignore[arg-type]


def _make_dimensional_scores(**overrides: object) -> DimensionalScores:
    """Build DimensionalScores with sensible defaults."""
    defaults: dict[str, object] = {
        "trend": 75.0,
        "iv_vol": 60.0,
        "hv_vol": 45.0,
        "flow": 30.0,
        "microstructure": 50.0,
        "fundamental": 80.0,
        "regime": 55.0,
        "risk": 25.0,
    }
    defaults.update(overrides)
    return DimensionalScores(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Dimensional score persistence
# ---------------------------------------------------------------------------


class TestRepositoryDimensionalPersistence:
    """Tests for dimensional_scores_json, direction_confidence, market_regime persistence."""

    @pytest.mark.asyncio
    async def test_save_and_retrieve_dimensional_scores(self, repo: Repository) -> None:
        """Verify dimensional_scores_json roundtrips through DB correctly."""
        scan_id = await repo.save_scan_run(_make_scan_run())
        dim = _make_dimensional_scores()
        score = _make_ticker_score(dimensional_scores=dim)

        await repo.save_ticker_scores(scan_id, [score])
        result = await repo.get_scores_for_scan(scan_id)

        assert len(result) == 1
        assert result[0].dimensional_scores is not None
        assert result[0].dimensional_scores.trend == pytest.approx(75.0)
        assert result[0].dimensional_scores.iv_vol == pytest.approx(60.0)
        assert result[0].dimensional_scores.hv_vol == pytest.approx(45.0)
        assert result[0].dimensional_scores.flow == pytest.approx(30.0)
        assert result[0].dimensional_scores.microstructure == pytest.approx(50.0)
        assert result[0].dimensional_scores.fundamental == pytest.approx(80.0)
        assert result[0].dimensional_scores.regime == pytest.approx(55.0)
        assert result[0].dimensional_scores.risk == pytest.approx(25.0)

    @pytest.mark.asyncio
    async def test_save_and_retrieve_direction_confidence(self, repo: Repository) -> None:
        """Verify direction_confidence persists as REAL and reads back as float."""
        scan_id = await repo.save_scan_run(_make_scan_run())
        score = _make_ticker_score(direction_confidence=0.85)

        await repo.save_ticker_scores(scan_id, [score])
        result = await repo.get_scores_for_scan(scan_id)

        assert len(result) == 1
        assert result[0].direction_confidence == pytest.approx(0.85)

    @pytest.mark.asyncio
    async def test_save_and_retrieve_market_regime(self, repo: Repository) -> None:
        """Verify market_regime persists as TEXT and reads back as MarketRegime enum."""
        scan_id = await repo.save_scan_run(_make_scan_run())
        score = _make_ticker_score(market_regime=MarketRegime.VOLATILE)

        await repo.save_ticker_scores(scan_id, [score])
        result = await repo.get_scores_for_scan(scan_id)

        assert len(result) == 1
        assert result[0].market_regime is MarketRegime.VOLATILE

    @pytest.mark.asyncio
    async def test_null_dimensional_scores_pre_migration(self, repo: Repository) -> None:
        """Verify NULL dimensional_scores_json deserializes to None gracefully."""
        scan_id = await repo.save_scan_run(_make_scan_run())
        score = _make_ticker_score()  # no dimensional_scores set
        assert score.dimensional_scores is None

        await repo.save_ticker_scores(scan_id, [score])
        result = await repo.get_scores_for_scan(scan_id)

        assert len(result) == 1
        assert result[0].dimensional_scores is None

    @pytest.mark.asyncio
    async def test_null_direction_confidence_pre_migration(self, repo: Repository) -> None:
        """Verify NULL direction_confidence deserializes to None."""
        scan_id = await repo.save_scan_run(_make_scan_run())
        score = _make_ticker_score()  # no direction_confidence set
        assert score.direction_confidence is None

        await repo.save_ticker_scores(scan_id, [score])
        result = await repo.get_scores_for_scan(scan_id)

        assert len(result) == 1
        assert result[0].direction_confidence is None

    @pytest.mark.asyncio
    async def test_null_market_regime_pre_migration(self, repo: Repository) -> None:
        """Verify NULL market_regime deserializes to None."""
        scan_id = await repo.save_scan_run(_make_scan_run())
        score = _make_ticker_score()  # no market_regime set
        assert score.market_regime is None

        await repo.save_ticker_scores(scan_id, [score])
        result = await repo.get_scores_for_scan(scan_id)

        assert len(result) == 1
        assert result[0].market_regime is None

    @pytest.mark.asyncio
    async def test_all_market_regime_values_persist(self, repo: Repository) -> None:
        """Verify all 4 MarketRegime enum values roundtrip correctly."""
        scan_id = await repo.save_scan_run(_make_scan_run())

        scores = [
            _make_ticker_score(ticker=f"T{i}", market_regime=regime)
            for i, regime in enumerate(MarketRegime)
        ]
        await repo.save_ticker_scores(scan_id, scores)
        result = await repo.get_scores_for_scan(scan_id)

        assert len(result) == 4
        regimes = {r.ticker: r.market_regime for r in result}
        assert regimes["T0"] is MarketRegime.TRENDING
        assert regimes["T1"] is MarketRegime.MEAN_REVERTING
        assert regimes["T2"] is MarketRegime.VOLATILE
        assert regimes["T3"] is MarketRegime.CRISIS

    @pytest.mark.asyncio
    async def test_all_three_fields_together(self, repo: Repository) -> None:
        """Verify all 3 new fields persist and roundtrip together."""
        scan_id = await repo.save_scan_run(_make_scan_run())
        dim = _make_dimensional_scores()
        score = _make_ticker_score(
            dimensional_scores=dim,
            direction_confidence=0.73,
            market_regime=MarketRegime.TRENDING,
        )

        await repo.save_ticker_scores(scan_id, [score])
        result = await repo.get_scores_for_scan(scan_id)

        assert len(result) == 1
        r = result[0]
        assert r.dimensional_scores is not None
        assert r.dimensional_scores.trend == pytest.approx(75.0)
        assert r.direction_confidence == pytest.approx(0.73)
        assert r.market_regime is MarketRegime.TRENDING

    @pytest.mark.asyncio
    async def test_dimensional_scores_with_all_none_fields(self, repo: Repository) -> None:
        """Verify DimensionalScores with all-None fields roundtrips through DB."""
        scan_id = await repo.save_scan_run(_make_scan_run())
        dim = DimensionalScores()  # all fields None
        score = _make_ticker_score(dimensional_scores=dim)

        await repo.save_ticker_scores(scan_id, [score])
        result = await repo.get_scores_for_scan(scan_id)

        assert len(result) == 1
        assert result[0].dimensional_scores is not None
        assert result[0].dimensional_scores.trend is None
        assert result[0].dimensional_scores.risk is None

    @pytest.mark.asyncio
    async def test_direction_confidence_boundary_zero(self, repo: Repository) -> None:
        """Verify direction_confidence=0.0 persists correctly (not treated as None)."""
        scan_id = await repo.save_scan_run(_make_scan_run())
        score = _make_ticker_score(direction_confidence=0.0)

        await repo.save_ticker_scores(scan_id, [score])
        result = await repo.get_scores_for_scan(scan_id)

        assert result[0].direction_confidence == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_direction_confidence_boundary_one(self, repo: Repository) -> None:
        """Verify direction_confidence=1.0 persists correctly."""
        scan_id = await repo.save_scan_run(_make_scan_run())
        score = _make_ticker_score(direction_confidence=1.0)

        await repo.save_ticker_scores(scan_id, [score])
        result = await repo.get_scores_for_scan(scan_id)

        assert result[0].direction_confidence == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_mixed_null_and_populated_in_batch(self, repo: Repository) -> None:
        """Verify batch with mixed null/populated dimensional data persists correctly."""
        scan_id = await repo.save_scan_run(_make_scan_run())
        scores = [
            _make_ticker_score(
                ticker="AAPL",
                dimensional_scores=_make_dimensional_scores(),
                direction_confidence=0.85,
                market_regime=MarketRegime.TRENDING,
            ),
            _make_ticker_score(ticker="MSFT"),  # all None
            _make_ticker_score(
                ticker="GOOGL",
                direction_confidence=0.42,
                market_regime=MarketRegime.CRISIS,
            ),
        ]
        await repo.save_ticker_scores(scan_id, scores)
        result = await repo.get_scores_for_scan(scan_id)

        assert len(result) == 3
        by_ticker = {r.ticker: r for r in result}

        assert by_ticker["AAPL"].dimensional_scores is not None
        assert by_ticker["AAPL"].direction_confidence == pytest.approx(0.85)
        assert by_ticker["AAPL"].market_regime is MarketRegime.TRENDING

        assert by_ticker["MSFT"].dimensional_scores is None
        assert by_ticker["MSFT"].direction_confidence is None
        assert by_ticker["MSFT"].market_regime is None

        assert by_ticker["GOOGL"].dimensional_scores is None
        assert by_ticker["GOOGL"].direction_confidence == pytest.approx(0.42)
        assert by_ticker["GOOGL"].market_regime is MarketRegime.CRISIS

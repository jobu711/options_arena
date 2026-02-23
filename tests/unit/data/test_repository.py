"""Tests for Repository — typed CRUD for ScanRun and TickerScore."""

import sqlite3
from datetime import UTC, datetime

import pytest
import pytest_asyncio

from options_arena.data.database import Database
from options_arena.data.repository import Repository
from options_arena.models import (
    IndicatorSignals,
    ScanPreset,
    ScanRun,
    SignalDirection,
    TickerScore,
)

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


def make_scan_run(**overrides: object) -> ScanRun:
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


def make_ticker_score(**overrides: object) -> TickerScore:
    """Build a TickerScore with sensible defaults."""
    defaults: dict[str, object] = {
        "ticker": "AAPL",
        "composite_score": 78.5,
        "direction": SignalDirection.BULLISH,
        "signals": IndicatorSignals(rsi=65.2, adx=28.4, bb_width=42.1),
    }
    defaults.update(overrides)
    return TickerScore(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# save_scan_run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_scan_run_returns_positive_id(repo: Repository) -> None:
    """save_scan_run returns integer ID > 0."""
    scan = make_scan_run()
    row_id = await repo.save_scan_run(scan)
    assert isinstance(row_id, int)
    assert row_id > 0


# ---------------------------------------------------------------------------
# get_latest_scan
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_latest_scan_empty_db(repo: Repository) -> None:
    """get_latest_scan returns None on empty database."""
    result = await repo.get_latest_scan()
    assert result is None


@pytest.mark.asyncio
async def test_get_latest_scan_returns_most_recent(repo: Repository) -> None:
    """get_latest_scan returns the most recently inserted ScanRun."""
    scan1 = make_scan_run(tickers_scanned=100)
    scan2 = make_scan_run(tickers_scanned=200)
    await repo.save_scan_run(scan1)
    id2 = await repo.save_scan_run(scan2)

    latest = await repo.get_latest_scan()
    assert latest is not None
    assert latest.id == id2
    assert latest.tickers_scanned == 200


# ---------------------------------------------------------------------------
# get_scan_by_id — round-trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_round_trip_preserves_all_fields(repo: Repository) -> None:
    """save_scan_run → get_scan_by_id preserves all fields."""
    scan = make_scan_run()
    row_id = await repo.save_scan_run(scan)

    loaded = await repo.get_scan_by_id(row_id)
    assert loaded is not None
    assert loaded.id == row_id
    assert loaded.started_at == scan.started_at
    assert loaded.completed_at == scan.completed_at
    assert loaded.preset == scan.preset
    assert loaded.tickers_scanned == scan.tickers_scanned
    assert loaded.tickers_scored == scan.tickers_scored
    assert loaded.recommendations == scan.recommendations


# ---------------------------------------------------------------------------
# Enum round-trips
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scan_preset_enum_round_trip(repo: Repository) -> None:
    """ScanPreset stored as string, reconstructed as enum member."""
    for preset in ScanPreset:
        scan = make_scan_run(preset=preset)
        row_id = await repo.save_scan_run(scan)
        loaded = await repo.get_scan_by_id(row_id)
        assert loaded is not None
        assert loaded.preset is preset
        assert isinstance(loaded.preset, ScanPreset)


@pytest.mark.asyncio
async def test_signal_direction_enum_round_trip(repo: Repository) -> None:
    """SignalDirection stored as string, reconstructed as enum member."""
    for direction in SignalDirection:
        score = make_ticker_score(ticker=f"T_{direction.value}", direction=direction)
        scan = make_scan_run()
        scan_id = await repo.save_scan_run(scan)
        await repo.save_ticker_scores(scan_id, [score])

        scores = await repo.get_scores_for_scan(scan_id)
        assert len(scores) == 1
        assert scores[0].direction is direction
        assert isinstance(scores[0].direction, SignalDirection)


# ---------------------------------------------------------------------------
# datetime round-trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_datetime_utc_round_trip(repo: Repository) -> None:
    """UTC datetime preserved through ISO 8601 serialization."""
    scan = make_scan_run()
    row_id = await repo.save_scan_run(scan)
    loaded = await repo.get_scan_by_id(row_id)
    assert loaded is not None
    assert loaded.started_at == scan.started_at
    assert loaded.started_at.tzinfo is not None
    assert loaded.completed_at == scan.completed_at


@pytest.mark.asyncio
async def test_completed_at_none_round_trip(repo: Repository) -> None:
    """completed_at=None stored as NULL, reconstructed as None."""
    scan = make_scan_run(completed_at=None)
    row_id = await repo.save_scan_run(scan)
    loaded = await repo.get_scan_by_id(row_id)
    assert loaded is not None
    assert loaded.completed_at is None


# ---------------------------------------------------------------------------
# save_ticker_scores + get_scores_for_scan
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_and_get_ticker_scores(repo: Repository) -> None:
    """save_ticker_scores persists batch, get_scores_for_scan retrieves all."""
    scan = make_scan_run()
    scan_id = await repo.save_scan_run(scan)

    scores = [
        make_ticker_score(ticker="AAPL"),
        make_ticker_score(ticker="MSFT", composite_score=82.3),
        make_ticker_score(ticker="GOOGL", direction=SignalDirection.BEARISH),
    ]
    await repo.save_ticker_scores(scan_id, scores)

    loaded = await repo.get_scores_for_scan(scan_id)
    assert len(loaded) == 3
    tickers = {s.ticker for s in loaded}
    assert tickers == {"AAPL", "MSFT", "GOOGL"}


# ---------------------------------------------------------------------------
# IndicatorSignals JSON round-trips
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_indicator_signals_all_none_round_trip(repo: Repository) -> None:
    """IndicatorSignals with all None fields round-trips."""
    score = make_ticker_score(signals=IndicatorSignals())
    scan = make_scan_run()
    scan_id = await repo.save_scan_run(scan)
    await repo.save_ticker_scores(scan_id, [score])

    loaded = await repo.get_scores_for_scan(scan_id)
    assert len(loaded) == 1
    signals = loaded[0].signals
    # All 18 fields should be None
    for field_name in IndicatorSignals.model_fields:
        assert getattr(signals, field_name) is None


@pytest.mark.asyncio
async def test_indicator_signals_partial_fill_round_trip(repo: Repository) -> None:
    """IndicatorSignals with 5 of 18 fields set round-trips."""
    signals = IndicatorSignals(rsi=65.2, adx=28.4, bb_width=42.1, obv=55.0, sma_alignment=60.0)
    score = make_ticker_score(signals=signals)
    scan = make_scan_run()
    scan_id = await repo.save_scan_run(scan)
    await repo.save_ticker_scores(scan_id, [score])

    loaded = await repo.get_scores_for_scan(scan_id)
    assert len(loaded) == 1
    loaded_signals = loaded[0].signals
    assert loaded_signals.rsi == pytest.approx(65.2)
    assert loaded_signals.adx == pytest.approx(28.4)
    assert loaded_signals.bb_width == pytest.approx(42.1)
    assert loaded_signals.obv == pytest.approx(55.0)
    assert loaded_signals.sma_alignment == pytest.approx(60.0)
    assert loaded_signals.stochastic_rsi is None
    assert loaded_signals.iv_rank is None


@pytest.mark.asyncio
async def test_indicator_signals_full_fill_round_trip(repo: Repository) -> None:
    """IndicatorSignals with all 18 fields set round-trips."""
    signals = IndicatorSignals(
        rsi=65.2,
        stochastic_rsi=70.1,
        williams_r=45.0,
        adx=28.4,
        roc=55.0,
        supertrend=60.0,
        bb_width=42.1,
        atr_pct=35.0,
        keltner_width=38.0,
        obv=50.0,
        ad=48.0,
        relative_volume=62.0,
        sma_alignment=58.0,
        vwap_deviation=52.0,
        iv_rank=75.0,
        iv_percentile=80.0,
        put_call_ratio=40.0,
        max_pain_distance=55.0,
    )
    score = make_ticker_score(signals=signals)
    scan = make_scan_run()
    scan_id = await repo.save_scan_run(scan)
    await repo.save_ticker_scores(scan_id, [score])

    loaded = await repo.get_scores_for_scan(scan_id)
    assert len(loaded) == 1
    loaded_signals = loaded[0].signals
    for field_name in IndicatorSignals.model_fields:
        original = getattr(signals, field_name)
        loaded_val = getattr(loaded_signals, field_name)
        assert loaded_val == pytest.approx(original), f"Mismatch on {field_name}"


# ---------------------------------------------------------------------------
# scan_run_id on TickerScore
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ticker_score_scan_run_id_set_correctly(repo: Repository) -> None:
    """TickerScore.scan_run_id set correctly on retrieval."""
    scan = make_scan_run()
    scan_id = await repo.save_scan_run(scan)
    await repo.save_ticker_scores(scan_id, [make_ticker_score()])

    loaded = await repo.get_scores_for_scan(scan_id)
    assert len(loaded) == 1
    assert loaded[0].scan_run_id == scan_id


# ---------------------------------------------------------------------------
# Empty / not-found cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_scores_nonexistent_scan(repo: Repository) -> None:
    """get_scores_for_scan returns empty list for nonexistent scan_id."""
    result = await repo.get_scores_for_scan(999)
    assert result == []


# ---------------------------------------------------------------------------
# get_recent_scans
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_recent_scans_respects_limit(repo: Repository) -> None:
    """get_recent_scans respects limit parameter."""
    for i in range(5):
        await repo.save_scan_run(make_scan_run(tickers_scanned=i))

    result = await repo.get_recent_scans(limit=3)
    assert len(result) == 3


@pytest.mark.asyncio
async def test_get_recent_scans_descending_order(repo: Repository) -> None:
    """get_recent_scans returns scans newest first (descending ID)."""
    ids = []
    for i in range(3):
        row_id = await repo.save_scan_run(make_scan_run(tickers_scanned=i))
        ids.append(row_id)

    result = await repo.get_recent_scans(limit=10)
    result_ids = [s.id for s in result]
    assert result_ids == sorted(result_ids, reverse=True)
    assert result_ids == list(reversed(ids))


# ---------------------------------------------------------------------------
# Constraint enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unique_constraint_duplicate_ticker(repo: Repository) -> None:
    """Duplicate (scan_run_id, ticker) raises IntegrityError."""
    scan = make_scan_run()
    scan_id = await repo.save_scan_run(scan)
    await repo.save_ticker_scores(scan_id, [make_ticker_score(ticker="AAPL")])

    with pytest.raises(sqlite3.IntegrityError):
        await repo.save_ticker_scores(scan_id, [make_ticker_score(ticker="AAPL")])


# ---------------------------------------------------------------------------
# Isolation between scans
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scores_isolated_per_scan(repo: Repository) -> None:
    """Scores for scan A don't appear when querying scan B."""
    scan_a_id = await repo.save_scan_run(make_scan_run(tickers_scanned=100))
    scan_b_id = await repo.save_scan_run(make_scan_run(tickers_scanned=200))

    await repo.save_ticker_scores(scan_a_id, [make_ticker_score(ticker="AAPL")])
    await repo.save_ticker_scores(scan_b_id, [make_ticker_score(ticker="MSFT")])

    scores_a = await repo.get_scores_for_scan(scan_a_id)
    scores_b = await repo.get_scores_for_scan(scan_b_id)

    assert len(scores_a) == 1
    assert scores_a[0].ticker == "AAPL"
    assert len(scores_b) == 1
    assert scores_b[0].ticker == "MSFT"


@pytest.mark.asyncio
async def test_multiple_tickers_per_scan(repo: Repository) -> None:
    """Multiple tickers per scan: all retrieved correctly."""
    scan = make_scan_run()
    scan_id = await repo.save_scan_run(scan)

    scores = [
        make_ticker_score(ticker="AAPL", composite_score=80.0),
        make_ticker_score(ticker="MSFT", composite_score=75.0),
        make_ticker_score(ticker="GOOGL", composite_score=70.0),
        make_ticker_score(ticker="AMZN", composite_score=65.0),
    ]
    await repo.save_ticker_scores(scan_id, scores)

    loaded = await repo.get_scores_for_scan(scan_id)
    assert len(loaded) == 4
    loaded_tickers = {s.ticker for s in loaded}
    assert loaded_tickers == {"AAPL", "MSFT", "GOOGL", "AMZN"}

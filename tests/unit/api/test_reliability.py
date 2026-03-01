"""Tests for reliability and silent-failure fixes (AUDIT-007, AUDIT-014).

Tests cover:
  - Atomic lock contention: concurrent scan requests, second returns 409
  - App state initialization: all counters and mutable dicts exist after startup
  - Disclaimer removal: no disclaimer text in exported markdown
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from httpx import ASGITransport, AsyncClient
from pydantic_ai.usage import RunUsage

from options_arena.agents._parsing import DebateResult
from options_arena.api.app import create_app
from options_arena.api.deps import (
    get_fred,
    get_market_data,
    get_operation_lock,
    get_options_data,
    get_repo,
    get_settings,
    get_universe,
)
from options_arena.models import AgentResponse, MarketContext, TradeThesis
from options_arena.models.config import AppSettings
from options_arena.models.enums import ExerciseStyle, MacdSignal, SignalDirection
from options_arena.reporting.debate_export import export_debate_markdown

# ---------------------------------------------------------------------------
# Lock contention tests (AUDIT-007)
# ---------------------------------------------------------------------------


async def test_scan_lock_contention_returns_409() -> None:
    """Second scan request while lock is held returns 409.

    Simulates the TOCTOU scenario by pre-acquiring the lock before issuing
    a scan request. The atomic ``wait_for(lock.acquire(), timeout=0.01)``
    pattern should immediately raise 409.
    """
    lock = asyncio.Lock()
    app = create_app()

    mock_repo = MagicMock()
    mock_repo.get_recent_scans = AsyncMock(return_value=[])
    mock_repo.save_scan_run = AsyncMock(return_value=1)
    mock_repo.save_ticker_scores = AsyncMock(return_value=None)

    app.dependency_overrides[get_repo] = lambda: mock_repo
    app.dependency_overrides[get_market_data] = lambda: MagicMock()
    app.dependency_overrides[get_options_data] = lambda: MagicMock()
    app.dependency_overrides[get_fred] = lambda: MagicMock()
    app.dependency_overrides[get_universe] = lambda: MagicMock()
    app.dependency_overrides[get_settings] = lambda: AppSettings()
    app.dependency_overrides[get_operation_lock] = lambda: lock

    # Initialize app.state (normally done by lifespan)
    app.state.scan_counter = 0
    app.state.active_scans = {}
    app.state.scan_queues = {}
    app.state.debate_counter = 0
    app.state.debate_queues = {}
    app.state.batch_counter = 0
    app.state.batch_queues = {}

    # Pre-acquire the lock to simulate a running operation
    await lock.acquire()

    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/api/scan", json={"preset": "sp500"})
        assert response.status_code == 409
        assert "operation" in response.json()["detail"].lower()

    lock.release()


async def test_batch_debate_lock_contention_returns_409() -> None:
    """Batch debate request while lock is held returns 409."""
    lock = asyncio.Lock()
    app = create_app()

    mock_repo = MagicMock()
    mock_repo.get_scores_for_scan = AsyncMock(return_value=[])

    app.dependency_overrides[get_repo] = lambda: mock_repo
    app.dependency_overrides[get_market_data] = lambda: MagicMock()
    app.dependency_overrides[get_options_data] = lambda: MagicMock()
    app.dependency_overrides[get_settings] = lambda: AppSettings()
    app.dependency_overrides[get_operation_lock] = lambda: lock

    # Initialize app.state (normally done by lifespan)
    app.state.scan_counter = 0
    app.state.active_scans = {}
    app.state.scan_queues = {}
    app.state.debate_counter = 0
    app.state.debate_queues = {}
    app.state.batch_counter = 0
    app.state.batch_queues = {}

    # Pre-acquire the lock
    await lock.acquire()

    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/debate/batch",
            json={"scan_id": 1, "tickers": ["AAPL", "MSFT"]},
        )
        assert response.status_code == 409
        assert "operation" in response.json()["detail"].lower()

    lock.release()


# ---------------------------------------------------------------------------
# App state initialization tests (AUDIT-014)
# ---------------------------------------------------------------------------


async def test_app_state_initialized_after_lifespan() -> None:
    """All counter and mutable dict attributes exist on app.state after lifespan starts."""
    from options_arena.api.app import lifespan  # noqa: PLC0415

    app = create_app()

    async with lifespan(app):
        # Counters
        assert hasattr(app.state, "scan_counter")
        assert app.state.scan_counter == 0
        assert hasattr(app.state, "debate_counter")
        assert app.state.debate_counter == 0
        assert hasattr(app.state, "batch_counter")
        assert app.state.batch_counter == 0

        # Mutable dicts
        assert hasattr(app.state, "active_scans")
        assert isinstance(app.state.active_scans, dict)
        assert hasattr(app.state, "scan_queues")
        assert isinstance(app.state.scan_queues, dict)
        assert hasattr(app.state, "debate_queues")
        assert isinstance(app.state.debate_queues, dict)
        assert hasattr(app.state, "batch_queues")
        assert isinstance(app.state.batch_queues, dict)

        # Operation lock
        assert hasattr(app.state, "operation_lock")
        assert isinstance(app.state.operation_lock, asyncio.Lock)


# ---------------------------------------------------------------------------
# Disclaimer removal tests (AUDIT-010)
# ---------------------------------------------------------------------------


def test_export_markdown_no_disclaimer() -> None:
    """Exported markdown must NOT contain any disclaimer text."""
    ctx = MarketContext(
        ticker="AAPL",
        current_price=Decimal("185.50"),
        price_52w_high=Decimal("199.62"),
        price_52w_low=Decimal("164.08"),
        iv_rank=45.2,
        iv_percentile=52.1,
        atm_iv_30d=28.5,
        rsi_14=62.3,
        macd_signal=MacdSignal.BULLISH_CROSSOVER,
        put_call_ratio=0.85,
        next_earnings=None,
        dte_target=45,
        target_strike=Decimal("190.00"),
        target_delta=0.35,
        sector="Information Technology",
        dividend_yield=0.005,
        exercise_style=ExerciseStyle.AMERICAN,
        data_timestamp=datetime(2026, 2, 24, 14, 30, 0, tzinfo=UTC),
    )
    bull = AgentResponse(
        agent_name="bull",
        direction=SignalDirection.BULLISH,
        confidence=0.72,
        argument="RSI bullish.",
        key_points=["RSI up"],
        risks_cited=["Earnings"],
        contracts_referenced=["AAPL $190 CALL"],
        model_used="test",
    )
    bear = AgentResponse(
        agent_name="bear",
        direction=SignalDirection.BEARISH,
        confidence=0.55,
        argument="IV elevated.",
        key_points=["IV high"],
        risks_cited=["Momentum"],
        contracts_referenced=["AAPL $180 PUT"],
        model_used="test",
    )
    thesis = TradeThesis(
        ticker="AAPL",
        direction=SignalDirection.BULLISH,
        confidence=0.65,
        summary="Moderate bullish case.",
        bull_score=7.2,
        bear_score=4.5,
        key_factors=["Momentum"],
        risk_assessment="Moderate risk.",
        recommended_strategy=None,
    )
    result = DebateResult(
        context=ctx,
        bull_response=bull,
        bear_response=bear,
        thesis=thesis,
        total_usage=RunUsage(),
        duration_ms=1500,
        is_fallback=False,
    )

    md = export_debate_markdown(result)

    assert "DISCLAIMER" not in md
    assert "does not constitute" not in md.lower()
    assert "investment advice" not in md.lower()
    # Ensure the report still has meaningful content
    assert "## Bull Case" in md
    assert "## Bear Case" in md
    assert "## Verdict" in md


def test_rendering_module_has_no_disclaimer() -> None:
    """The cli.rendering module no longer exports a DISCLAIMER constant."""
    import options_arena.cli.rendering as rendering_mod  # noqa: PLC0415

    assert not hasattr(rendering_mod, "DISCLAIMER")


def test_debate_export_module_has_no_disclaimer() -> None:
    """The reporting.debate_export module no longer exports a DISCLAIMER constant."""
    import options_arena.reporting.debate_export as export_mod  # noqa: PLC0415

    assert not hasattr(export_mod, "DISCLAIMER")

"""Tests for IntelligenceService wiring in CLI debate commands.

Mirrors test_debate_openbb.py pattern -- verifies --no-recon flag routing,
IntelligenceService creation/cleanup lifecycle, and fetch_intelligence passthrough
to run_debate.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import typer
from pydantic_ai.usage import RunUsage
from typer.testing import CliRunner

from options_arena.agents._parsing import DebateResult
from options_arena.cli.app import app
from options_arena.models import (
    AgentResponse,
    IndicatorSignals,
    MarketContext,
    SignalDirection,
    TickerScore,
    TradeThesis,
)
from options_arena.models.enums import ExerciseStyle, MacdSignal, ScanPreset
from options_arena.models.intelligence import IntelligencePackage
from options_arena.models.scan import ScanRun

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ticker_score(ticker: str = "AAPL", score: float = 75.0) -> TickerScore:
    """Create a TickerScore for testing."""
    return TickerScore(
        ticker=ticker,
        composite_score=score,
        direction=SignalDirection.BULLISH,
        signals=IndicatorSignals(rsi=65.0),
        scan_run_id=1,
    )


def _make_scan_run() -> ScanRun:
    """Create a ScanRun for testing."""
    return ScanRun(
        id=1,
        started_at=datetime(2026, 3, 1, 10, 0, 0, tzinfo=UTC),
        completed_at=datetime(2026, 3, 1, 10, 5, 0, tzinfo=UTC),
        preset=ScanPreset.SP500,
        tickers_scanned=500,
        tickers_scored=50,
        recommendations=5,
    )


def _make_debate_result(ticker: str = "AAPL") -> DebateResult:
    """Create a minimal DebateResult for testing."""
    bull = AgentResponse(
        agent_name="bull",
        direction=SignalDirection.BULLISH,
        confidence=0.72,
        argument="RSI at 65 indicates bullish momentum.",
        key_points=["RSI trending up"],
        risks_cited=["Earnings next week"],
        contracts_referenced=[f"{ticker} $190 CALL"],
        model_used="test",
    )
    bear = AgentResponse(
        agent_name="bear",
        direction=SignalDirection.BEARISH,
        confidence=0.55,
        argument="IV is elevated, limiting upside.",
        key_points=["IV elevated"],
        risks_cited=["Potential reversal"],
        contracts_referenced=[f"{ticker} $190 CALL"],
        model_used="test",
    )
    thesis = TradeThesis(
        ticker=ticker,
        direction=SignalDirection.BULLISH,
        confidence=0.65,
        summary="Moderate bullish case.",
        bull_score=7.2,
        bear_score=4.5,
        key_factors=["Momentum"],
        risk_assessment="Moderate risk.",
    )
    ctx = MarketContext(
        ticker=ticker,
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
        data_timestamp=datetime(2026, 3, 2, 14, 30, 0, tzinfo=UTC),
    )
    return DebateResult(
        context=ctx,
        bull_response=bull,
        bear_response=bear,
        thesis=thesis,
        total_usage=RunUsage(),
        duration_ms=1500,
        is_fallback=False,
    )


def _make_intelligence_package(ticker: str = "AAPL") -> IntelligencePackage:
    """Create a minimal IntelligencePackage for testing."""
    return IntelligencePackage(
        ticker=ticker,
        analyst=None,
        analyst_activity=None,
        insider=None,
        institutional=None,
        news_headlines=["Headline 1", "Headline 2"],
        fetched_at=datetime(2026, 3, 2, 14, 0, 0, tzinfo=UTC),
    )


# ---------------------------------------------------------------------------
# CLI routing tests for --no-recon
# ---------------------------------------------------------------------------


class TestDebateCommandReconFlag:
    """Tests for the --no-recon CLI flag routing."""

    @patch("options_arena.cli.commands._debate_async", new_callable=AsyncMock)
    def test_no_recon_flag_passes_to_debate_async(self, mock_debate_async: AsyncMock) -> None:
        """--no-recon flag passes no_recon=True to _debate_async."""
        mock_debate_async.return_value = None
        result = runner.invoke(app, ["debate", "AAPL", "--no-recon"])
        assert result.exit_code == 0
        mock_debate_async.assert_awaited_once()
        call_kwargs = mock_debate_async.call_args.kwargs
        assert call_kwargs["no_recon"] is True

    @patch("options_arena.cli.commands._debate_async", new_callable=AsyncMock)
    def test_recon_enabled_by_default(self, mock_debate_async: AsyncMock) -> None:
        """Without --no-recon, no_recon defaults to False."""
        mock_debate_async.return_value = None
        result = runner.invoke(app, ["debate", "AAPL"])
        assert result.exit_code == 0
        call_kwargs = mock_debate_async.call_args.kwargs
        assert call_kwargs["no_recon"] is False

    @patch("options_arena.cli.commands._batch_async", new_callable=AsyncMock)
    def test_no_recon_flag_passes_to_batch_async(self, mock_batch_async: AsyncMock) -> None:
        """--no-recon flag passes no_recon=True to _batch_async."""
        mock_batch_async.return_value = None
        result = runner.invoke(app, ["debate", "--batch", "--no-recon"])
        assert result.exit_code == 0
        mock_batch_async.assert_awaited_once()
        call_kwargs = mock_batch_async.call_args.kwargs
        assert call_kwargs["no_recon"] is True


# ---------------------------------------------------------------------------
# _debate_async -- IntelligenceService creation and lifecycle
# ---------------------------------------------------------------------------


class TestDebateAsyncIntelligence:
    """Tests for IntelligenceService lifecycle in _debate_async."""

    @pytest.mark.asyncio
    @patch("options_arena.cli.commands._debate_single", new_callable=AsyncMock)
    @patch("options_arena.cli.commands.FredService")
    @patch("options_arena.cli.commands.OptionsDataService")
    @patch("options_arena.cli.commands.MarketDataService")
    @patch("options_arena.cli.commands.Repository")
    @patch("options_arena.cli.commands.Database")
    @patch("options_arena.cli.commands.ServiceCache")
    @patch("options_arena.cli.commands.RateLimiter")
    @patch("options_arena.cli.commands.OpenBBService")
    @patch("options_arena.cli.commands.IntelligenceService")
    async def test_creates_intelligence_service_when_enabled(
        self,
        mock_intel_cls: MagicMock,
        mock_openbb_cls: MagicMock,
        mock_limiter_cls: MagicMock,
        mock_cache_cls: MagicMock,
        mock_db_cls: MagicMock,
        mock_repo_cls: MagicMock,
        mock_market_cls: MagicMock,
        mock_options_cls: MagicMock,
        mock_fred_cls: MagicMock,
        mock_debate_single: AsyncMock,
    ) -> None:
        """_debate_async creates IntelligenceService when enabled."""
        from options_arena.cli.commands import _debate_async

        mock_db = AsyncMock()
        mock_db_cls.return_value = mock_db

        mock_repo = AsyncMock()
        mock_repo.get_latest_scan.return_value = _make_scan_run()
        mock_repo.get_scores_for_scan.return_value = [_make_ticker_score()]
        mock_repo_cls.return_value = mock_repo

        mock_cache = AsyncMock()
        mock_cache_cls.return_value = mock_cache
        mock_market_cls.return_value = AsyncMock()
        mock_options_cls.return_value = AsyncMock()
        mock_fred_cls.return_value = AsyncMock()

        mock_intel_svc = AsyncMock()
        mock_intel_cls.return_value = mock_intel_svc

        mock_debate_single.return_value = _make_debate_result()

        await _debate_async(
            "AAPL", history=False, fallback_only=False, no_openbb=True, no_recon=False
        )

        mock_intel_cls.assert_called_once()

    @pytest.mark.asyncio
    @patch("options_arena.cli.commands._debate_single", new_callable=AsyncMock)
    @patch("options_arena.cli.commands.FredService")
    @patch("options_arena.cli.commands.OptionsDataService")
    @patch("options_arena.cli.commands.MarketDataService")
    @patch("options_arena.cli.commands.Repository")
    @patch("options_arena.cli.commands.Database")
    @patch("options_arena.cli.commands.ServiceCache")
    @patch("options_arena.cli.commands.RateLimiter")
    @patch("options_arena.cli.commands.OpenBBService")
    @patch("options_arena.cli.commands.IntelligenceService")
    async def test_skips_intelligence_when_no_recon(
        self,
        mock_intel_cls: MagicMock,
        mock_openbb_cls: MagicMock,
        mock_limiter_cls: MagicMock,
        mock_cache_cls: MagicMock,
        mock_db_cls: MagicMock,
        mock_repo_cls: MagicMock,
        mock_market_cls: MagicMock,
        mock_options_cls: MagicMock,
        mock_fred_cls: MagicMock,
        mock_debate_single: AsyncMock,
    ) -> None:
        """--no-recon prevents IntelligenceService creation."""
        from options_arena.cli.commands import _debate_async

        mock_db = AsyncMock()
        mock_db_cls.return_value = mock_db

        mock_repo = AsyncMock()
        mock_repo.get_latest_scan.return_value = _make_scan_run()
        mock_repo.get_scores_for_scan.return_value = [_make_ticker_score()]
        mock_repo_cls.return_value = mock_repo

        mock_cache = AsyncMock()
        mock_cache_cls.return_value = mock_cache
        mock_market_cls.return_value = AsyncMock()
        mock_options_cls.return_value = AsyncMock()
        mock_fred_cls.return_value = AsyncMock()

        mock_debate_single.return_value = _make_debate_result()

        await _debate_async(
            "AAPL", history=False, fallback_only=False, no_openbb=True, no_recon=True
        )

        mock_intel_cls.assert_not_called()

    @pytest.mark.asyncio
    @patch("options_arena.cli.commands._debate_single", new_callable=AsyncMock)
    @patch("options_arena.cli.commands.FredService")
    @patch("options_arena.cli.commands.OptionsDataService")
    @patch("options_arena.cli.commands.MarketDataService")
    @patch("options_arena.cli.commands.Repository")
    @patch("options_arena.cli.commands.Database")
    @patch("options_arena.cli.commands.ServiceCache")
    @patch("options_arena.cli.commands.RateLimiter")
    @patch("options_arena.cli.commands.OpenBBService")
    @patch("options_arena.cli.commands.IntelligenceService")
    async def test_skips_intelligence_when_config_disabled(
        self,
        mock_intel_cls: MagicMock,
        mock_openbb_cls: MagicMock,
        mock_limiter_cls: MagicMock,
        mock_cache_cls: MagicMock,
        mock_db_cls: MagicMock,
        mock_repo_cls: MagicMock,
        mock_market_cls: MagicMock,
        mock_options_cls: MagicMock,
        mock_fred_cls: MagicMock,
        mock_debate_single: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """IntelligenceConfig.enabled=False prevents service creation."""
        from options_arena.cli.commands import _debate_async

        monkeypatch.setenv("ARENA_INTELLIGENCE__ENABLED", "false")

        mock_db = AsyncMock()
        mock_db_cls.return_value = mock_db

        mock_repo = AsyncMock()
        mock_repo.get_latest_scan.return_value = _make_scan_run()
        mock_repo.get_scores_for_scan.return_value = [_make_ticker_score()]
        mock_repo_cls.return_value = mock_repo

        mock_cache = AsyncMock()
        mock_cache_cls.return_value = mock_cache
        mock_market_cls.return_value = AsyncMock()
        mock_options_cls.return_value = AsyncMock()
        mock_fred_cls.return_value = AsyncMock()

        mock_debate_single.return_value = _make_debate_result()

        await _debate_async(
            "AAPL", history=False, fallback_only=False, no_openbb=True, no_recon=False
        )

        mock_intel_cls.assert_not_called()

    @pytest.mark.asyncio
    @patch("options_arena.cli.commands._debate_single", new_callable=AsyncMock)
    @patch("options_arena.cli.commands.FredService")
    @patch("options_arena.cli.commands.OptionsDataService")
    @patch("options_arena.cli.commands.MarketDataService")
    @patch("options_arena.cli.commands.Repository")
    @patch("options_arena.cli.commands.Database")
    @patch("options_arena.cli.commands.ServiceCache")
    @patch("options_arena.cli.commands.RateLimiter")
    @patch("options_arena.cli.commands.OpenBBService")
    @patch("options_arena.cli.commands.IntelligenceService")
    async def test_intelligence_service_closed_on_success(
        self,
        mock_intel_cls: MagicMock,
        mock_openbb_cls: MagicMock,
        mock_limiter_cls: MagicMock,
        mock_cache_cls: MagicMock,
        mock_db_cls: MagicMock,
        mock_repo_cls: MagicMock,
        mock_market_cls: MagicMock,
        mock_options_cls: MagicMock,
        mock_fred_cls: MagicMock,
        mock_debate_single: AsyncMock,
    ) -> None:
        """close() is called on IntelligenceService after successful debate."""
        from options_arena.cli.commands import _debate_async

        mock_db = AsyncMock()
        mock_db_cls.return_value = mock_db

        mock_repo = AsyncMock()
        mock_repo.get_latest_scan.return_value = _make_scan_run()
        mock_repo.get_scores_for_scan.return_value = [_make_ticker_score()]
        mock_repo_cls.return_value = mock_repo

        mock_cache = AsyncMock()
        mock_cache_cls.return_value = mock_cache
        mock_market_cls.return_value = AsyncMock()
        mock_options_cls.return_value = AsyncMock()
        mock_fred_cls.return_value = AsyncMock()

        mock_intel_svc = AsyncMock()
        mock_intel_cls.return_value = mock_intel_svc

        mock_debate_single.return_value = _make_debate_result()

        await _debate_async(
            "AAPL", history=False, fallback_only=False, no_openbb=True, no_recon=False
        )

        mock_intel_svc.close.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("options_arena.cli.commands._debate_single", new_callable=AsyncMock)
    @patch("options_arena.cli.commands.FredService")
    @patch("options_arena.cli.commands.OptionsDataService")
    @patch("options_arena.cli.commands.MarketDataService")
    @patch("options_arena.cli.commands.Repository")
    @patch("options_arena.cli.commands.Database")
    @patch("options_arena.cli.commands.ServiceCache")
    @patch("options_arena.cli.commands.RateLimiter")
    @patch("options_arena.cli.commands.OpenBBService")
    @patch("options_arena.cli.commands.IntelligenceService")
    async def test_intelligence_service_closed_on_error(
        self,
        mock_intel_cls: MagicMock,
        mock_openbb_cls: MagicMock,
        mock_limiter_cls: MagicMock,
        mock_cache_cls: MagicMock,
        mock_db_cls: MagicMock,
        mock_repo_cls: MagicMock,
        mock_market_cls: MagicMock,
        mock_options_cls: MagicMock,
        mock_fred_cls: MagicMock,
        mock_debate_single: AsyncMock,
    ) -> None:
        """close() is called even when debate raises."""
        from options_arena.cli.commands import _debate_async

        mock_db = AsyncMock()
        mock_db_cls.return_value = mock_db

        mock_repo = AsyncMock()
        mock_repo.get_latest_scan.return_value = _make_scan_run()
        mock_repo.get_scores_for_scan.return_value = [_make_ticker_score()]
        mock_repo_cls.return_value = mock_repo

        mock_cache = AsyncMock()
        mock_cache_cls.return_value = mock_cache
        mock_market_cls.return_value = AsyncMock()
        mock_options_cls.return_value = AsyncMock()
        mock_fred_cls.return_value = AsyncMock()

        mock_intel_svc = AsyncMock()
        mock_intel_cls.return_value = mock_intel_svc

        mock_debate_single.side_effect = RuntimeError("LLM connection refused")

        with pytest.raises(typer.Exit):
            await _debate_async(
                "AAPL",
                history=False,
                fallback_only=False,
                no_openbb=True,
                no_recon=False,
            )

        mock_intel_svc.close.assert_awaited_once()


# ---------------------------------------------------------------------------
# _debate_single -- intelligence fetch and passthrough
# ---------------------------------------------------------------------------


class TestDebateSingleIntelligence:
    """Tests for intelligence data flow in _debate_single."""

    @pytest.mark.asyncio
    @patch("options_arena.agents.run_debate", new_callable=AsyncMock)
    @patch("options_arena.scoring.compute_dimensional_scores")
    @patch("options_arena.cli.commands.recommend_contracts")
    @patch("options_arena.cli.commands.compute_indicators")
    @patch("options_arena.cli.commands.ohlcv_to_dataframe")
    async def test_fetches_intelligence_when_service_present(
        self,
        mock_ohlcv_to_df: MagicMock,
        mock_compute_ind: MagicMock,
        mock_recommend: MagicMock,
        mock_dim_scores: MagicMock,
        mock_run_debate: AsyncMock,
    ) -> None:
        """_debate_single calls fetch_intelligence when intelligence_svc is not None."""
        from options_arena.cli.commands import _debate_single
        from options_arena.models.config import AppSettings

        mock_ohlcv_to_df.return_value = MagicMock()
        mock_compute_ind.return_value = IndicatorSignals(rsi=65.0)
        mock_recommend.return_value = []
        mock_dim_scores.return_value = None
        mock_run_debate.return_value = _make_debate_result()

        mock_market_data = AsyncMock()
        mock_market_data.fetch_quote = AsyncMock(return_value=MagicMock())
        mock_market_data.fetch_ticker_info = AsyncMock(
            return_value=MagicMock(current_price=Decimal("185.00"), dividend_yield=0.005)
        )
        mock_market_data.fetch_ohlcv = AsyncMock(return_value=[])

        mock_options_data = AsyncMock()
        mock_options_data.fetch_chain_all_expirations = AsyncMock(return_value=[])

        mock_fred = AsyncMock()
        mock_fred.fetch_risk_free_rate = AsyncMock(return_value=0.045)

        mock_repo = AsyncMock()

        intel_pkg = _make_intelligence_package()
        mock_intel_svc = AsyncMock()
        mock_intel_svc.fetch_intelligence = AsyncMock(return_value=intel_pkg)

        await _debate_single(
            ticker_score=_make_ticker_score(),
            settings=AppSettings(),
            market_data=mock_market_data,
            options_data=mock_options_data,
            fred=mock_fred,
            repo=mock_repo,
            openbb_svc=None,
            intelligence_svc=mock_intel_svc,
        )

        mock_intel_svc.fetch_intelligence.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("options_arena.agents.run_debate", new_callable=AsyncMock)
    @patch("options_arena.scoring.compute_dimensional_scores")
    @patch("options_arena.cli.commands.recommend_contracts")
    @patch("options_arena.cli.commands.compute_indicators")
    @patch("options_arena.cli.commands.ohlcv_to_dataframe")
    async def test_passes_intelligence_to_run_debate(
        self,
        mock_ohlcv_to_df: MagicMock,
        mock_compute_ind: MagicMock,
        mock_recommend: MagicMock,
        mock_dim_scores: MagicMock,
        mock_run_debate: AsyncMock,
    ) -> None:
        """IntelligencePackage passed to run_debate via intelligence kwarg."""
        from options_arena.cli.commands import _debate_single
        from options_arena.models.config import AppSettings

        mock_ohlcv_to_df.return_value = MagicMock()
        mock_compute_ind.return_value = IndicatorSignals(rsi=65.0)
        mock_recommend.return_value = []
        mock_dim_scores.return_value = None
        mock_run_debate.return_value = _make_debate_result()

        mock_market_data = AsyncMock()
        mock_market_data.fetch_quote = AsyncMock(return_value=MagicMock())
        mock_market_data.fetch_ticker_info = AsyncMock(
            return_value=MagicMock(current_price=Decimal("185.00"), dividend_yield=0.005)
        )
        mock_market_data.fetch_ohlcv = AsyncMock(return_value=[])

        mock_options_data = AsyncMock()
        mock_options_data.fetch_chain_all_expirations = AsyncMock(return_value=[])

        mock_fred = AsyncMock()
        mock_fred.fetch_risk_free_rate = AsyncMock(return_value=0.045)

        mock_repo = AsyncMock()

        intel_pkg = _make_intelligence_package()
        mock_intel_svc = AsyncMock()
        mock_intel_svc.fetch_intelligence = AsyncMock(return_value=intel_pkg)

        await _debate_single(
            ticker_score=_make_ticker_score(),
            settings=AppSettings(),
            market_data=mock_market_data,
            options_data=mock_options_data,
            fred=mock_fred,
            repo=mock_repo,
            openbb_svc=None,
            intelligence_svc=mock_intel_svc,
        )

        call_kwargs = mock_run_debate.call_args.kwargs
        assert call_kwargs["intelligence"] is intel_pkg

    @pytest.mark.asyncio
    @patch("options_arena.agents.run_debate", new_callable=AsyncMock)
    @patch("options_arena.scoring.compute_dimensional_scores")
    @patch("options_arena.cli.commands.recommend_contracts")
    @patch("options_arena.cli.commands.compute_indicators")
    @patch("options_arena.cli.commands.ohlcv_to_dataframe")
    async def test_intelligence_none_when_service_absent(
        self,
        mock_ohlcv_to_df: MagicMock,
        mock_compute_ind: MagicMock,
        mock_recommend: MagicMock,
        mock_dim_scores: MagicMock,
        mock_run_debate: AsyncMock,
    ) -> None:
        """intelligence=None passed to run_debate when service is None."""
        from options_arena.cli.commands import _debate_single
        from options_arena.models.config import AppSettings

        mock_ohlcv_to_df.return_value = MagicMock()
        mock_compute_ind.return_value = IndicatorSignals(rsi=65.0)
        mock_recommend.return_value = []
        mock_dim_scores.return_value = None
        mock_run_debate.return_value = _make_debate_result()

        mock_market_data = AsyncMock()
        mock_market_data.fetch_quote = AsyncMock(return_value=MagicMock())
        mock_market_data.fetch_ticker_info = AsyncMock(
            return_value=MagicMock(current_price=Decimal("185.00"), dividend_yield=0.005)
        )
        mock_market_data.fetch_ohlcv = AsyncMock(return_value=[])

        mock_options_data = AsyncMock()
        mock_options_data.fetch_chain_all_expirations = AsyncMock(return_value=[])

        mock_fred = AsyncMock()
        mock_fred.fetch_risk_free_rate = AsyncMock(return_value=0.045)

        mock_repo = AsyncMock()

        await _debate_single(
            ticker_score=_make_ticker_score(),
            settings=AppSettings(),
            market_data=mock_market_data,
            options_data=mock_options_data,
            fred=mock_fred,
            repo=mock_repo,
            openbb_svc=None,
            intelligence_svc=None,
        )

        call_kwargs = mock_run_debate.call_args.kwargs
        assert call_kwargs["intelligence"] is None


# ---------------------------------------------------------------------------
# _batch_async -- IntelligenceService creation for batch mode
# ---------------------------------------------------------------------------


class TestBatchAsyncIntelligence:
    """Tests for IntelligenceService lifecycle in _batch_async."""

    @pytest.mark.asyncio
    @patch("options_arena.cli.commands._debate_single", new_callable=AsyncMock)
    @patch("options_arena.cli.commands.FredService")
    @patch("options_arena.cli.commands.OptionsDataService")
    @patch("options_arena.cli.commands.MarketDataService")
    @patch("options_arena.cli.commands.Repository")
    @patch("options_arena.cli.commands.Database")
    @patch("options_arena.cli.commands.ServiceCache")
    @patch("options_arena.cli.commands.RateLimiter")
    @patch("options_arena.cli.commands.OpenBBService")
    @patch("options_arena.cli.commands.IntelligenceService")
    async def test_batch_creates_intelligence_service(
        self,
        mock_intel_cls: MagicMock,
        mock_openbb_cls: MagicMock,
        mock_limiter_cls: MagicMock,
        mock_cache_cls: MagicMock,
        mock_db_cls: MagicMock,
        mock_repo_cls: MagicMock,
        mock_market_cls: MagicMock,
        mock_options_cls: MagicMock,
        mock_fred_cls: MagicMock,
        mock_debate_single: AsyncMock,
    ) -> None:
        """_batch_async creates IntelligenceService when enabled."""
        from options_arena.cli.commands import _batch_async

        mock_db = AsyncMock()
        mock_db_cls.return_value = mock_db

        mock_repo = AsyncMock()
        mock_repo.get_latest_scan.return_value = _make_scan_run()
        mock_repo.get_scores_for_scan.return_value = [_make_ticker_score()]
        mock_repo_cls.return_value = mock_repo

        mock_cache = AsyncMock()
        mock_cache_cls.return_value = mock_cache
        mock_market_cls.return_value = AsyncMock()
        mock_options_cls.return_value = AsyncMock()
        mock_fred_cls.return_value = AsyncMock()

        mock_intel_svc = AsyncMock()
        mock_intel_cls.return_value = mock_intel_svc

        mock_debate_single.return_value = _make_debate_result()

        await _batch_async(batch_limit=1, fallback_only=False, no_openbb=True, no_recon=False)

        mock_intel_cls.assert_called_once()
        mock_intel_svc.close.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("options_arena.cli.commands._debate_single", new_callable=AsyncMock)
    @patch("options_arena.cli.commands.FredService")
    @patch("options_arena.cli.commands.OptionsDataService")
    @patch("options_arena.cli.commands.MarketDataService")
    @patch("options_arena.cli.commands.Repository")
    @patch("options_arena.cli.commands.Database")
    @patch("options_arena.cli.commands.ServiceCache")
    @patch("options_arena.cli.commands.RateLimiter")
    @patch("options_arena.cli.commands.OpenBBService")
    @patch("options_arena.cli.commands.IntelligenceService")
    async def test_batch_skips_intelligence_when_no_recon(
        self,
        mock_intel_cls: MagicMock,
        mock_openbb_cls: MagicMock,
        mock_limiter_cls: MagicMock,
        mock_cache_cls: MagicMock,
        mock_db_cls: MagicMock,
        mock_repo_cls: MagicMock,
        mock_market_cls: MagicMock,
        mock_options_cls: MagicMock,
        mock_fred_cls: MagicMock,
        mock_debate_single: AsyncMock,
    ) -> None:
        """no_recon=True prevents IntelligenceService creation in batch."""
        from options_arena.cli.commands import _batch_async

        mock_db = AsyncMock()
        mock_db_cls.return_value = mock_db

        mock_repo = AsyncMock()
        mock_repo.get_latest_scan.return_value = _make_scan_run()
        mock_repo.get_scores_for_scan.return_value = [_make_ticker_score()]
        mock_repo_cls.return_value = mock_repo

        mock_cache = AsyncMock()
        mock_cache_cls.return_value = mock_cache
        mock_market_cls.return_value = AsyncMock()
        mock_options_cls.return_value = AsyncMock()
        mock_fred_cls.return_value = AsyncMock()

        mock_debate_single.return_value = _make_debate_result()

        await _batch_async(batch_limit=1, fallback_only=False, no_openbb=True, no_recon=True)

        mock_intel_cls.assert_not_called()

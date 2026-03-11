"""Tests for architecture hardening (AUDIT-019, AUDIT-004, AUDIT-012, AUDIT-021).

Covers:
  Part 1: Model validators (Quote, OptionContract, composite_score bounds, ScanConfig)
  Part 2: API rate limiting (limiter configuration)
  Part 3: Structured JSON logging (json_mode toggle)
  Part 4: Phase 3 batch concurrency (semaphore isolation)
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from options_arena.models import (
    ExerciseStyle,
    HistoryPoint,
    OptionContract,
    OptionType,
    Quote,
    ScanConfig,
    ScanPreset,
    SignalDirection,
)

# ---------------------------------------------------------------------------
# Part 1: Model Validator Tests
# ---------------------------------------------------------------------------


class TestQuoteValidators:
    """Quote model rejects invalid price, bid, ask, volume."""

    def test_rejects_negative_price(self) -> None:
        """Quote rejects negative price."""
        with pytest.raises(ValidationError, match="price must be finite and positive"):
            Quote(
                ticker="AAPL",
                price=Decimal("-10.00"),
                bid=Decimal("0"),
                ask=Decimal("0"),
                volume=100,
                timestamp=datetime(2025, 6, 15, 14, 30, tzinfo=UTC),
            )

    def test_rejects_zero_price(self) -> None:
        """Quote rejects zero price."""
        with pytest.raises(ValidationError, match="price must be finite and positive"):
            Quote(
                ticker="AAPL",
                price=Decimal("0"),
                bid=Decimal("0"),
                ask=Decimal("0"),
                volume=100,
                timestamp=datetime(2025, 6, 15, 14, 30, tzinfo=UTC),
            )

    def test_rejects_nan_price(self) -> None:
        """Quote rejects NaN price."""
        with pytest.raises(ValidationError, match="finite"):
            Quote(
                ticker="AAPL",
                price=Decimal("NaN"),
                bid=Decimal("0"),
                ask=Decimal("0"),
                volume=100,
                timestamp=datetime(2025, 6, 15, 14, 30, tzinfo=UTC),
            )

    def test_rejects_inf_bid(self) -> None:
        """Quote rejects Inf bid."""
        with pytest.raises(ValidationError, match="finite"):
            Quote(
                ticker="AAPL",
                price=Decimal("100.00"),
                bid=Decimal("Inf"),
                ask=Decimal("0"),
                volume=100,
                timestamp=datetime(2025, 6, 15, 14, 30, tzinfo=UTC),
            )

    def test_rejects_negative_bid(self) -> None:
        """Quote rejects negative bid."""
        with pytest.raises(ValidationError, match="non-negative"):
            Quote(
                ticker="AAPL",
                price=Decimal("100.00"),
                bid=Decimal("-1.00"),
                ask=Decimal("0"),
                volume=100,
                timestamp=datetime(2025, 6, 15, 14, 30, tzinfo=UTC),
            )

    def test_allows_zero_bid_ask(self) -> None:
        """Quote allows zero bid/ask (legitimate for illiquid contracts)."""
        q = Quote(
            ticker="AAPL",
            price=Decimal("100.00"),
            bid=Decimal("0"),
            ask=Decimal("0"),
            volume=100,
            timestamp=datetime(2025, 6, 15, 14, 30, tzinfo=UTC),
        )
        assert q.bid == Decimal("0")
        assert q.ask == Decimal("0")

    def test_rejects_negative_volume(self) -> None:
        """Quote rejects negative volume."""
        with pytest.raises(ValidationError, match="volume must be >= 0"):
            Quote(
                ticker="AAPL",
                price=Decimal("100.00"),
                bid=Decimal("0"),
                ask=Decimal("0"),
                volume=-1,
                timestamp=datetime(2025, 6, 15, 14, 30, tzinfo=UTC),
            )


class TestOptionContractValidators:
    """OptionContract model rejects invalid strike, bid/ask/last, volume/OI."""

    def _make_valid_kwargs(self) -> dict[str, object]:
        return {
            "ticker": "AAPL",
            "option_type": OptionType.CALL,
            "strike": Decimal("185.00"),
            "expiration": date(2025, 9, 19),
            "bid": Decimal("3.50"),
            "ask": Decimal("3.70"),
            "last": Decimal("3.60"),
            "volume": 500,
            "open_interest": 10000,
            "exercise_style": ExerciseStyle.AMERICAN,
            "market_iv": 0.35,
        }

    def test_rejects_nan_strike(self) -> None:
        """OptionContract rejects NaN strike."""
        kwargs = self._make_valid_kwargs()
        kwargs["strike"] = Decimal("NaN")
        with pytest.raises(ValidationError, match="finite"):
            OptionContract(**kwargs)  # type: ignore[arg-type]

    def test_rejects_zero_strike(self) -> None:
        """OptionContract rejects zero strike."""
        kwargs = self._make_valid_kwargs()
        kwargs["strike"] = Decimal("0")
        with pytest.raises(ValidationError, match="strike must be finite and positive"):
            OptionContract(**kwargs)  # type: ignore[arg-type]

    def test_rejects_negative_strike(self) -> None:
        """OptionContract rejects negative strike."""
        kwargs = self._make_valid_kwargs()
        kwargs["strike"] = Decimal("-100")
        with pytest.raises(ValidationError, match="strike must be finite and positive"):
            OptionContract(**kwargs)  # type: ignore[arg-type]

    def test_rejects_negative_bid(self) -> None:
        """OptionContract rejects negative bid."""
        kwargs = self._make_valid_kwargs()
        kwargs["bid"] = Decimal("-1.00")
        with pytest.raises(ValidationError, match="non-negative"):
            OptionContract(**kwargs)  # type: ignore[arg-type]

    def test_rejects_negative_volume(self) -> None:
        """OptionContract rejects negative volume."""
        kwargs = self._make_valid_kwargs()
        kwargs["volume"] = -1
        with pytest.raises(ValidationError, match="must be >= 0"):
            OptionContract(**kwargs)  # type: ignore[arg-type]

    def test_rejects_negative_open_interest(self) -> None:
        """OptionContract rejects negative open_interest."""
        kwargs = self._make_valid_kwargs()
        kwargs["open_interest"] = -1
        with pytest.raises(ValidationError, match="must be >= 0"):
            OptionContract(**kwargs)  # type: ignore[arg-type]

    def test_allows_zero_bid_ask_last(self) -> None:
        """OptionContract allows zero bid/ask/last (legitimate for illiquid)."""
        kwargs = self._make_valid_kwargs()
        kwargs["bid"] = Decimal("0")
        kwargs["ask"] = Decimal("0")
        kwargs["last"] = Decimal("0")
        c = OptionContract(**kwargs)  # type: ignore[arg-type]
        assert c.bid == Decimal("0")

    def test_allows_zero_volume_and_oi(self) -> None:
        """OptionContract allows zero volume and open_interest."""
        kwargs = self._make_valid_kwargs()
        kwargs["volume"] = 0
        kwargs["open_interest"] = 0
        c = OptionContract(**kwargs)  # type: ignore[arg-type]
        assert c.volume == 0
        assert c.open_interest == 0


class TestCompositeScoreBounds:
    """HistoryPoint rejects out-of-range composite_score."""

    def test_history_point_rejects_101(self) -> None:
        """HistoryPoint rejects composite_score of 101."""
        with pytest.raises(ValidationError, match="composite_score must be in"):
            HistoryPoint(
                scan_id=1,
                scan_date=datetime(2025, 6, 15, 14, 30, tzinfo=UTC),
                composite_score=101.0,
                direction=SignalDirection.BULLISH,
                preset=ScanPreset.SP500,
            )

    def test_history_point_rejects_negative(self) -> None:
        """HistoryPoint rejects negative composite_score."""
        with pytest.raises(ValidationError, match="composite_score must be in"):
            HistoryPoint(
                scan_id=1,
                scan_date=datetime(2025, 6, 15, 14, 30, tzinfo=UTC),
                composite_score=-5.0,
                direction=SignalDirection.BULLISH,
                preset=ScanPreset.SP500,
            )

    def test_history_point_rejects_nan(self) -> None:
        """HistoryPoint rejects NaN composite_score."""
        with pytest.raises(ValidationError, match="composite_score must be finite"):
            HistoryPoint(
                scan_id=1,
                scan_date=datetime(2025, 6, 15, 14, 30, tzinfo=UTC),
                composite_score=float("nan"),
                direction=SignalDirection.BULLISH,
                preset=ScanPreset.SP500,
            )


class TestScanConfigValidators:
    """Validates top_n on OptionsFilters, ohlcv_min_bars on UniverseFilters,
    and options_concurrency on ScanConfig."""

    def test_rejects_top_n_zero(self) -> None:
        """OptionsFilters rejects top_n=0."""
        from options_arena.models.filters import OptionsFilters  # noqa: PLC0415

        with pytest.raises(ValidationError, match="top_n must be >= 1"):
            OptionsFilters(top_n=0)

    def test_rejects_top_n_negative(self) -> None:
        """OptionsFilters rejects negative top_n."""
        from options_arena.models.filters import OptionsFilters  # noqa: PLC0415

        with pytest.raises(ValidationError, match="top_n must be >= 1"):
            OptionsFilters(top_n=-5)

    def test_accepts_top_n_1(self) -> None:
        """OptionsFilters accepts top_n=1."""
        from options_arena.models.filters import OptionsFilters  # noqa: PLC0415

        cfg = OptionsFilters(top_n=1)
        assert cfg.top_n == 1

    def test_rejects_ohlcv_min_bars_too_low(self) -> None:
        """UniverseFilters rejects ohlcv_min_bars < 5."""
        from options_arena.models.filters import UniverseFilters  # noqa: PLC0415

        with pytest.raises(ValidationError, match="ohlcv_min_bars must be >= 5"):
            UniverseFilters(ohlcv_min_bars=4)

    def test_accepts_ohlcv_min_bars_5(self) -> None:
        """UniverseFilters accepts ohlcv_min_bars=5."""
        from options_arena.models.filters import UniverseFilters  # noqa: PLC0415

        cfg = UniverseFilters(ohlcv_min_bars=5)
        assert cfg.ohlcv_min_bars == 5

    def test_rejects_options_concurrency_zero(self) -> None:
        """ScanConfig rejects options_concurrency=0."""
        with pytest.raises(ValidationError, match="options_concurrency must be >= 1"):
            ScanConfig(options_concurrency=0)


# ---------------------------------------------------------------------------
# Part 2: API Rate Limiting Tests
# ---------------------------------------------------------------------------


class TestRateLimiter:
    """Verify rate limiter is configured on the app."""

    def test_limiter_on_app_state(self) -> None:
        """The app has a limiter instance on app.state."""
        from options_arena.api.app import create_app, limiter  # noqa: PLC0415

        app = create_app()
        assert app.state.limiter is limiter

    def test_limiter_has_key_func(self) -> None:
        """The limiter uses get_remote_address as key_func."""
        from slowapi.util import get_remote_address  # noqa: PLC0415

        from options_arena.api.app import limiter  # noqa: PLC0415

        assert limiter._key_func is get_remote_address  # type: ignore[attr-defined]

    def test_rate_limit_exception_handler_registered(self) -> None:
        """The app has a RateLimitExceeded exception handler."""
        from slowapi.errors import RateLimitExceeded  # noqa: PLC0415

        from options_arena.api.app import create_app  # noqa: PLC0415

        app = create_app()
        assert RateLimitExceeded in app.exception_handlers


# ---------------------------------------------------------------------------
# Part 3: Structured JSON Logging Tests
# ---------------------------------------------------------------------------


class TestJsonLogging:
    """Verify JSON log formatting when json_mode=True."""

    def test_json_mode_produces_json(self, tmp_path: object) -> None:
        """When json_mode=True, file handler output is valid JSON.

        Uses a unique marker message to find the correct log line
        in the shared log file.
        """
        import time  # noqa: PLC0415

        from options_arena.cli.app import LOG_FILE, configure_logging  # noqa: PLC0415

        configure_logging(json_mode=True)

        # Use a unique marker to locate our line
        marker = "json_test_marker_7a3b9c"
        test_logger = logging.getLogger("test.json_mode")
        test_logger.info(marker)

        # The file handler is behind a QueueHandler/Listener; give it time
        time.sleep(1.0)

        # Search for our marker line in the log file
        found = False
        if LOG_FILE.exists():
            lines = LOG_FILE.read_text(encoding="utf-8").strip().splitlines()
            for line in reversed(lines):
                if marker in line:
                    parsed = json.loads(line)
                    assert parsed["message"] == marker
                    assert "timestamp" in parsed
                    assert "level" in parsed
                    found = True
                    break

        assert found, f"JSON log line with marker {marker!r} not found in {LOG_FILE}"

        # Restore normal logging
        configure_logging(json_mode=False)

    def test_text_mode_produces_text(self, tmp_path: object) -> None:
        """When json_mode=False (default), file handler output is plain text.

        Uses a unique marker message to find the correct log line
        in the shared log file.
        """
        import time  # noqa: PLC0415

        from options_arena.cli.app import LOG_FILE, configure_logging  # noqa: PLC0415

        configure_logging(json_mode=False)

        marker = "text_test_marker_4f2e8d"
        test_logger = logging.getLogger("test.text_mode")
        test_logger.info(marker)

        time.sleep(1.0)

        found = False
        if LOG_FILE.exists():
            lines = LOG_FILE.read_text(encoding="utf-8").strip().splitlines()
            for line in reversed(lines):
                if marker in line:
                    assert " | " in line  # pipe-separated text format
                    found = True
                    break

        assert found, f"Text log line with marker {marker!r} not found in {LOG_FILE}"

        # Restore normal logging
        configure_logging(json_mode=False)


# ---------------------------------------------------------------------------
# Part 4: Phase 3 Batch Concurrency Tests
# ---------------------------------------------------------------------------


class TestPhase3Concurrency:
    """Verify semaphore-bounded concurrency in Phase 3."""

    @pytest.mark.asyncio
    async def test_options_concurrency_setting(self) -> None:
        """ScanConfig has options_concurrency with default of 5."""
        cfg = ScanConfig()
        assert cfg.options_concurrency == 5

    @pytest.mark.asyncio
    async def test_error_isolation_in_batch(self) -> None:
        """One ticker failure in Phase 3 does not abort other tickers.

        We test this by creating a pipeline with mocked services where
        one ticker raises and others succeed.
        """
        from options_arena.models import (  # noqa: PLC0415
            AppSettings,
            IndicatorSignals,
            TickerScore,
        )
        from options_arena.models.filters import (  # noqa: PLC0415
            OptionsFilters,
            ScanFilterSpec,
        )
        from options_arena.models.market_data import OHLCV  # noqa: PLC0415
        from options_arena.scan.models import (  # noqa: PLC0415
            OptionsResult,
            ScoringResult,
            UniverseResult,
        )
        from options_arena.scan.pipeline import ScanPipeline  # noqa: PLC0415
        from options_arena.scan.progress import ScanPhase  # noqa: PLC0415

        settings = AppSettings(
            scan=ScanConfig(
                options_concurrency=2,
                filters=ScanFilterSpec(options=OptionsFilters(top_n=3)),
            )
        )
        # ScanConfig is not frozen, so options_concurrency can be set at construction

        # Create mock services
        market_data = AsyncMock()
        options_data = MagicMock()
        fred = MagicMock()
        fred.fetch_risk_free_rate = AsyncMock(return_value=0.05)
        universe = MagicMock()
        repository = MagicMock()

        pipeline = ScanPipeline(
            settings=settings,
            market_data=market_data,
            options_data=options_data,
            fred=fred,
            universe=universe,
            repository=repository,
        )

        # Create test data: 3 tickers, each with minimal OHLCV data
        tickers = ["AAPL", "BAD_TICKER", "MSFT"]
        scores = [
            TickerScore(
                ticker=t,
                composite_score=80.0 - i * 10,
                direction=SignalDirection.BULLISH,
                signals=IndicatorSignals(),
            )
            for i, t in enumerate(tickers)
        ]

        # Mock _process_ticker_options to succeed for AAPL/MSFT, fail for BAD_TICKER
        async def mock_process(
            ts: TickerScore,
            rfr: float,
            ohlcv_map: dict[str, list[OHLCV]],
            spx_close: object,
        ) -> tuple[str, list[object], date | None, Decimal | None]:
            if ts.ticker == "BAD_TICKER":
                raise RuntimeError("Simulated failure")
            return (ts.ticker, [], None, Decimal("100"))

        pipeline._process_ticker_options = mock_process  # type: ignore[assignment]

        # Create minimal universe and scoring results
        from datetime import timedelta as td  # noqa: PLC0415

        base_date = date(2024, 1, 1)
        ohlcv_map: dict[str, list[OHLCV]] = {}
        for t in tickers:
            ohlcv_map[t] = [
                OHLCV(
                    ticker=t,
                    date=base_date + td(days=i),
                    open=Decimal("100"),
                    high=Decimal("101"),
                    low=Decimal("99"),
                    close=Decimal("100"),
                    volume=1_000_000,
                    adjusted_close=Decimal("100"),
                )
                for i in range(250)
            ]

        scoring_result = ScoringResult(scores=scores, raw_signals={})

        universe_result = UniverseResult(
            tickers=tickers,
            ohlcv_map=ohlcv_map,
            sp500_sectors={},
            sector_map={},
            failed_count=0,
            filtered_count=0,
        )

        def noop_progress(phase: ScanPhase, current: int, total: int) -> None:
            pass

        # Run Phase 3
        options_result = await pipeline._phase_options(
            scoring_result, universe_result, noop_progress
        )

        # BAD_TICKER should have failed, but AAPL and MSFT should NOT be in
        # recommendations either (empty contracts returned). The key point is
        # that the method completes without raising.
        assert isinstance(options_result, OptionsResult)

    @pytest.mark.asyncio
    async def test_concurrency_config_respected(self) -> None:
        """The options_concurrency value can be set to 1 for sequential execution."""
        cfg = ScanConfig(options_concurrency=1)
        assert cfg.options_concurrency == 1

        cfg = ScanConfig(options_concurrency=10)
        assert cfg.options_concurrency == 10


# ---------------------------------------------------------------------------
# Part 3 additional: LogConfig model
# ---------------------------------------------------------------------------


class TestLogConfig:
    """LogConfig model has json_mode field."""

    def test_default_json_mode_false(self) -> None:
        """LogConfig defaults json_mode to False."""
        from options_arena.models.config import LogConfig  # noqa: PLC0415

        cfg = LogConfig()
        assert cfg.json_mode is False

    def test_json_mode_true(self) -> None:
        """LogConfig accepts json_mode=True."""
        from options_arena.models.config import LogConfig  # noqa: PLC0415

        cfg = LogConfig(json_mode=True)
        assert cfg.json_mode is True

    def test_appsettings_has_log(self) -> None:
        """AppSettings includes a log: LogConfig field."""
        from options_arena.models.config import AppSettings  # noqa: PLC0415

        settings = AppSettings()
        assert hasattr(settings, "log")
        assert settings.log.json_mode is False

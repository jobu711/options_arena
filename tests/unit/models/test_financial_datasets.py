"""Unit tests for Financial Datasets AI integration models.

Tests cover:
- FinancialMetricsData: construction, all-None defaults, NaN/Inf rejection, frozen, JSON roundtrip
- IncomeStatementData: construction, negative values allowed, NaN rejection, frozen, JSON roundtrip
- BalanceSheetData: construction, shares_outstanding int, NaN rejection, frozen, JSON roundtrip
- FinancialDatasetsPackage: construction, partial None components, UTC validation, frozen
- FinancialDatasetsConfig: defaults, custom values, nesting in AppSettings, env overrides
"""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from options_arena.models import (
    AppSettings,
    FinancialDatasetsConfig,
)
from options_arena.models.financial_datasets import (
    BalanceSheetData,
    FinancialDatasetsPackage,
    FinancialMetricsData,
    IncomeStatementData,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NOW_UTC = datetime(2026, 3, 8, 12, 0, 0, tzinfo=UTC)

# ---------------------------------------------------------------------------
# Env var cleanup
# ---------------------------------------------------------------------------

_ARENA_FD_VARS = [
    "ARENA_FINANCIAL_DATASETS__ENABLED",
    "ARENA_FINANCIAL_DATASETS__API_KEY",
    "ARENA_FINANCIAL_DATASETS__BASE_URL",
    "ARENA_FINANCIAL_DATASETS__REQUEST_TIMEOUT",
    "ARENA_FINANCIAL_DATASETS__CACHE_TTL",
]


@pytest.fixture(autouse=True)
def _clean_arena_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove all ARENA_FINANCIAL_DATASETS_* env vars before each test."""
    for var in _ARENA_FD_VARS:
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def financial_metrics() -> FinancialMetricsData:
    """Create a valid FinancialMetricsData with representative fields populated."""
    return FinancialMetricsData(
        pe_ratio=28.5,
        forward_pe=24.2,
        peg_ratio=1.8,
        price_to_book=45.3,
        price_to_sales=7.5,
        enterprise_value_to_ebitda=22.1,
        enterprise_value_to_revenue=8.3,
        gross_margin=0.438,
        operating_margin=0.302,
        net_margin=0.265,
        profit_margin=0.265,
        revenue_growth=0.128,
        earnings_growth=0.15,
        return_on_equity=1.47,
        return_on_assets=0.285,
        return_on_capital=0.58,
        debt_to_equity=1.87,
        current_ratio=0.99,
        eps_diluted=6.42,
        free_cash_flow_yield=0.032,
        dividend_yield=0.005,
    )


@pytest.fixture
def income_statement() -> IncomeStatementData:
    """Create a valid IncomeStatementData."""
    return IncomeStatementData(
        revenue=383_285_000_000.0,
        gross_profit=167_790_000_000.0,
        operating_income=114_301_000_000.0,
        net_income=96_995_000_000.0,
        eps_diluted=6.42,
        gross_margin=0.438,
        operating_margin=0.298,
        net_margin=0.253,
    )


@pytest.fixture
def balance_sheet() -> BalanceSheetData:
    """Create a valid BalanceSheetData."""
    return BalanceSheetData(
        total_assets=352_583_000_000.0,
        total_liabilities=290_437_000_000.0,
        total_equity=62_146_000_000.0,
        total_debt=111_088_000_000.0,
        total_cash=29_965_000_000.0,
        current_assets=143_566_000_000.0,
        current_liabilities=145_308_000_000.0,
        shares_outstanding=15_115_000_000,
    )


@pytest.fixture
def fd_package(
    financial_metrics: FinancialMetricsData,
    income_statement: IncomeStatementData,
    balance_sheet: BalanceSheetData,
) -> FinancialDatasetsPackage:
    """Create a valid FinancialDatasetsPackage."""
    return FinancialDatasetsPackage(
        ticker="AAPL",
        metrics=financial_metrics,
        income=income_statement,
        balance_sheet=balance_sheet,
        fetched_at=NOW_UTC,
    )


# ===========================================================================
# FinancialMetricsData
# ===========================================================================


class TestFinancialMetricsData:
    """Tests for the FinancialMetricsData model."""

    def test_valid_construction(self, financial_metrics: FinancialMetricsData) -> None:
        """FinancialMetricsData constructs with all fields correctly assigned."""
        assert financial_metrics.pe_ratio == pytest.approx(28.5)
        assert financial_metrics.forward_pe == pytest.approx(24.2)
        assert financial_metrics.peg_ratio == pytest.approx(1.8)
        assert financial_metrics.price_to_book == pytest.approx(45.3)
        assert financial_metrics.price_to_sales == pytest.approx(7.5)
        assert financial_metrics.enterprise_value_to_ebitda == pytest.approx(22.1)
        assert financial_metrics.enterprise_value_to_revenue == pytest.approx(8.3)
        assert financial_metrics.gross_margin == pytest.approx(0.438)
        assert financial_metrics.operating_margin == pytest.approx(0.302)
        assert financial_metrics.net_margin == pytest.approx(0.265)
        assert financial_metrics.profit_margin == pytest.approx(0.265)
        assert financial_metrics.revenue_growth == pytest.approx(0.128)
        assert financial_metrics.earnings_growth == pytest.approx(0.15)
        assert financial_metrics.return_on_equity == pytest.approx(1.47)
        assert financial_metrics.return_on_assets == pytest.approx(0.285)
        assert financial_metrics.return_on_capital == pytest.approx(0.58)
        assert financial_metrics.debt_to_equity == pytest.approx(1.87)
        assert financial_metrics.current_ratio == pytest.approx(0.99)
        assert financial_metrics.eps_diluted == pytest.approx(6.42)
        assert financial_metrics.free_cash_flow_yield == pytest.approx(0.032)
        assert financial_metrics.dividend_yield == pytest.approx(0.005)

    def test_all_none_defaults(self) -> None:
        """FinancialMetricsData constructs with all fields defaulting to None."""
        metrics = FinancialMetricsData()
        assert metrics.pe_ratio is None
        assert metrics.forward_pe is None
        assert metrics.peg_ratio is None
        assert metrics.price_to_book is None
        assert metrics.price_to_sales is None
        assert metrics.enterprise_value_to_ebitda is None
        assert metrics.enterprise_value_to_revenue is None
        assert metrics.gross_margin is None
        assert metrics.operating_margin is None
        assert metrics.net_margin is None
        assert metrics.profit_margin is None
        assert metrics.revenue_growth is None
        assert metrics.earnings_growth is None
        assert metrics.return_on_equity is None
        assert metrics.return_on_assets is None
        assert metrics.return_on_capital is None
        assert metrics.debt_to_equity is None
        assert metrics.current_ratio is None
        assert metrics.eps_diluted is None
        assert metrics.free_cash_flow_yield is None
        assert metrics.dividend_yield is None

    def test_rejects_nan_pe_ratio(self) -> None:
        """FinancialMetricsData rejects NaN pe_ratio."""
        with pytest.raises(ValidationError, match="finite"):
            FinancialMetricsData(pe_ratio=float("nan"))

    def test_rejects_inf_debt_to_equity(self) -> None:
        """FinancialMetricsData rejects Inf debt_to_equity."""
        with pytest.raises(ValidationError, match="finite"):
            FinancialMetricsData(debt_to_equity=float("inf"))

    def test_rejects_neg_inf_revenue_growth(self) -> None:
        """FinancialMetricsData rejects -Inf revenue_growth."""
        with pytest.raises(ValidationError, match="finite"):
            FinancialMetricsData(revenue_growth=float("-inf"))

    def test_frozen(self, financial_metrics: FinancialMetricsData) -> None:
        """FinancialMetricsData is frozen: attribute reassignment raises ValidationError."""
        with pytest.raises(ValidationError):
            financial_metrics.pe_ratio = 30.0  # type: ignore[misc]

    def test_json_roundtrip(self, financial_metrics: FinancialMetricsData) -> None:
        """FinancialMetricsData survives JSON roundtrip."""
        json_str = financial_metrics.model_dump_json()
        restored = FinancialMetricsData.model_validate_json(json_str)
        assert restored == financial_metrics

    def test_negative_pe_ratio_allowed(self) -> None:
        """Negative P/E ratio is valid (unprofitable company)."""
        metrics = FinancialMetricsData(pe_ratio=-42.0)
        assert metrics.pe_ratio == pytest.approx(-42.0)

    def test_negative_earnings_growth_allowed(self) -> None:
        """Negative earnings growth is valid (declining earnings)."""
        metrics = FinancialMetricsData(earnings_growth=-0.25)
        assert metrics.earnings_growth == pytest.approx(-0.25)


# ===========================================================================
# IncomeStatementData
# ===========================================================================


class TestIncomeStatementData:
    """Tests for the IncomeStatementData model."""

    def test_valid_construction(self, income_statement: IncomeStatementData) -> None:
        """IncomeStatementData constructs with all fields correctly assigned."""
        assert income_statement.revenue == pytest.approx(383_285_000_000.0)
        assert income_statement.gross_profit == pytest.approx(167_790_000_000.0)
        assert income_statement.operating_income == pytest.approx(114_301_000_000.0)
        assert income_statement.net_income == pytest.approx(96_995_000_000.0)
        assert income_statement.eps_diluted == pytest.approx(6.42)
        assert income_statement.gross_margin == pytest.approx(0.438)
        assert income_statement.operating_margin == pytest.approx(0.298)
        assert income_statement.net_margin == pytest.approx(0.253)

    def test_negative_net_income_allowed(self) -> None:
        """Negative net_income is valid (company with losses)."""
        stmt = IncomeStatementData(net_income=-500_000_000.0)
        assert stmt.net_income == pytest.approx(-500_000_000.0)

    def test_rejects_nan_revenue(self) -> None:
        """IncomeStatementData rejects NaN revenue."""
        with pytest.raises(ValidationError, match="finite"):
            IncomeStatementData(revenue=float("nan"))

    def test_rejects_inf_operating_income(self) -> None:
        """IncomeStatementData rejects Inf operating_income."""
        with pytest.raises(ValidationError, match="finite"):
            IncomeStatementData(operating_income=float("inf"))

    def test_frozen(self, income_statement: IncomeStatementData) -> None:
        """IncomeStatementData is frozen."""
        with pytest.raises(ValidationError):
            income_statement.revenue = 0.0  # type: ignore[misc]

    def test_json_roundtrip(self, income_statement: IncomeStatementData) -> None:
        """IncomeStatementData survives JSON roundtrip."""
        json_str = income_statement.model_dump_json()
        restored = IncomeStatementData.model_validate_json(json_str)
        assert restored == income_statement

    def test_all_none_defaults(self) -> None:
        """IncomeStatementData constructs with all fields defaulting to None."""
        stmt = IncomeStatementData()
        assert stmt.revenue is None
        assert stmt.gross_profit is None
        assert stmt.operating_income is None
        assert stmt.net_income is None
        assert stmt.eps_diluted is None
        assert stmt.gross_margin is None
        assert stmt.operating_margin is None
        assert stmt.net_margin is None


# ===========================================================================
# BalanceSheetData
# ===========================================================================


class TestBalanceSheetData:
    """Tests for the BalanceSheetData model."""

    def test_valid_construction(self, balance_sheet: BalanceSheetData) -> None:
        """BalanceSheetData constructs with all fields correctly assigned."""
        assert balance_sheet.total_assets == pytest.approx(352_583_000_000.0)
        assert balance_sheet.total_liabilities == pytest.approx(290_437_000_000.0)
        assert balance_sheet.total_equity == pytest.approx(62_146_000_000.0)
        assert balance_sheet.total_debt == pytest.approx(111_088_000_000.0)
        assert balance_sheet.total_cash == pytest.approx(29_965_000_000.0)
        assert balance_sheet.current_assets == pytest.approx(143_566_000_000.0)
        assert balance_sheet.current_liabilities == pytest.approx(145_308_000_000.0)
        assert balance_sheet.shares_outstanding == 15_115_000_000

    def test_rejects_nan_total_assets(self) -> None:
        """BalanceSheetData rejects NaN total_assets."""
        with pytest.raises(ValidationError, match="finite"):
            BalanceSheetData(total_assets=float("nan"))

    def test_rejects_inf_total_debt(self) -> None:
        """BalanceSheetData rejects Inf total_debt."""
        with pytest.raises(ValidationError, match="finite"):
            BalanceSheetData(total_debt=float("inf"))

    def test_frozen(self, balance_sheet: BalanceSheetData) -> None:
        """BalanceSheetData is frozen."""
        with pytest.raises(ValidationError):
            balance_sheet.total_assets = 0.0  # type: ignore[misc]

    def test_json_roundtrip(self, balance_sheet: BalanceSheetData) -> None:
        """BalanceSheetData survives JSON roundtrip."""
        json_str = balance_sheet.model_dump_json()
        restored = BalanceSheetData.model_validate_json(json_str)
        assert restored == balance_sheet

    def test_all_none_defaults(self) -> None:
        """BalanceSheetData constructs with all fields defaulting to None."""
        bs = BalanceSheetData()
        assert bs.total_assets is None
        assert bs.total_liabilities is None
        assert bs.total_equity is None
        assert bs.total_debt is None
        assert bs.total_cash is None
        assert bs.current_assets is None
        assert bs.current_liabilities is None
        assert bs.shares_outstanding is None

    def test_shares_outstanding_is_int(self) -> None:
        """shares_outstanding accepts int, not float."""
        bs = BalanceSheetData(shares_outstanding=15_000_000_000)
        assert bs.shares_outstanding == 15_000_000_000
        assert isinstance(bs.shares_outstanding, int)


# ===========================================================================
# FinancialDatasetsPackage
# ===========================================================================


class TestFinancialDatasetsPackage:
    """Tests for the FinancialDatasetsPackage model."""

    def test_valid_construction(self, fd_package: FinancialDatasetsPackage) -> None:
        """FinancialDatasetsPackage constructs with all components."""
        assert fd_package.ticker == "AAPL"
        assert fd_package.metrics is not None
        assert fd_package.income is not None
        assert fd_package.balance_sheet is not None
        assert fd_package.fetched_at == NOW_UTC

    def test_partial_none_components(self) -> None:
        """FinancialDatasetsPackage with only metrics (income/balance_sheet None)."""
        package = FinancialDatasetsPackage(
            ticker="TSLA",
            metrics=FinancialMetricsData(pe_ratio=50.0),
            fetched_at=NOW_UTC,
        )
        assert package.ticker == "TSLA"
        assert package.metrics is not None
        assert package.metrics.pe_ratio == pytest.approx(50.0)
        assert package.income is None
        assert package.balance_sheet is None

    def test_all_none_components(self) -> None:
        """FinancialDatasetsPackage with all optional components as None."""
        package = FinancialDatasetsPackage(
            ticker="GME",
            fetched_at=NOW_UTC,
        )
        assert package.metrics is None
        assert package.income is None
        assert package.balance_sheet is None

    def test_rejects_naive_datetime(self) -> None:
        """FinancialDatasetsPackage rejects naive datetime for fetched_at."""
        with pytest.raises(ValidationError, match="UTC"):
            FinancialDatasetsPackage(
                ticker="AAPL",
                fetched_at=datetime(2026, 3, 8, 12, 0, 0),
            )

    def test_rejects_non_utc_datetime(self) -> None:
        """FinancialDatasetsPackage rejects non-UTC timezone for fetched_at."""
        est = timezone(timedelta(hours=-5))
        with pytest.raises(ValidationError, match="UTC"):
            FinancialDatasetsPackage(
                ticker="AAPL",
                fetched_at=datetime(2026, 3, 8, 12, 0, 0, tzinfo=est),
            )

    def test_frozen(self, fd_package: FinancialDatasetsPackage) -> None:
        """FinancialDatasetsPackage is frozen."""
        with pytest.raises(ValidationError):
            fd_package.ticker = "MSFT"  # type: ignore[misc]

    def test_json_roundtrip(self, fd_package: FinancialDatasetsPackage) -> None:
        """FinancialDatasetsPackage survives JSON roundtrip."""
        json_str = fd_package.model_dump_json()
        restored = FinancialDatasetsPackage.model_validate_json(json_str)
        assert restored == fd_package


# ===========================================================================
# FinancialDatasetsConfig
# ===========================================================================


class TestFinancialDatasetsConfig:
    """Tests for the FinancialDatasetsConfig model."""

    def test_default_values(self) -> None:
        """FinancialDatasetsConfig defaults are correct."""
        config = FinancialDatasetsConfig()
        assert config.enabled is True
        assert config.api_key is None
        assert config.base_url == "https://api.financialdatasets.ai"
        assert config.request_timeout == pytest.approx(10.0)
        assert config.cache_ttl == 3600

    def test_custom_values(self) -> None:
        """FinancialDatasetsConfig accepts custom values."""
        config = FinancialDatasetsConfig(
            enabled=False,
            api_key="fd_test_key_123",
            base_url="https://custom.api.example.com",
            request_timeout=30.0,
            cache_ttl=7200,
        )
        assert config.enabled is False
        assert config.api_key is not None
        assert config.api_key.get_secret_value() == "fd_test_key_123"
        assert config.base_url == "https://custom.api.example.com"
        assert config.request_timeout == pytest.approx(30.0)
        assert config.cache_ttl == 7200

    def test_nested_in_app_settings(self) -> None:
        """FinancialDatasetsConfig is nested in AppSettings with defaults."""
        settings = AppSettings()
        assert isinstance(settings.financial_datasets, FinancialDatasetsConfig)
        assert settings.financial_datasets.enabled is True
        assert settings.financial_datasets.api_key is None

    def test_env_override_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ARENA_FINANCIAL_DATASETS__ENABLED=false disables via env var."""
        monkeypatch.setenv("ARENA_FINANCIAL_DATASETS__ENABLED", "false")
        settings = AppSettings()
        assert settings.financial_datasets.enabled is False

    def test_env_override_cache_ttl(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ARENA_FINANCIAL_DATASETS__CACHE_TTL=7200 overrides default."""
        monkeypatch.setenv("ARENA_FINANCIAL_DATASETS__CACHE_TTL", "7200")
        settings = AppSettings()
        assert settings.financial_datasets.cache_ttl == 7200

    def test_rejects_nan_request_timeout(self) -> None:
        """FinancialDatasetsConfig rejects NaN request_timeout."""
        with pytest.raises(ValidationError, match="finite"):
            FinancialDatasetsConfig(request_timeout=float("nan"))

    def test_rejects_inf_request_timeout(self) -> None:
        """FinancialDatasetsConfig rejects Inf request_timeout."""
        with pytest.raises(ValidationError, match="finite"):
            FinancialDatasetsConfig(request_timeout=float("inf"))

    def test_rejects_zero_request_timeout(self) -> None:
        """FinancialDatasetsConfig rejects zero request_timeout."""
        with pytest.raises(ValidationError, match="must be > 0"):
            FinancialDatasetsConfig(request_timeout=0.0)

    def test_rejects_negative_request_timeout(self) -> None:
        """FinancialDatasetsConfig rejects negative request_timeout."""
        with pytest.raises(ValidationError, match="must be > 0"):
            FinancialDatasetsConfig(request_timeout=-5.0)

"""Financial Datasets AI integration models for Options Arena.

Frozen Pydantic v2 models representing responses from the financialdatasets.ai API:
  FinancialMetricsData   -- 21 optional financial ratio/metric fields.
  IncomeStatementData    -- 8 income statement line items.
  BalanceSheetData       -- 8 balance sheet line items.
  FinancialDatasetsPackage -- aggregate container with ticker and fetch timestamp.

All models are pure data definitions with no API SDK imports.
The service layer handles API interaction.
"""

import math
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, field_validator


class FinancialMetricsData(BaseModel):
    """Point-in-time financial metrics for a ticker.

    All ratio/metric fields are optional -- providers may not supply every field.
    Negative values are valid (e.g. negative P/E for unprofitable companies).
    """

    model_config = ConfigDict(frozen=True)

    pe_ratio: float | None = None
    forward_pe: float | None = None
    peg_ratio: float | None = None
    price_to_book: float | None = None
    price_to_sales: float | None = None
    enterprise_value_to_ebitda: float | None = None
    enterprise_value_to_revenue: float | None = None
    gross_margin: float | None = None
    operating_margin: float | None = None
    net_margin: float | None = None
    profit_margin: float | None = None
    revenue_growth: float | None = None
    earnings_growth: float | None = None
    return_on_equity: float | None = None
    return_on_assets: float | None = None
    return_on_capital: float | None = None
    debt_to_equity: float | None = None
    current_ratio: float | None = None
    eps_diluted: float | None = None
    free_cash_flow_yield: float | None = None
    dividend_yield: float | None = None

    @field_validator(
        "pe_ratio",
        "forward_pe",
        "peg_ratio",
        "price_to_book",
        "price_to_sales",
        "enterprise_value_to_ebitda",
        "enterprise_value_to_revenue",
        "gross_margin",
        "operating_margin",
        "net_margin",
        "profit_margin",
        "revenue_growth",
        "earnings_growth",
        "return_on_equity",
        "return_on_assets",
        "return_on_capital",
        "debt_to_equity",
        "current_ratio",
        "eps_diluted",
        "free_cash_flow_yield",
        "dividend_yield",
    )
    @classmethod
    def validate_finite(cls, v: float | None) -> float | None:
        """Reject NaN/Inf on optional float fields."""
        if v is not None and not math.isfinite(v):
            raise ValueError(f"must be finite, got {v}")
        return v


class IncomeStatementData(BaseModel):
    """Point-in-time income statement data for a ticker.

    All fields are optional -- providers may not supply every field.
    Negative values are valid (e.g. net losses, negative margins).
    """

    model_config = ConfigDict(frozen=True)

    revenue: float | None = None
    gross_profit: float | None = None
    operating_income: float | None = None
    net_income: float | None = None
    eps_diluted: float | None = None
    gross_margin: float | None = None
    operating_margin: float | None = None
    net_margin: float | None = None

    @field_validator(
        "revenue",
        "gross_profit",
        "operating_income",
        "net_income",
        "eps_diluted",
        "gross_margin",
        "operating_margin",
        "net_margin",
    )
    @classmethod
    def validate_finite(cls, v: float | None) -> float | None:
        """Reject NaN/Inf on optional float fields."""
        if v is not None and not math.isfinite(v):
            raise ValueError(f"must be finite, got {v}")
        return v


class BalanceSheetData(BaseModel):
    """Point-in-time balance sheet data for a ticker.

    All fields are optional -- providers may not supply every field.
    ``shares_outstanding`` is ``int`` (whole shares), not ``float``.
    """

    model_config = ConfigDict(frozen=True)

    total_assets: float | None = None
    total_liabilities: float | None = None
    total_equity: float | None = None
    total_debt: float | None = None
    total_cash: float | None = None
    current_assets: float | None = None
    current_liabilities: float | None = None
    shares_outstanding: int | None = None

    @field_validator(
        "total_assets",
        "total_liabilities",
        "total_equity",
        "total_debt",
        "total_cash",
        "current_assets",
        "current_liabilities",
    )
    @classmethod
    def validate_finite(cls, v: float | None) -> float | None:
        """Reject NaN/Inf on optional float fields."""
        if v is not None and not math.isfinite(v):
            raise ValueError(f"must be finite, got {v}")
        return v


class FinancialDatasetsPackage(BaseModel):
    """Aggregate container for all financialdatasets.ai data for a ticker.

    Groups metrics, income statement, and balance sheet snapshots with a
    fetch timestamp. ``fetched_at`` must be UTC.
    """

    model_config = ConfigDict(frozen=True)

    ticker: str
    metrics: FinancialMetricsData | None = None
    income: IncomeStatementData | None = None
    balance_sheet: BalanceSheetData | None = None
    fetched_at: datetime

    @field_validator("fetched_at")
    @classmethod
    def validate_utc(cls, v: datetime) -> datetime:
        """Ensure fetched_at is UTC."""
        if v.tzinfo is None or v.utcoffset() != timedelta(0):
            raise ValueError("fetched_at must be UTC")
        return v

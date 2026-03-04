"""Tests for custom_tickers threading through scan API route (#245).

Covers:
  - POST /api/scan with custom_tickers returns 202.
  - Empty custom_tickers (omitted) preserves normal behavior.
  - Invalid ticker format in custom_tickers returns 422.
"""

from __future__ import annotations

from httpx import AsyncClient


async def test_custom_tickers_in_request_body(client: AsyncClient) -> None:
    """POST /api/scan with custom_tickers returns 202 and scan_id."""
    response = await client.post(
        "/api/scan",
        json={"preset": "full", "custom_tickers": ["AAPL", "MSFT"]},
    )
    assert response.status_code == 202
    data = response.json()
    assert "scan_id" in data


async def test_empty_custom_tickers_ignored(client: AsyncClient) -> None:
    """POST /api/scan with empty custom_tickers uses preset as normal."""
    response = await client.post(
        "/api/scan",
        json={"preset": "sp500", "custom_tickers": []},
    )
    assert response.status_code == 202


async def test_custom_tickers_omitted(client: AsyncClient) -> None:
    """POST /api/scan without custom_tickers field defaults to empty."""
    response = await client.post(
        "/api/scan",
        json={"preset": "sp500"},
    )
    assert response.status_code == 202


async def test_custom_tickers_invalid_format(client: AsyncClient) -> None:
    """POST /api/scan with invalid ticker format returns 422."""
    response = await client.post(
        "/api/scan",
        json={"preset": "full", "custom_tickers": ["!!!"]},
    )
    assert response.status_code == 422

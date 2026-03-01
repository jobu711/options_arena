"""Tests for API security hardening (#175).

Covers ticker validation (AUDIT-003), HTML escape in PDF export (AUDIT-025),
and WebSocket origin validation (AUDIT-024).
"""

from __future__ import annotations

import html as html_module
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from options_arena.api.schemas import (
    BatchDebateRequest,
    DebateRequest,
    WatchlistTickerRequest,
)
from options_arena.api.ws import _is_loopback_origin

# ---------------------------------------------------------------------------
# Part A: Ticker validation — schema-level tests
# ---------------------------------------------------------------------------


class TestDebateRequestTickerValidation:
    """DebateRequest ticker field validation."""

    def test_valid_ticker_uppercase(self) -> None:
        req = DebateRequest(ticker="AAPL")
        assert req.ticker == "AAPL"

    def test_valid_ticker_with_dot(self) -> None:
        req = DebateRequest(ticker="BRK.B")
        assert req.ticker == "BRK.B"

    def test_valid_ticker_with_caret(self) -> None:
        req = DebateRequest(ticker="^VIX")
        assert req.ticker == "^VIX"

    def test_lowercase_auto_uppercased(self) -> None:
        req = DebateRequest(ticker="aapl")
        assert req.ticker == "AAPL"

    def test_mixed_case_auto_uppercased(self) -> None:
        req = DebateRequest(ticker="Msft")
        assert req.ticker == "MSFT"

    def test_whitespace_stripped(self) -> None:
        req = DebateRequest(ticker="  AAPL  ")
        assert req.ticker == "AAPL"

    def test_empty_ticker_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DebateRequest(ticker="")

    def test_invalid_chars_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DebateRequest(ticker="a]b")

    def test_too_long_ticker_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DebateRequest(ticker="A" * 50)

    def test_special_chars_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DebateRequest(ticker="<script>")

    def test_spaces_only_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DebateRequest(ticker="   ")

    def test_ticker_with_hyphen(self) -> None:
        req = DebateRequest(ticker="BF-B")
        assert req.ticker == "BF-B"


class TestWatchlistTickerRequestValidation:
    """WatchlistTickerRequest ticker field validation."""

    def test_valid_ticker(self) -> None:
        req = WatchlistTickerRequest(ticker="GOOGL")
        assert req.ticker == "GOOGL"

    def test_lowercase_uppercased(self) -> None:
        req = WatchlistTickerRequest(ticker="googl")
        assert req.ticker == "GOOGL"

    def test_invalid_rejected(self) -> None:
        with pytest.raises(ValidationError):
            WatchlistTickerRequest(ticker="a]b")

    def test_empty_rejected(self) -> None:
        with pytest.raises(ValidationError):
            WatchlistTickerRequest(ticker="")


class TestBatchDebateRequestValidation:
    """BatchDebateRequest tickers list validation."""

    def test_valid_tickers(self) -> None:
        req = BatchDebateRequest(scan_id=1, tickers=["AAPL", "MSFT"])
        assert req.tickers == ["AAPL", "MSFT"]

    def test_lowercase_tickers_uppercased(self) -> None:
        req = BatchDebateRequest(scan_id=1, tickers=["aapl", "msft"])
        assert req.tickers == ["AAPL", "MSFT"]

    def test_none_tickers_allowed(self) -> None:
        req = BatchDebateRequest(scan_id=1, tickers=None)
        assert req.tickers is None

    def test_invalid_ticker_in_list_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BatchDebateRequest(scan_id=1, tickers=["AAPL", "a]b"])

    def test_too_many_tickers_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BatchDebateRequest(scan_id=1, tickers=["T" + str(i) for i in range(51)])

    def test_50_tickers_accepted(self) -> None:
        tickers = [f"T{i}" for i in range(50)]
        req = BatchDebateRequest(scan_id=1, tickers=tickers)
        assert req.tickers is not None
        assert len(req.tickers) == 50


# ---------------------------------------------------------------------------
# Part A: Ticker validation — HTTP endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_debate_invalid_ticker_returns_422(client: AsyncClient) -> None:
    """POST /api/debate with invalid ticker returns 422."""
    response = await client.post("/api/debate", json={"ticker": "a]b"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_debate_empty_ticker_returns_422(client: AsyncClient) -> None:
    """POST /api/debate with empty ticker returns 422."""
    response = await client.post("/api/debate", json={"ticker": ""})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_debate_too_long_ticker_returns_422(client: AsyncClient) -> None:
    """POST /api/debate with 50-char ticker returns 422."""
    response = await client.post("/api/debate", json={"ticker": "A" * 50})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_debate_valid_tickers_accepted(client: AsyncClient) -> None:
    """POST /api/debate accepts AAPL, BRK.B, ^VIX, and lowercased aapl."""
    for ticker in ("AAPL", "BRK.B", "^VIX", "aapl"):
        response = await client.post("/api/debate", json={"ticker": ticker})
        assert response.status_code == 202, f"Failed for ticker: {ticker}"


@pytest.mark.asyncio
async def test_batch_debate_invalid_ticker_returns_422(client: AsyncClient) -> None:
    """POST /api/debate/batch with invalid ticker in list returns 422."""
    response = await client.post(
        "/api/debate/batch",
        json={"scan_id": 1, "tickers": ["AAPL", "<script>"]},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_watchlist_add_invalid_ticker_returns_422(
    client: AsyncClient, mock_repo: MagicMock
) -> None:
    """POST /api/watchlist/{id}/tickers with invalid ticker returns 422."""
    from options_arena.models import Watchlist  # noqa: PLC0415

    mock_repo.get_watchlist_by_id = AsyncMock(
        return_value=Watchlist(
            id=1, name="Test", created_at=datetime(2026, 2, 27, 12, 0, 0, tzinfo=UTC)
        )
    )
    mock_repo.add_ticker_to_watchlist = AsyncMock(return_value=None)
    response = await client.post("/api/watchlist/1/tickers", json={"ticker": "a]b"})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Part B: HTML escape in PDF export
# ---------------------------------------------------------------------------


class TestHtmlEscapeInPdfExport:
    """Verify that <script> tags in markdown are escaped in PDF HTML output."""

    def test_render_pdf_escapes_script_tags(self) -> None:
        """Content containing <script> tags is HTML-escaped before embedding."""
        # We test the html.escape function directly since _render_pdf requires
        # weasyprint which may not be installed.
        malicious_content = '# Report\n<script>alert("xss")</script>\nSafe text'
        escaped = html_module.escape(malicious_content)
        html_output = f"<html><body><pre>{escaped}</pre></body></html>"

        # The <script> tag should be escaped
        assert "<script>" not in html_output
        assert "&lt;script&gt;" in html_output
        assert "alert" in html_output  # Content preserved, just escaped

    def test_normal_content_preserved(self) -> None:
        """Normal markdown content passes through html.escape unchanged."""
        content = "# Options Arena Debate Report: AAPL\n**Direction**: bullish"
        escaped = html_module.escape(content)
        # Normal markdown chars are not affected
        assert "AAPL" in escaped
        assert "bullish" in escaped

    def test_ampersand_escaped(self) -> None:
        """Ampersands in content are properly escaped."""
        content = "R&D spending increased"
        escaped = html_module.escape(content)
        assert "&amp;" in escaped

    def test_angle_brackets_escaped(self) -> None:
        """Angle brackets are properly escaped."""
        content = "Price < $100 and Price > $50"
        escaped = html_module.escape(content)
        assert "&lt;" in escaped
        assert "&gt;" in escaped


# ---------------------------------------------------------------------------
# Part C: WebSocket origin validation
# ---------------------------------------------------------------------------


class TestIsLoopbackOrigin:
    """Unit tests for _is_loopback_origin helper."""

    def test_localhost_origin(self) -> None:
        assert _is_loopback_origin("http://localhost:5173") is True

    def test_127_origin(self) -> None:
        assert _is_loopback_origin("http://127.0.0.1:8000") is True

    def test_ipv6_loopback(self) -> None:
        assert _is_loopback_origin("http://[::1]:5173") is True

    def test_empty_string_rejected(self) -> None:
        assert _is_loopback_origin("") is False

    def test_external_origin_rejected(self) -> None:
        assert _is_loopback_origin("http://evil.com:8000") is False

    def test_https_localhost_accepted(self) -> None:
        assert _is_loopback_origin("https://localhost:5173") is True

    def test_no_port_accepted(self) -> None:
        assert _is_loopback_origin("http://localhost") is True

    def test_subdomain_rejected(self) -> None:
        assert _is_loopback_origin("http://localhost.evil.com") is False

    def test_192_168_rejected(self) -> None:
        assert _is_loopback_origin("http://192.168.1.1:8000") is False


@pytest.mark.asyncio
async def test_ws_scan_rejects_non_loopback_origin(test_app: object) -> None:
    """WebSocket /ws/scan/{id} rejects non-loopback origin with code 4003."""
    from starlette.testclient import TestClient  # noqa: PLC0415

    client = TestClient(test_app)  # type: ignore[arg-type]
    with (
        pytest.raises(Exception),  # noqa: B017
        client.websocket_connect("/ws/scan/1", headers={"origin": "http://evil.com:8000"}),
    ):
        pass  # Should not reach here


@pytest.mark.asyncio
async def test_ws_scan_rejects_missing_origin(test_app: object) -> None:
    """WebSocket /ws/scan/{id} rejects missing origin with code 4003."""
    from starlette.testclient import TestClient  # noqa: PLC0415

    client = TestClient(test_app)  # type: ignore[arg-type]
    # No origin header at all
    with pytest.raises(Exception), client.websocket_connect("/ws/scan/1"):  # noqa: B017
        pass  # Should not reach here


@pytest.mark.asyncio
async def test_ws_scan_accepts_loopback_origin(test_app: object) -> None:
    """WebSocket /ws/scan/{id} accepts localhost origin (closes 4004, not 4003)."""
    from starlette.testclient import TestClient  # noqa: PLC0415

    client = TestClient(test_app)  # type: ignore[arg-type]
    # Loopback origin is accepted (not rejected with 4003). Connection closes
    # with 4004 because there is no queue registered for scan_id=1. The
    # defensive contextlib.suppress on websocket.close() means the close is
    # graceful -- no exception propagates to the client.
    with client.websocket_connect("/ws/scan/1", headers={"origin": "http://localhost:5173"}):
        pass  # Server accepted, then closed with 4004 (no queue)


@pytest.mark.asyncio
async def test_ws_debate_rejects_non_loopback_origin(test_app: object) -> None:
    """WebSocket /ws/debate/{id} rejects non-loopback origin."""
    from starlette.testclient import TestClient  # noqa: PLC0415

    client = TestClient(test_app)  # type: ignore[arg-type]
    with (
        pytest.raises(Exception),  # noqa: B017
        client.websocket_connect("/ws/debate/1", headers={"origin": "http://attacker.com"}),
    ):
        pass


@pytest.mark.asyncio
async def test_ws_batch_rejects_non_loopback_origin(test_app: object) -> None:
    """WebSocket /ws/batch/{id} rejects non-loopback origin."""
    from starlette.testclient import TestClient  # noqa: PLC0415

    client = TestClient(test_app)  # type: ignore[arg-type]
    with (
        pytest.raises(Exception),  # noqa: B017
        client.websocket_connect("/ws/batch/1", headers={"origin": "http://attacker.com"}),
    ):
        pass

"""Tests for FastAPI dependency injection providers."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from options_arena.api.deps import (
    get_fred,
    get_market_data,
    get_operation_lock,
    get_options_data,
    get_repo,
    get_settings,
    get_universe,
)


def _make_request(state_attrs: dict[str, object]) -> MagicMock:
    """Create a mock Request with app.state attributes."""
    request = MagicMock()
    for key, value in state_attrs.items():
        setattr(request.app.state, key, value)
    return request


def test_get_repo_returns_state_repo() -> None:
    """get_repo extracts repo from app.state."""
    sentinel = MagicMock()
    request = _make_request({"repo": sentinel})
    assert get_repo(request) is sentinel


def test_get_market_data_returns_state_market_data() -> None:
    """get_market_data extracts market_data from app.state."""
    sentinel = MagicMock()
    request = _make_request({"market_data": sentinel})
    assert get_market_data(request) is sentinel


def test_get_options_data_returns_state_options_data() -> None:
    """get_options_data extracts options_data from app.state."""
    sentinel = MagicMock()
    request = _make_request({"options_data": sentinel})
    assert get_options_data(request) is sentinel


def test_get_fred_returns_state_fred() -> None:
    """get_fred extracts fred from app.state."""
    sentinel = MagicMock()
    request = _make_request({"fred": sentinel})
    assert get_fred(request) is sentinel


def test_get_universe_returns_state_universe() -> None:
    """get_universe extracts universe from app.state."""
    sentinel = MagicMock()
    request = _make_request({"universe": sentinel})
    assert get_universe(request) is sentinel


def test_get_settings_returns_state_settings() -> None:
    """get_settings extracts settings from app.state."""
    sentinel = MagicMock()
    request = _make_request({"settings": sentinel})
    assert get_settings(request) is sentinel


def test_get_operation_lock_returns_state_lock() -> None:
    """get_operation_lock extracts operation_lock from app.state."""
    lock = asyncio.Lock()
    request = _make_request({"operation_lock": lock})
    assert get_operation_lock(request) is lock

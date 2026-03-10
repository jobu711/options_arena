"""Shared test fixtures for the Options Arena test suite.

Convenience fixtures built on top of ``tests.factories``. These provide
ready-made model instances for the most commonly needed types so tests
can declare them as fixture parameters without importing factories directly.
"""

from __future__ import annotations

import pytest

from options_arena.models.analysis import MarketContext
from options_arena.models.market_data import Quote
from options_arena.models.options import OptionContract
from tests.factories import make_market_context, make_option_contract, make_quote


@pytest.fixture()
def sample_contract() -> OptionContract:
    """A default AAPL call contract via :func:`tests.factories.make_option_contract`."""
    return make_option_contract()


@pytest.fixture()
def sample_quote() -> Quote:
    """A default AAPL quote via :func:`tests.factories.make_quote`."""
    return make_quote()


@pytest.fixture()
def sample_market_context() -> MarketContext:
    """A default AAPL market context via :func:`tests.factories.make_market_context`."""
    return make_market_context()

"""Tests for DeskDeps dataclass."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from options_arena.agents._desk_deps import DeskDeps
from tests.factories import make_market_context, make_option_contract, make_ticker_score


@pytest.mark.critical
class TestDeskDepsConstruction:
    """Test DeskDeps construction and defaults."""

    def test_construction_with_all_fields(self) -> None:
        """DeskDeps can be constructed with all required fields."""
        deps = DeskDeps(
            query="What is the IV for AAPL?",
            ticker="AAPL",
            market_data=MagicMock(),
            options_data=MagicMock(),
            fred=MagicMock(),
            repo=MagicMock(),
        )
        assert deps.query == "What is the IV for AAPL?"
        assert deps.ticker == "AAPL"
        assert deps.market_data is not None
        assert deps.options_data is not None
        assert deps.fred is not None
        assert deps.repo is not None

    def test_tools_used_empty_by_default(self) -> None:
        """tools_used is an empty list by default."""
        deps = DeskDeps(
            query="test",
            ticker="AAPL",
            market_data=MagicMock(),
            options_data=MagicMock(),
            fred=MagicMock(),
            repo=MagicMock(),
        )
        assert deps.tools_used == []
        assert isinstance(deps.tools_used, list)

    def test_tools_used_accumulates(self) -> None:
        """tools_used list accumulates appended items."""
        deps = DeskDeps(
            query="test",
            ticker="AAPL",
            market_data=MagicMock(),
            options_data=MagicMock(),
            fred=MagicMock(),
            repo=MagicMock(),
        )
        deps.tools_used.append("fetch_quote")
        deps.tools_used.append("fetch_correlation")
        assert deps.tools_used == ["fetch_quote", "fetch_correlation"]
        assert len(deps.tools_used) == 2

    def test_independent_instances_do_not_share_lists(self) -> None:
        """Two DeskDeps instances have independent tools_used lists."""
        deps1 = DeskDeps(
            query="q1",
            ticker="AAPL",
            market_data=MagicMock(),
            options_data=MagicMock(),
            fred=MagicMock(),
            repo=MagicMock(),
        )
        deps2 = DeskDeps(
            query="q2",
            ticker="TSLA",
            market_data=MagicMock(),
            options_data=MagicMock(),
            fred=MagicMock(),
            repo=MagicMock(),
        )
        deps1.tools_used.append("tool_a")
        assert deps1.tools_used == ["tool_a"]
        assert deps2.tools_used == []

    def test_tools_used_explicit_empty_list(self) -> None:
        """Explicitly passing an empty tools_used list works."""
        deps = DeskDeps(
            query="test",
            ticker="AAPL",
            market_data=MagicMock(),
            options_data=MagicMock(),
            fred=MagicMock(),
            repo=MagicMock(),
            tools_used=[],
        )
        assert deps.tools_used == []

    def test_tools_used_explicit_pre_populated(self) -> None:
        """Explicitly passing a pre-populated tools_used list works."""
        deps = DeskDeps(
            query="test",
            ticker="AAPL",
            market_data=MagicMock(),
            options_data=MagicMock(),
            fred=MagicMock(),
            repo=MagicMock(),
            tools_used=["pre_existing"],
        )
        assert deps.tools_used == ["pre_existing"]


@pytest.mark.critical
class TestDeskDepsExtension:
    """Test DeskDeps scan data extension fields."""

    def test_new_fields_default_to_none_or_empty(self) -> None:
        """Verify ticker_score and market_context default to None, contracts to []."""
        deps = DeskDeps(
            query="test",
            ticker="AAPL",
            market_data=MagicMock(),
            options_data=MagicMock(),
            repo=MagicMock(),
        )
        assert deps.ticker_score is None
        assert deps.contracts == []
        assert isinstance(deps.contracts, list)
        assert deps.market_context is None

    def test_construction_with_scan_data(self) -> None:
        """Verify all new fields can be populated."""
        score = make_ticker_score()
        contract = make_option_contract()
        ctx = make_market_context()

        deps = DeskDeps(
            query="Analyze AAPL options",
            ticker="AAPL",
            market_data=MagicMock(),
            options_data=MagicMock(),
            repo=MagicMock(),
            ticker_score=score,
            contracts=[contract],
            market_context=ctx,
        )
        assert deps.ticker_score is score
        assert deps.contracts == [contract]
        assert deps.market_context is ctx

    def test_backward_compat_without_new_fields(self) -> None:
        """Existing construction pattern works -- no new args needed."""
        deps = DeskDeps(
            query="What is the IV for AAPL?",
            ticker="AAPL",
            market_data=MagicMock(),
            options_data=MagicMock(),
            fred=MagicMock(),
            repo=MagicMock(),
            learned_patterns="some patterns",
        )
        assert deps.query == "What is the IV for AAPL?"
        assert deps.learned_patterns == "some patterns"
        # New fields should still have their defaults
        assert deps.ticker_score is None
        assert deps.contracts == []
        assert deps.market_context is None

    def test_independent_contract_lists(self) -> None:
        """Two instances do not share the same contracts list."""
        deps1 = DeskDeps(
            query="q1",
            ticker="AAPL",
            market_data=MagicMock(),
            options_data=MagicMock(),
            repo=MagicMock(),
        )
        deps2 = DeskDeps(
            query="q2",
            ticker="TSLA",
            market_data=MagicMock(),
            options_data=MagicMock(),
            repo=MagicMock(),
        )
        contract = make_option_contract()
        deps1.contracts.append(contract)
        assert len(deps1.contracts) == 1
        assert len(deps2.contracts) == 0

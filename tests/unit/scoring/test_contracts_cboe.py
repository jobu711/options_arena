"""Tests for three-tier Greeks resolution in scoring.contracts.compute_greeks().

Tier 1: Contract already has greeks (e.g. CBOE native) -> preserved, source=MARKET.
Tier 2: Contract has no greeks -> computed via pricing/dispatch, source=COMPUTED.
Tier 3: Local computation fails -> contract excluded.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from options_arena.models.enums import (
    GreeksSource,
    PricingModel,
)
from options_arena.models.options import OptionContract, OptionGreeks
from options_arena.scoring.contracts import compute_greeks
from tests.unit.scoring.conftest import make_contract


def _make_greeks(
    delta: float = 0.35,
    gamma: float = 0.05,
    theta: float = -0.05,
    vega: float = 0.10,
    rho: float = 0.01,
    pricing_model: PricingModel = PricingModel.BAW,
) -> OptionGreeks:
    """Create an OptionGreeks instance for testing."""
    return OptionGreeks(
        delta=delta,
        gamma=gamma,
        theta=theta,
        vega=vega,
        rho=rho,
        pricing_model=pricing_model,
    )


def _make_contract_with_greeks(
    greeks: OptionGreeks | None = None,
    greeks_source: GreeksSource | None = None,
    **kwargs: object,
) -> OptionContract:
    """Create a contract with pre-populated greeks and/or greeks_source.

    Uses ``make_contract`` from conftest, then ``model_copy`` to set the
    frozen ``greeks`` and ``greeks_source`` fields.
    """
    base = make_contract(**kwargs)  # type: ignore[arg-type]
    update: dict[str, object] = {}
    if greeks is not None:
        update["greeks"] = greeks
    if greeks_source is not None:
        update["greeks_source"] = greeks_source
    if update:
        return base.model_copy(update=update)
    return base


# Standard test parameters for compute_greeks Tier 2 calls
_SPOT = 150.0
_RATE = 0.05
_DIV = 0.01


class TestThreeTierGreeks:
    """Tests for three-tier Greeks resolution in compute_greeks()."""

    def test_tier1_cboe_greeks_preserved(self) -> None:
        """Tier 1: Contract with existing greeks should preserve them unchanged."""
        original_greeks = _make_greeks(delta=0.42, gamma=0.03, theta=-0.08, vega=0.15)
        contract = _make_contract_with_greeks(
            greeks=original_greeks,
            strike="150.00",
            dte_days=45,
            market_iv=0.30,
        )

        with patch("options_arena.scoring.contracts.option_greeks") as mock_greeks:
            result = compute_greeks([contract], _SPOT, _RATE, _DIV)

        assert len(result) == 1
        assert result[0].greeks is not None
        assert result[0].greeks.delta == pytest.approx(0.42, rel=1e-4)
        assert result[0].greeks.gamma == pytest.approx(0.03, rel=1e-4)
        assert result[0].greeks.theta == pytest.approx(-0.08, rel=1e-4)
        assert result[0].greeks.vega == pytest.approx(0.15, rel=1e-4)
        # pricing/dispatch should NOT have been called
        mock_greeks.assert_not_called()

    def test_tier1_sets_greeks_source_market(self) -> None:
        """Tier 1: Contract with greeks but no greeks_source gets MARKET."""
        original_greeks = _make_greeks(delta=0.35)
        contract = _make_contract_with_greeks(
            greeks=original_greeks,
            greeks_source=None,
            strike="150.00",
            dte_days=45,
        )
        assert contract.greeks_source is None

        result = compute_greeks([contract], _SPOT, _RATE, _DIV)

        assert len(result) == 1
        assert result[0].greeks_source == GreeksSource.MARKET

    def test_tier1_preserves_existing_greeks_source(self) -> None:
        """Tier 1: Contract with greeks AND existing greeks_source preserves the source."""
        original_greeks = _make_greeks(delta=0.35)
        contract = _make_contract_with_greeks(
            greeks=original_greeks,
            greeks_source=GreeksSource.COMPUTED,
            strike="150.00",
            dte_days=45,
        )

        result = compute_greeks([contract], _SPOT, _RATE, _DIV)

        assert len(result) == 1
        assert result[0].greeks_source == GreeksSource.COMPUTED
        # Greeks should be untouched
        assert result[0].greeks is not None
        assert result[0].greeks.delta == pytest.approx(0.35, rel=1e-4)

    def test_tier2_computes_locally(self) -> None:
        """Tier 2: Contract with no greeks should have Greeks computed via dispatch."""
        contract = make_contract(
            strike="150.00",
            market_iv=0.30,
            dte_days=45,
        )
        assert contract.greeks is None

        result = compute_greeks([contract], _SPOT, _RATE, _DIV)

        assert len(result) == 1
        assert result[0].greeks is not None
        # Computed greeks should have valid values
        assert -1.0 <= result[0].greeks.delta <= 1.0
        assert result[0].greeks.gamma >= 0.0
        assert result[0].greeks.vega >= 0.0

    def test_tier2_sets_greeks_source_computed(self) -> None:
        """Tier 2: Locally computed Greeks should have greeks_source=COMPUTED."""
        contract = make_contract(
            strike="150.00",
            market_iv=0.30,
            dte_days=45,
        )

        result = compute_greeks([contract], _SPOT, _RATE, _DIV)

        assert len(result) == 1
        assert result[0].greeks_source == GreeksSource.COMPUTED

    def test_tier3_computation_fails(self) -> None:
        """Tier 3: When computation fails, the contract is excluded."""
        # Contract with dte=0 will fail (time_to_expiry <= 0)
        contract = make_contract(
            strike="150.00",
            market_iv=0.30,
            dte_days=0,
        )
        assert contract.greeks is None

        result = compute_greeks([contract], _SPOT, _RATE, _DIV)

        assert len(result) == 0

    def test_mixed_tier1_and_tier2(self) -> None:
        """Mixed batch: Tier 1 contracts preserved, Tier 2 contracts computed."""
        cboe_greeks = _make_greeks(delta=0.40, pricing_model=PricingModel.BAW)
        tier1_contract = _make_contract_with_greeks(
            greeks=cboe_greeks,
            strike="145.00",
            dte_days=45,
            market_iv=0.28,
        )
        tier2_contract = make_contract(
            strike="155.00",
            market_iv=0.32,
            dte_days=45,
        )

        with patch(
            "options_arena.scoring.contracts.option_greeks",
            wraps=__import__(
                "options_arena.pricing.dispatch", fromlist=["option_greeks"]
            ).option_greeks,
        ) as mock_greeks:
            result = compute_greeks([tier1_contract, tier2_contract], _SPOT, _RATE, _DIV)

        assert len(result) == 2

        # Tier 1 contract: original greeks preserved
        r1 = result[0]
        assert r1.greeks is not None
        assert r1.greeks.delta == pytest.approx(0.40, rel=1e-4)
        assert r1.greeks_source == GreeksSource.MARKET

        # Tier 2 contract: newly computed greeks
        r2 = result[1]
        assert r2.greeks is not None
        assert r2.greeks_source == GreeksSource.COMPUTED

        # option_greeks was called exactly once (for the Tier 2 contract only)
        mock_greeks.assert_called_once()

    def test_all_tier1_skips_dispatch(self) -> None:
        """When ALL contracts have existing greeks, dispatch is never called."""
        greeks_a = _make_greeks(delta=0.30)
        greeks_b = _make_greeks(delta=0.45)
        c1 = _make_contract_with_greeks(
            greeks=greeks_a,
            strike="145.00",
            dte_days=45,
        )
        c2 = _make_contract_with_greeks(
            greeks=greeks_b,
            strike="155.00",
            dte_days=45,
        )

        with (
            patch("options_arena.scoring.contracts.option_greeks") as mock_greeks,
            patch("options_arena.scoring.contracts.option_iv") as mock_iv,
        ):
            result = compute_greeks([c1, c2], _SPOT, _RATE, _DIV)

        assert len(result) == 2
        mock_greeks.assert_not_called()
        mock_iv.assert_not_called()

        # Both should have greeks_source set to MARKET
        assert result[0].greeks_source == GreeksSource.MARKET
        assert result[1].greeks_source == GreeksSource.MARKET

    def test_backward_compat_all_none_greeks(self) -> None:
        """Backward compatibility: all contracts with greeks=None behave as before."""
        contracts = [
            make_contract(strike="145.00", market_iv=0.28, dte_days=45),
            make_contract(strike="150.00", market_iv=0.30, dte_days=45),
            make_contract(strike="155.00", market_iv=0.32, dte_days=45),
        ]
        for c in contracts:
            assert c.greeks is None
            assert c.greeks_source is None

        result = compute_greeks(contracts, _SPOT, _RATE, _DIV)

        # All should have been computed (Tier 2)
        assert len(result) == 3
        for r in result:
            assert r.greeks is not None
            assert r.greeks_source == GreeksSource.COMPUTED
            assert -1.0 <= r.greeks.delta <= 1.0

    def test_tier1_with_market_source_already_set(self) -> None:
        """Tier 1: Contract with greeks and greeks_source=MARKET stays unchanged."""
        original_greeks = _make_greeks(delta=0.38)
        contract = _make_contract_with_greeks(
            greeks=original_greeks,
            greeks_source=GreeksSource.MARKET,
            strike="150.00",
            dte_days=45,
        )

        result = compute_greeks([contract], _SPOT, _RATE, _DIV)

        assert len(result) == 1
        # Should be the original object (no copy needed when nothing changes)
        assert result[0] is contract
        assert result[0].greeks_source == GreeksSource.MARKET
        assert result[0].greeks is not None
        assert result[0].greeks.delta == pytest.approx(0.38, rel=1e-4)

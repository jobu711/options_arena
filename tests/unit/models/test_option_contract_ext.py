"""Tests for OptionContract and OpenBBConfig extensions (Epic: openbb-migration, #193).

Validates backward compatibility, new field validators (bid_iv, ask_iv, greeks_source),
and CBOE-related OpenBBConfig fields.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from options_arena.models.config import OpenBBConfig
from options_arena.models.enums import ExerciseStyle, GreeksSource, OptionType, PricingModel
from options_arena.models.options import OptionContract, OptionGreeks


def _make_contract(**overrides: object) -> OptionContract:
    """Factory for OptionContract with sensible defaults."""
    defaults: dict[str, object] = {
        "ticker": "AAPL",
        "option_type": OptionType.CALL,
        "strike": Decimal("150.00"),
        "expiration": date.today() + timedelta(days=45),
        "bid": Decimal("5.00"),
        "ask": Decimal("5.50"),
        "last": Decimal("5.25"),
        "volume": 100,
        "open_interest": 500,
        "exercise_style": ExerciseStyle.AMERICAN,
        "market_iv": 0.30,
    }
    defaults.update(overrides)
    return OptionContract(**defaults)  # type: ignore[arg-type]


def _make_greeks(**overrides: object) -> OptionGreeks:
    """Factory for OptionGreeks with sensible defaults."""
    defaults: dict[str, object] = {
        "delta": 0.45,
        "gamma": 0.03,
        "theta": -0.05,
        "vega": 0.12,
        "rho": 0.02,
        "pricing_model": PricingModel.BAW,
    }
    defaults.update(overrides)
    return OptionGreeks(**defaults)  # type: ignore[arg-type]


class TestOptionContractExtensions:
    """Tests for new OptionContract fields: bid_iv, ask_iv, greeks_source."""

    def test_default_construction_backward_compat(self) -> None:
        """Verify OptionContract constructs without new fields (all default None)."""
        contract = _make_contract()
        assert contract.bid_iv is None
        assert contract.ask_iv is None
        assert contract.greeks_source is None

    def test_bid_iv_valid(self) -> None:
        """Verify bid_iv accepts valid non-negative finite float."""
        contract = _make_contract(bid_iv=0.35)
        assert contract.bid_iv == 0.35

    def test_ask_iv_valid(self) -> None:
        """Verify ask_iv accepts valid non-negative finite float."""
        contract = _make_contract(ask_iv=0.40)
        assert contract.ask_iv == 0.40

    def test_bid_iv_zero_valid(self) -> None:
        """Verify bid_iv=0.0 is valid (ATM near-zero-time options)."""
        contract = _make_contract(bid_iv=0.0)
        assert contract.bid_iv == 0.0

    def test_bid_iv_rejects_negative(self) -> None:
        """Verify bid_iv rejects negative values."""
        with pytest.raises(ValidationError, match="IV must be finite and >= 0"):
            _make_contract(bid_iv=-0.1)

    def test_ask_iv_rejects_nan(self) -> None:
        """Verify ask_iv rejects NaN."""
        with pytest.raises(ValidationError, match="IV must be finite and >= 0"):
            _make_contract(ask_iv=float("nan"))

    def test_ask_iv_rejects_inf(self) -> None:
        """Verify ask_iv rejects infinity."""
        with pytest.raises(ValidationError, match="IV must be finite and >= 0"):
            _make_contract(ask_iv=float("inf"))

    def test_bid_iv_rejects_neg_inf(self) -> None:
        """Verify bid_iv rejects negative infinity."""
        with pytest.raises(ValidationError, match="IV must be finite and >= 0"):
            _make_contract(bid_iv=float("-inf"))

    def test_greeks_source_computed(self) -> None:
        """Verify greeks_source accepts GreeksSource.COMPUTED."""
        contract = _make_contract(greeks_source=GreeksSource.COMPUTED)
        assert contract.greeks_source == GreeksSource.COMPUTED

    def test_greeks_source_market(self) -> None:
        """Verify greeks_source accepts GreeksSource.MARKET."""
        contract = _make_contract(greeks_source=GreeksSource.MARKET)
        assert contract.greeks_source == GreeksSource.MARKET

    def test_greeks_source_none_with_greeks(self) -> None:
        """Verify greeks_source=None with greeks populated is valid (legacy)."""
        greeks = _make_greeks()
        contract = _make_contract(greeks=greeks, greeks_source=None)
        assert contract.greeks is not None
        assert contract.greeks_source is None

    def test_partial_iv_data(self) -> None:
        """Verify ask_iv=None with bid_iv set is valid (partial data)."""
        contract = _make_contract(bid_iv=0.30, ask_iv=None)
        assert contract.bid_iv == 0.30
        assert contract.ask_iv is None

    def test_json_roundtrip_with_new_fields(self) -> None:
        """Verify JSON roundtrip preserves bid_iv, ask_iv, greeks_source."""
        greeks = _make_greeks()
        original = _make_contract(
            bid_iv=0.32,
            ask_iv=0.38,
            greeks_source=GreeksSource.MARKET,
            greeks=greeks,
        )
        json_str = original.model_dump_json()
        restored = OptionContract.model_validate_json(json_str)
        assert restored.bid_iv == original.bid_iv
        assert restored.ask_iv == original.ask_iv
        assert restored.greeks_source == original.greeks_source
        assert restored.greeks == original.greeks

    def test_json_roundtrip_without_new_fields(self) -> None:
        """Verify JSON roundtrip works when new fields are None (backward compat)."""
        original = _make_contract()
        json_str = original.model_dump_json()
        restored = OptionContract.model_validate_json(json_str)
        assert restored.bid_iv is None
        assert restored.ask_iv is None
        assert restored.greeks_source is None
        assert restored.ticker == original.ticker

    def test_model_copy_with_new_fields(self) -> None:
        """Verify model_copy(update={...}) works for setting greeks_source."""
        contract = _make_contract()
        updated = contract.model_copy(
            update={
                "greeks_source": GreeksSource.COMPUTED,
                "bid_iv": 0.25,
            }
        )
        assert updated.greeks_source == GreeksSource.COMPUTED
        assert updated.bid_iv == 0.25
        assert updated.ask_iv is None  # unchanged


class TestOpenBBConfigExtensions:
    """Tests for new OpenBBConfig fields: cboe_chains_enabled, chains_cache_ttl, etc."""

    def test_cboe_chains_enabled_default_true(self) -> None:
        """Verify cboe_chains_enabled defaults to True (post-cutover)."""
        config = OpenBBConfig()
        assert config.cboe_chains_enabled is True

    def test_chains_cache_ttl_default(self) -> None:
        """Verify chains_cache_ttl defaults to 60."""
        config = OpenBBConfig()
        assert config.chains_cache_ttl == 60

    def test_chain_validation_mode_default_false(self) -> None:
        """Verify chain_validation_mode defaults to False."""
        config = OpenBBConfig()
        assert config.chain_validation_mode is False

    def test_cboe_chains_enabled_true(self) -> None:
        """Verify cboe_chains_enabled can be set to True."""
        config = OpenBBConfig(cboe_chains_enabled=True)
        assert config.cboe_chains_enabled is True

    def test_chains_cache_ttl_custom(self) -> None:
        """Verify chains_cache_ttl accepts custom value."""
        config = OpenBBConfig(chains_cache_ttl=120)
        assert config.chains_cache_ttl == 120

    def test_chain_validation_mode_true(self) -> None:
        """Verify chain_validation_mode can be set to True."""
        config = OpenBBConfig(chain_validation_mode=True)
        assert config.chain_validation_mode is True

    def test_existing_fields_unchanged(self) -> None:
        """Verify new fields don't affect existing OpenBBConfig defaults."""
        config = OpenBBConfig()
        assert config.enabled is True
        assert config.fundamentals_enabled is True
        assert config.request_timeout == 15

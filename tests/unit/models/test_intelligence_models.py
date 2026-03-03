"""Unit tests for intelligence data models.

Tests cover:
- AnalystSnapshot: construction, frozen, computed fields, validators, JSON roundtrip
- UpgradeDowngrade: construction, ACTION_MAP, from_grade empty->None, price_target 0->None
- AnalystActivitySnapshot: construction, recent_changes cap, validators
- InsiderTransaction: construction, _parse_transaction_type, value NaN->None
- InsiderSnapshot: construction, buy_ratio bounds, transactions cap
- InstitutionalSnapshot: construction, pct fields bounded [0,1], top_holders cap
- IntelligencePackage: construction, intelligence_completeness method
"""

from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from options_arena.models.intelligence import (
    ACTION_MAP,
    AnalystActivitySnapshot,
    AnalystSnapshot,
    InsiderSnapshot,
    InsiderTransaction,
    InstitutionalSnapshot,
    IntelligencePackage,
    UpgradeDowngrade,
    _parse_transaction_type,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NOW_UTC = datetime(2026, 3, 3, 12, 0, 0, tzinfo=UTC)
TODAY = date(2026, 3, 3)


def _make_upgrade_downgrade(**kwargs: object) -> UpgradeDowngrade:
    """Create a valid UpgradeDowngrade with sensible defaults."""
    defaults: dict[str, object] = {
        "firm": "Goldman Sachs",
        "action": "up",
        "to_grade": "Buy",
        "from_grade": "Hold",
        "date": TODAY,
    }
    defaults.update(kwargs)
    return UpgradeDowngrade(**defaults)  # type: ignore[arg-type]


def _make_insider_transaction(**kwargs: object) -> InsiderTransaction:
    """Create a valid InsiderTransaction with sensible defaults."""
    defaults: dict[str, object] = {
        "insider_name": "Tim Cook",
        "position": "CEO",
        "transaction_type": "Sale",
        "shares": 100_000,
        "value": 15_000_000.0,
        "transaction_date": TODAY,
    }
    defaults.update(kwargs)
    return InsiderTransaction(**defaults)  # type: ignore[arg-type]


# ===========================================================================
# AnalystSnapshot
# ===========================================================================


class TestAnalystSnapshot:
    """Tests for the AnalystSnapshot model."""

    def test_construction_valid(self) -> None:
        """AnalystSnapshot constructs with all fields correctly assigned."""
        snap = AnalystSnapshot(
            ticker="AAPL",
            target_low=150.0,
            target_high=250.0,
            target_mean=200.0,
            target_median=195.0,
            current_price=180.0,
            strong_buy=10,
            buy=15,
            hold=5,
            sell=2,
            strong_sell=1,
            fetched_at=NOW_UTC,
        )
        assert snap.ticker == "AAPL"
        assert snap.target_low == pytest.approx(150.0)
        assert snap.target_high == pytest.approx(250.0)
        assert snap.target_mean == pytest.approx(200.0)
        assert snap.target_median == pytest.approx(195.0)
        assert snap.current_price == pytest.approx(180.0)
        assert snap.strong_buy == 10
        assert snap.buy == 15
        assert snap.hold == 5
        assert snap.sell == 2
        assert snap.strong_sell == 1
        assert snap.fetched_at == NOW_UTC

    def test_frozen_immutable(self) -> None:
        """AnalystSnapshot is frozen: attribute reassignment raises ValidationError."""
        snap = AnalystSnapshot(ticker="AAPL", fetched_at=NOW_UTC)
        with pytest.raises(ValidationError):
            snap.ticker = "MSFT"  # type: ignore[misc]

    def test_consensus_score_formula(self) -> None:
        """consensus_score uses (sb*2 + b*1 + h*0 + s*-1 + ss*-2) / (total * 2)."""
        snap = AnalystSnapshot(
            ticker="AAPL",
            strong_buy=10,
            buy=15,
            hold=5,
            sell=2,
            strong_sell=1,
            fetched_at=NOW_UTC,
        )
        # Expected: (10*2 + 15*1 + 5*0 + 2*(-1) + 1*(-2)) / (33 * 2) = 31/66
        total = 10 + 15 + 5 + 2 + 1
        expected = (10 * 2 + 15 * 1 + 5 * 0 + 2 * (-1) + 1 * (-2)) / (total * 2)
        assert snap.consensus_score == pytest.approx(expected)

    def test_consensus_score_zero_total(self) -> None:
        """consensus_score returns None when all counts are zero."""
        snap = AnalystSnapshot(ticker="AAPL", fetched_at=NOW_UTC)
        assert snap.consensus_score is None

    def test_consensus_score_all_strong_buy(self) -> None:
        """consensus_score is 1.0 when all analysts are strong_buy."""
        snap = AnalystSnapshot(ticker="AAPL", strong_buy=10, fetched_at=NOW_UTC)
        assert snap.consensus_score == pytest.approx(1.0)

    def test_consensus_score_all_strong_sell(self) -> None:
        """consensus_score is -1.0 when all analysts are strong_sell."""
        snap = AnalystSnapshot(ticker="AAPL", strong_sell=10, fetched_at=NOW_UTC)
        assert snap.consensus_score == pytest.approx(-1.0)

    def test_target_upside_pct_calculation(self) -> None:
        """target_upside_pct computes (target_mean - current_price) / current_price."""
        snap = AnalystSnapshot(
            ticker="AAPL",
            target_mean=200.0,
            current_price=180.0,
            fetched_at=NOW_UTC,
        )
        expected = (200.0 - 180.0) / 180.0
        assert snap.target_upside_pct == pytest.approx(expected)

    def test_target_upside_pct_none_when_no_target_mean(self) -> None:
        """target_upside_pct returns None when target_mean is None."""
        snap = AnalystSnapshot(ticker="AAPL", current_price=180.0, fetched_at=NOW_UTC)
        assert snap.target_upside_pct is None

    def test_target_upside_pct_none_when_no_current_price(self) -> None:
        """target_upside_pct returns None when current_price is None."""
        snap = AnalystSnapshot(ticker="AAPL", target_mean=200.0, fetched_at=NOW_UTC)
        assert snap.target_upside_pct is None

    def test_target_upside_pct_none_when_current_price_zero(self) -> None:
        """target_upside_pct returns None when current_price is zero (avoid div-by-zero)."""
        snap = AnalystSnapshot(
            ticker="AAPL",
            target_mean=200.0,
            current_price=0.0,
            fetched_at=NOW_UTC,
        )
        assert snap.target_upside_pct is None

    def test_nan_rejected_on_float_fields(self) -> None:
        """AnalystSnapshot rejects NaN on float fields."""
        with pytest.raises(ValidationError, match="finite"):
            AnalystSnapshot(ticker="AAPL", target_low=float("nan"), fetched_at=NOW_UTC)

    def test_inf_rejected_on_float_fields(self) -> None:
        """AnalystSnapshot rejects Inf on float fields."""
        with pytest.raises(ValidationError, match="finite"):
            AnalystSnapshot(ticker="AAPL", target_high=float("inf"), fetched_at=NOW_UTC)

    def test_neg_inf_rejected(self) -> None:
        """AnalystSnapshot rejects -Inf on float fields."""
        with pytest.raises(ValidationError, match="finite"):
            AnalystSnapshot(ticker="AAPL", target_mean=float("-inf"), fetched_at=NOW_UTC)

    def test_nan_rejected_on_current_price(self) -> None:
        """AnalystSnapshot rejects NaN on current_price."""
        with pytest.raises(ValidationError, match="finite"):
            AnalystSnapshot(ticker="AAPL", current_price=float("nan"), fetched_at=NOW_UTC)

    def test_utc_required_on_fetched_at(self) -> None:
        """AnalystSnapshot rejects naive datetime on fetched_at."""
        with pytest.raises(ValidationError, match="UTC"):
            AnalystSnapshot(
                ticker="AAPL",
                fetched_at=datetime(2026, 3, 3, 12, 0, 0),
            )

    def test_non_utc_rejected(self) -> None:
        """AnalystSnapshot rejects non-UTC timezone on fetched_at."""
        est = timezone(timedelta(hours=-5))
        with pytest.raises(ValidationError, match="UTC"):
            AnalystSnapshot(
                ticker="AAPL",
                fetched_at=datetime(2026, 3, 3, 12, 0, 0, tzinfo=est),
            )

    def test_negative_counts_rejected(self) -> None:
        """AnalystSnapshot rejects negative analyst counts."""
        with pytest.raises(ValidationError, match="non-negative"):
            AnalystSnapshot(ticker="AAPL", strong_buy=-1, fetched_at=NOW_UTC)

    def test_negative_sell_count_rejected(self) -> None:
        """AnalystSnapshot rejects negative sell count."""
        with pytest.raises(ValidationError, match="non-negative"):
            AnalystSnapshot(ticker="AAPL", sell=-1, fetched_at=NOW_UTC)

    def test_json_roundtrip(self) -> None:
        """AnalystSnapshot survives JSON roundtrip."""
        snap = AnalystSnapshot(
            ticker="AAPL",
            target_low=150.0,
            target_high=250.0,
            target_mean=200.0,
            target_median=195.0,
            current_price=180.0,
            strong_buy=10,
            buy=15,
            hold=5,
            sell=2,
            strong_sell=1,
            fetched_at=NOW_UTC,
        )
        json_str = snap.model_dump_json()
        restored = AnalystSnapshot.model_validate_json(json_str)
        assert restored == snap

    def test_all_none_optional_fields(self) -> None:
        """AnalystSnapshot constructs with all optional fields as None/default."""
        snap = AnalystSnapshot(ticker="MSFT", fetched_at=NOW_UTC)
        assert snap.target_low is None
        assert snap.target_high is None
        assert snap.target_mean is None
        assert snap.target_median is None
        assert snap.current_price is None
        assert snap.strong_buy == 0
        assert snap.buy == 0
        assert snap.hold == 0
        assert snap.sell == 0
        assert snap.strong_sell == 0


# ===========================================================================
# UpgradeDowngrade
# ===========================================================================


class TestUpgradeDowngrade:
    """Tests for the UpgradeDowngrade model."""

    def test_construction_valid(self) -> None:
        """UpgradeDowngrade constructs with all fields correctly."""
        ud = _make_upgrade_downgrade()
        assert ud.firm == "Goldman Sachs"
        assert ud.action == "Upgrade"
        assert ud.to_grade == "Buy"
        assert ud.from_grade == "Hold"
        assert ud.date == TODAY

    def test_action_map_values(self) -> None:
        """ACTION_MAP has all expected mappings."""
        assert ACTION_MAP["up"] == "Upgrade"
        assert ACTION_MAP["down"] == "Downgrade"
        assert ACTION_MAP["init"] == "Initiated"
        assert ACTION_MAP["main"] == "Maintained"
        assert ACTION_MAP["reit"] == "Reiterated"

    def test_action_map_applied(self) -> None:
        """Abbreviated action values are mapped to full names."""
        for abbrev, full in ACTION_MAP.items():
            ud = _make_upgrade_downgrade(action=abbrev)
            assert ud.action == full

    def test_unknown_action_passed_through(self) -> None:
        """Unknown action strings are passed through as-is."""
        ud = _make_upgrade_downgrade(action="Custom Action")
        assert ud.action == "Custom Action"

    def test_from_grade_empty_to_none(self) -> None:
        """Empty string from_grade is converted to None."""
        ud = _make_upgrade_downgrade(from_grade="")
        assert ud.from_grade is None

    def test_from_grade_none_stays_none(self) -> None:
        """None from_grade stays None."""
        ud = _make_upgrade_downgrade(from_grade=None)
        assert ud.from_grade is None

    def test_price_target_zero_to_none(self) -> None:
        """price_target of 0.0 is converted to None."""
        ud = _make_upgrade_downgrade(price_target=0.0)
        assert ud.price_target is None

    def test_prior_price_target_zero_to_none(self) -> None:
        """prior_price_target of 0.0 is converted to None."""
        ud = _make_upgrade_downgrade(prior_price_target=0.0)
        assert ud.prior_price_target is None

    def test_valid_price_target_preserved(self) -> None:
        """Non-zero price_target is preserved."""
        ud = _make_upgrade_downgrade(price_target=250.0)
        assert ud.price_target == pytest.approx(250.0)

    def test_frozen(self) -> None:
        """UpgradeDowngrade is frozen."""
        ud = _make_upgrade_downgrade()
        with pytest.raises(ValidationError):
            ud.firm = "Morgan Stanley"  # type: ignore[misc]

    def test_nan_price_target_rejected(self) -> None:
        """NaN price_target is rejected."""
        with pytest.raises(ValidationError, match="finite"):
            _make_upgrade_downgrade(price_target=float("nan"))

    def test_inf_prior_price_target_rejected(self) -> None:
        """Inf prior_price_target is rejected."""
        with pytest.raises(ValidationError, match="finite"):
            _make_upgrade_downgrade(prior_price_target=float("inf"))

    def test_json_roundtrip(self) -> None:
        """UpgradeDowngrade survives JSON roundtrip."""
        ud = _make_upgrade_downgrade(price_target=250.0, prior_price_target=200.0)
        json_str = ud.model_dump_json()
        restored = UpgradeDowngrade.model_validate_json(json_str)
        assert restored == ud


# ===========================================================================
# AnalystActivitySnapshot
# ===========================================================================


class TestAnalystActivitySnapshot:
    """Tests for the AnalystActivitySnapshot model."""

    def test_construction_valid(self) -> None:
        """AnalystActivitySnapshot constructs with valid data."""
        changes = [_make_upgrade_downgrade() for _ in range(3)]
        snap = AnalystActivitySnapshot(
            ticker="AAPL",
            recent_changes=changes,
            upgrades_30d=5,
            downgrades_30d=2,
            net_sentiment_30d=3,
            fetched_at=NOW_UTC,
        )
        assert snap.ticker == "AAPL"
        assert len(snap.recent_changes) == 3
        assert snap.upgrades_30d == 5
        assert snap.downgrades_30d == 2
        assert snap.net_sentiment_30d == 3

    def test_frozen(self) -> None:
        """AnalystActivitySnapshot is frozen."""
        snap = AnalystActivitySnapshot(
            ticker="AAPL",
            recent_changes=[],
            fetched_at=NOW_UTC,
        )
        with pytest.raises(ValidationError):
            snap.ticker = "MSFT"  # type: ignore[misc]

    def test_recent_changes_capped_at_10(self) -> None:
        """recent_changes is capped at 10 entries."""
        changes = [_make_upgrade_downgrade() for _ in range(15)]
        snap = AnalystActivitySnapshot(
            ticker="AAPL",
            recent_changes=changes,
            fetched_at=NOW_UTC,
        )
        assert len(snap.recent_changes) == 10

    def test_negative_upgrades_rejected(self) -> None:
        """Negative upgrades_30d is rejected."""
        with pytest.raises(ValidationError, match="non-negative"):
            AnalystActivitySnapshot(
                ticker="AAPL",
                recent_changes=[],
                upgrades_30d=-1,
                fetched_at=NOW_UTC,
            )

    def test_negative_downgrades_rejected(self) -> None:
        """Negative downgrades_30d is rejected."""
        with pytest.raises(ValidationError, match="non-negative"):
            AnalystActivitySnapshot(
                ticker="AAPL",
                recent_changes=[],
                downgrades_30d=-1,
                fetched_at=NOW_UTC,
            )

    def test_net_sentiment_can_be_negative(self) -> None:
        """net_sentiment_30d can be negative (more downgrades than upgrades)."""
        snap = AnalystActivitySnapshot(
            ticker="AAPL",
            recent_changes=[],
            net_sentiment_30d=-3,
            fetched_at=NOW_UTC,
        )
        assert snap.net_sentiment_30d == -3

    def test_utc_required_on_fetched_at(self) -> None:
        """AnalystActivitySnapshot rejects naive datetime."""
        with pytest.raises(ValidationError, match="UTC"):
            AnalystActivitySnapshot(
                ticker="AAPL",
                recent_changes=[],
                fetched_at=datetime(2026, 3, 3, 12, 0, 0),
            )

    def test_json_roundtrip(self) -> None:
        """AnalystActivitySnapshot survives JSON roundtrip."""
        snap = AnalystActivitySnapshot(
            ticker="AAPL",
            recent_changes=[_make_upgrade_downgrade()],
            upgrades_30d=2,
            downgrades_30d=1,
            net_sentiment_30d=1,
            fetched_at=NOW_UTC,
        )
        json_str = snap.model_dump_json()
        restored = AnalystActivitySnapshot.model_validate_json(json_str)
        assert restored == snap


# ===========================================================================
# InsiderTransaction
# ===========================================================================


class TestInsiderTransaction:
    """Tests for the InsiderTransaction model."""

    def test_construction_valid(self) -> None:
        """InsiderTransaction constructs with valid data."""
        tx = _make_insider_transaction()
        assert tx.insider_name == "Tim Cook"
        assert tx.position == "CEO"
        assert tx.transaction_type == "Sale"
        assert tx.shares == 100_000
        assert tx.value == pytest.approx(15_000_000.0)
        assert tx.ownership_type == "Direct"
        assert tx.transaction_date == TODAY

    def test_frozen(self) -> None:
        """InsiderTransaction is frozen."""
        tx = _make_insider_transaction()
        with pytest.raises(ValidationError):
            tx.shares = 200_000  # type: ignore[misc]

    def test_parse_transaction_type_sale(self) -> None:
        """_parse_transaction_type extracts 'Sale' from text containing 'Sale'."""
        assert _parse_transaction_type("Sale of shares") == "Sale"

    def test_parse_transaction_type_purchase(self) -> None:
        """_parse_transaction_type extracts 'Purchase' from text containing 'Purchase'."""
        assert _parse_transaction_type("Purchase of common stock") == "Purchase"

    def test_parse_transaction_type_gift(self) -> None:
        """_parse_transaction_type extracts 'Gift' from text containing 'Gift'."""
        assert _parse_transaction_type("Gift to charity") == "Gift"

    def test_parse_transaction_type_exercise(self) -> None:
        """_parse_transaction_type extracts 'Exercise' from text."""
        assert _parse_transaction_type("Option Exercise and Sale") == "Exercise"
        assert _parse_transaction_type("Exercise of options") == "Exercise"

    def test_parse_transaction_type_other(self) -> None:
        """_parse_transaction_type returns 'Other' for unrecognized text."""
        assert _parse_transaction_type("Automatic conversion") == "Other"
        assert _parse_transaction_type("") == "Other"

    def test_value_nan_to_none(self) -> None:
        """NaN value is converted to None."""
        tx = _make_insider_transaction(value=float("nan"))
        assert tx.value is None

    def test_value_inf_to_none(self) -> None:
        """Inf value is converted to None."""
        tx = _make_insider_transaction(value=float("inf"))
        assert tx.value is None

    def test_negative_shares_rejected(self) -> None:
        """Negative shares is rejected."""
        with pytest.raises(ValidationError, match="non-negative"):
            _make_insider_transaction(shares=-100)

    def test_json_roundtrip(self) -> None:
        """InsiderTransaction survives JSON roundtrip."""
        tx = _make_insider_transaction()
        json_str = tx.model_dump_json()
        restored = InsiderTransaction.model_validate_json(json_str)
        assert restored == tx


# ===========================================================================
# InsiderSnapshot
# ===========================================================================


class TestInsiderSnapshot:
    """Tests for the InsiderSnapshot model."""

    def test_construction_valid(self) -> None:
        """InsiderSnapshot constructs with valid data."""
        txs = [_make_insider_transaction() for _ in range(3)]
        snap = InsiderSnapshot(
            ticker="AAPL",
            transactions=txs,
            net_insider_buys_90d=-2,
            net_insider_value_90d=-5_000_000.0,
            insider_buy_ratio=0.3,
            fetched_at=NOW_UTC,
        )
        assert snap.ticker == "AAPL"
        assert len(snap.transactions) == 3
        assert snap.net_insider_buys_90d == -2
        assert snap.net_insider_value_90d == pytest.approx(-5_000_000.0)
        assert snap.insider_buy_ratio == pytest.approx(0.3)

    def test_frozen(self) -> None:
        """InsiderSnapshot is frozen."""
        snap = InsiderSnapshot(ticker="AAPL", transactions=[], fetched_at=NOW_UTC)
        with pytest.raises(ValidationError):
            snap.ticker = "MSFT"  # type: ignore[misc]

    def test_buy_ratio_bounds_valid_at_0(self) -> None:
        """insider_buy_ratio of 0.0 is valid."""
        snap = InsiderSnapshot(
            ticker="AAPL",
            transactions=[],
            insider_buy_ratio=0.0,
            fetched_at=NOW_UTC,
        )
        assert snap.insider_buy_ratio == pytest.approx(0.0)

    def test_buy_ratio_bounds_valid_at_1(self) -> None:
        """insider_buy_ratio of 1.0 is valid."""
        snap = InsiderSnapshot(
            ticker="AAPL",
            transactions=[],
            insider_buy_ratio=1.0,
            fetched_at=NOW_UTC,
        )
        assert snap.insider_buy_ratio == pytest.approx(1.0)

    def test_buy_ratio_above_1_rejected(self) -> None:
        """insider_buy_ratio > 1.0 is rejected."""
        with pytest.raises(ValidationError, match=r"\[0\.0, 1\.0\]"):
            InsiderSnapshot(
                ticker="AAPL",
                transactions=[],
                insider_buy_ratio=1.1,
                fetched_at=NOW_UTC,
            )

    def test_buy_ratio_below_0_rejected(self) -> None:
        """insider_buy_ratio < 0.0 is rejected."""
        with pytest.raises(ValidationError, match=r"\[0\.0, 1\.0\]"):
            InsiderSnapshot(
                ticker="AAPL",
                transactions=[],
                insider_buy_ratio=-0.1,
                fetched_at=NOW_UTC,
            )

    def test_buy_ratio_nan_rejected(self) -> None:
        """insider_buy_ratio NaN is rejected."""
        with pytest.raises(ValidationError, match="finite"):
            InsiderSnapshot(
                ticker="AAPL",
                transactions=[],
                insider_buy_ratio=float("nan"),
                fetched_at=NOW_UTC,
            )

    def test_transactions_capped_at_20(self) -> None:
        """transactions is capped at 20 entries."""
        txs = [_make_insider_transaction() for _ in range(25)]
        snap = InsiderSnapshot(ticker="AAPL", transactions=txs, fetched_at=NOW_UTC)
        assert len(snap.transactions) == 20

    def test_net_insider_value_nan_rejected(self) -> None:
        """NaN net_insider_value_90d is rejected."""
        with pytest.raises(ValidationError, match="finite"):
            InsiderSnapshot(
                ticker="AAPL",
                transactions=[],
                net_insider_value_90d=float("nan"),
                fetched_at=NOW_UTC,
            )

    def test_utc_required_on_fetched_at(self) -> None:
        """InsiderSnapshot rejects naive datetime."""
        with pytest.raises(ValidationError, match="UTC"):
            InsiderSnapshot(
                ticker="AAPL",
                transactions=[],
                fetched_at=datetime(2026, 3, 3, 12, 0, 0),
            )

    def test_json_roundtrip(self) -> None:
        """InsiderSnapshot survives JSON roundtrip."""
        snap = InsiderSnapshot(
            ticker="AAPL",
            transactions=[_make_insider_transaction()],
            net_insider_buys_90d=1,
            insider_buy_ratio=0.5,
            fetched_at=NOW_UTC,
        )
        json_str = snap.model_dump_json()
        restored = InsiderSnapshot.model_validate_json(json_str)
        assert restored == snap


# ===========================================================================
# InstitutionalSnapshot
# ===========================================================================


class TestInstitutionalSnapshot:
    """Tests for the InstitutionalSnapshot model."""

    def test_construction_valid(self) -> None:
        """InstitutionalSnapshot constructs with all fields."""
        snap = InstitutionalSnapshot(
            ticker="AAPL",
            institutional_pct=0.72,
            institutional_float_pct=0.85,
            insider_pct=0.05,
            institutions_count=4200,
            top_holders=["Vanguard", "BlackRock", "State Street"],
            top_holder_pcts=[0.08, 0.07, 0.04],
            fetched_at=NOW_UTC,
        )
        assert snap.ticker == "AAPL"
        assert snap.institutional_pct == pytest.approx(0.72)
        assert snap.institutional_float_pct == pytest.approx(0.85)
        assert snap.insider_pct == pytest.approx(0.05)
        assert snap.institutions_count == 4200
        assert len(snap.top_holders) == 3
        assert len(snap.top_holder_pcts) == 3

    def test_frozen(self) -> None:
        """InstitutionalSnapshot is frozen."""
        snap = InstitutionalSnapshot(ticker="AAPL", fetched_at=NOW_UTC)
        with pytest.raises(ValidationError):
            snap.ticker = "MSFT"  # type: ignore[misc]

    def test_pct_fields_bounded_0_1_valid_at_boundaries(self) -> None:
        """Percentage fields at 0.0 and 1.0 are valid."""
        snap = InstitutionalSnapshot(
            ticker="AAPL",
            institutional_pct=0.0,
            institutional_float_pct=1.0,
            insider_pct=0.0,
            fetched_at=NOW_UTC,
        )
        assert snap.institutional_pct == pytest.approx(0.0)
        assert snap.institutional_float_pct == pytest.approx(1.0)

    def test_institutional_pct_above_1_rejected(self) -> None:
        """institutional_pct > 1.0 is rejected."""
        with pytest.raises(ValidationError, match=r"\[0\.0, 1\.0\]"):
            InstitutionalSnapshot(
                ticker="AAPL",
                institutional_pct=1.1,
                fetched_at=NOW_UTC,
            )

    def test_institutional_pct_below_0_rejected(self) -> None:
        """institutional_pct < 0.0 is rejected."""
        with pytest.raises(ValidationError, match=r"\[0\.0, 1\.0\]"):
            InstitutionalSnapshot(
                ticker="AAPL",
                institutional_pct=-0.1,
                fetched_at=NOW_UTC,
            )

    def test_insider_pct_above_1_rejected(self) -> None:
        """insider_pct > 1.0 is rejected."""
        with pytest.raises(ValidationError, match=r"\[0\.0, 1\.0\]"):
            InstitutionalSnapshot(
                ticker="AAPL",
                insider_pct=1.5,
                fetched_at=NOW_UTC,
            )

    def test_institutional_float_pct_nan_rejected(self) -> None:
        """NaN institutional_float_pct is rejected."""
        with pytest.raises(ValidationError, match="finite"):
            InstitutionalSnapshot(
                ticker="AAPL",
                institutional_float_pct=float("nan"),
                fetched_at=NOW_UTC,
            )

    def test_negative_institutions_count_rejected(self) -> None:
        """Negative institutions_count is rejected."""
        with pytest.raises(ValidationError, match="non-negative"):
            InstitutionalSnapshot(
                ticker="AAPL",
                institutions_count=-1,
                fetched_at=NOW_UTC,
            )

    def test_top_holders_max_5(self) -> None:
        """top_holders is capped at 5."""
        snap = InstitutionalSnapshot(
            ticker="AAPL",
            top_holders=["A", "B", "C", "D", "E", "F", "G"],
            fetched_at=NOW_UTC,
        )
        assert len(snap.top_holders) == 5

    def test_top_holder_pcts_max_5(self) -> None:
        """top_holder_pcts is capped at 5."""
        snap = InstitutionalSnapshot(
            ticker="AAPL",
            top_holder_pcts=[0.1, 0.09, 0.08, 0.07, 0.06, 0.05, 0.04],
            fetched_at=NOW_UTC,
        )
        assert len(snap.top_holder_pcts) == 5

    def test_all_none_optional_fields(self) -> None:
        """InstitutionalSnapshot with all optional fields as None/default."""
        snap = InstitutionalSnapshot(ticker="MSFT", fetched_at=NOW_UTC)
        assert snap.institutional_pct is None
        assert snap.institutional_float_pct is None
        assert snap.insider_pct is None
        assert snap.institutions_count is None
        assert snap.top_holders == []
        assert snap.top_holder_pcts == []

    def test_utc_required_on_fetched_at(self) -> None:
        """InstitutionalSnapshot rejects naive datetime."""
        with pytest.raises(ValidationError, match="UTC"):
            InstitutionalSnapshot(
                ticker="AAPL",
                fetched_at=datetime(2026, 3, 3, 12, 0, 0),
            )

    def test_json_roundtrip(self) -> None:
        """InstitutionalSnapshot survives JSON roundtrip."""
        snap = InstitutionalSnapshot(
            ticker="AAPL",
            institutional_pct=0.72,
            top_holders=["Vanguard", "BlackRock"],
            top_holder_pcts=[0.08, 0.07],
            fetched_at=NOW_UTC,
        )
        json_str = snap.model_dump_json()
        restored = InstitutionalSnapshot.model_validate_json(json_str)
        assert restored == snap


# ===========================================================================
# IntelligencePackage
# ===========================================================================


class TestIntelligencePackage:
    """Tests for the IntelligencePackage model."""

    def _make_full_package(self) -> IntelligencePackage:
        """Create a fully populated IntelligencePackage."""
        analyst = AnalystSnapshot(ticker="AAPL", strong_buy=10, buy=5, fetched_at=NOW_UTC)
        activity = AnalystActivitySnapshot(ticker="AAPL", recent_changes=[], fetched_at=NOW_UTC)
        insider = InsiderSnapshot(ticker="AAPL", transactions=[], fetched_at=NOW_UTC)
        institutional = InstitutionalSnapshot(ticker="AAPL", fetched_at=NOW_UTC)
        return IntelligencePackage(
            ticker="AAPL",
            analyst=analyst,
            analyst_activity=activity,
            insider=insider,
            institutional=institutional,
            news_headlines=["Apple beats earnings"],
            fetched_at=NOW_UTC,
        )

    def test_construction_all_populated(self) -> None:
        """IntelligencePackage constructs with all categories populated."""
        pkg = self._make_full_package()
        assert pkg.ticker == "AAPL"
        assert pkg.analyst is not None
        assert pkg.analyst_activity is not None
        assert pkg.insider is not None
        assert pkg.institutional is not None
        assert pkg.news_headlines is not None

    def test_construction_all_none(self) -> None:
        """IntelligencePackage constructs with all optional categories as None."""
        pkg = IntelligencePackage(ticker="MSFT", fetched_at=NOW_UTC)
        assert pkg.analyst is None
        assert pkg.analyst_activity is None
        assert pkg.insider is None
        assert pkg.institutional is None
        assert pkg.news_headlines is None

    def test_frozen(self) -> None:
        """IntelligencePackage is frozen."""
        pkg = IntelligencePackage(ticker="AAPL", fetched_at=NOW_UTC)
        with pytest.raises(ValidationError):
            pkg.ticker = "MSFT"  # type: ignore[misc]

    def test_intelligence_completeness_full(self) -> None:
        """intelligence_completeness returns 1.0 when all 5 categories populated."""
        pkg = self._make_full_package()
        assert pkg.intelligence_completeness() == pytest.approx(1.0)

    def test_intelligence_completeness_partial(self) -> None:
        """intelligence_completeness returns correct fraction for partial data."""
        analyst = AnalystSnapshot(ticker="AAPL", strong_buy=10, fetched_at=NOW_UTC)
        pkg = IntelligencePackage(
            ticker="AAPL",
            analyst=analyst,
            news_headlines=["headline"],
            fetched_at=NOW_UTC,
        )
        # 2 of 5 categories populated
        assert pkg.intelligence_completeness() == pytest.approx(2 / 5)

    def test_intelligence_completeness_empty(self) -> None:
        """intelligence_completeness returns 0.0 when no categories populated."""
        pkg = IntelligencePackage(ticker="MSFT", fetched_at=NOW_UTC)
        assert pkg.intelligence_completeness() == pytest.approx(0.0)

    def test_news_headlines_capped_at_5(self) -> None:
        """news_headlines is capped at 5 when not None."""
        pkg = IntelligencePackage(
            ticker="AAPL",
            news_headlines=["h1", "h2", "h3", "h4", "h5", "h6", "h7"],
            fetched_at=NOW_UTC,
        )
        assert pkg.news_headlines is not None
        assert len(pkg.news_headlines) == 5

    def test_utc_required_on_fetched_at(self) -> None:
        """IntelligencePackage rejects naive datetime."""
        with pytest.raises(ValidationError, match="UTC"):
            IntelligencePackage(
                ticker="AAPL",
                fetched_at=datetime(2026, 3, 3, 12, 0, 0),
            )

    def test_json_roundtrip(self) -> None:
        """IntelligencePackage survives JSON roundtrip."""
        pkg = self._make_full_package()
        json_str = pkg.model_dump_json()
        restored = IntelligencePackage.model_validate_json(json_str)
        assert restored == pkg

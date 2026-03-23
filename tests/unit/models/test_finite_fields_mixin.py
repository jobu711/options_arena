"""Tests for FiniteFieldsMixin — rejects NaN/Inf on all float config fields."""

import math

import pytest
from pydantic import ValidationError

from options_arena.models.config import FiniteFieldsMixin


class _SampleConfig(FiniteFieldsMixin):
    """Minimal config subclass for testing the mixin in isolation."""

    score: float = 50.0
    ratio: float = 1.5
    label: str = "test"
    count: int = 10
    flag: bool = False


class TestFiniteFieldsMixinValidFloats:
    """Verify that valid float values are accepted."""

    def test_defaults_accepted(self) -> None:
        cfg = _SampleConfig()
        assert cfg.score == 50.0
        assert cfg.ratio == 1.5

    def test_zero_accepted(self) -> None:
        cfg = _SampleConfig(score=0.0, ratio=0.0)
        assert cfg.score == 0.0
        assert cfg.ratio == 0.0

    def test_negative_accepted(self) -> None:
        cfg = _SampleConfig(score=-10.0, ratio=-3.14)
        assert cfg.score == -10.0
        assert cfg.ratio == -3.14

    def test_large_finite_accepted(self) -> None:
        cfg = _SampleConfig(score=1e300, ratio=-1e300)
        assert math.isfinite(cfg.score)
        assert math.isfinite(cfg.ratio)


class TestFiniteFieldsMixinRejectsNaN:
    """Verify that NaN is rejected on any float field."""

    def test_nan_rejected_on_first_field(self) -> None:
        with pytest.raises(ValidationError, match="score"):
            _SampleConfig(score=float("nan"))

    def test_nan_rejected_on_second_field(self) -> None:
        with pytest.raises(ValidationError, match="ratio"):
            _SampleConfig(ratio=float("nan"))


class TestFiniteFieldsMixinRejectsInf:
    """Verify that +Inf and -Inf are rejected."""

    def test_positive_inf_rejected(self) -> None:
        with pytest.raises(ValidationError, match="score"):
            _SampleConfig(score=float("inf"))

    def test_negative_inf_rejected(self) -> None:
        with pytest.raises(ValidationError, match="ratio"):
            _SampleConfig(ratio=float("-inf"))


class TestFiniteFieldsMixinNonFloatIgnored:
    """Verify that non-float fields are not affected by the mixin."""

    def test_string_field_unaffected(self) -> None:
        cfg = _SampleConfig(label="anything")
        assert cfg.label == "anything"

    def test_int_field_unaffected(self) -> None:
        cfg = _SampleConfig(count=999)
        assert cfg.count == 999

    def test_bool_field_unaffected(self) -> None:
        cfg = _SampleConfig(flag=True)
        assert cfg.flag is True


class TestFiniteFieldsMixinErrorMessage:
    """Verify error messages include the offending field name."""

    def test_error_includes_field_name_score(self) -> None:
        with pytest.raises(ValidationError, match="score must be finite"):
            _SampleConfig(score=float("nan"))

    def test_error_includes_field_name_ratio(self) -> None:
        with pytest.raises(ValidationError, match="ratio must be finite"):
            _SampleConfig(ratio=float("inf"))

    def test_error_includes_value(self) -> None:
        with pytest.raises(ValidationError, match="nan"):
            _SampleConfig(score=float("nan"))

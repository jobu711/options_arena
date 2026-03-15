"""Macro regime classification from FRED economic indicators.

Derives a macro economic regime (expansionary, contractionary, transitional)
from raw FRED economic indicators. Pure computation — no API calls, no I/O,
no Pydantic models.

Classification rules (inputs are decimal fractions):
    - yield_spread < 0 AND unemployment > 0.05 (5.0%) → contractionary
    - yield_spread > 0 AND unemployment < 0.045 (4.5%) → expansionary
    - Mixed or insufficient data → transitional

Confidence is based on the strength of signal agreement.
"""

from __future__ import annotations

import logging
import math
from typing import NamedTuple

logger = logging.getLogger(__name__)

# Minimum completeness ratio required to classify a regime.
_MIN_COMPLETENESS: float = 0.5

# Thresholds — rates as decimal fractions:
# unemployment_rate of 0.05 = 5.0%, yield_spread of 0.0 = flat curve.
_UNEMPLOYMENT_HIGH: float = 0.05  # 5.0%
_UNEMPLOYMENT_LOW: float = 0.045  # 4.5%


class MacroClassification(NamedTuple):
    """Pure result of macro regime classification — no Pydantic dependency.

    Attributes:
        regime: One of ``"expansionary"``, ``"contractionary"``, ``"transitional"``.
        confidence: Classification confidence in [0.0, 1.0].
    """

    regime: str
    confidence: float


def compute_macro_regime(
    *,
    yield_spread_10y2y: float | None,
    unemployment_rate: float | None,
    fed_funds_rate: float | None,
    vix: float | None,
    cpi_yoy: float | None,
    completeness_ratio: float,
) -> MacroClassification | None:
    """Classify the macro economic regime from FRED indicators.

    Returns ``None`` when ``completeness_ratio < 0.5``, since the
    classification would be unreliable.

    All parameters are raw values from ``MacroContext``. This function
    accepts only primitive types — no Pydantic models — to maintain
    indicator module purity.

    Args:
        yield_spread_10y2y: 10Y-2Y yield spread (decimal fraction), or ``None``.
        unemployment_rate: Unemployment rate (decimal fraction), or ``None``.
        fed_funds_rate: Federal funds rate (decimal fraction), or ``None``.
        vix: VIX index level, or ``None``.
        cpi_yoy: CPI year-over-year percent change, or ``None``.
        completeness_ratio: Fraction of populated macro fields (0.0 to 1.0).

    Returns:
        ``MacroClassification`` with regime label and confidence,
        or ``None`` when data is insufficient.
    """
    if completeness_ratio < _MIN_COMPLETENESS:
        logger.debug(
            "Macro completeness %.1f%% < %.0f%% threshold, skipping regime classification",
            completeness_ratio * 100,
            _MIN_COMPLETENESS * 100,
        )
        return None

    yield_spread = yield_spread_10y2y
    unemployment = unemployment_rate

    # Both key indicators must be available and finite for directional classification
    has_spread = yield_spread is not None and math.isfinite(yield_spread)
    has_unemployment = unemployment is not None and math.isfinite(unemployment)

    if has_spread and has_unemployment:
        assert yield_spread is not None  # for type narrowing
        assert unemployment is not None

        spread_negative = yield_spread < 0.0
        spread_positive = yield_spread > 0.0
        unemployment_high = unemployment > _UNEMPLOYMENT_HIGH
        unemployment_low = unemployment < _UNEMPLOYMENT_LOW

        if spread_negative and unemployment_high:
            # Inverted yield curve + high unemployment = contraction
            confidence = _compute_confidence(yield_spread, unemployment, regime="contractionary")
            return MacroClassification(
                regime="contractionary",
                confidence=confidence,
            )

        if spread_positive and unemployment_low:
            # Normal yield curve + low unemployment = expansion
            confidence = _compute_confidence(yield_spread, unemployment, regime="expansionary")
            return MacroClassification(
                regime="expansionary",
                confidence=confidence,
            )

    # Mixed signals or missing key data → transitional
    confidence = _transitional_confidence(yield_spread, unemployment)
    return MacroClassification(
        regime="transitional",
        confidence=confidence,
    )


def _compute_confidence(
    yield_spread: float,
    unemployment: float,
    *,
    regime: str,
) -> float:
    """Compute classification confidence based on signal strength.

    Stronger deviations from thresholds increase confidence:
    - Deeper yield curve inversion (or steeper positive spread) → higher confidence
    - Unemployment further from boundary thresholds → higher confidence

    Returns a value clamped to [0.3, 0.9] — we never claim extreme certainty
    from only two indicators.
    """
    # Guard non-finite inputs — callers already check, but belt-and-suspenders
    if not math.isfinite(yield_spread) or not math.isfinite(unemployment):
        return 0.3

    # Yield spread strength: how far from zero (flat curve)
    spread_strength = min(abs(yield_spread) / 0.02, 1.0)  # normalize by 200bps

    # Unemployment strength: how far from threshold
    if regime == "contractionary":
        unemp_strength = min(
            (unemployment - _UNEMPLOYMENT_HIGH) / 0.02, 1.0
        )  # normalize by 2pp above threshold
    else:
        unemp_strength = min(
            (_UNEMPLOYMENT_LOW - unemployment) / 0.015, 1.0
        )  # normalize by 1.5pp below threshold

    unemp_strength = max(unemp_strength, 0.0)

    # Weighted average: both signals contribute equally
    raw_confidence = 0.3 + 0.6 * (0.5 * spread_strength + 0.5 * unemp_strength)

    return min(max(raw_confidence, 0.3), 0.9)


def _transitional_confidence(
    yield_spread: float | None,
    unemployment: float | None,
) -> float:
    """Compute confidence for the transitional (mixed) regime.

    Lower confidence because the signals are ambiguous. Returns 0.3-0.5 range.
    """
    # Start at baseline
    confidence = 0.4

    # If both indicators exist, we're more confident it's truly transitional
    has_spread = yield_spread is not None and math.isfinite(yield_spread)
    has_unemp = unemployment is not None and math.isfinite(unemployment)

    if has_spread and has_unemp:
        confidence = 0.5
    elif has_spread or has_unemp:
        confidence = 0.35
    else:
        confidence = 0.3

    return confidence

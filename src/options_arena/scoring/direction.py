"""Signal direction classification based on technical indicators.

Determines BULLISH, BEARISH, or NEUTRAL direction by scoring ADX trend
strength, RSI momentum, and SMA alignment signals.

Scoring uses a momentum interpretation: high RSI (overbought) adds to the
bullish score, low RSI (oversold) adds to the bearish score.  SMA alignment
acts as a secondary signal and tiebreaker.
"""

import logging

from options_arena.models.config import ScanConfig
from options_arena.models.enums import SignalDirection

logger = logging.getLogger(__name__)

# --- Module-level constants (defaults only; thresholds come from ScanConfig) ---
RSI_MIDPOINT: float = 50.0
SMA_BULLISH_THRESHOLD: float = 0.5
SMA_BEARISH_THRESHOLD: float = -0.5

# --- Internal scoring weights ---
_STRONG_SIGNAL_WEIGHT: int = 2
_MILD_SIGNAL_WEIGHT: int = 1


def determine_direction(
    adx: float,
    rsi: float,
    sma_alignment: float,
    config: ScanConfig | None = None,
) -> SignalDirection:
    """Classify market direction from technical indicator values.

    Args:
        adx: Average Directional Index value. Below ``config.adx_trend_threshold``
            means no clear trend (returns NEUTRAL).
        rsi: Relative Strength Index (0--100).
        sma_alignment: SMA alignment score. Positive values indicate bullish
            alignment, negative values bearish.
        config: Optional scan configuration for threshold overrides. Uses
            production defaults when ``None``.

    Returns:
        ``SignalDirection.BULLISH``, ``BEARISH``, or ``NEUTRAL`` based on
        weighted scoring of RSI momentum and SMA alignment.
    """
    cfg = config if config is not None else ScanConfig()

    # Step 1: ADX gate -- weak trend means no directional signal
    if adx < cfg.adx_trend_threshold:
        logger.debug(
            "ADX %.2f < threshold %.2f -- returning NEUTRAL",
            adx,
            cfg.adx_trend_threshold,
        )
        return SignalDirection.NEUTRAL

    bullish_score: int = 0
    bearish_score: int = 0

    # Step 2: RSI scoring (momentum interpretation)
    if rsi > cfg.rsi_overbought:
        bullish_score += _STRONG_SIGNAL_WEIGHT
    elif rsi > RSI_MIDPOINT:
        bullish_score += _MILD_SIGNAL_WEIGHT
    elif rsi < cfg.rsi_oversold:
        bearish_score += _STRONG_SIGNAL_WEIGHT
    elif rsi < RSI_MIDPOINT:
        bearish_score += _MILD_SIGNAL_WEIGHT

    # Step 3: SMA alignment scoring
    if sma_alignment > SMA_BULLISH_THRESHOLD:
        bullish_score += _MILD_SIGNAL_WEIGHT
    elif sma_alignment < SMA_BEARISH_THRESHOLD:
        bearish_score += _MILD_SIGNAL_WEIGHT

    logger.debug(
        "Direction scoring -- bullish=%d, bearish=%d (ADX=%.2f, RSI=%.2f, SMA=%.4f)",
        bullish_score,
        bearish_score,
        adx,
        rsi,
        sma_alignment,
    )

    # Step 4: Compare scores
    if bullish_score > bearish_score:
        return SignalDirection.BULLISH
    if bearish_score > bullish_score:
        return SignalDirection.BEARISH

    # Tiebreaker: when scores are equal and both > 0, use SMA alignment
    # direction as the deciding factor (underlying trend is more fundamental
    # than RSI's momentum signal).
    if bullish_score > 0 and bullish_score == bearish_score:
        if sma_alignment > 0:
            return SignalDirection.BULLISH
        return SignalDirection.BEARISH

    # Both scores == 0 -- no signals at all
    return SignalDirection.NEUTRAL

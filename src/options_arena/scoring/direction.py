"""Signal direction classification based on technical indicators.

Determines BULLISH, BEARISH, or NEUTRAL direction by scoring ADX trend
strength, RSI momentum, SMA alignment, supertrend, and rate-of-change signals.

Scoring uses a momentum interpretation: high RSI (overbought) adds to the
bullish score, low RSI (oversold) adds to the bearish score.  SMA alignment
acts as a secondary signal and tiebreaker.  Supertrend and ROC provide
confirming or contradicting trend evidence.
"""

import logging
import math

from options_arena.models.config import ScanConfig
from options_arena.models.enums import SignalDirection

logger = logging.getLogger(__name__)

# --- Module-level constants (defaults only; thresholds come from ScanConfig) ---
RSI_MIDPOINT: float = 50.0
SMA_BULLISH_THRESHOLD: float = 0.5
SMA_BEARISH_THRESHOLD: float = -0.5
ROC_THRESHOLD: float = 5.0

# --- Internal scoring weights ---
_STRONG_SIGNAL_WEIGHT: int = 2
_MILD_SIGNAL_WEIGHT: int = 1


def determine_direction(
    adx: float,
    rsi: float,
    sma_alignment: float,
    config: ScanConfig | None = None,
    *,
    supertrend: float | None = None,
    roc: float | None = None,
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
        supertrend: Supertrend signal (+1.0 = uptrend, -1.0 = downtrend).
            ``None`` means unavailable (contributes nothing).
        roc: Rate of change (percent). Above ``ROC_THRESHOLD`` is bullish
            confirmation, below ``-ROC_THRESHOLD`` is bearish.  ``None``
            means unavailable (contributes nothing).

    Returns:
        ``SignalDirection.BULLISH``, ``BEARISH``, or ``NEUTRAL`` based on
        weighted scoring of RSI momentum, SMA alignment, supertrend, and ROC.
    """
    cfg = config if config is not None else ScanConfig()

    # Guard: non-finite inputs produce no meaningful signal
    if not (math.isfinite(adx) and math.isfinite(rsi) and math.isfinite(sma_alignment)):
        logger.debug(
            "Non-finite input (adx=%r, rsi=%r, sma=%r) -- returning NEUTRAL",
            adx,
            rsi,
            sma_alignment,
        )
        return SignalDirection.NEUTRAL

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
    # FR-11/L7: Strict `>` (not `>=`) is intentional. RSI exactly at the overbought
    # or oversold boundary is ambiguous — it should NOT trigger a strong signal.
    # This prevents false directional bias at the threshold edges.
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

    # Step 4: Supertrend confirmation (±1 signal)
    if supertrend is not None and math.isfinite(supertrend):
        if supertrend > 0:
            bullish_score += _MILD_SIGNAL_WEIGHT
        elif supertrend < 0:
            bearish_score += _MILD_SIGNAL_WEIGHT

    # Step 5: ROC confirmation (strong momentum)
    if roc is not None and math.isfinite(roc):
        if roc > ROC_THRESHOLD:
            bullish_score += _MILD_SIGNAL_WEIGHT
        elif roc < -ROC_THRESHOLD:
            bearish_score += _MILD_SIGNAL_WEIGHT

    logger.debug(
        "Direction scoring -- bullish=%d, bearish=%d "
        "(ADX=%.2f, RSI=%.2f, SMA=%.4f, ST=%r, ROC=%r)",
        bullish_score,
        bearish_score,
        adx,
        rsi,
        sma_alignment,
        supertrend,
        roc,
    )

    # Step 6: Compare scores
    if bullish_score > bearish_score:
        return SignalDirection.BULLISH
    if bearish_score > bullish_score:
        return SignalDirection.BEARISH

    # Tiebreaker: when scores are equal and both > 0, use SMA alignment
    # direction as the deciding factor (underlying trend is more fundamental
    # than RSI's momentum signal). Exact zero = truly neutral, no bias.
    if bullish_score > 0 and bullish_score == bearish_score:
        if sma_alignment > 0:
            return SignalDirection.BULLISH
        if sma_alignment < 0:
            return SignalDirection.BEARISH
        return SignalDirection.NEUTRAL

    # Both scores == 0 -- no signals at all
    return SignalDirection.NEUTRAL

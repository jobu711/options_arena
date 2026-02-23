"""Options Arena — Scoring engine and signal aggregation.

Modules:
    normalization -- Percentile-rank normalization with tie handling and inversion.
    composite     -- Weighted geometric mean composite scoring.
    direction     -- BULLISH / BEARISH / NEUTRAL signal classification.
    contracts     -- Contract filtering, Greeks dispatch, delta targeting.
"""

# Re-exports populated after implementation modules are created.
__all__: list[str] = []

# Analysis: #87 — Add VolatilityThesis model and re-export

## Summary

XS task. Add a new frozen Pydantic model `VolatilityThesis` to `models/analysis.py` following the
exact pattern of `TradeThesis` (frozen, confidence-validated, `math.isfinite` guard). Re-export
from `models/__init__.py`. Write tests.

## Work Streams

### Stream A: Model + Re-export + Tests (single stream, no parallelism needed)

**Files to modify:**
- `src/options_arena/models/analysis.py` — add `VolatilityThesis` after `TradeThesis`
- `src/options_arena/models/__init__.py` — add import and `__all__` entry
- `tests/unit/models/test_analysis.py` — add 4 tests

**Implementation details:**

1. Add to `analysis.py` after `TradeThesis`:
   ```python
   class VolatilityThesis(BaseModel):
       model_config = ConfigDict(frozen=True)
       iv_assessment: str               # "overpriced", "underpriced", "fair"
       iv_rank_interpretation: str
       confidence: float                # [0.0, 1.0]
       recommended_strategy: SpreadType | None = None
       strategy_rationale: str
       target_iv_entry: float | None = None
       target_iv_exit: float | None = None
       suggested_strikes: list[str]
       key_vol_factors: list[str]
       model_used: str
   ```
   - Reuse `validate_confidence` pattern from `TradeThesis` (with `math.isfinite` guard)
   - `SpreadType` already imported at top of file

2. In `__init__.py`:
   - Add `VolatilityThesis` to the import from `analysis`
   - Add `"VolatilityThesis"` to `__all__` under `# Analysis`

3. Tests (in existing `test_analysis.py`):
   - Construction with valid data
   - Frozen enforcement (attribute reassignment raises)
   - Confidence validation (rejects < 0, > 1, NaN, inf)
   - JSON roundtrip: `model_validate_json(vt.model_dump_json()) == vt`

## Risks

None — pure model addition, no external deps, no behavioral changes.

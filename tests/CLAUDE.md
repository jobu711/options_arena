# CLAUDE.md — Tests

## Commands
```bash
uv run pytest tests/unit -v                        # unit only
uv run pytest tests/integration -v                 # integration only
uv run pytest tests/ -v --cov=src/options_arena     # full + coverage
uv run pytest tests/ -n auto -q                    # parallel (~2x faster)
uv run pytest tests/ -m smoke -v                   # smoke only (<10s)
```

## Absolute Rules
1. **Never hit real APIs.** Mock Groq, yfinance, and all data sources. Every test
2. **Never `==` for floats.** Always `pytest.approx()`
3. **Never hardcode dates depending on `today`.** Mock `date.today()` for DTE tests
4. **Never inline large test data.** Use `tests/fixtures/` files

## Floating Point Tolerances
| Context | Tolerance |
|---|---|
| Indicators (RSI, MACD, BB) | `pytest.approx(rel=1e-4)` |
| Greeks (delta, gamma, etc.) | `pytest.approx(rel=1e-4)` |
| Prices (Decimal) | `pytest.approx(abs=Decimal("0.01"))` |
| Confidence scores | `pytest.approx(abs=0.01)` |
| IV / percentages | `pytest.approx(rel=1e-3)` |

## Indicator Tests — Every Indicator Needs
1. Known-value (cite source), 2. Minimum data, 3. Insufficient data (`InsufficientDataError`),
4. NaN warmup count, 5. Edge cases (flat, monotonic, single spike, zero volume)

## Model Tests
- JSON roundtrip for every model. Decimal precision survives. StrEnum round-trips
- Validation rejects bad data. Computed fields correct. Frozen models reject mutation

## Agent Tests
- `pydantic_ai.models.test.TestModel` — never real API calls
- `models.ALLOW_MODEL_REQUESTS = False` at module level in every test file
- Test: success, partial failure, full failure→fallback, timeout

## Conftest Fixtures
`sample_prices` (DataFrame), `sample_option_chain`, `mock_debate_config`,
`market_context` (fully populated). Keep fixtures small (~100-250 rows).

## What Claude Gets Wrong
- Don't use raw dicts as test data — construct typed Pydantic models
- Don't compare floats with `==`
- Don't test indicators without citing source of expected values
- Don't skip NaN warmup tests
- Don't let any test make a network call

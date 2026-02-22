<claude_instructions>
# CLAUDE.md — Tests

## Commands
```bash
uv run pytest tests/unit -v                        # unit only
uv run pytest tests/integration -v                 # integration only
uv run pytest tests/ -v --cov=src/options_arena     # full + coverage
uv run pytest tests/ -k "test_rsi" -v              # specific test
```

## Absolute Rules
1. **Never hit real APIs.** Mock Anthropic, Ollama, and all data sources. Every test. No exceptions.
2. **Never use `==` for floats.** Always `pytest.approx()`.
3. **Never hardcode dates that depend on `today`.** Mock `date.today()` for DTE tests.
4. **Never inline large test data.** Use `tests/fixtures/` files.

## Fixture Files (`tests/fixtures/`)
- `sample_prices.csv` — OHLCV (include SOURCE in a comment: ticker, date range, provider)
- `option_chain.json` — realistic bid/ask spreads, not just last prices
- `greeks_reference.json` — hand-calculated Greeks with methodology cited
- `debate_transcript.json` — sample 3-round debate for moderator tests
Keep fixtures small: 100-250 rows of daily data is enough.

## Floating Point Tolerances
| Context | Tolerance |
|---|---|
| Indicators (RSI, MACD, BB) | `pytest.approx(rel=1e-4)` |
| Greeks (delta, gamma, etc.) | `pytest.approx(rel=1e-4)` |
| Prices (Decimal) | `pytest.approx(abs=Decimal("0.01"))` |
| Confidence scores | `pytest.approx(abs=0.01)` |
| IV / percentages | `pytest.approx(rel=1e-3)` |

## Indicator Tests — Every Indicator Needs All Five
1. **Known-value**: compare against published source (cite it in comment/docstring).
2. **Minimum data**: exactly `period + 1` rows → one valid output.
3. **Insufficient data**: fewer than minimum → `InsufficientDataError`.
4. **NaN warmup**: verify correct NaN count in output.
5. **Edge cases**: flat data (all same), monotonic, single spike, zero volume.

## Options Model Tests
- JSON roundtrip: `Model.model_validate_json(m.model_dump_json()) == m` for every model.
- Validation rejects bad data: negative volume, delta > 1.0, expiration in past.
- `Decimal` precision survives serialization: `Decimal("1.05")` ≠ `1.0500000000000000444`.
- Computed fields (mid, spread, DTE) produce correct values with known inputs.
- `StrEnum` serialization: `OptionType.CALL` → `"call"` → `OptionType.CALL`.
- Spread models: max_profit/max_loss/breakeven correct for vertical, iron condor, straddle.

## Agent & Debate Tests

### Mocking Anthropic
```python
mock_message = Mock()
mock_message.content = [Mock(text="Bear case: IV is elevated at 72nd percentile...")]
mock_message.stop_reason = "end_turn"
mock_message.usage = Mock(input_tokens=500, output_tokens=200)
mock_client.messages.create.return_value = mock_message
```
Use the actual SDK response shape — don't mock as plain dicts.

### Mocking Ollama
```python
mock_response = Mock()
mock_response.message.content = "Bull case: RSI at 35 suggests oversold..."
mock_client.chat.return_value = mock_response
```

### Debate Tests
- Full 3-round loop with deterministic mock responses.
- Timeout handling: mock a slow response → verify `asyncio.TimeoutError` caught.
- Agent failure mid-debate: other agent wins by default.
- Moderator produces `DebateVerdict` with all required fields populated.
- Debate arguments reference specific contracts (strikes, expirations, Greeks) — not vague claims.

## Conftest Shared Fixtures
Define in `conftest.py`:
- `sample_prices` — DataFrame from `fixtures/sample_prices.csv`
- `sample_option_chain` — parsed `OptionChain` from `fixtures/option_chain.json`
- `mock_anthropic_client` — patched `Anthropic` returning canned responses
- `mock_ollama_client` — patched `ollama.Client` returning canned responses
- `market_context` — fully populated `MarketContext` with realistic options data

## What Claude Gets Wrong Here (Fix These)
- Don't use raw dicts as test data — construct typed Pydantic models (`OptionContract(...)`, `MarketContext(...)`, etc.) just like production code would. Test fixtures should prove that the typed model pipeline works end-to-end.
- Don't compare floats with `==`.
- Don't test indicators without citing source of expected values.
- Don't mock Anthropic as plain dicts — use SDK response objects.
- Don't skip NaN warmup tests — they catch smoothing bugs.
- Don't write date-dependent tests without mocking `date.today()`.
- Don't let any test make a network call.
- Don't skip spread strategy P&L tests — max_profit/max_loss math is error-prone.
</claude_instructions>

# No Raw Dicts

Every function that returns structured data MUST return a Pydantic model, dataclass,
or StrEnum. NEVER `dict`, `dict[str, Any]`, `dict[str, float]`, or any dict variant.

```python
# WRONG
def get_greeks(contract: OptionContract) -> dict[str, float]: ...
def get_signals(ticker: str) -> dict[str, Any]: ...

# RIGHT
def get_greeks(contract: OptionContract) -> OptionGreeks: ...
def get_signals(ticker: str) -> IndicatorSignals: ...
```

Applies to: function returns, parameters, model fields, intermediate variables
between modules, API response parsing. Exception: `indicators/` uses pandas
Series/DataFrames (not dicts).

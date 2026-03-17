# Financial Precision

| Data Type | Python Type | Construction | Examples |
|-----------|------------|--------------|----------|
| Prices, P&L, cost | `Decimal` | From string: `Decimal("185.50")` | strike, bid, ask, last |
| Greeks, IV, ratios | `float` | Direct: `0.45` | delta, gamma, iv_rank, rsi |
| Volume, OI | `int` | Direct: `1500` | volume, open_interest |
| Expiration | `date` | `datetime.date` | expiration |
| Timestamps | `datetime` | With UTC tzinfo | data_timestamp, checked_at |

Rules:
- `Decimal` from STRING, never float: `Decimal("1.05")` not `Decimal(1.05)`
- Every `Decimal` field needs `field_serializer` to `str` (prevents float precision loss in JSON)
- `mid` divides by `Decimal("2")` not `2` (keeps Decimal precision)
- `datetime` fields need UTC validator: reject naive and non-UTC
- `dividend_yield` is `float` default `0.0`, NEVER `None` — waterfall uses `is None`, not falsy

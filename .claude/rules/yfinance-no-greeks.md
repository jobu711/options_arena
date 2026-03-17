# yfinance Provides NO Greeks

yfinance option chains provide ONLY `impliedVolatility`. No delta, gamma, theta,
vega, or rho. All Greeks are computed locally by `pricing/dispatch.py`.

- `OptionContract.greeks` is ALWAYS `None` from yfinance/services
- Greeks are populated by `scoring/contracts.py` via `pricing/dispatch.py`
- `impliedVolatility` is stored as `market_iv` (already annualized, do NOT re-annualize)
- `market_iv` is used as IV solver seed and sanity-check against locally computed IV
- `pricing/dispatch.py` is the SOLE source of Greeks for the entire pipeline

This is the single most common assumption error in this codebase.

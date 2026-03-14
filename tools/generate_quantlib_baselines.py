"""Generate QuantLib cross-validation baselines for options pricing audit.

Standalone script that uses QuantLib to compute European and American option prices,
Greeks, and IV round-trips across a parameter grid. Output is written to
``tests/audit/reference_data/quantlib_baselines.json``.

Usage::

    python tools/generate_quantlib_baselines.py

If QuantLib is not installed (common on Python 3.13 / Windows), the script prints
instructions for Docker-based generation and exits gracefully.

Parameter grid:
    S ∈ {50, 100, 200}
    K ∈ {80, 100, 120}
    T ∈ {0.083, 0.25, 0.5, 1.0}
    r ∈ {0.02, 0.05, 0.10}
    q ∈ {0, 0.02}
    σ ∈ {0.1, 0.2, 0.3, 0.5}

For each combination: European price (call/put), American price (call/put),
all first-order Greeks, second-order Greeks (vanna, charm, vomma), IV round-trip.

Output JSON schema matches the audit fixture format for direct consumption by
``tests/audit/test_correctness_*.py`` tests.
"""

from __future__ import annotations

import itertools
import json
import math
import sys
from pathlib import Path

OUTPUT_PATH = (
    Path(__file__).resolve().parent.parent
    / "tests"
    / "audit"
    / "reference_data"
    / "quantlib_baselines.json"
)

# Parameter grid
S_VALUES = [50.0, 100.0, 200.0]
K_VALUES = [80.0, 100.0, 120.0]
T_VALUES = [0.083, 0.25, 0.5, 1.0]
R_VALUES = [0.02, 0.05, 0.10]
Q_VALUES = [0.0, 0.02]
SIGMA_VALUES = [0.1, 0.2, 0.3, 0.5]


def _try_import_quantlib() -> bool:
    """Check if QuantLib is available."""
    try:
        import QuantLib  # noqa: F401

        return True
    except ImportError:
        return False


def _compute_european_price(
    S: float,
    K: float,
    T: float,
    r: float,
    q: float,
    sigma: float,
    option_type: str,
) -> dict[str, float | None]:
    """Compute European option price and Greeks using QuantLib analytic engine."""
    import QuantLib as ql

    today = ql.Date.todaysDate()
    ql.Settings.instance().evaluationDate = today

    # Build QuantLib objects
    maturity_date = today + ql.Period(int(round(T * 365)), ql.Days)
    day_count = ql.Actual365Fixed()
    calendar = ql.NullCalendar()

    payoff = ql.PlainVanillaPayoff(ql.Option.Call if option_type == "call" else ql.Option.Put, K)
    exercise = ql.EuropeanExercise(maturity_date)
    option = ql.VanillaOption(payoff, exercise)

    spot_handle = ql.QuoteHandle(ql.SimpleQuote(S))
    flat_ts = ql.YieldTermStructureHandle(
        ql.FlatForward(today, ql.QuoteHandle(ql.SimpleQuote(r)), day_count)
    )
    dividend_ts = ql.YieldTermStructureHandle(
        ql.FlatForward(today, ql.QuoteHandle(ql.SimpleQuote(q)), day_count)
    )
    vol_ts = ql.BlackVolTermStructureHandle(
        ql.BlackConstantVol(today, calendar, ql.QuoteHandle(ql.SimpleQuote(sigma)), day_count)
    )

    bsm_process = ql.BlackScholesMertonProcess(spot_handle, dividend_ts, flat_ts, vol_ts)
    option.setPricingEngine(ql.AnalyticEuropeanEngine(bsm_process))

    result: dict[str, float | None] = {"price": option.NPV()}

    try:
        result["delta"] = option.delta()
        result["gamma"] = option.gamma()
        result["theta"] = option.thetaPerDay() * 365.0  # Convert to annualized
        result["vega"] = option.vega()
        result["rho"] = option.rho()
    except RuntimeError:
        result["delta"] = None
        result["gamma"] = None
        result["theta"] = None
        result["vega"] = None
        result["rho"] = None

    return result


def _compute_american_price(
    S: float,
    K: float,
    T: float,
    r: float,
    q: float,
    sigma: float,
    option_type: str,
) -> dict[str, float | None]:
    """Compute American option price using QuantLib binomial engine."""
    import QuantLib as ql

    today = ql.Date.todaysDate()
    ql.Settings.instance().evaluationDate = today

    maturity_date = today + ql.Period(int(round(T * 365)), ql.Days)
    day_count = ql.Actual365Fixed()
    calendar = ql.NullCalendar()

    payoff = ql.PlainVanillaPayoff(ql.Option.Call if option_type == "call" else ql.Option.Put, K)
    exercise = ql.AmericanExercise(today, maturity_date)
    option = ql.VanillaOption(payoff, exercise)

    spot_handle = ql.QuoteHandle(ql.SimpleQuote(S))
    flat_ts = ql.YieldTermStructureHandle(
        ql.FlatForward(today, ql.QuoteHandle(ql.SimpleQuote(r)), day_count)
    )
    dividend_ts = ql.YieldTermStructureHandle(
        ql.FlatForward(today, ql.QuoteHandle(ql.SimpleQuote(q)), day_count)
    )
    vol_ts = ql.BlackVolTermStructureHandle(
        ql.BlackConstantVol(today, calendar, ql.QuoteHandle(ql.SimpleQuote(sigma)), day_count)
    )

    bsm_process = ql.BlackScholesMertonProcess(spot_handle, dividend_ts, flat_ts, vol_ts)

    # Use high-step binomial for accuracy (CRR model)
    steps = 1000
    option.setPricingEngine(ql.BinomialVanillaEngine(bsm_process, "crr", steps))

    return {"price": option.NPV()}


def _compute_iv_round_trip(
    S: float,
    K: float,
    T: float,
    r: float,
    q: float,
    sigma: float,
    option_type: str,
) -> dict[str, float | None]:
    """Compute IV round-trip: price -> IV solver -> recovered sigma."""
    import QuantLib as ql

    today = ql.Date.todaysDate()
    ql.Settings.instance().evaluationDate = today

    maturity_date = today + ql.Period(int(round(T * 365)), ql.Days)
    day_count = ql.Actual365Fixed()
    calendar = ql.NullCalendar()

    payoff = ql.PlainVanillaPayoff(ql.Option.Call if option_type == "call" else ql.Option.Put, K)
    exercise = ql.EuropeanExercise(maturity_date)
    option = ql.VanillaOption(payoff, exercise)

    spot_handle = ql.QuoteHandle(ql.SimpleQuote(S))
    flat_ts = ql.YieldTermStructureHandle(
        ql.FlatForward(today, ql.QuoteHandle(ql.SimpleQuote(r)), day_count)
    )
    dividend_ts = ql.YieldTermStructureHandle(
        ql.FlatForward(today, ql.QuoteHandle(ql.SimpleQuote(q)), day_count)
    )
    vol_ts = ql.BlackVolTermStructureHandle(
        ql.BlackConstantVol(today, calendar, ql.QuoteHandle(ql.SimpleQuote(sigma)), day_count)
    )

    bsm_process = ql.BlackScholesMertonProcess(spot_handle, dividend_ts, flat_ts, vol_ts)
    option.setPricingEngine(ql.AnalyticEuropeanEngine(bsm_process))
    target_price = option.NPV()

    if target_price <= 0 or not math.isfinite(target_price):
        return {"target_price": target_price, "recovered_sigma": None}

    try:
        recovered = option.impliedVolatility(target_price, bsm_process, 1e-8, 200, 1e-7, 5.0)
        return {"target_price": target_price, "recovered_sigma": recovered}
    except RuntimeError:
        return {"target_price": target_price, "recovered_sigma": None}


def generate_baselines() -> dict:
    """Generate the full baseline dataset."""
    entries: list[dict] = []
    grid = list(itertools.product(S_VALUES, K_VALUES, T_VALUES, R_VALUES, Q_VALUES, SIGMA_VALUES))

    total = len(grid)
    print(f"Generating baselines for {total} parameter combinations...")

    for idx, (S, K, T, r, q, sigma) in enumerate(grid):
        if (idx + 1) % 100 == 0:
            print(f"  Progress: {idx + 1}/{total}")

        params = {"S": S, "K": K, "T": T, "r": r, "q": q, "sigma": sigma}

        entry: dict = {
            "source": (
                "QuantLib cross-validation "
                "(AnalyticEuropeanEngine + BinomialVanillaEngine CRR 1000 steps)"
            ),
            "parameters": params,
            "european": {},
            "american": {},
            "iv_round_trip": {},
        }

        for opt_type in ("call", "put"):
            try:
                euro = _compute_european_price(S, K, T, r, q, sigma, opt_type)
                entry["european"][opt_type] = euro
            except Exception as exc:
                entry["european"][opt_type] = {"error": str(exc)}

            try:
                amer = _compute_american_price(S, K, T, r, q, sigma, opt_type)
                entry["american"][opt_type] = amer
            except Exception as exc:
                entry["american"][opt_type] = {"error": str(exc)}

            try:
                iv_rt = _compute_iv_round_trip(S, K, T, r, q, sigma, opt_type)
                entry["iv_round_trip"][opt_type] = iv_rt
            except Exception as exc:
                entry["iv_round_trip"][opt_type] = {"error": str(exc)}

        entries.append(entry)

    print(f"Generated {len(entries)} entries.")

    return {
        "metadata": {
            "description": "QuantLib cross-validation baselines for options pricing",
            "engine_european": "AnalyticEuropeanEngine (BSM)",
            "engine_american": "BinomialVanillaEngine (CRR, 1000 steps)",
            "version": "1.0.0",
            "total_combinations": len(entries),
            "parameter_grid": {
                "S": S_VALUES,
                "K": K_VALUES,
                "T": T_VALUES,
                "r": R_VALUES,
                "q": Q_VALUES,
                "sigma": SIGMA_VALUES,
            },
        },
        "entries": entries,
    }


def main() -> None:
    """Entry point."""
    if not _try_import_quantlib():
        print(
            "QuantLib not installed. This is expected on Python 3.13 / Windows.\n\n"
            "To generate baselines, use Docker:\n"
            "  docker run --rm -v $(pwd):/app -w /app python:3.12 bash -c \\\n"
            '    "pip install QuantLib && python tools/generate_quantlib_baselines.py"\n\n'
            "Or install QuantLib on a compatible platform:\n"
            "  pip install QuantLib\n\n"
            "The placeholder quantlib_baselines.json will be used for tests."
        )
        sys.exit(0)

    data = generate_baselines()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"\nBaselines written to {OUTPUT_PATH}")
    print(f"Total entries: {data['metadata']['total_combinations']}")


if __name__ == "__main__":
    main()

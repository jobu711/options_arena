<role>
You are a quantitative derivatives analyst who has built
and validated pricing libraries at multiple institutions.
You know the practical limitations of analytical models:
BAW's approximation error near the early exercise boundary,
BSM's assumption of constant vol and no dividends, and the
difference between model Greeks (smooth, theoretical) and
market Greeks (noisy, reflecting supply/demand/skew).
You validate models by measuring their impact on
actual trading decisions, not just theoretical accuracy.
</role>

<context>
{{CLAUDE.md from project root}}
{{src/options_arena/pricing/CLAUDE.md}}
{{src/options_arena/pricing/dispatch.py — price_option(), compute_greeks()}}
{{src/options_arena/pricing/bsm.py — BSM formulas}}
{{src/options_arena/pricing/american.py — BAW formulas}}
{{src/options_arena/services/cboe_provider.py — CBOE native Greeks}}
{{src/options_arena/scoring/contracts.py — recommend_contracts(), delta targeting}}
{{data from: recommended_contracts — delta, greeks_source, pricing_model}}

### Three-Tier Greeks in ChainProvider
Tier 1: CBOE native Greeks (market-derived, trusted)
Tier 2: Local BAW/BSM computation (analytical, may deviate)
Tier 3: Exclude contract (no Greeks available)

### Contract Selection Criteria
- Target delta: ~0.35 (configurable)
- DTE: 30-365 days
- Liquidity: volume >= 100, OI >= 100
- Spread: < 15% of mid

### What We Can Compare
For contracts where both CBOE Greeks AND local Greeks were computed:
- Delta deviation: |local_delta - cboe_delta|
- Gamma, theta, vega deviations
- Did the deviation cause a DIFFERENT contract to be selected?
</context>

<task>
Audit the accuracy of locally computed Greeks (BAW/BSM)
against CBOE market Greeks, and measure whether
inaccuracies affect contract selection quality.

The question is NOT "are the formulas correct?"
(they're textbook). The question is: "do the practical
inputs (IV, dividend yield, risk-free rate) produce
Greeks close enough to market values to select the
RIGHT contract?"
</task>

<instructions>
### Framework 1 — Delta Accuracy
Delta is the most critical Greek (drives contract selection):
- For all contracts with both CBOE and local delta:
  Compute mean absolute error, RMSE, max deviation
- Stratify by: moneyness (ITM/ATM/OTM), DTE bucket,
  IV regime, option type (call/put)
- Where is deviation worst? (Expected: deep ITM American calls
  near dividends, where early exercise premium matters most)
- Does the deviation cross the 0.35 target threshold?
  (e.g., local says 0.35, CBOE says 0.28 — wrong contract)

### Framework 2 — Input Sensitivity
Greeks accuracy depends on inputs:
- **IV**: Local uses market_iv from chain. Is this ATM IV,
  strike-specific IV, or bid/ask IV? Mismatch → delta error.
- **Dividend yield**: Uses TickerInfo.dividend_yield (trailing 12m).
  CBOE may use forward dividend schedule. Mismatch for
  high-yield stocks → significant call delta error.
- **Risk-free rate**: Uses FRED 10yr Treasury. CBOE may use
  different tenor or different rate. Small impact.
- **Time**: Do we use calendar days or trading days for DTE?
  CBOE models typically use calendar days.

For each input, estimate its contribution to observed delta error.

### Framework 3 — Contract Selection Impact
The key question — does delta inaccuracy change which contract
is recommended?
- Take all scans where CBOE Greeks were available
- Recompute contract selection using CBOE delta vs local delta
- How often is a DIFFERENT contract selected?
- When different, which contract had better actual P&L?
- Is the delta-targeting threshold (0.35) itself optimal,
  or should it adapt to what the local model is actually computing?

### Framework 4 — Theta/Vega Impact on Debates
Theta and vega go into MarketContext for debate agents:
- If local theta is -0.05 but market theta is -0.08,
  agents underestimate time decay cost
- If local vega is 0.45 but market vega is 0.30,
  agents overestimate IV sensitivity
- How often do these deviations change the agent's
  qualitative assessment? (e.g., "theta is manageable"
  vs "theta is aggressive")
</instructions>

<constraints>
- Only compare where BOTH CBOE and local Greeks exist
  (greeks_source="market" vs greeks_source="computed")
- BAW for American is an approximation — some deviation is expected
  and acceptable. Quantify "acceptable" in delta terms
- Small sample sizes for deep ITM/OTM — flag statistical uncertainty
- This audit doesn't require outcome data — it compares two
  computed values, not predictions vs reality
</constraints>

<output_format>
1. **Delta Accuracy Table** — MAE, RMSE by moneyness/DTE/IV regime
2. **Input Sensitivity** — Which input contributes most to error
3. **Contract Selection Impact** — % of scans where wrong contract was chosen
4. **Theta/Vega Debate Impact** — Qualitative assessment changes
5. **Recommended Fixes** — Input adjustments, model improvements,
   or fallback strategies
6. **Model Adequacy Verdict** — Is BAW/BSM good enough, or do we
   need a different approach?
</output_format>

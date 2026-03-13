# Options Arena — Technical Reference

> Auto-generated codebase reference. Version 2.8.0.

## Table of Contents

- [Section 1: API Reference](#section-1-api-reference)
- [Section 2: Call / Dependency Graph](#section-2-call--dependency-graph)
- [Section 3: Traceability Matrix](#section-3-traceability-matrix)

---

## Section 1: API Reference

Modules ordered by dependency depth (leaf modules first, entry points last).

---

### 1.1 `utils/` — Exception Hierarchy

#### utils/exceptions.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `DataFetchError` | class | `(Exception)` | 8 | Base exception for all data fetching and data quality errors. |
| `TickerNotFoundError` | class | `(DataFetchError)` | 12 | Raised when a requested ticker symbol cannot be found in any data source. |
| `InsufficientDataError` | class | `(DataFetchError)` | 16 | Raised when available data is insufficient for the requested computation. |
| `DataSourceUnavailableError` | class | `(DataFetchError)` | 20 | Raised when an external data source is unreachable or returns an error. |
| `RateLimitExceededError` | class | `(DataFetchError)` | 24 | Raised when an external API rate limit has been exceeded. |

---

### 1.2 `models/` — Pydantic Models, Enums, Config

#### models/_validators.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `validate_unit_interval` | func | `(v: float, field_name: str = 'confidence') -> float` | 11 | Validate a float is finite and within [0.0, 1.0]. |
| `validate_non_empty_list` | func | `(v: list[str], field_name: str = 'list') -> list[str]` | 23 | Validate a list of strings has at least one element. |

#### models/analysis.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `MarketContext` | model |  | 52 | Snapshot of ticker state for analysis and debate agents. |
| `AgentResponse` | model | `frozen=True` | 482 | Structured response from a debate agent. |
| `TradeThesis` | model | `frozen=True` | 519 | Final trade recommendation produced by the debate system. |
| `VolatilityThesis` | model | `frozen=True` | 607 | Structured output from the Volatility Agent. |
| `FlowThesis` | model | `frozen=True` | 654 | Structured output from the Flow Agent. |
| `RiskAssessment` | model | `frozen=True` | 685 | Expanded risk assessment output from the Risk Agent. |
| `FundamentalThesis` | model | `frozen=True` | 730 | Structured output from the Fundamental Agent. |
| `ContrarianThesis` | model | `frozen=True` | 762 | Structured output from the Contrarian Agent. |
| `ExtendedTradeThesis` | model | `(TradeThesis)` | 792 | Extended trade thesis with contrarian dissent, agreement scoring, and dimensional scores. |
| `AgentPrediction` | model | `frozen=True` | 837 | Per-agent prediction record for accuracy tracking. |

#### models/analytics.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `RecommendedContract` | model | `frozen=True` | 35 | A recommended option contract persisted from a scan run. |
| `ContractOutcome` | model | `frozen=True` | 203 | Outcome data for a recommended contract at a given exit point. |
| `NormalizationStats` | model | `frozen=True` | 293 | Normalization statistics for a single indicator in a scan run. |
| `WinRateResult` | model | `frozen=True` | 356 | Win rate analytics result grouped by signal direction. |
| `ScoreCalibrationBucket` | model | `frozen=True` | 394 | Score calibration analytics result for a score range bucket. |
| `IndicatorAttributionResult` | model | `frozen=True` | 440 | Indicator attribution analytics result. |
| `HoldingPeriodResult` | model | `frozen=True` | 491 | Holding period analytics result. |
| `DeltaPerformanceResult` | model | `frozen=True` | 541 | Delta performance analytics result. |
| `PerformanceSummary` | model | `frozen=True` | 591 | Aggregate performance summary over a lookback period. |
| `AgentAccuracyReport` | model | `frozen=True` | 660 | Per-agent direction accuracy and Brier score. |
| `CalibrationBucket` | model | `frozen=True` | 710 | Single confidence calibration bucket. |
| `AgentCalibrationData` | model | `frozen=True` | 761 | Per-agent or aggregate confidence calibration data. |
| `AgentWeightsComparison` | model | `frozen=True` | 779 | Manual vs auto-tuned weight comparison for a single agent. |
| `EquityCurvePoint` | model | `frozen=True` | 825 | A single data point on the backtesting equity curve. |
| `DrawdownPoint` | model | `frozen=True` | 857 | A single data point on the backtesting drawdown curve. |
| `SectorPerformanceResult` | model | `frozen=True` | 889 | Backtesting performance analytics grouped by GICS sector. |
| `DTEBucketResult` | model | `frozen=True` | 933 | Backtesting performance analytics grouped by days-to-expiration range. |
| `IVRankBucketResult` | model | `frozen=True` | 987 | Backtesting performance analytics grouped by implied volatility rank range. |
| `GreeksDecompositionResult` | model | `frozen=True` | 1041 | Backtesting P&L decomposition by Greeks for a group of contracts. |
| `HoldingPeriodComparison` | model | `frozen=True` | 1077 | Backtesting holding period comparison for a specific duration and direction. |
| `WeightSnapshot` | model | `frozen=True` | 1142 | A point-in-time snapshot of auto-tuned agent weights. |

#### models/config.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `ScanConfig` | model |  | 28 | Scan pipeline configuration — scoring thresholds, timeouts, toggles, and filters. |
| `PricingConfig` | model |  | 69 | Options pricing configuration — delta targeting and IV solver parameters. |
| `ServiceConfig` | model |  | 91 | External service configuration — timeouts, rate limits, cache TTLs. |
| `LogConfig` | model |  | 124 | Logging configuration — controls JSON mode for structured logging. |
| `DataConfig` | model |  | 130 | Data layer configuration — controls database path. |
| `DebateConfig` | model |  | 136 | AI debate configuration — controls LLM provider, timeouts, and fallback behavior. |
| `IntelligenceConfig` | model |  | 281 | Intelligence data configuration — controls yfinance intelligence fetching. |
| `AnalyticsConfig` | model |  | 310 | Analytics persistence configuration — controls outcome collection and batch sizing. |
| `FinancialDatasetsConfig` | model |  | 353 | Financial Datasets AI configuration — controls optional fundamental data enrichment. |
| `OpenBBConfig` | model |  | 395 | OpenBB Platform SDK configuration — controls optional enrichment data. |
| `AppSettings` | model |  | 417 | Root application settings — the sole BaseSettings subclass. |

#### models/enums.py

| Symbol | Kind | Values | Line | Description |
|--------|------|--------|------|-------------|
| `TICKER_RE` | const | re.compile | 11 |  |
| `OptionType` | StrEnum | CALL, PUT | 14 | Type of option contract. |
| `PositionSide` | StrEnum | LONG, SHORT | 21 | Direction of a position (long or short). |
| `SignalDirection` | StrEnum | BULLISH, BEARISH, NEUTRAL | 28 | Directional signal from indicators or analysis. |
| `ExerciseStyle` | StrEnum | AMERICAN, EUROPEAN | 36 | Exercise style of an option contract. |
| `PricingModel` | StrEnum | BSM, BAW | 47 | Pricing model used to compute Greeks. |
| `MarketCapTier` | StrEnum | MEGA, LARGE, MID, SMALL, MICRO | 58 | Market capitalisation tier for ticker classification. |
| `DividendSource` | StrEnum | FORWARD, TRAILING, COMPUTED, NONE | 68 | Provenance of the dividend yield value on ``TickerInfo``. |
| `SpreadType` | StrEnum | VERTICAL, CALENDAR, IRON_CONDOR, STRADDLE, STRANGLE, BUTTERFLY | 84 | Type of option spread strategy. |
| `MacdSignal` | StrEnum | BULLISH_CROSSOVER, BEARISH_CROSSOVER, NEUTRAL | 95 | MACD crossover signal for market context. |
| `ScanPreset` | StrEnum | FULL, SP500, ETFS, NASDAQ100, RUSSELL2000, MOST_ACTIVE | 108 | Scan universe preset for the scan pipeline. |
| `ScanSource` | StrEnum | MANUAL | 127 | Origin of a scan request. |
| `GreeksSource` | StrEnum | COMPUTED, MARKET | 136 | Source of Greeks values on an option contract. |
| `VolAssessment` | StrEnum | OVERPRICED, UNDERPRICED, FAIR | 147 | Implied volatility assessment from the Volatility Agent. |
| `MarketRegime` | StrEnum | TRENDING, MEAN_REVERTING, VOLATILE, CRISIS | 160 | Market regime classification for regime-adjusted scoring weights. |
| `VolRegime` | StrEnum | LOW, NORMAL, ELEVATED, EXTREME | 169 | Implied volatility regime classification. |
| `IVTermStructureShape` | StrEnum | CONTANGO, FLAT, BACKWARDATION | 178 | IV term structure shape classification. |
| `RiskLevel` | StrEnum | LOW, MODERATE, HIGH, EXTREME | 186 | Quantified risk level for risk assessment. |
| `CatalystImpact` | StrEnum | LOW, MODERATE, HIGH | 195 | Expected impact of upcoming catalysts (earnings, dividends, etc.). |
| `SentimentLabel` | StrEnum | BULLISH, BEARISH, NEUTRAL | 203 | Sentiment classification for news or social media analysis. |
| `OutcomeCollectionMethod` | StrEnum | MARKET, INTRINSIC, EXPIRED_WORTHLESS | 214 | Method used to collect contract outcome data. |
| `GreeksGroupBy` | StrEnum | DIRECTION, SECTOR | 227 | Grouping column for Greeks P&L decomposition. |
| `LLMProvider` | StrEnum | GROQ, ANTHROPIC | 238 | LLM provider for AI debate agents. |
| `GICSSector` | StrEnum | 11 values (COMMUNICATION_SERVICES ... UTILITIES) | 249 | Global Industry Classification Standard (GICS) sectors. |
| `SECTOR_ALIASES` | const | dict[str, GICSSector] | 269 |  |
| `GICSIndustryGroup` | StrEnum | 26 values (TELECOMMUNICATION_SERVICES ... UTILITIES) | 309 | GICS Industry Groups (2023 standard). |
| `INDUSTRY_GROUP_ALIASES` | const | dict[str, GICSIndustryGroup] | 355 |  |
| `SECTOR_TO_INDUSTRY_GROUPS` | const | dict[GICSSector, list[GICSIndustryGroup]] | 666 |  |

#### models/filters.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `UniverseFilters` | model | `frozen=True` | 30 | Phase 1 universe selection filters — controls which tickers enter the pipeline. |
| `ScoringFilters` | model | `frozen=True` | 172 | Post-Phase 2 scoring threshold filters. |
| `OptionsFilters` | model | `frozen=True` | 210 | Phase 3 option chain selection filters. |
| `ScanFilterSpec` | model | `frozen=True` | 359 | Composite container for all scan pipeline filters. |

#### models/financial_datasets.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `FinancialMetricsData` | model | `frozen=True` | 19 | Point-in-time financial metrics for a ticker. |
| `IncomeStatementData` | model | `frozen=True` | 81 | Point-in-time income statement data for a ticker. |
| `BalanceSheetData` | model | `frozen=True` | 117 | Point-in-time balance sheet data for a ticker. |
| `FinancialDatasetsPackage` | model | `frozen=True` | 152 | Aggregate container for all financialdatasets.ai data for a ticker. |

#### models/health.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `HealthStatus` | model | `frozen=True` | 13 | Health check result for an external service. |

#### models/history.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `HistoryPoint` | model | `frozen=True` | 18 | A single scan-score data point for a ticker. |
| `TrendingTicker` | model | `frozen=True` | 52 | A ticker trending in one direction over multiple consecutive scans. |

#### models/intelligence.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `ACTION_MAP` | const | `dict[str, str]` | 25 |  |
| `parse_transaction_type` | func | `(text: str) -> str` | 39 | Parse insider transaction type from descriptive text. |
| `AnalystSnapshot` | model | `frozen=True` | 64 | Point-in-time analyst consensus data for a ticker. |
| `UpgradeDowngrade` | model | `frozen=True` | 151 | Single analyst upgrade/downgrade event. |
| `AnalystActivitySnapshot` | model | `frozen=True` | 194 | Recent analyst activity summary for a ticker. |
| `InsiderTransaction` | model | `frozen=True` | 232 | Single insider transaction record. |
| `InsiderSnapshot` | model | `frozen=True` | 268 | Insider trading activity summary for a ticker. |
| `InstitutionalSnapshot` | model | `frozen=True` | 318 | Institutional ownership data for a ticker. |
| `IntelligencePackage` | model | `frozen=True` | 383 | Combined intelligence data for a ticker. |

#### models/market_data.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `OHLCV` | model | `frozen=True` | 22 | Historical daily price bar. |
| `Quote` | model | `frozen=True` | 90 | Real-time price snapshot with bid/ask. |
| `TickerInfo` | model | `frozen=True` | 144 | Fundamental data for a ticker including dividend yield with provenance tracking. |

#### models/metadata.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `TickerMetadata` | model | `frozen=True` | 18 | Cached sector, industry group, and market-cap classification for a ticker. |
| `MetadataCoverage` | model | `frozen=True` | 44 | Coverage statistics for the ticker metadata index. |

#### models/openbb.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `FundamentalSnapshot` | model | `frozen=True` | 22 | Point-in-time fundamental metrics for a ticker. |
| `UnusualFlowSnapshot` | model | `frozen=True` | 69 | Point-in-time unusual options/dark-pool flow data for a ticker. |
| `NewsHeadline` | model | `frozen=True` | 103 | Single news headline with VADER sentiment score. |
| `NewsSentimentSnapshot` | model | `frozen=True` | 135 | Aggregated news sentiment for a ticker. |
| `OpenBBHealthStatus` | model | `frozen=True` | 179 | Health status of OpenBB data providers. |

#### models/options.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `OptionGreeks` | model | `frozen=True` | 32 | Sensitivity measures for an option contract. |
| `OptionContract` | model | `frozen=True` | 98 | A single option contract with market data and optional computed Greeks. |
| `SpreadLeg` | model | `frozen=True` | 206 | A single leg of an option spread. |
| `OptionSpread` | model | `frozen=True` | 234 | A multi-leg option spread strategy. |

#### models/scan.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `IndicatorSignals` | model |  | 31 | 65 named indicator fields (18 original + 1 MACD + 40 DSE + 2 liquidity + 4 native quant). |
| `ScanRun` | model | `frozen=True` | 155 | Metadata for a completed scan run. |
| `TickerScore` | model |  | 192 | Scored ticker from the scan pipeline. |

#### models/scan_delta.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `TickerDelta` | model | `frozen=True` | 20 | Score change for a single ticker between two scans. |
| `ScanDiff` | model | `frozen=True` | 46 | Full diff between two scans. |

#### models/scoring.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `DimensionalScores` | model | `frozen=True` | 15 | 8 per-family sub-scores computed from IndicatorSignals. |
| `DirectionSignal` | model | `frozen=True` | 50 | Continuous direction confidence with contributing signal breakdown. |

---

### 1.3 `indicators/` — Pure Math Functions

#### indicators/_validation.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `validate_aligned` | func | `(*series: pd.Series) -> None` | 6 | Validate that all input Series have the same length. |

#### indicators/flow_analytics.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `compute_gex` | func | `(chain_calls: pd.DataFrame, chain_puts: pd.DataFrame, spot: float) -> float | None` | 16 | Net Gamma Exposure (GEX). |
| `compute_oi_concentration` | func | `(chain: pd.DataFrame) -> float | None` | 78 | OI concentration: max_strike_OI / total_OI. |
| `compute_unusual_activity` | func | `(chain: pd.DataFrame) -> float | None` | 104 | Unusual activity score: premium-weighted volume/OI for strikes where vol > 2x OI. |
| `compute_max_pain_magnet` | func | `(spot: float, max_pain: float | None) -> float | None` | 147 | Max pain magnet strength: 1 - (\|spot - max_pain\| / spot). |
| `compute_dollar_volume_trend` | func | `(close: pd.Series, volume: pd.Series, period: int = 20) -> float | None` | 172 | 20-day slope of dollar volume (close x volume). |

#### indicators/fundamental.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `compute_earnings_em_ratio` | func | `(expected_move: float | None, avg_post_earnings_move: float | None) -> float | None` | 15 | Earnings expected move ratio: IV-implied EM / avg actual post-earnings move. |
| `compute_earnings_impact` | func | `(days_to_earnings: int | None, dte: int) -> float | None` | 41 | Days-to-earnings impact score. |
| `compute_short_interest` | func | `(short_ratio: float | None) -> float | None` | 74 | Short interest ratio passthrough with validation. |
| `compute_div_impact` | func | `(div_yield: float, dte: int, days_to_ex: int | None) -> float | None` | 97 | Dividend impact score. |
| `compute_iv_crush_history` | func | `(hv_pre_earnings: pd.Series | None, hv_post_earnings: pd.Series | None) -> float | None` | 136 | IV crush proxy using historical volatility before vs after earnings. |

#### indicators/hv_estimators.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `compute_hv_parkinson` | func | `(high: pd.Series, low: pd.Series, period: int = 20) -> float | None` | 25 | Parkinson (1980) historical volatility estimator using high-low range. |
| `compute_hv_rogers_satchell` | func | `(open_: pd.Series, high: pd.Series, low: pd.Series, close: pd.Series, period: int = 20) -> float ...` | 87 | Rogers-Satchell (1991) historical volatility estimator. |
| `compute_hv_yang_zhang` | func | `(open_: pd.Series, high: pd.Series, low: pd.Series, close: pd.Series, period: int = 20) -> float ...` | 150 | Yang-Zhang (2000) historical volatility estimator. |

#### indicators/iv_analytics.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `compute_iv_hv_spread` | func | `(atm_iv_30d: float | None, hv_20d: float | None) -> float | None` | 22 | IV-HV spread: implied volatility minus realized volatility. |
| `compute_hv_20d` | func | `(close_series: pd.Series) -> float | None` | 49 | 20-day historical volatility (annualized standard deviation of log returns). |
| `compute_iv_term_slope` | func | `(iv_60d: float | None, iv_30d: float | None) -> float | None` | 84 | IV term structure slope: (IV_60d - IV_30d) / IV_30d. |
| `compute_iv_term_shape` | func | `(slope: float | None) -> IVTermStructureShape | None` | 113 | Classify IV term structure shape from slope. |
| `compute_put_skew` | func | `(iv_25d_put: float | None, iv_atm: float | None) -> float | None` | 138 | Put skew index: (IV_25delta_put - IV_ATM) / IV_ATM. |
| `compute_call_skew` | func | `(iv_25d_call: float | None, iv_atm: float | None) -> float | None` | 167 | Call skew index: (IV_25delta_call - IV_ATM) / IV_ATM. |
| `compute_skew_ratio` | func | `(iv_25d_put: float | None, iv_25d_call: float | None) -> float | None` | 195 | Skew ratio: IV_25d_put / IV_25d_call. |
| `classify_vol_regime` | func | `(iv_rank: float | None) -> VolRegime | None` | 224 | Classify volatility regime from IV rank. |
| `compute_ewma_vol_forecast` | func | `(returns: pd.Series, lambda_: float = 0.94) -> float | None` | 254 | EWMA volatility forecast (RiskMetrics methodology). |
| `compute_vol_cone_pctl` | func | `(hv_20d: float | None, hv_history: pd.Series) -> float | None` | 298 | Volatility cone percentile: where current HV sits in historical HV distribution. |
| `compute_vix_correlation` | func | `(ticker_returns: pd.Series, vix_changes: pd.Series) -> float | None` | 331 | Rolling 60-day correlation between ticker returns and VIX changes. |
| `compute_expected_move` | func | `(spot: float, atm_iv: float | None, dte: int) -> float | None` | 371 | Expected move: spot * atm_iv * sqrt(dte / 365). |
| `compute_expected_move_ratio` | func | `(iv_em: float | None, avg_actual_move: float | None) -> float | None` | 404 | Ratio of IV-implied expected move to average actual move. |

#### indicators/moving_averages.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `sma_alignment` | func | `(close: pd.Series, short: int = 20, medium: int = 50, long: int = 200) -> pd.Series` | 14 | SMA convergence/alignment measure. |
| `vwap_deviation` | func | `(close: pd.Series, volume: pd.Series) -> pd.Series` | 53 | Percentage deviation from cumulative VWAP. |

#### indicators/options_specific.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `iv_rank` | func | `(current_iv: float, iv_high: float, iv_low: float) -> float` | 18 | IV Rank: (current - low) / (high - low) * 100. |
| `iv_percentile` | func | `(iv_history: pd.Series, current_iv: float) -> float` | 34 | IV Percentile: % of days in history where IV was lower than current. |
| `put_call_ratio_volume` | func | `(put_volume: int, call_volume: int) -> float` | 61 | Put/Call ratio by volume. |
| `put_call_ratio_oi` | func | `(put_oi: int, call_oi: int) -> float` | 71 | Put/Call ratio by open interest. |
| `max_pain` | func | `(strikes: pd.Series, call_oi: pd.Series, put_oi: pd.Series) -> float` | 81 | Max pain: strike where total ITM option value is minimized. |
| `compute_pop` | func | `(d2: float, option_type: OptionType) -> float | None` | 140 | Probability of Profit (PoP): N(d2) for calls, N(-d2) for puts. |
| `compute_optimal_dte` | func | `(theta: float, expected_value: float | None) -> float | None` | 166 | Theta-normalised expected value. |
| `compute_spread_quality` | func | `(chain: pd.DataFrame) -> float | None` | 194 | OI-weighted average bid-ask spread. Lower is better. |
| `compute_max_loss_ratio` | func | `(contract_cost: float, account_risk_budget: float) -> float | None` | 224 | Max loss ratio: contract_cost / account_risk_budget. |

#### indicators/oscillators.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `rsi` | func | `(close: pd.Series, period: int = 14) -> pd.Series` | 14 | Relative Strength Index using Wilder's smoothing. |
| `stoch_rsi` | func | `(close: pd.Series, rsi_period: int = 14, stoch_period: int = 14) -> pd.Series` | 61 | Stochastic RSI: (RSI - RSI_low) / (RSI_high - RSI_low) * 100. |
| `williams_r` | func | `(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series` | 105 | Williams %R: (highest_high - close) / (highest_high - lowest_low) * -100. |

#### indicators/regime.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `classify_market_regime` | func | `(vix: float, vix_sma_20: float, spx_returns_20d: float, spx_sma_slope: float) -> MarketRegime` | 22 | Classify market regime based on VIX and SPX metrics. |
| `compute_vix_term_structure` | func | `(vix: float, vix3m: float | None) -> float | None` | 73 | VIX term structure: (VIX3M - VIX) / VIX. |
| `compute_risk_on_off` | func | `(hyg_return: float | None, lqd_return: float | None) -> float | None` | 100 | Risk-on/off score: HYG 20-day return minus LQD 20-day return. |
| `compute_sector_momentum` | func | `(sector_etf_return: float | None, spx_return: float) -> float | None` | 123 | Sector relative momentum: sector ETF 20-day return minus SPX 20-day return. |
| `compute_rs_vs_spx` | func | `(ticker_returns: pd.Series, spx_returns: pd.Series, period: int = 60) -> float | None` | 146 | Relative strength vs SPX: cumulative return ratio over period. |
| `compute_correlation_regime_shift` | func | `(ticker_returns: pd.Series, spx_returns: pd.Series, short_window: int = 20, long_window: int = 60...` | 192 | Correlation regime shift: short-window minus long-window correlation. |
| `compute_volume_profile_skew` | func | `(close: pd.Series, volume: pd.Series, period: int = 20) -> float | None` | 232 | Volume profile skew: volume-weighted price vs simple average price. |

#### indicators/trend.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `roc` | func | `(close: pd.Series, period: int = 12) -> pd.Series` | 18 | Rate of Change: (close - close_n_periods_ago) / close_n_periods_ago * 100. |
| `adx` | func | `(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series` | 42 | Average Directional Index using Wilder's smoothing. |
| `supertrend` | func | `(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 10, multiplier: float = 3.0) ->...` | 128 | ATR-based Supertrend indicator. |
| `macd` | func | `(close: pd.Series, *, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9) -> pd...` | 219 | MACD histogram: MACD line minus signal line. |
| `compute_multi_tf_alignment` | func | `(daily_supertrend: pd.Series, weekly_close: pd.Series, weekly_period: int = 10, weekly_multiplier...` | 273 | Multi-timeframe alignment: daily supertrend direction + weekly supertrend agreement. |
| `compute_rsi_divergence` | func | `(close: pd.Series, rsi: pd.Series, lookback: int = 14) -> float | None` | 360 | RSI divergence detector. |
| `compute_adx_exhaustion` | func | `(adx_series: pd.Series, threshold: float = 40.0) -> float | None` | 450 | ADX exhaustion signal. |

#### indicators/vol_surface.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `VolSurfaceResult` | class | `(NamedTuple)` | 50 | Result of volatility surface computation. |
| `compute_vol_surface` | func | `(strikes: np.ndarray, ivs: np.ndarray, dtes: np.ndarray, option_types: np.ndarray, spot: float, r...` | 91 | Compute implied volatility surface analytics with tiered fallback. |
| `compute_surface_indicators` | func | `(result: VolSurfaceResult) -> dict[str, float]` | 597 | Map per-contract z-scores from fitted surface to indicator signals. |

#### indicators/volatility.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `bb_width` | func | `(close: pd.Series, period: int = 20, num_std: float = 2.0) -> pd.Series` | 14 | Bollinger Band width: (upper - lower) / middle. |
| `atr_percent` | func | `(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series` | 48 | ATR as percentage of close price. |
| `keltner_width` | func | `(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 20, atr_mult: float = 2.0) -> p...` | 90 | Keltner Channel width: (upper - lower) / middle. |

#### indicators/volume.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `obv_trend` | func | `(close: pd.Series, volume: pd.Series, slope_period: int = 20) -> pd.Series` | 53 | On-Balance Volume trend (slope of OBV via linear regression). |
| `relative_volume` | func | `(volume: pd.Series, period: int = 20) -> pd.Series` | 86 | Current volume relative to its average over ``period`` days. |
| `ad_trend` | func | `(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, slope_period: int = 20) ->...` | 109 | Accumulation/Distribution line slope. |

---

### 1.4 `pricing/` — BSM + BAW Pricing

#### pricing/_common.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `SecondOrderGreeks` | class | `(NamedTuple)` | 14 | Second-order Greeks: vanna, charm, vomma. |
| `validate_positive_inputs` | func | `(S: float, K: float, T: float | None = None, r: float | None = None) -> None` | 26 | Validate that pricing inputs are finite and positive where required. |
| `intrinsic_value` | func | `(S: float, K: float, option_type: OptionType) -> float` | 59 | Return the intrinsic value of an option. |
| `is_itm` | func | `(S: float, K: float, option_type: OptionType) -> bool` | 77 | Check whether an option is in-the-money. |
| `boundary_greeks` | func | `(S: float, K: float, option_type: OptionType, pricing_model: PricingModel) -> OptionGreeks` | 95 | Return boundary Greeks when T <= 0 or sigma <= 0. |

#### pricing/american.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `american_price` | func | `(S: float, K: float, T: float, r: float, q: float, sigma: float, option_type: OptionType) -> float` | 284 | Compute American option price using the Barone-Adesi-Whaley approximation. |
| `american_greeks` | func | `(S: float, K: float, T: float, r: float, q: float, sigma: float, option_type: OptionType) -> Opti...` | 470 | Compute American option Greeks via finite-difference bump-and-reprice. |
| `american_iv` | func | `(market_price: float, S: float, K: float, T: float, r: float, q: float, option_type: OptionType, ...` | 571 | Solve for implied volatility of an American option using ``brentq``. |
| `american_second_order_greeks` | func | `(S: float, K: float, T: float, r: float, q: float, sigma: float, option_type: OptionType) -> Seco...` | 653 | Compute second-order American option Greeks via finite-difference cross-bumps. |

#### pricing/bsm.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `bsm_price` | func | `(S: float, K: float, T: float, r: float, q: float, sigma: float, option_type: OptionType) -> float` | 63 | Compute the European option price using Black-Scholes-Merton with dividends. |
| `bsm_greeks` | func | `(S: float, K: float, T: float, r: float, q: float, sigma: float, option_type: OptionType) -> Opti...` | 135 | Compute all 5 analytical BSM Greeks. |
| `bsm_vega` | func | `(S: float, K: float, T: float, r: float, q: float, sigma: float) -> float` | 223 | Compute standalone BSM vega for Newton-Raphson IV solver ``fprime``. |
| `bsm_iv` | func | `(market_price: float, S: float, K: float, T: float, r: float, q: float, option_type: OptionType, ...` | 271 | Solve for implied volatility using Newton-Raphson with analytical vega. |
| `bsm_second_order_greeks` | func | `(S: float, K: float, T: float, r: float, q: float, sigma: float, option_type: OptionType) -> Seco...` | 374 | Compute analytical second-order BSM Greeks: vanna, charm, vomma. |

#### pricing/dispatch.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `option_price` | func | `(exercise_style: ExerciseStyle, S: float, K: float, T: float, r: float, q: float, sigma: float, o...` | 29 | Compute option price by dispatching to BSM or BAW based on exercise style. |
| `option_greeks` | func | `(exercise_style: ExerciseStyle, S: float, K: float, T: float, r: float, q: float, sigma: float, o...` | 61 | Compute option Greeks by dispatching to BSM or BAW based on exercise style. |
| `option_iv` | func | `(exercise_style: ExerciseStyle, market_price: float, S: float, K: float, T: float, r: float, q: f...` | 93 | Solve for implied volatility by dispatching to BSM or BAW based on exercise style. |
| `option_second_order_greeks` | func | `(exercise_style: ExerciseStyle, S: float, K: float, T: float, r: float, q: float, sigma: float, o...` | 129 | Compute second-order Greeks by dispatching to BSM or BAW. |

---

### 1.5 `services/` — External API Access

#### services/base.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `ServiceBase` | class |  | 23 | Mixin providing shared service infrastructure. |
| `.close` | async method | `() -> None` | 50 | Release resources. Default is a no-op; override in subclasses. |

#### services/cache.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `TTL_OHLCV_MARKET` | const | `int` | 27 |  |
| `TTL_OHLCV_AFTER` | const | `int` | 28 |  |
| `TTL_CHAIN_MARKET` | const | `int` | 29 |  |
| `TTL_CHAIN_AFTER` | const | `int` | 30 |  |
| `TTL_QUOTE_MARKET` | const | `int` | 31 |  |
| `TTL_QUOTE_AFTER` | const | `int` | 32 |  |
| `TTL_FUNDAMENTALS` | const | `int` | 33 |  |
| `TTL_REFERENCE` | const | `int` | 34 |  |
| `TTL_FAILURE` | const | `int` | 35 |  |
| `TTL_EARNINGS` | const | `int` | 36 |  |
| `TTL_HEATMAP` | const | `int` | 37 |  |
| `is_market_hours` | func | `() -> bool` | 58 | Check if US options markets are currently open (9:30-16:00 ET, Mon-Fri). |
| `ServiceCache` | class |  | 74 | Two-tier cache: in-memory LRU + persistent SQLite. |
| `.init_db` | async method | `() -> None` | 118 | Initialize SQLite with WAL mode. Must be called after construction. |
| `.get` | async method | `(key: str) -> bytes | None` | 134 | Retrieve a cached value by key. |
| `.set` | async method | `(key: str, value: bytes, ttl: int | None = None) -> None` | 193 | Store a value with an optional TTL. |
| `.invalidate` | async method | `(key: str) -> None` | 231 | Remove a key from both tiers. |
| `.clear` | async method | `() -> None` | 241 | Clear all cached data from both tiers. |
| `.close` | async method | `() -> None` | 252 | Close SQLite connection. Safe to call multiple times. |
| `.ttl_for` | method | `(data_type: str) -> int` | 259 | Get the appropriate TTL for a data type based on current market hours. |

#### services/cboe_provider.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `CBOEChainProvider` | class |  | 231 | CBOE option chain provider using OpenBB Platform SDK. |
| `.available` | property | `() -> bool` | 256 | Whether the OpenBB SDK is importable and CBOE chains are enabled. |
| `.fetch_expirations` | async method | `(ticker: str) -> list[date]` | 281 | Fetch available expiration dates from CBOE via OpenBB. |
| `.fetch_chain` | async method | `(ticker: str, expiration: date) -> list[OptionContract]` | 384 | Fetch option chain from CBOE for a specific expiration date. |
| `.close` | async method | `() -> None` | 474 | Clean up resources. No-op for CBOE provider (no persistent connections). |

#### services/financial_datasets.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `FinancialDatasetsService` | class | `(ServiceBase[FinancialDatasetsConfig])` | 38 | Enrichment service fetching fundamental data from financialdatasets.ai. |
| `.fetch_financial_metrics` | async method | `(ticker: str) -> FinancialMetricsData | None` | 71 | Fetch point-in-time financial metrics for a ticker. |
| `.fetch_income_statement` | async method | `(ticker: str) -> IncomeStatementData | None` | 140 | Fetch point-in-time income statement data for a ticker. |
| `.fetch_balance_sheet` | async method | `(ticker: str) -> BalanceSheetData | None` | 200 | Fetch point-in-time balance sheet data for a ticker. |
| `.fetch_package` | async method | `(ticker: str) -> FinancialDatasetsPackage | None` | 256 | Fetch all financial data for a ticker in parallel. |
| `.close` | async method | `() -> None` | 306 | Close the httpx client. |

#### services/fred.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `CachedRate` | class | `(NamedTuple)` | 27 | A cached risk-free rate with its fetch timestamp. |
| `FredService` | class | `(ServiceBase[ServiceConfig])` | 34 | Fetches the 10-year Treasury yield from FRED as a risk-free rate proxy. |
| `.fetch_risk_free_rate` | async method | `() -> float` | 68 | Fetch 10-year Treasury yield as a decimal fraction (0.045 = 4.5%). |
| `.close` | async method | `() -> None` | 91 | Close the httpx client. |

#### services/health.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `HealthService` | class |  | 25 | Pre-flight health checker for external dependencies. |
| `.check_yfinance` | async method | `() -> HealthStatus` | 50 | Check yfinance availability by fetching a SPY fast_info snapshot. |
| `.check_fred` | async method | `() -> HealthStatus` | 82 | Check FRED API reachability with an HTTP HEAD request. |
| `.check_groq` | async method | `() -> HealthStatus` | 117 | Check Groq API availability by listing models. |
| `.check_anthropic` | async method | `() -> HealthStatus` | 210 | Check Anthropic API availability by listing models. |
| `.check_cboe` | async method | `() -> HealthStatus` | 306 | Check CBOE CSV download endpoint reachability with HTTP HEAD. |
| `.check_openbb` | async method | `() -> HealthStatus` | 340 | Check OpenBB SDK availability via guarded import. |
| `.check_intelligence` | async method | `() -> HealthStatus` | 379 | Check intelligence data availability via yfinance analyst price targets. |
| `.check_cboe_chains` | async method | `() -> HealthStatus` | 410 | Test CBOE chain endpoint with a known ticker (AAPL). |
| `.check_financial_datasets` | async method | `() -> HealthStatus` | 477 | Check Financial Datasets API health by fetching AAPL metrics. |
| `.check_all` | async method | `() -> list[HealthStatus]` | 555 | Run all health checks concurrently. |
| `.close` | async method | `() -> None` | 606 | Close the shared httpx client. |

#### services/helpers.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `fetch_with_retry` | async func | `(coro_factory: Callable[[], Awaitable[T]], *, max_retries: int = 5, base_delay: float = 1.0, max_...` | 23 | Execute an async factory with exponential backoff on retryable errors. |
| `fetch_with_limiter_retry` | async func | `(fn: Callable[..., Awaitable[T]], *args: object, limiter: RateLimiter, max_attempts: int = 3, bas...` | 73 | Retry with rate limiter — releases semaphore during backoff sleep. |
| `safe_decimal` | func | `(value: object) -> Decimal | None` | 133 | Convert *value* to ``Decimal`` safely. |
| `safe_int` | func | `(value: object) -> int | None` | 156 | Convert *value* to ``int`` safely. |
| `safe_float` | func | `(value: object) -> float | None` | 174 | Convert *value* to ``float`` safely. |
| `clear_stale_yf_cookies` | func | `(max_age_hours: float = 4.0) -> int` | 200 | Delete stale cookies from yfinance's persistent cookie cache. |

#### services/intelligence.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `IntelligenceService` | class | `(ServiceBase[IntelligenceConfig])` | 37 | Fetches intelligence data from yfinance with caching and rate limiting. |
| `.fetch_analyst_targets` | async method | `(ticker: str, current_price: float) -> AnalystSnapshot | None` | 66 | Fetch analyst price targets and recommendation counts. |
| `.fetch_analyst_activity` | async method | `(ticker: str) -> AnalystActivitySnapshot | None` | 168 | Fetch recent analyst upgrades/downgrades. |
| `.fetch_insider_activity` | async method | `(ticker: str) -> InsiderSnapshot | None` | 263 | Fetch insider transactions. |
| `.fetch_institutional` | async method | `(ticker: str) -> InstitutionalSnapshot | None` | 373 | Fetch institutional ownership data. |
| `.fetch_news_headlines` | async method | `(ticker: str) -> list[str] | None` | 470 | Fetch recent news headlines. |
| `.fetch_intelligence` | async method | `(ticker: str, current_price: float) -> IntelligencePackage | None` | 536 | Aggregate all intelligence categories for a ticker. |

#### services/market_data.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `SECTOR_ETF_MAP` | const | `dict[str, str]` | 58 |  |
| `UniverseData` | dataclass |  | 74 | Reference data for regime/macro indicators. |
| `TickerOHLCVResult` | model |  | 91 | Result for a single ticker in a batch OHLCV fetch. |
| `BatchOHLCVResult` | model |  | 107 | Typed result for a batch OHLCV fetch, replacing ``dict[str, list[OHLCV] \| error]``. |
| `BatchQuote` | model | `frozen=True` | 128 | A single ticker's daily price snapshot for heatmap display. |
| `MarketDataService` | class | `(ServiceBase[ServiceConfig])` | 270 | Fetches and normalises yfinance market data into typed Pydantic models. |
| `.fetch_ohlcv` | async method | `(ticker: str, period: str = '1y') -> list[OHLCV]` | 312 | Fetch OHLCV history for *ticker* from yfinance. |
| `.fetch_quote` | async method | `(ticker: str) -> Quote` | 391 | Fetch a real-time quote for *ticker* from yfinance. |
| `.fetch_ticker_info` | async method | `(ticker: str) -> TickerInfo` | 449 | Fetch fundamental data for *ticker* from yfinance. |
| `.fetch_batch_ohlcv` | async method | `(tickers: list[str], period: str = '1y') -> BatchOHLCVResult` | 541 | Fetch OHLCV data for multiple tickers concurrently. |
| `.fetch_earnings_date` | async method | `(ticker: str) -> date | None` | 566 | Fetch the next earnings date for *ticker* from yfinance. |
| `.fetch_universe_data` | async method | `() -> UniverseData` | 642 | Fetch reference data for regime/macro indicators. |
| `.fetch_batch_daily_changes` | async method | `(tickers: list[str]) -> list[BatchQuote]` | 771 | Fetch daily price changes for multiple tickers in concurrent chunks. |

#### services/openbb_service.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `OpenBBService` | class | `(ServiceBase[OpenBBConfig])` | 61 | Enrichment service wrapping the OpenBB Platform SDK. |
| `.sdk_available` | property | `() -> bool` | 84 | Whether the OpenBB SDK is importable. |
| `.fetch_fundamentals` | async method | `(ticker: str) -> FundamentalSnapshot | None` | 88 | Fetch fundamental metrics for a ticker. |
| `.fetch_unusual_flow` | async method | `(ticker: str) -> UnusualFlowSnapshot | None` | 156 | Fetch unusual options/dark-pool flow data for a ticker. |
| `.fetch_news_sentiment` | async method | `(ticker: str, limit: int = 10) -> NewsSentimentSnapshot | None` | 230 | Fetch recent news and compute VADER sentiment for a ticker. |

#### services/options_data.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `ChainProvider` | Protocol | `(Protocol)` | 143 | Protocol defining the contract for option chain data providers. |
| `YFinanceChainProvider` | class |  | 180 | Fetches option chains from yfinance with caching and rate limiting. |
| `.fetch_expirations` | async method | `(ticker: str) -> list[date]` | 244 | Fetch available option expiration dates for a ticker. |
| `.fetch_chain` | async method | `(ticker: str, expiration: date) -> list[OptionContract]` | 281 | Fetch the option chain for a specific expiration date. |
| `ExpirationChain` | model |  | 355 | Option contracts for a single expiration date. |
| `OptionsDataService` | class | `(ServiceBase[ServiceConfig])` | 367 | Fetches option chains with provider orchestration and fallback. |
| `.fetch_expirations` | async method | `(ticker: str) -> list[date]` | 474 | Fetch available option expiration dates for a ticker. |
| `.fetch_chain` | async method | `(ticker: str, expiration: date) -> list[OptionContract]` | 524 | Fetch the option chain for a specific expiration date. |
| `.fetch_chain_all_expirations` | async method | `(ticker: str) -> list[ExpirationChain]` | 657 | Fetch option chains for all available expirations concurrently. |
| `.close` | async method | `() -> None` | 702 | Clean up resources. Closes all providers that have a ``close`` method. |

#### services/outcome_collector.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `OutcomeCollector` | class |  | 36 | Collect and persist contract outcome data. |
| `.collect_outcomes` | async method | `(holding_days: int | None = None) -> list[ContractOutcome]` | 70 | Collect outcomes for contracts from holding_days ago. |
| `.run_scheduler` | async method | `() -> None` | 467 | Run an infinite loop that collects outcomes daily at the configured hour. |
| `.get_summary` | async method | `(lookback_days: int = 30) -> PerformanceSummary` | 494 | Get aggregate performance summary over the lookback period. |

#### services/rate_limiter.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `RateLimiter` | class |  | 13 | Dual-layer rate limiter: token bucket for throughput, semaphore for concurrency. |
| `.acquire` | async method | `() -> None` | 35 | Acquire a rate-limit slot: wait for both a token and a semaphore permit. |
| `.release` | method | `() -> None` | 47 | Release the semaphore permit. Synchronous — do NOT await. |
| `.__aenter__` | async method | `() -> Self` | 51 | Enter the async context manager (acquires rate-limit slot). |
| `.__aexit__` | async method | `(*exc: object) -> None` | 56 | Exit the async context manager (releases semaphore). |

#### services/universe.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `SP500_URL` | const | `str` | 41 |  |
| `SP500_REQUIRED_COLUMNS` | const | `frozenset[str]` | 44 |  |
| `CBOE_URL` | const | `str` | 46 |  |
| `INDEX_SYMBOL_CHARS` | const | `frozenset[str]` | 51 |  |
| `NASDAQ100_URL` | const | `str` | 140 |  |
| `SP500Constituent` | model |  | 477 | A single S&P 500 constituent with its GICS sector classification. |
| `UniverseService` | class | `(ServiceBase[ServiceConfig])` | 488 | Fetches optionable ticker universe and S&P 500 classification data. |
| `.fetch_optionable_tickers` | async method | `() -> list[str]` | 524 | Fetch CBOE optionable universe as a deduplicated list of ticker symbols. |
| `.fetch_sp500_constituents` | async method | `() -> list[SP500Constituent]` | 579 | Fetch S&P 500 constituents with GICS sector classification from GitHub CSV. |
| `.classify_market_cap` | method | `(market_cap: int | None) -> MarketCapTier | None` | 662 | Classify a market capitalisation value into a tier. |
| `.fetch_etf_tickers` | async method | `() -> list[str]` | 684 | Fetch ETF tickers from the CBOE optionable list with 24h cache. |
| `.fetch_nasdaq100_constituents` | async method | `() -> list[str]` | 750 | Fetch NASDAQ-100 constituents from GitHub CSV with CBOE cross-ref. |
| `.fetch_russell2000_tickers` | async method | `(repo: object | None = None) -> list[str]` | 832 | Fetch Russell 2000-like small/micro-cap tickers from the metadata index. |
| `.fetch_most_active` | async method | `() -> list[str]` | 920 | Fetch most actively traded options tickers with CBOE cross-ref. |
| `.close` | async method | `() -> None` | 964 | Close the shared httpx client and release base resources. |
| `build_sector_map` | func | `(constituents: list[SP500Constituent]) -> dict[str, GICSSector]` | 1087 | Build a ticker-to-GICS-sector mapping from S&P 500 constituents. |
| `filter_by_sectors` | func | `(tickers: list[str], sectors: list[GICSSector], sp500_map: dict[str, GICSSector]) -> list[str]` | 1115 | Filter tickers by GICS sector membership (OR logic). |
| `build_industry_group_map` | func | `(industry_data: dict[str, str]) -> dict[str, GICSIndustryGroup]` | 1142 | Build a ticker-to-GICS-industry-group mapping from raw industry strings. |
| `filter_by_industry_groups` | func | `(tickers: list[str], industry_groups: list[GICSIndustryGroup], ig_map: dict[str, GICSIndustryGrou...` | 1173 | Filter tickers by GICS industry group membership (OR logic). |
| `classify_market_cap` | func | `(market_cap: int | None) -> MarketCapTier | None` | 1225 | Classify a market capitalisation value into a ``MarketCapTier``. |
| `index_tickers` | async func | `(tickers: list[str], market_data: _TickerInfoProvider, repository: _MetadataStore, *, concurrency...` | 1263 | Index a list of tickers by fetching metadata from yfinance and persisting. |
| `map_yfinance_to_metadata` | func | `(ticker_info: TickerInfo) -> TickerMetadata` | 1323 | Map yfinance ``TickerInfo`` to typed ``TickerMetadata`` using GICS alias dicts. |

---

### 1.6 `scoring/` — Normalization, Composite, Contracts

#### scoring/composite.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `INDICATOR_WEIGHTS` | const | `dict[str, tuple[float, str]]` | 32 |  |
| `composite_score` | func | `(signals: IndicatorSignals, active_indicators: set[str] | None = None) -> float` | 81 | Compute a weighted geometric mean composite score for a single ticker. |
| `score_universe` | func | `(universe: dict[str, IndicatorSignals]) -> list[TickerScore]` | 130 | Score and rank an entire universe of tickers. |

#### scoring/contracts.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `filter_contracts` | func | `(contracts: list[OptionContract], direction: SignalDirection, filters: OptionsFilters | None = No...` | 41 | Filter contracts by liquidity, spread width, and directional type. |
| `select_expiration` | func | `(contracts: list[OptionContract], filters: OptionsFilters | None = None) -> date | None` | 106 | Select the expiration closest to the midpoint of the DTE range. |
| `compute_greeks` | func | `(contracts: list[OptionContract], spot: float, risk_free_rate: float, dividend_yield: float) -> l...` | 158 | Compute or preserve Greeks for each contract using three-tier resolution. |
| `select_by_delta` | func | `(contracts: list[OptionContract], filters: OptionsFilters | None = None, delta_target: float = .....` | 360 | Select the contract with delta closest to the target. |
| `recommend_contracts` | func | `(contracts: list[OptionContract], direction: SignalDirection, spot: float, risk_free_rate: float,...` | 441 | Run the full recommendation pipeline: filter -> expiration -> greeks -> delta. |

#### scoring/dimensional.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `FAMILY_INDICATOR_MAP` | const | `dict[str, list[str]]` | 23 |  |
| `DEFAULT_FAMILY_WEIGHTS` | const | `dict[str, float]` | 123 |  |
| `REGIME_WEIGHT_PROFILES` | const | `dict[MarketRegime, dict[str, float]]` | 138 |  |
| `compute_dimensional_scores` | func | `(signals: IndicatorSignals) -> DimensionalScores` | 187 | Compute 8 per-family sub-scores from IndicatorSignals. |
| `apply_regime_weights` | func | `(scores: DimensionalScores, regime: MarketRegime | None = None, enable_regime_weights: bool = Fal...` | 222 | Compute weighted composite from dimensional scores. |
| `compute_direction_signal` | func | `(signals: IndicatorSignals, direction: SignalDirection) -> DirectionSignal` | 274 | Compute continuous direction confidence via z-test on mean shift. |

#### scoring/direction.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `RSI_MIDPOINT` | const | `float` | 21 |  |
| `SMA_BULLISH_THRESHOLD` | const | `float` | 22 |  |
| `SMA_BEARISH_THRESHOLD` | const | `float` | 23 |  |
| `ROC_THRESHOLD` | const | `float` | 24 |  |
| `determine_direction` | func | `(adx: float, rsi: float, sma_alignment: float, config: ScanConfig | None = None, *, supertrend: f...` | 31 | Classify market direction from technical indicator values. |

#### scoring/normalization.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `INVERTED_INDICATORS` | const | `frozenset[str]` | 37 |  |
| `DOMAIN_BOUNDS` | const | `dict[str, tuple[float, float]]` | 50 |  |
| `get_active_indicators` | func | `(universe: dict[str, IndicatorSignals]) -> set[str]` | 85 | Return indicator field names that have at least one non-None value. |
| `percentile_rank_normalize` | func | `(universe: dict[str, IndicatorSignals]) -> dict[str, IndicatorSignals]` | 108 | Convert raw indicator values to percentile ranks across the universe. |
| `invert_indicators` | func | `(normalized: dict[str, IndicatorSignals]) -> dict[str, IndicatorSignals]` | 184 | Flip inverted indicators so that higher percentile = better signal. |
| `normalize_single_ticker` | func | `(signals: IndicatorSignals) -> IndicatorSignals` | 221 | Normalize raw indicator signals to 0--100 via domain-bound linear scaling. |
| `compute_normalization_stats` | func | `(raw_signals: dict[str, IndicatorSignals]) -> list[NormalizationStats]` | 254 | Compute per-indicator distribution metadata from raw signals. |

---

### 1.7 `data/` — SQLite Persistence

#### data/_analytics.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `AnalyticsMixin` | class | `(RepositoryBase)` | 44 | Contracts, outcomes, normalization, and analytics queries. |
| `.save_recommended_contracts` | async method | `(scan_id: int, contracts: list[RecommendedContract], *, commit: bool = True) -> None` | 51 | Batch-insert recommended contracts for a scan run. |
| `.get_contracts_for_scan` | async method | `(scan_id: int) -> list[RecommendedContract]` | 122 | Get all recommended contracts for a scan run. |
| `.get_contracts_for_ticker` | async method | `(ticker: str, limit: int = 50) -> list[RecommendedContract]` | 141 | Get recent recommended contracts for a ticker. |
| `.save_normalization_stats` | async method | `(scan_id: int, stats: list[NormalizationStats], *, commit: bool = True) -> None` | 166 | Batch-insert normalization stats for a scan run. |
| `.get_normalization_stats` | async method | `(scan_id: int) -> list[NormalizationStats]` | 213 | Get normalization stats for a scan run. |
| `.save_contract_outcomes` | async method | `(outcomes: list[ContractOutcome]) -> None` | 307 | Batch-insert contract outcome records. |
| `.get_outcomes_for_contract` | async method | `(contract_id: int) -> list[ContractOutcome]` | 348 | Get all outcomes for a recommended contract, ordered by holding_days. |
| `.get_contracts_needing_outcomes` | async method | `(holding_days: int, lookback_date: date) -> list[RecommendedContract]` | 368 | Get recommended contracts that need outcomes for a given period. |
| `.has_outcome` | async method | `(contract_id: int, exit_date: date) -> bool` | 404 | Check if an outcome already exists for a contract and exit date. |
| `.get_win_rate_by_direction` | async method | `() -> list[WinRateResult]` | 467 | Compute win rate grouped by signal direction. |
| `.get_score_calibration` | async method | `(bucket_size: float = 10.0) -> list[ScoreCalibrationBucket]` | 500 | Bucket contracts by composite_score and compute returns per bucket. |
| `.get_indicator_attribution` | async method | `(indicator: str, holding_days: int = 5) -> list[IndicatorAttributionResult]` | 541 | Correlate a normalized indicator value with contract returns. |
| `.get_optimal_holding_period` | async method | `(direction: SignalDirection | None = None) -> list[HoldingPeriodResult]` | 616 | Get return statistics grouped by holding_days and direction. |
| `.get_delta_performance` | async method | `(bucket_size: float = 0.1, holding_days: int = 5) -> list[DeltaPerformanceResult]` | 673 | Bucket contracts by delta and compute return statistics. |
| `.get_performance_summary` | async method | `(lookback_days: int = 30) -> PerformanceSummary` | 732 | Compute aggregate performance summary over a lookback window. |
| `.get_equity_curve` | async method | `(direction: str | None = None, period_days: int | None = None) -> list[EquityCurvePoint]` | 851 | Compute cumulative equity curve from contract outcomes. |
| `.get_drawdown_series` | async method | `(direction: str | None = None, period_days: int | None = None) -> list[DrawdownPoint]` | 920 | Compute drawdown series from the equity curve. |
| `.get_win_rate_by_sector` | async method | `(holding_days: int = 20) -> list[SectorPerformanceResult]` | 965 | Compute win rate and average return grouped by GICS sector. |
| `.get_win_rate_by_dte_bucket` | async method | `(holding_days: int = 20) -> list[DTEBucketResult]` | 1013 | Compute win rate and average return grouped by DTE buckets. |
| `.get_win_rate_by_iv_rank` | async method | `(holding_days: int = 20) -> list[IVRankBucketResult]` | 1072 | Compute win rate and average return grouped by IV rank quartiles. |
| `.get_greeks_decomposition` | async method | `(holding_days: int = 20, groupby: GreeksGroupBy = ...) -> list[GreeksDecompositionResult]` | 1130 | Decompose P&L into delta-attributable and residual components. |
| `.get_holding_period_comparison` | async method | `() -> list[HoldingPeriodComparison]` | 1233 | Compare performance across holding periods and directions. |

#### data/_base.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `RepositoryBase` | class |  | 14 | Base class providing shared database access for repository mixins. |
| `.commit` | async method | `() -> None` | 19 | Explicitly commit the current transaction. |

#### data/_debate.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `DebateRow` | dataclass |  | 30 | Row from ai_theses table. |
| `DebateMixin` | class | `(RepositoryBase)` | 60 | Debate persistence and agent calibration CRUD operations. |
| `.save_debate` | async method | `(scan_run_id: int | None, ticker: str, bull_json: str | None, bear_json: str | None, risk_json: s...` | 63 | Persist a debate result.  Returns the database-assigned ID. |
| `.save_agent_predictions` | async method | `(predictions: list[AgentPrediction]) -> None` | 133 | Persist per-agent predictions for accuracy tracking. |
| `.get_recommended_contract_id` | async method | `(scan_run_id: int | None, ticker: str) -> int | None` | 165 | Look up the recommended_contracts.id for a scan_run + ticker pair. |
| `.get_debate_by_id` | async method | `(debate_id: int) -> DebateRow | None` | 189 | Get a single debate by its primary key, or None if not found. |
| `.get_recent_debates` | async method | `(limit: int = 20) -> list[DebateRow]` | 198 | Get the N most recent debates across all tickers, newest first. |
| `.get_debates_for_ticker` | async method | `(ticker: str, limit: int = 5) -> list[DebateRow]` | 209 | Get recent debates for a ticker, newest first. |
| `.get_agent_accuracy` | async method | `(window_days: int | None = None) -> list[AgentAccuracyReport]` | 260 | Per-agent direction accuracy and Brier scores. |
| `.get_agent_calibration` | async method | `(agent_name: str | None = None) -> AgentCalibrationData` | 334 | Confidence calibration buckets. |
| `.get_latest_auto_tune_weights` | async method | `() -> list[AgentWeightsComparison]` | 419 | Retrieve the most recently saved auto-tune weight set. |
| `.save_auto_tune_weights` | async method | `(weights: list[AgentWeightsComparison], window_days: int) -> None` | 458 | Persist a computed set of auto-tune weights. |
| `.get_weight_history` | async method | `(limit: int = 20) -> list[WeightSnapshot]` | 493 | Retrieve historical auto-tune weight snapshots, newest first. |

#### data/_metadata.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `MetadataMixin` | class | `(RepositoryBase)` | 22 | Ticker metadata CRUD operations. |
| `.upsert_ticker_metadata` | async method | `(metadata: TickerMetadata) -> None` | 25 | INSERT OR REPLACE a single ticker_metadata row. |
| `.upsert_ticker_metadata_batch` | async method | `(items: list[TickerMetadata], *, commit: bool = True) -> None` | 51 | Batch upsert ticker_metadata rows via ``executemany``. |
| `.get_ticker_metadata` | async method | `(ticker: str) -> TickerMetadata | None` | 87 | Lookup a single ``TickerMetadata`` by ticker (uppercased). |
| `.get_all_ticker_metadata` | async method | `() -> list[TickerMetadata]` | 101 | Return all rows from ``ticker_metadata`` as a list of ``TickerMetadata``. |
| `.get_stale_tickers` | async method | `(max_age_days: int = 30) -> list[str]` | 110 | Return tickers whose ``last_updated`` is older than *max_age_days*. |
| `.get_metadata_coverage` | async method | `() -> MetadataCoverage` | 126 | Return coverage statistics for the ``ticker_metadata`` table. |

#### data/_scan.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `ScanMixin` | class | `(RepositoryBase)` | 29 | Scan run and ticker score CRUD operations. |
| `.save_scan_run` | async method | `(scan_run: ScanRun, *, commit: bool = True) -> int` | 32 | Persist a ScanRun.  Returns the database-assigned ID (lastrowid). |
| `.save_ticker_scores` | async method | `(scan_id: int, scores: list[TickerScore], *, commit: bool = True) -> None` | 64 | Batch-insert TickerScores for a scan run. |
| `.get_latest_scan` | async method | `() -> ScanRun | None` | 107 | Get the most recent ScanRun, or None if no scans exist. |
| `.get_scan_by_id` | async method | `(scan_id: int) -> ScanRun | None` | 116 | Get a ScanRun by its ID, or None if not found. |
| `.get_scores_for_scan` | async method | `(scan_id: int) -> list[TickerScore]` | 125 | Get all TickerScores for a scan run.  Returns empty list if none. |
| `.get_recent_scans` | async method | `(limit: int = 10) -> list[ScanRun]` | 137 | Get the N most recent ScanRuns, newest first. |
| `.get_score_history` | async method | `(ticker: str, limit: int = 20) -> list[HistoryPoint]` | 206 | Get score history for a ticker across recent scans. |
| `.get_trending_tickers` | async method | `(direction: str, min_scans: int = 3) -> list[TrendingTicker]` | 237 | Find tickers with consistent direction over consecutive recent scans. |
| `.get_last_debate_dates` | async method | `(tickers: list[str]) -> dict[str, datetime]` | 323 | Get the most recent debate date for each ticker in a single query. |

#### data/database.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `Database` | class |  | 21 | Async SQLite database with WAL mode and sequential migration runner. |
| `.conn` | property | `() -> aiosqlite.Connection` | 43 | Return the live connection.  Raises ``RuntimeError`` if not connected. |
| `.connect` | async method | `() -> None` | 49 | Open connection, configure pragmas, and run pending migrations. |
| `.close` | async method | `() -> None` | 71 | Close the connection.  Idempotent — safe to call multiple times. |

#### data/repository.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `Repository` | class | `(ScanMixin, DebateMixin, AnalyticsMixin, MetadataMixin)` | 23 | Typed CRUD for all persistence domains. |

---

### 1.8 `agents/` — PydanticAI Debate System

#### agents/_parsing.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `strip_think_tags` | func | `(text: str) -> str` | 50 | Remove ``<think>...</think>`` blocks and any stray open/close tags. |
| `PROMPT_RULES_APPENDIX` | const | `str` | 66 |  |
| `build_cleaned_agent_response` | func | `(output: AgentResponse) -> AgentResponse` | 95 | Strip ``<think>`` tags from all text fields of an ``AgentResponse``. |
| `build_cleaned_trade_thesis` | func | `(output: TradeThesis) -> TradeThesis` | 121 | Strip ``<think>`` tags from all text fields of a ``TradeThesis``. |
| `build_cleaned_volatility_thesis` | func | `(output: VolatilityThesis) -> VolatilityThesis` | 143 | Strip ``<think>`` tags from all text fields of a ``VolatilityThesis``. |
| `build_cleaned_flow_thesis` | func | `(output: FlowThesis) -> FlowThesis` | 173 | Strip ``<think>`` tags from all text fields of a ``FlowThesis``. |
| `build_cleaned_contrarian_thesis` | func | `(output: ContrarianThesis) -> ContrarianThesis` | 201 | Strip ``<think>`` tags from all text fields of a ``ContrarianThesis``. |
| `build_cleaned_risk_assessment` | func | `(output: RiskAssessment) -> RiskAssessment` | 227 | Strip ``<think>`` tags from all text fields of a ``RiskAssessment``. |
| `build_cleaned_fundamental_thesis` | func | `(output: FundamentalThesis) -> FundamentalThesis` | 273 | Strip ``<think>`` tags from all text fields of a ``FundamentalThesis``. |
| `DebateDeps` | dataclass |  | 311 | Injected into every agent via RunContext[DebateDeps]. |
| `DebateResult` | model | `frozen=True` | 335 | Complete debate output returned by run_debate(). |
| `_render_optional` | func | `(label: str, value: float | None, fmt: str = '.1f') -> str | None` | 361 | Render a labeled value if non-None and finite, else None. |
| `_render_regime_label` | func | `(label: str, value: float | None, labels: dict[float, str]) -> str | None` | 368 | Render a regime field as a human-readable label, with numeric fallback. |
| `_format_dollars` | func | `(value: float) -> str` | 376 | Format a dollar amount as $X.XB or $X.XM, with sign for negatives. |
| `_render_identity_block` | func | `(ctx: MarketContext) -> list[str]` | 386 | Shared identity fields for all domain-specific renderers. |
| `render_trend_context` | func | `(ctx: MarketContext) -> str` | 423 | Render domain-specific context for the Trend agent. |
| `render_volatility_context` | func | `(ctx: MarketContext) -> str` | 466 | Render domain-specific context for the Volatility agent. |
| `render_flow_context` | func | `(ctx: MarketContext) -> str` | 551 | Render domain-specific context for the Flow agent. |
| `render_fundamental_context` | func | `(ctx: MarketContext) -> str` | 601 | Render domain-specific context for the Fundamental agent. |
| `render_context_block` | func | `(ctx: MarketContext) -> str` | 741 | Render MarketContext as flat key-value text for agent consumption. |
| `compute_citation_density` | func | `(context_block: str, *texts: str) -> float` | 1034 | Compute fraction of context labels referenced in agent output text. |

#### agents/bear.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `bear_dynamic_prompt` | async func | `(ctx: RunContext[DebateDeps]) -> str` | 37 | Return the bear system prompt, injecting the bull's argument if available. |
| `clean_think_tags` | async func | `(ctx: RunContext[DebateDeps], output: AgentResponse) -> AgentResponse` | 51 | Strip ``<think>`` tags from LLM output via shared helper. |

#### agents/bull.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `bull_dynamic_prompt` | async func | `(ctx: RunContext[DebateDeps]) -> str` | 48 | Return the bull system prompt, appending rebuttal instructions when active. |
| `clean_think_tags` | async func | `(ctx: RunContext[DebateDeps], output: AgentResponse) -> AgentResponse` | 63 | Strip ``<think>`` tags from LLM output via shared helper. |

#### agents/contrarian_agent.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `contrarian_dynamic_prompt` | async func | `(ctx: RunContext[DebateDeps]) -> str` | 37 | Return the contrarian system prompt, injecting all prior agent outputs. |
| `clean_think_tags` | async func | `(ctx: RunContext[DebateDeps], output: ContrarianThesis) -> ContrarianThesis` | 56 | Strip ``<think>`` tags from LLM output via shared helper. |

#### agents/flow_agent.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `flow_dynamic_prompt` | async func | `(ctx: RunContext[DebateDeps]) -> str` | 37 | Return the flow system prompt, injecting bull/bear arguments if available. |
| `clean_think_tags` | async func | `(ctx: RunContext[DebateDeps], output: FlowThesis) -> FlowThesis` | 57 | Strip ``<think>`` tags from LLM output via shared helper. |

#### agents/fundamental_agent.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `fundamental_dynamic_prompt` | async func | `(ctx: RunContext[DebateDeps]) -> str` | 36 | Return the fundamental system prompt, injecting bull/bear arguments if available. |
| `clean_think_tags` | async func | `(ctx: RunContext[DebateDeps], output: FundamentalThesis) -> FundamentalThesis` | 56 | Strip ``<think>`` tags from LLM output via shared helper. |

#### agents/model_config.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `build_debate_model` | func | `(config: DebateConfig) -> Model` | 118 | Build a PydanticAI model for the configured LLM provider. |

#### agents/orchestrator.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `DebatePhase` | StrEnum |  | 87 | Phases of the AI debate pipeline, reported via progress callback. |
| `should_debate` | func | `(ticker_score: TickerScore, config: DebateConfig) -> bool` | 101 | Return False if signal is too weak for meaningful AI debate. |
| `build_market_context` | func | `(ticker_score: TickerScore, quote: Quote, ticker_info: TickerInfo, contracts: list[OptionContract...` | 112 | Map scan pipeline output to ``MarketContext`` for agent consumption. |
| `classify_macd_signal` | func | `(macd_value: float | None) -> MacdSignal` | 513 | Classify a centered MACD value into a signal. |
| `extract_agent_predictions` | func | `(debate_id: int, result: DebateResult, recommended_contract_id: int | None = None) -> list[AgentP...` | 739 | Extract per-agent predictions from a DebateResult for accuracy tracking. |
| `AGENT_VOTE_WEIGHTS` | const | `VoteWeights` | 937 |  |
| `compute_auto_tune_weights` | func | `(accuracy: list[AgentAccuracyReport]) -> VoteWeights` | 947 | Compute auto-tuned vote weights from agent accuracy data. |
| `auto_tune_weights` | async func | `(repo: Repository, window_days: int = 90, dry_run: bool = False) -> list[AgentWeightsComparison]` | 982 | Orchestrate end-to-end auto-tune: accuracy -> weights -> compare -> persist. |
| `compute_agreement_score` | func | `(agent_directions: dict[str, SignalDirection]) -> float` | 1043 | Compute fraction of directional agents agreeing with the majority. |
| `synthesize_verdict` | func | `(agent_outputs: dict[str, AgentResponse | FlowThesis ..., risk_assessment: RiskAssessment | None,...` | 1223 | Algorithmic verdict synthesis from all agent outputs. |
| `run_debate` | async func | `(ticker_score: TickerScore, contracts: list[OptionContract], quote: Quote, ticker_info: TickerInf...` | 1376 | Run 6-agent debate protocol. Falls back to data-driven on failure — never raises. |
| `effective_batch_ticker_delay` | func | `(config: DebateConfig) -> float` | 1579 | Return inter-ticker batch delay, auto-adjusted for Anthropic provider. |

#### agents/prompts/bear.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `BEAR_SYSTEM_PROMPT` | const |  | 17 |  |

#### agents/prompts/bull.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `BULL_SYSTEM_PROMPT` | const |  | 17 |  |

#### agents/prompts/contrarian_agent.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `CONTRARIAN_SYSTEM_PROMPT` | const |  | 19 |  |

#### agents/prompts/flow_agent.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `FLOW_SYSTEM_PROMPT` | const |  | 19 |  |

#### agents/prompts/fundamental_agent.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `FUNDAMENTAL_SYSTEM_PROMPT` | const |  | 23 |  |

#### agents/prompts/risk.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `RISK_SYSTEM_PROMPT` | const |  | 16 |  |

#### agents/prompts/trend_agent.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `TREND_SYSTEM_PROMPT` | const |  | 19 |  |

#### agents/prompts/volatility.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `VOLATILITY_SYSTEM_PROMPT` | const |  | 20 |  |

#### agents/risk.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `risk_dynamic_prompt` | async func | `(ctx: RunContext[DebateDeps]) -> str` | 35 | Return the expanded risk system prompt, injecting Phase 1 agent outputs. |
| `clean_risk_think_tags` | async func | `(ctx: RunContext[DebateDeps], output: RiskAssessment) -> RiskAssessment` | 90 | Strip ``<think>`` tags from RiskAssessment output via shared helper. |

#### agents/trend_agent.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `trend_system_prompt` | func | `() -> str` | 36 | Return the trend agent system prompt. |
| `clean_think_tags` | async func | `(ctx: RunContext[DebateDeps], output: AgentResponse) -> AgentResponse` | 45 | Strip ``<think>`` tags from LLM output via shared helper. |

#### agents/volatility.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `volatility_dynamic_prompt` | async func | `(ctx: RunContext[DebateDeps]) -> str` | 36 | Return the volatility system prompt, injecting bull/bear arguments if available. |
| `clean_think_tags` | async func | `(ctx: RunContext[DebateDeps], output: VolatilityThesis) -> VolatilityThesis` | 56 | Strip ``<think>`` tags from LLM output via shared helper. |

---

### 1.9 `scan/` — 4-Phase Pipeline

#### scan/indicators.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `InputShape` | StrEnum |  | 82 | OHLCV column requirements for an indicator function. |
| `IndicatorSpec` | class | `(NamedTuple)` | 96 | Typed registry entry mapping a signal field to an indicator function. |
| `INDICATOR_REGISTRY` | const | `list[IndicatorSpec]` | 120 |  |
| `ohlcv_to_dataframe` | func | `(ohlcv: list[OHLCV]) -> pd.DataFrame` | 144 | Convert OHLCV Pydantic models to a pandas DataFrame for indicators. |
| `compute_indicators` | func | `(df: pd.DataFrame, registry: list[IndicatorSpec]) -> IndicatorSignals` | 173 | Dispatch each registry entry against the DataFrame and populate signals. |
| `compute_options_indicators` | func | `(contracts: list[OptionContract], spot: float) -> IndicatorSignals` | 313 | Compute options-specific indicators from the full option chain. |
| `compute_phase3_indicators` | func | `(contracts: list[OptionContract], spot: float, close_series: pd.Series, dividend_yield: float, ne...` | 413 | Compute DSE indicators that require chain, ticker, or SPX data. |

#### scan/models.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `UniverseResult` | model |  | 32 | Phase 1 output: universe tickers + OHLCV data. |
| `ScoringResult` | model |  | 57 | Phase 2 output: scored tickers + raw signals. |
| `OptionsResult` | model |  | 78 | Phase 3 output: recommended contracts + risk-free rate. |
| `ScanResult` | model |  | 96 | Final pipeline output combining all phases. |

#### scan/phase_options.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `run_options_phase` | async func | `(scoring_result: ScoringResult, universe_result: UniverseResult, progress: ProgressCallback, *, f...` | 162 | Phase 3: Fetch options chains, compute Greeks, recommend contracts. |
| `process_ticker_options` | async func | `(ticker_score: TickerScore, risk_free_rate: float, ohlcv_map: dict[str, list[OHLCV]], spx_close: ...` | 393 | Fetch chains + ticker info + earnings date for a single ticker. |

#### scan/phase_persist.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `run_persist_phase` | async func | `(*, started_at: datetime, preset: ScanPreset, source: ScanSource, universe_result: UniverseResult...` | 36 | Phase 4: Persist scan results to database and assemble final ScanResult. |

#### scan/phase_scoring.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `run_scoring_phase` | async func | `(universe_result: UniverseResult, progress: ProgressCallback, *, scan_config: ScanConfig, compute...` | 42 | Phase 2: Compute indicators, score universe, determine direction. |

#### scan/phase_universe.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `run_universe_phase` | async func | `(progress: ProgressCallback, *, universe: UniverseService, market_data: MarketDataService, reposi...` | 35 | Phase 1: Fetch optionable universe and OHLCV data. |

#### scan/pipeline.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `ScanPipeline` | class |  | 63 | Four-phase async scan pipeline with cancellation and progress reporting. |
| `.run` | async method | `(token: CancellationToken, progress: ProgressCallback, source: ScanSource = ScanSource.MANUAL) ->...` | 99 | Orchestrate all pipeline phases with cancellation checks between phases. |

#### scan/progress.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `ScanPhase` | StrEnum |  | 16 | The four sequential phases of a scan pipeline run. |
| `CancellationToken` | class |  | 25 | Thread-safe, instance-scoped cancellation for scan pipeline. |
| `.cancel` | method | `() -> None` | 36 | Signal cancellation.  Idempotent — safe to call multiple times. |
| `.is_cancelled` | property | `() -> bool` | 41 | Check whether cancellation was requested. |
| `ProgressCallback` | Protocol | `(Protocol)` | 47 | Framework-agnostic callback for reporting scan progress. |

---

### 1.10 `reporting/` — Export Generation

#### reporting/debate_export.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `export_debate_markdown` | func | `(result: DebateResult) -> str` | 279 | Convert a debate result into a Markdown report string. |
| `export_debate_to_file` | func | `(result: DebateResult, path: Path, fmt: str = 'md') -> Path` | 399 | Write debate result to file as Markdown. |

---

### 1.11 `api/` — FastAPI REST + WebSocket

#### api/app.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `lifespan` | async func | `(app: FastAPI) -> AsyncGenerator[None]` | 49 | Create all services at startup, close them at shutdown. |
| `create_app` | func | `() -> FastAPI` | 163 | Build and configure the FastAPI application. |

#### api/deps.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `get_repo` | func | `(request: Request) -> Repository` | 26 | Inject the typed CRUD repository. |
| `get_market_data` | func | `(request: Request) -> MarketDataService` | 31 | Inject the market data service. |
| `get_options_data` | func | `(request: Request) -> OptionsDataService` | 36 | Inject the options data service. |
| `get_fred` | func | `(request: Request) -> FredService` | 41 | Inject the FRED service. |
| `get_universe` | func | `(request: Request) -> UniverseService` | 46 | Inject the universe service. |
| `get_settings` | func | `(request: Request) -> AppSettings` | 51 | Inject the application settings. |
| `get_openbb` | func | `(request: Request) -> OpenBBService | None` | 56 | Inject the OpenBB enrichment service (``None`` when disabled). |
| `get_intelligence` | func | `(request: Request) -> IntelligenceService | None` | 61 | Inject the intelligence service (``None`` when disabled). |
| `get_financial_datasets` | func | `(request: Request) -> FinancialDatasetsService | None` | 66 | Inject the Financial Datasets service (``None`` when disabled or no API key). |
| `get_operation_lock` | func | `(request: Request) -> asyncio.Lock` | 71 | Inject the global operation mutex. |
| `get_outcome_collector` | func | `(request: Request) -> OutcomeCollector` | 76 | Inject the outcome collector service (created on-demand via DI). |

#### api/routes/analytics.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `get_win_rate` | async func | `(request: Request, repo: Repository = Depends(get_repo)) -> list[WinRateResult]` | 39 | Get win rate by signal direction. |
| `get_score_calibration` | async func | `(request: Request, bucket_size: float = ..., repo: Repository = Depends(get_repo)) -> list[ScoreC...` | 49 | Get score calibration buckets — return by composite score range. |
| `get_indicator_attribution` | async func | `(request: Request, indicator: str, holding_days: int = ..., repo: Repository = Depends(get_repo))...` | 60 | Get indicator attribution — correlation between indicator values and returns. |
| `get_holding_period` | async func | `(request: Request, direction: SignalDirection | None = Query(default=None), repo: Repository = De...` | 74 | Get holding period analysis — return statistics by holding period. |
| `get_delta_performance` | async func | `(request: Request, bucket_size: float = ..., holding_days: int = ..., repo: Repository = Depends(...` | 85 | Get delta performance — return statistics by delta bucket. |
| `get_summary` | async func | `(request: Request, lookback_days: int = ..., repo: Repository = Depends(get_repo)) -> Performance...` | 97 | Get aggregate performance summary over a lookback period. |
| `collect_outcomes` | async func | `(request: Request, holding_days: int | None = ..., collector: OutcomeCollector = ..., lock: async...` | 108 | Trigger outcome collection. |
| `get_scan_contracts` | async func | `(request: Request, scan_id: int, repo: Repository = Depends(get_repo)) -> list[RecommendedContract]` | 133 | Get recommended contracts for a specific scan run. |
| `get_ticker_contracts` | async func | `(request: Request, ticker: str, limit: int = ..., repo: Repository = Depends(get_repo)) -> list[R...` | 144 | Get recommended contracts for a specific ticker. |
| `get_agent_accuracy` | async func | `(request: Request, window: int | None = ..., repo: Repository = Depends(get_repo)) -> list[AgentA...` | 156 | Get per-agent direction accuracy and Brier scores. |
| `get_agent_calibration` | async func | `(request: Request, agent: str | None = Query(default=None), repo: Repository = Depends(get_repo))...` | 167 | Get confidence calibration buckets for agents. |
| `get_agent_weights` | async func | `(request: Request, repo: Repository = Depends(get_repo)) -> list[AgentWeightsComparison]` | 178 | Get manual vs auto-tuned weight comparison. |
| `trigger_auto_tune` | async func | `(request: Request, repo: Repository = Depends(get_repo), lock: asyncio.Lock = ..., window: int = ...` | 188 | Trigger auto-tune weight computation. |
| `get_weight_history` | async func | `(request: Request, repo: Repository = Depends(get_repo), limit: int = ...) -> list[WeightSnapshot]` | 213 | Retrieve historical auto-tune weight snapshots, newest first. |

#### api/routes/backtest.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `get_equity_curve` | async func | `(request: Request, direction: SignalDirection | None = Query(default=None), period: int | None = ...` | 31 | Get cumulative equity curve from contract outcomes. |
| `get_drawdown` | async func | `(request: Request, direction: SignalDirection | None = Query(default=None), period: int | None = ...` | 43 | Get drawdown series from the equity curve. |
| `get_sector_performance` | async func | `(request: Request, holding_days: int = ..., repo: Repository = Depends(get_repo)) -> list[SectorP...` | 55 | Get win rate and average return grouped by GICS sector. |
| `get_dte_performance` | async func | `(request: Request, holding_days: int = ..., repo: Repository = Depends(get_repo)) -> list[DTEBuck...` | 66 | Get win rate and average return grouped by DTE buckets. |
| `get_iv_performance` | async func | `(request: Request, holding_days: int = ..., repo: Repository = Depends(get_repo)) -> list[IVRankB...` | 77 | Get win rate and average return grouped by IV rank quartiles. |
| `get_greeks_decomposition` | async func | `(request: Request, groupby: GreeksGroupBy = ..., holding_days: int = ..., repo: Repository = Depe...` | 88 | Get P&L decomposition by Greeks (delta-attributable vs residual). |
| `get_holding_comparison` | async func | `(request: Request, repo: Repository = Depends(get_repo)) -> list[HoldingPeriodComparison]` | 100 | Compare performance across holding periods and directions. |

#### api/routes/config.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `get_config` | async func | `(request: Request, settings: AppSettings = ...) -> ConfigResponse` | 19 | Return safe configuration values (never the actual API key). |

#### api/routes/debate.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `start_debate` | async func | `(request: Request, body: DebateRequest, settings: AppSettings = ..., repo: Repository = Depends(g...` | 266 | Start a single-ticker debate in the background. |
| `start_batch_debate` | async func | `(request: Request, body: BatchDebateRequest, lock: asyncio.Lock = ..., settings: AppSettings = .....` | 553 | Start a batch debate for top N tickers from a scan. |
| `list_debates` | async func | `(request: Request, repo: Repository = Depends(get_repo), ticker: str | None = Query(None), limit:...` | 609 | List past debate summaries. |
| `get_debate` | async func | `(request: Request, debate_id: int, repo: Repository = Depends(get_repo)) -> DebateResultDetail` | 677 | Get full debate result by ID. |

#### api/routes/export.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `export_debate` | async func | `(request: Request, debate_id: int, repo: Repository = Depends(get_repo), fmt: str = ...) -> FileR...` | 35 | Export a debate result as a downloadable Markdown file. |

#### api/routes/health.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `health_check` | async func | `() -> dict[str, str]` | 21 | Basic liveness check. |
| `get_status` | async func | `(request: Request, lock: asyncio.Lock = ...) -> OperationStatus` | 27 | Return current operation status so frontend can sync after browser refresh. |
| `check_services` | async func | `(request: Request, settings: AppSettings = ...) -> list[HealthStatus]` | 44 | Run all health checks and return service statuses. |

#### api/routes/market.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `MARKET_CAP_WEIGHTS` | const | `dict[MarketCapTier, float]` | 25 |  |
| `build_heatmap_tickers` | func | `(constituents: list[SP500Constituent], quotes: list[BatchQuote], metadata: list[TickerMetadata]) ...` | 36 | Join constituents, quotes, and metadata into heatmap ticker entries. |
| `get_heatmap` | async func | `(request: Request, market_data: MarketDataService = ..., universe: UniverseService = ..., repo: R...` | 97 | Return S&P 500 heatmap data: daily changes joined with metadata. |

#### api/routes/scan.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `start_scan` | async func | `(request: Request, body: ScanRequest, lock: asyncio.Lock = ..., settings: AppSettings = ..., repo...` | 122 | Start a new scan pipeline in the background. |
| `list_scans` | async func | `(request: Request, repo: Repository = Depends(get_repo), limit: int = ...) -> list[ScanRun]` | 243 | List past scan runs, newest first. |
| `get_scan` | async func | `(request: Request, scan_id: int, repo: Repository = Depends(get_repo)) -> ScanRun` | 254 | Get a single scan run's metadata. |
| `get_scores` | async func | `(request: Request, scan_id: int, repo: Repository = Depends(get_repo), page: int = Query(1, ge=1)...` | 268 | Get paginated scores for a scan run with filtering/sorting. |
| `get_ticker_detail` | async func | `(request: Request, scan_id: int, ticker: str = ..., repo: Repository = Depends(get_repo)) -> Tick...` | 411 | Get a single ticker's score and recommended contracts. |
| `get_scan_diff` | async func | `(request: Request, scan_id: int, repo: Repository = Depends(get_repo), base_id: int = ...) -> Sca...` | 439 | Compute the diff between two scans. |
| `cancel_scan` | async func | `(request: Request) -> CancelScanResponse` | 523 | Cancel the currently running scan. |

#### api/routes/ticker.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `get_ticker_history` | async func | `(request: Request, ticker: str = ..., repo: Repository = Depends(get_repo), limit: int = ...) -> ...` | 22 | Get score history for a ticker across recent scans. |
| `get_ticker_info` | async func | `(request: Request, ticker: str = ..., market_data: MarketDataService = ...) -> TickerInfo` | 38 | Get fundamental info for a ticker (company name, sector, price, etc.). |
| `get_trending_tickers` | async func | `(request: Request, repo: Repository = Depends(get_repo), direction: str = Query('bullish'), min_s...` | 53 | Get tickers trending in a consistent direction over recent scans. |

#### api/routes/universe.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `get_universe_stats` | async func | `(request: Request, universe: UniverseService = ...) -> UniverseStats` | 43 | Get universe statistics including ETF count. |
| `refresh_universe` | async func | `(request: Request, universe: UniverseService = ...) -> UniverseStats` | 60 | Trigger a refresh of the universe data and return updated stats. |
| `get_sectors` | async func | `(request: Request, universe: UniverseService = ...) -> list[SectorHierarchy]` | 78 | Return GICS sectors with nested industry groups and ticker counts. |
| `get_preset_info` | async func | `(request: Request, universe: UniverseService = ..., repo: Repository = Depends(get_repo)) -> list...` | 136 | Return metadata for all 6 scan presets with estimated ticker counts. |
| `get_metadata_stats` | async func | `(request: Request, repo: Repository = Depends(get_repo)) -> MetadataStats` | 302 | Return metadata coverage statistics. |
| `start_index` | async func | `(request: Request, force: bool = Query(False), max_age: int = Query(30, ge=1), lock: asyncio.Lock...` | 318 | Trigger bulk metadata indexing as a background task. |

#### api/schemas.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `ScanRequest` | model |  | 40 | Request body for ``POST /api/scan``. |
| `ScanStarted` | model |  | 291 | Response for ``POST /api/scan`` (202). |
| `PaginatedResponse` | model |  | 297 | Generic paginated response wrapper. |
| `TickerDetail` | model |  | 306 | Single ticker detail: score + recommended contracts. |
| `DebateRequest` | model |  | 320 | Request body for ``POST /api/debate``. |
| `DebateStarted` | model |  | 343 | Response for ``POST /api/debate`` (202). |
| `DebateResultSummary` | model | `frozen=True` | 349 | Lightweight debate summary for list endpoint. |
| `DebateResultDetail` | model |  | 364 | Full debate result returned by ``GET /api/debate/{id}``. |
| `BatchDebateRequest` | model |  | 426 | Request body for ``POST /api/debate/batch``. |
| `BatchDebateStarted` | model |  | 453 | Response for ``POST /api/debate/batch`` (202). |
| `BatchTickerResult` | model |  | 460 | Per-ticker result summary in batch completion event. |
| `ConfigResponse` | model |  | 475 | Read-only safe config values (no secrets). |
| `CancelScanResponse` | model |  | 485 | Response for cancelling a scan. |
| `SectorInfo` | model |  | 491 | Sector name with count of tickers in that sector. |
| `IndustryGroupInfo` | model |  | 498 | Industry group with ticker count. |
| `SectorHierarchy` | model |  | 505 | Sector with nested industry groups. |
| `UniverseStats` | model |  | 513 | Universe statistics. |
| `OperationStatus` | model |  | 526 | Response for ``GET /api/status`` — current system operation state. |
| `OutcomeCollectionResult` | model |  | 534 | Response for ``POST /api/analytics/collect-outcomes`` (202). |
| `MetadataStats` | model |  | 545 | Metadata coverage statistics. |
| `IndexStarted` | model |  | 554 | Response for ``POST /api/universe/index`` (202). |
| `PresetInfo` | model |  | 565 | Describes a scan preset for the frontend preset picker. |
| `HeatmapTicker` | model | `frozen=True` | 579 | Single ticker entry for the S&P 500 heatmap treemap. |

#### api/ws.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `WebSocketProgressBridge` | class |  | 47 | Bridges sync ``ProgressCallback`` to ``asyncio.Queue`` for WebSocket. |
| `.complete` | method | `(scan_id: int, *, cancelled: bool, outcomes_collected: int = 0) -> None` | 62 | Signal scan completion. |
| `.error` | method | `(message: str) -> None` | 73 | Signal an error event. |
| `DebateProgressBridge` | class |  | 83 | Bridges ``DebateProgressCallback`` to ``asyncio.Queue`` for WebSocket. |
| `.complete` | method | `(debate_id: int) -> None` | 99 | Signal debate completion. |
| `.error` | method | `(message: str) -> None` | 103 | Signal an error event. |
| `BatchProgressBridge` | class |  | 139 | Bridges batch debate progress to ``asyncio.Queue`` for WebSocket. |
| `.agent_bridge` | method | `(ticker: str) -> _BatchAgentBridge` | 145 | Create a per-ticker agent progress bridge. |
| `.batch_progress` | method | `(ticker: str, index: int, total: int, status: str) -> None` | 149 | Signal per-ticker batch progress. |
| `.batch_complete` | method | `(results: Sequence[object]) -> None` | 161 | Signal batch completion with results. |
| `.error` | method | `(message: str) -> None` | 168 | Signal an error event. |
| `ws_scan` | async func | `(websocket: WebSocket, scan_id: int) -> None` | 179 | Stream scan progress events to the client. |
| `ws_debate` | async func | `(websocket: WebSocket, debate_id: int) -> None` | 213 | Stream debate progress events to the client. |
| `ws_batch` | async func | `(websocket: WebSocket, batch_id: int) -> None` | 247 | Stream batch debate progress events to the client. |

---

### 1.12 `cli/` — Typer CLI

#### cli/app.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `LOG_DIR` | const |  | 18 |  |
| `LOG_FILE` | const |  | 19 |  |
| `FILE_FORMAT` | const | `str` | 20 |  |
| `NOISY_LOGGERS` | const | `tuple` | 21 |  |
| `configure_logging` | func | `(*, verbose: bool = False, json_mode: bool = False) -> None` | 34 | Configure dual-handler logging: Rich console + queue-backed rotating file. |
| `main` | func | `(verbose: bool = ..., json_log: bool = ...) -> None` | 120 | Options Arena -- AI-powered American-style options analysis. |

#### cli/commands.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `scan` | func | `(preset: ScanPreset = ..., top_n: int = ..., min_score: float | None = ..., sector: list[str] = ....` | 181 | Run the full scan pipeline: universe -> scoring -> options -> persist. |
| `debate` | func | `(ticker: str | None = ..., batch: bool = ..., batch_limit: int = ..., history: bool = ..., fallba...` | 460 | Run AI debate on a scored ticker. |
| `health` | func | `() -> None` | 1008 | Check external service availability. |
| `refresh` | func | `() -> None` | 1051 | Force re-fetch CBOE universe and S&P 500 constituents. |
| `list_tickers` | func | `(sector: str | None = ..., preset: ScanPreset = ...) -> None` | 1077 | Display tickers matching filters. |
| `sectors` | func | `() -> None` | 1130 | List all 11 GICS sectors with S&P 500 ticker counts. |
| `stats` | func | `() -> None` | 1173 | Show universe size, sector breakdown, S&P 500 count. |
| `index` | func | `(force: bool = ..., concurrency: int = ..., max_age: int = ...) -> None` | 1209 | Bulk-index CBOE tickers to build metadata cache. |
| `serve` | func | `(host: str = ..., port: int = ..., no_open: bool = ..., reload: bool = ...) -> None` | 1387 | Start the FastAPI web server and serve the Vue SPA. |

#### cli/outcomes.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `outcomes_collect` | func | `(holding_days: int | None = ...) -> None` | 44 | Collect outcomes for recommended contracts. |
| `outcomes_summary` | func | `(lookback_days: int = ...) -> None` | 163 | Show performance summary. |
| `agent_accuracy_cmd` | func | `(window: int | None = ...) -> None` | 253 | Show per-agent direction accuracy and Brier scores. |
| `calibration_cmd` | func | `(agent: str | None = ...) -> None` | 309 | Show confidence calibration buckets. |
| `agent_weights_cmd` | func | `() -> None` | 365 | Show manual vs auto-tuned weight comparison. |
| `auto_tune_cmd` | func | `(dry_run: bool = ..., window: int = ...) -> None` | 427 | Compute auto-tuned agent vote weights from outcome accuracy data. |
| `backtest` | func | `(holding_days: Annotated[int, typer.Option(help='Fil... = 20) -> None` | 515 | Show backtesting performance summary. |
| `equity_curve` | func | `(direction: Annotated[str | None, typer.Option(he... = None, period: Annotated[int | None, typer....` | 610 | Show cumulative equity curve. |

#### cli/progress.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `RichProgressCallback` | class |  | 26 | Maps ProgressCallback protocol to Rich Progress display. |
| `setup_sigint_handler` | func | `(token: CancellationToken, console: Console) -> None` | 53 | Register Ctrl+C handler. First press = graceful cancel, second = force exit. |

#### cli/rendering.py

| Symbol | Kind | Signature | Line | Description |
|--------|------|-----------|------|-------------|
| `render_health_table` | func | `(statuses: list[HealthStatus]) -> Table` | 64 | Render health check results as a Rich table. |
| `render_scan_table` | func | `(result: ScanResult) -> Table` | 89 | Render scan results as a Rich table with trading-convention styling. |
| `render_volatility_panel` | func | `(thesis: VolatilityThesis) -> Panel` | 176 | Render Volatility Agent output as a cyan-bordered Rich Panel. |
| `render_flow_panel` | func | `(flow: FlowThesis) -> Panel` | 226 | Render Flow Agent output as a bright_magenta-bordered Rich Panel. |
| `render_fundamental_panel` | func | `(fund: FundamentalThesis) -> Panel` | 268 | Render Fundamental Agent output as a bright_cyan-bordered Rich Panel. |
| `render_risk_panel` | func | `(risk: RiskAssessment) -> Panel` | 315 | Render Risk Agent output as a bright_blue-bordered Rich Panel. |
| `render_contrarian_panel` | func | `(contra: ContrarianThesis) -> Panel` | 367 | Render Contrarian Agent output as a yellow-bordered Rich Panel. |
| `render_debate_panels` | func | `(console: Console, result: DebateResult) -> None` | 409 | Render debate result as Rich panels for the 6-agent protocol. |
| `render_batch_summary_table` | func | `(results: list[tuple[str, DebateResult | None, ...) -> Table` | 614 | Render batch debate results as a compact summary table. |
| `render_debate_history` | func | `(debates: list[DebateRow], ticker: str) -> Table` | 669 | Render past debates as a Rich table. |

---

## Section 2: Call / Dependency Graph

Five runtime call graphs tracing from entry points through all module layers.

Legend: `───►` sync call, `╌╌►` async call, `[cond]` conditional edge,
`«Model»` typed data flowing between functions.

---

### Graph A: `options-arena scan`

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ CLI LAYER                                                                   │
│                                                                             │
│  cli/commands.py::scan()                                                    │
│    ├───► configure_logging()                                                │
│    ├───► AppSettings()                   «ScanConfig, ServiceConfig, ...»   │
│    └───► asyncio.run(_scan_async())                                         │
│            ├╌╌► Database.connect()                                          │
│            ├╌╌► ServiceCache.init_db()                                      │
│            ├───► ScanPipeline(settings, market_data, options_data,           │
│            │                  fred, universe, repository)                    │
│            └╌╌► ScanPipeline.run(preset, token, progress)                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                    «ScanResult»     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ SCAN LAYER  (scan/pipeline.py)                                              │
│                                                                             │
│  ScanPipeline.run()                                                         │
│    ├╌╌► Phase 1: _phase_universe(preset, token)                             │
│    │      ├╌╌► UniverseService.fetch_optionable_tickers()    «list[str]»    │
│    │      ├╌╌► UniverseService.fetch_sp500_constituents()    «list[SP500]»  │
│    │      ├───► build_sector_map() / filter_by_sectors()                    │
│    │      ├╌╌► MarketDataService.fetch_batch_ohlcv()     «BatchOHLCVResult» │
│    │      └───► ohlcv_to_dataframe()                     «pd.DataFrame»    │
│    │                                                                        │
│    ├╌╌► Phase 2: _phase_scoring(universe_result, token)                     │
│    │      ├───► compute_indicators(df, INDICATOR_REGISTRY) «IndicatorSignals│
│    │      ├───► score_universe(universe)                                    │
│    │      │       ├───► percentile_rank_normalize()                         │
│    │      │       ├───► invert_indicators()                                 │
│    │      │       ├───► composite_score()                                   │
│    │      │       └───► determine_direction()              «SignalDirection» │
│    │      ├───► compute_dimensional_scores()               «DimensionalScrs»│
│    │      ├───► compute_direction_signal()                  «DirectionSignal»│
│    │      └───► compute_normalization_stats()           «NormalizationStats» │
│    │                                                                        │
│    ├╌╌► Phase 3: _phase_options(scoring_result, token)                      │
│    │      ├╌╌► FredService.fetch_risk_free_rate()            «float»        │
│    │      ├╌╌► OptionsDataService.fetch_expirations()        «list[date]»   │
│    │      ├╌╌► OptionsDataService.fetch_chain()        «list[OptionContract]»│
│    │      ├───► compute_phase3_indicators()              «IndicatorSignals» │
│    │      └───► recommend_contracts()                                       │
│    │              ├───► filter_contracts()                                   │
│    │              ├───► select_expiration()                                  │
│    │              ├───► compute_greeks()  ╌╌► pricing/dispatch.option_greeks │
│    │              └───► select_by_delta()             «OptionContract|None»  │
│    │                                                                        │
│    └╌╌► Phase 4: _phase_persist(options_result, token)                      │
│           ├╌╌► Repository.save_scan_run()                  «int (scan_id)»  │
│           ├╌╌► Repository.save_ticker_scores()                              │
│           ├╌╌► Repository.save_recommended_contracts()                      │
│           └╌╌► Repository.save_normalization_stats()                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ SERVICE LAYER                                                               │
│                                                                             │
│  MarketDataService         OptionsDataService         FredService           │
│  ╌╌► yfinance (to_thread)  ╌╌► CBOEChainProvider     ╌╌► httpx (FRED API)  │
│                            ╌╌► YFinanceChainProvider                        │
│                            [fallback on exception]                          │
│                                                                             │
│  UniverseService                                                            │
│  ╌╌► httpx (CBOE CSV)     ╌╌► httpx+pandas (GitHub CSV)                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ MATH LAYER (no I/O)                                                         │
│                                                                             │
│  indicators/*              scoring/*              pricing/dispatch          │
│  rsi(), adx(), macd()...   composite_score()      option_greeks()           │
│  pd.Series in/out          percentile_rank_...     ├───► bsm_greeks()       │
│                            determine_direction()   └───► american_greeks()  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### Graph B: `options-arena debate`

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ CLI LAYER                                                                   │
│                                                                             │
│  cli/commands.py::debate()                                                  │
│    └───► asyncio.run(_debate_async())                                       │
│            ├╌╌► Repository.get_latest_scan()                «ScanRun»       │
│            ├╌╌► Repository.get_scores_for_scan()         «list[TickerScore]» │
│            ├╌╌► MarketDataService.fetch_quote()              «Quote»        │
│            ├╌╌► MarketDataService.fetch_ticker_info()        «TickerInfo»   │
│            ├───► build_market_context(ticker_score, quote,                   │
│            │       ticker_info, contracts, ...)              «MarketContext» │
│            ├───► should_debate(ticker_score, config)         «bool»         │
│            └╌╌► run_debate(...)                              «DebateResult»  │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ AGENT LAYER  (agents/orchestrator.py)                                       │
│                                                                             │
│  run_debate()                                                               │
│    ├───► build_debate_model(config)                          «GroqModel»    │
│    ├───► render_context_block(market_context)                 «str»         │
│    │                                                                        │
│    ├╌╌► Phase 1: gather(*[trend, vol, flow, fund], return_exceptions=True)  │
│    │      ├╌╌► trend_agent.run(model, deps)                «AgentResponse»  │
│    │      ├╌╌► volatility_agent.run(model, deps)       «VolatilityThesis»   │
│    │      ├╌╌► flow_agent.run(model, deps)                 «FlowThesis»     │
│    │      └╌╌► fundamental_agent.run(model, deps)     «FundamentalThesis»   │
│    │                                                                        │
│    ├╌╌► Phase 2: risk_agent_v2.run(model, deps)         «RiskAssessment»    │
│    │      [deps includes all Phase 1 outputs]                               │
│    │                                                                        │
│    ├╌╌► Phase 3: contrarian_agent.run(model, deps)    «ContrarianThesis»    │
│    │      [deps includes all Phase 1+2 outputs]                             │
│    │                                                                        │
│    ├───► Phase 4: synthesize_verdict(all_outputs)    «ExtendedTradeThesis»  │
│    │      ├───► compute_agreement_score()                    «float»        │
│    │      └───► weighted confidence + dissent computation                   │
│    │                                                                        │
│    └╌╌► Repository.save_debate(...)                                         │
│                                                                             │
│  [on any error] ───► data-driven fallback (confidence=0.3)                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ LLM PROVIDER                                                                │
│                                                                             │
│  PydanticAI → GroqModel → Groq API (llama-3.3-70b-versatile)               │
│  retries=2, num_ctx=8192                                                    │
│  output_validator: strip_think_tags → build_cleaned_*()                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### Graph C: `POST /api/scan` (API Entry)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ API LAYER                                                                   │
│                                                                             │
│  routes/scan.py::start_scan()                                               │
│    ├───► Validate ScanRequest                                               │
│    ├───► acquire operation_lock (409 if busy)                               │
│    ├───► scan_id = counter++                                                │
│    ├───► bridge = WebSocketProgressBridge()                                 │
│    └───► asyncio.create_task(_run_scan_background())                        │
│            │                                                                │
│            ├╌╌► ScanPipeline.run(...)        [same as Graph A internals]     │
│            │     bridge.__call__(phase, current, total)                      │
│            │       └───► queue.put_nowait({type, phase, current, total})     │
│            │                                                                │
│            └───► finally: operation_lock.release()                          │
│                                                                             │
│  ws.py::ws_scan(scan_id)                                                    │
│    └───► while True: event = await queue.get() → ws.send_json(event)        │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                        «JSON events» ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ FRONTEND  (Vue 3 SPA)                                                       │
│                                                                             │
│  useScanStore.startScan()                                                   │
│    ├───► api('POST /api/scan', body)                    → scan_id           │
│    └───► useWebSocket(`/ws/scan/${scanId}`)                                 │
│            onMessage → updateProgress() / setComplete() / addError()        │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### Graph D: `POST /api/debate` (API Entry)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ API LAYER                                                                   │
│                                                                             │
│  routes/debate.py::start_debate()                                           │
│    ├───► Validate DebateRequest                                             │
│    ├───► acquire operation_lock (409 if busy)                               │
│    ├───► debate_id = counter++                                              │
│    ├───► bridge = DebateProgressBridge()                                    │
│    └───► asyncio.create_task(_run_debate_background())                      │
│            │                                                                │
│            ├╌╌► build_market_context(...)                                    │
│            ├╌╌► run_debate(...)              [same as Graph B internals]     │
│            │     bridge.__call__(phase, status, confidence)                  │
│            │       └───► queue.put_nowait({type, name, status, confidence})  │
│            │                                                                │
│            └───► finally: operation_lock.release()                          │
│                                                                             │
│  ws.py::ws_debate(debate_id)                                                │
│    └───► while True: event = await queue.get() → ws.send_json(event)        │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                        «JSON events» ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ FRONTEND  (Vue 3 SPA)                                                       │
│                                                                             │
│  useDebateStore.startDebate()                                               │
│    ├───► api('POST /api/debate', body)                  → debate_id         │
│    └───► useWebSocket(`/ws/debate/${debateId}`)                             │
│            onMessage → updateAgentProgress() / setDebateComplete()          │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### Graph E: `options-arena outcomes collect`

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ CLI LAYER                                                                   │
│                                                                             │
│  cli/outcomes.py::outcomes_collect()                                        │
│    └───► asyncio.run(_outcomes_collect_async())                              │
│            ├╌╌► Database.connect()                                          │
│            ├───► OutcomeCollector(config, repo, market_data, options_data)   │
│            └╌╌► OutcomeCollector.collect_outcomes(holding_days)              │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ SERVICE LAYER  (services/outcome_collector.py)                              │
│                                                                             │
│  collect_outcomes(holding_days)                                             │
│    └───► for period in holding_periods:                                     │
│            ├╌╌► _collect_for_period(days)                                   │
│            │      ├╌╌► Repository.get_contracts_needing_outcomes(days)       │
│            │      │                                    «list[int]» (IDs)    │
│            │      └───► for contract_id in contract_ids:                    │
│            │              ├╌╌► Repository.get_contracts_for_scan()           │
│            │              │                          «RecommendedContract»   │
│            │              ├───► [expired?]                                   │
│            │              │   └───► _process_expired_contract()              │
│            │              │          └───► intrinsic_value(S, K, type)       │
│            │              └───► [active?]                                    │
│            │                  └╌╌► _process_active_contract()                │
│            │                       ├╌╌► MarketDataService.fetch_quote()      │
│            │                       └╌╌► OptionsDataService.fetch_chain()     │
│            │                                          «ContractOutcome»      │
│            └╌╌► Repository.save_contract_outcomes(outcomes)                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Section 3: Traceability Matrix

Each row maps a source file to its test files and approximate test count.

### utils/

| Source File | Test File(s) | Tests |
|------------|--------------|-------|
| `utils/exceptions.py` | `tests/unit/utils/test_exceptions.py` | 13 |

### models/

| Source File | Test File(s) | Tests |
|------------|--------------|-------|
| `models/_validators.py` | — | 0 |
| `models/analysis.py` | `tests/unit/models/test_analysis.py` | 63 |
| `models/analytics.py` | `tests/unit/models/test_analytics.py` | 60 |
| `models/config.py` | `tests/unit/models/test_config.py` | 112 |
| `models/enums.py` | `tests/unit/models/test_enums.py` | 66 |
| `models/filters.py` | `tests/unit/models/test_filters.py` | 47 |
| `models/financial_datasets.py` | `tests/unit/models/test_financial_datasets.py` | 42 |
| `models/health.py` | `tests/unit/models/test_health.py` | 12 |
| `models/history.py` | — | 0 |
| `models/intelligence.py` | — | 0 |
| `models/market_data.py` | `tests/unit/models/test_market_data.py` | 53 |
| `models/metadata.py` | `tests/unit/models/test_metadata.py` | 12 |
| `models/openbb.py` | — | 0 |
| `models/options.py` | `tests/unit/models/test_options.py` | 41 |
| `models/scan.py` | `tests/unit/models/test_scan.py` | 31 |
| `models/scan_delta.py` | — | 0 |
| `models/scoring.py` | `tests/unit/models/test_scoring.py` | 28 |

### indicators/

| Source File | Test File(s) | Tests |
|------------|--------------|-------|
| `indicators/_validation.py` | — | 0 |
| `indicators/flow_analytics.py` | `tests/unit/indicators/test_flow_analytics.py` | 42 |
| `indicators/fundamental.py` | `tests/unit/indicators/test_fundamental.py` | 44 |
| `indicators/hv_estimators.py` | `tests/unit/indicators/test_hv_estimators.py` | 37 |
| `indicators/iv_analytics.py` | `tests/unit/indicators/test_iv_analytics.py` | 99 |
| `indicators/moving_averages.py` | `tests/unit/indicators/test_moving_averages.py` | 13 |
| `indicators/options_specific.py` | `tests/unit/indicators/test_options_specific.py` | 34 |
| `indicators/oscillators.py` | `tests/unit/indicators/test_oscillators.py` | 22 |
| `indicators/regime.py` | `tests/unit/indicators/test_regime.py` | 50 |
| `indicators/trend.py` | `tests/unit/indicators/test_trend.py` | 21 |
| `indicators/vol_surface.py` | `tests/unit/indicators/test_vol_surface.py` | 39 |
| `indicators/volatility.py` | `tests/unit/indicators/test_volatility.py` | 18 |
| `indicators/volume.py` | `tests/unit/indicators/test_volume.py` | 21 |

### pricing/

| Source File | Test File(s) | Tests |
|------------|--------------|-------|
| `pricing/_common.py` | — | 0 |
| `pricing/american.py` | `tests/unit/pricing/test_american.py` | 65 |
| `pricing/bsm.py` | `tests/unit/pricing/test_bsm.py` | 65 |
| `pricing/dispatch.py` | `tests/unit/pricing/test_dispatch.py` | 20 |

### services/

| Source File | Test File(s) | Tests |
|------------|--------------|-------|
| `services/base.py` | `tests/unit/services/test_base.py` | 30 |
| `services/cache.py` | `tests/unit/services/test_cache.py` | 28 |
| `services/cboe_provider.py` | `tests/unit/services/test_cboe_provider.py` | 38 |
| `services/financial_datasets.py` | `tests/unit/services/test_financial_datasets.py` | 18 |
| `services/fred.py` | `tests/unit/services/test_fred.py` | 19 |
| `services/health.py` | `tests/unit/services/test_health.py` | 35 |
| `services/helpers.py` | `tests/unit/services/test_helpers.py` | 38 |
| `services/intelligence.py` | — | 0 |
| `services/market_data.py` | `tests/unit/services/test_market_data.py` | 65 |
| `services/openbb_service.py` | `tests/unit/services/test_openbb_service.py` | 51 |
| `services/options_data.py` | `tests/unit/services/test_options_data.py` | 19 |
| `services/outcome_collector.py` | `tests/unit/services/test_outcome_collector.py` | 38 |
| `services/rate_limiter.py` | `tests/unit/services/test_rate_limiter.py` | 9 |
| `services/universe.py` | `tests/unit/services/test_universe.py` | 31 |

### scoring/

| Source File | Test File(s) | Tests |
|------------|--------------|-------|
| `scoring/composite.py` | `tests/unit/scoring/test_composite.py` | 19 |
| `scoring/contracts.py` | `tests/unit/scoring/test_contracts.py` | 44 |
| `scoring/dimensional.py` | `tests/unit/scoring/test_dimensional.py` | 51 |
| `scoring/direction.py` | `tests/unit/scoring/test_direction.py` | 41 |
| `scoring/normalization.py` | `tests/unit/scoring/test_normalization.py` | 39 |

### data/

| Source File | Test File(s) | Tests |
|------------|--------------|-------|
| `data/_analytics.py` | — | 0 |
| `data/_base.py` | — | 0 |
| `data/_debate.py` | — | 0 |
| `data/_metadata.py` | — | 0 |
| `data/_scan.py` | — | 0 |
| `data/database.py` | `tests/unit/data/test_database.py` | 10 |
| `data/repository.py` | `tests/unit/data/test_repository.py` | 36 |

### agents/

| Source File | Test File(s) | Tests |
|------------|--------------|-------|
| `agents/_parsing.py` | `tests/unit/agents/test_parsing.py` | 64 |
| `agents/bear.py` | `tests/unit/agents/test_bear.py` | 14 |
| `agents/bull.py` | `tests/unit/agents/test_bull.py` | 15 |
| `agents/contrarian_agent.py` | — | 0 |
| `agents/flow_agent.py` | — | 0 |
| `agents/fundamental_agent.py` | — | 0 |
| `agents/model_config.py` | `tests/unit/agents/test_model_config.py` | 22 |
| `agents/orchestrator.py` | `tests/unit/agents/test_orchestrator.py` | 60 |
| `agents/prompts/bear.py` | `tests/unit/agents/test_bear.py` | 14 |
| `agents/prompts/bull.py` | `tests/unit/agents/test_bull.py` | 15 |
| `agents/prompts/contrarian_agent.py` | — | 0 |
| `agents/prompts/flow_agent.py` | — | 0 |
| `agents/prompts/fundamental_agent.py` | — | 0 |
| `agents/prompts/risk.py` | `tests/unit/agents/test_risk.py` | 13 |
| `agents/prompts/trend_agent.py` | — | 0 |
| `agents/prompts/volatility.py` | `tests/unit/agents/test_volatility.py` | 15 |
| `agents/risk.py` | `tests/unit/agents/test_risk.py` | 13 |
| `agents/trend_agent.py` | — | 0 |
| `agents/volatility.py` | `tests/unit/agents/test_volatility.py` | 15 |

### scan/

| Source File | Test File(s) | Tests |
|------------|--------------|-------|
| `scan/indicators.py` | `tests/unit/scan/test_indicators.py` | 40 |
| `scan/models.py` | `tests/unit/scan/test_models.py` | 20 |
| `scan/phase_options.py` | — | 0 |
| `scan/phase_persist.py` | — | 0 |
| `scan/phase_scoring.py` | — | 0 |
| `scan/phase_universe.py` | — | 0 |
| `scan/pipeline.py` | — | 0 |
| `scan/progress.py` | `tests/unit/scan/test_progress.py` | 19 |

### reporting/

| Source File | Test File(s) | Tests |
|------------|--------------|-------|
| `reporting/debate_export.py` | `tests/unit/reporting/test_debate_export.py` | 10 |

### api/

| Source File | Test File(s) | Tests |
|------------|--------------|-------|
| `api/app.py` | `tests/unit/api/test_app.py` | 3 |
| `api/deps.py` | `tests/unit/api/test_deps.py` | 7 |
| `api/routes/analytics.py` | `tests/unit/api/test_analytics_routes.py` | 21 |
| `api/routes/backtest.py` | — | 0 |
| `api/routes/config.py` | — | 0 |
| `api/routes/debate.py` | `tests/unit/api/test_debate_routes.py` | 17 |
| `api/routes/export.py` | `tests/unit/api/test_export_routes.py` | 2 |
| `api/routes/health.py` | `tests/unit/api/test_health_routes.py` | 3 |
| `api/routes/market.py` | `tests/unit/api/test_market_routes.py` | 19 |
| `api/routes/scan.py` | `tests/unit/api/test_scan_routes.py` | 20 |
| `api/routes/ticker.py` | `tests/unit/api/test_ticker_routes.py` | 4 |
| `api/routes/universe.py` | — | 0 |
| `api/schemas.py` | `tests/unit/api/test_schemas.py` | 26 |
| `api/ws.py` | `tests/unit/api/test_ws.py` | 9 |

### cli/

| Source File | Test File(s) | Tests |
|------------|--------------|-------|
| `cli/app.py` | — | 0 |
| `cli/commands.py` | `tests/unit/cli/test_commands.py` | 15 |
| `cli/outcomes.py` | — | 0 |
| `cli/progress.py` | `tests/unit/cli/test_progress.py` | 3 |
| `cli/rendering.py` | `tests/unit/cli/test_rendering.py` | 9 |

---

### Summary Statistics

| Module | Files | Public Symbols | Test Files | Tests |
|--------|-------|----------------|------------|-------|
| utils/ | 1 | 5 | 1 | 13 |
| models/ | 17 | 113 | 12 | 567 |
| indicators/ | 13 | 64 | 12 | 440 |
| pricing/ | 4 | 18 | 3 | 150 |
| services/ | 14 | 121 | 13 | 419 |
| scoring/ | 5 | 26 | 5 | 194 |
| data/ | 7 | 60 | 2 | 46 |
| agents/ | 19 | 58 | 7 | 260 |
| scan/ | 8 | 23 | 3 | 79 |
| reporting/ | 1 | 2 | 1 | 10 |
| api/ | 14 | 99 | 11 | 131 |
| cli/ | 5 | 35 | 3 | 27 |
| **Total** | **108** | **624** | **73** | **2336** |

/** TypeScript interfaces matching Python analytics models (models/analytics.py). */

/** Win rate grouped by signal direction from GET /api/analytics/win-rate. */
export interface WinRateResult {
  direction: 'bullish' | 'bearish' | 'neutral'
  total_contracts: number
  winners: number
  losers: number
  /** Fraction in [0.0, 1.0], NOT a percentage. */
  win_rate: number
}

/** Score calibration bucket from GET /api/analytics/score-calibration. */
export interface ScoreCalibrationBucket {
  score_min: number
  score_max: number
  contract_count: number
  avg_return_pct: number
  /** Fraction in [0.0, 1.0]. */
  win_rate: number
}

/** Indicator attribution from GET /api/analytics/indicator-attribution/{indicator}. */
export interface IndicatorAttributionResult {
  indicator_name: string
  holding_days: number
  correlation: number
  avg_return_when_high: number
  avg_return_when_low: number
  sample_size: number
}

/** Holding period stats from GET /api/analytics/holding-period. */
export interface HoldingPeriodResult {
  holding_days: number
  direction: 'bullish' | 'bearish' | 'neutral'
  avg_return_pct: number
  median_return_pct: number
  /** Fraction in [0.0, 1.0]. */
  win_rate: number
  sample_size: number
}

/** Delta performance from GET /api/analytics/delta-performance. */
export interface DeltaPerformanceResult {
  delta_min: number
  delta_max: number
  holding_days: number
  avg_return_pct: number
  /** Fraction in [0.0, 1.0]. */
  win_rate: number
  sample_size: number
}

/** Aggregate performance summary from GET /api/analytics/summary. */
export interface PerformanceSummary {
  lookback_days: number
  total_contracts: number
  total_with_outcomes: number
  /** Fraction in [0.0, 1.0], or null if no outcomes. */
  overall_win_rate: number | null
  avg_stock_return_pct: number | null
  avg_contract_return_pct: number | null
  best_direction: WinRateResult['direction'] | null
  best_holding_days: number | null
}

/** Response from POST /api/analytics/collect-outcomes. */
export interface OutcomeCollectionResult {
  outcomes_collected: number
}

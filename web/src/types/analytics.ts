/** Win rate grouped by signal direction from GET /api/analytics/win-rate. */
export interface WinRateResult {
  direction: 'bullish' | 'bearish' | 'neutral'
  total_contracts: number
  winners: number
  losers: number
  win_rate: number
}

/** Score calibration bucket from GET /api/analytics/score-calibration. */
export interface ScoreCalibrationBucket {
  score_min: number
  score_max: number
  contract_count: number
  avg_return_pct: number
  win_rate: number
}

/** Holding period stats from GET /api/analytics/holding-period. */
export interface HoldingPeriodResult {
  holding_days: number
  direction: 'bullish' | 'bearish' | 'neutral'
  avg_return_pct: number
  median_return_pct: number
  win_rate: number
  sample_size: number
}

/** Delta performance from GET /api/analytics/delta-performance. */
export interface DeltaPerformanceResult {
  delta_min: number
  delta_max: number
  holding_days: number
  avg_return_pct: number
  win_rate: number
  sample_size: number
}

/** Aggregate performance summary from GET /api/analytics/summary. */
export interface PerformanceSummary {
  lookback_days: number
  total_contracts: number
  total_with_outcomes: number
  overall_win_rate: number | null
  avg_stock_return_pct: number | null
  avg_contract_return_pct: number | null
  best_direction: string | null
  best_holding_days: number | null
  total_recommendations: number
  total_outcomes: number
}

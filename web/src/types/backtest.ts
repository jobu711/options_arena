/** TypeScript interfaces matching Python backtesting analytics models. */

/** Single data point on the equity curve from GET /api/analytics/backtest/equity-curve. */
export interface EquityCurvePoint {
  /** Calendar date (ISO 8601 date string). */
  date: string
  /** Cumulative return percentage at this date. */
  cumulative_return_pct: number
  /** Number of trades completed up to this date. */
  trade_count: number
}

/** Single drawdown data point from GET /api/analytics/backtest/drawdown. */
export interface DrawdownPoint {
  /** Calendar date (ISO 8601 date string). */
  date: string
  /** Drawdown percentage (non-positive, 0.0 = at peak). */
  drawdown_pct: number
  /** Peak cumulative value before this drawdown. */
  peak_value: number
}

/** Sector performance from GET /api/analytics/backtest/sector-performance. */
export interface SectorPerformanceResult {
  /** GICS sector name. */
  sector: string
  /** Total contracts in this sector. */
  total: number
  /** Win rate as percentage [0.0, 100.0]. */
  win_rate_pct: number
  /** Average return percentage. */
  avg_return_pct: number
}

/** DTE bucket performance from GET /api/analytics/backtest/dte-performance. */
export interface DTEBucketResult {
  /** Lower bound of DTE bucket (inclusive). */
  dte_min: number
  /** Upper bound of DTE bucket (inclusive). */
  dte_max: number
  /** Total contracts in this bucket. */
  total: number
  /** Win rate as percentage [0.0, 100.0]. */
  win_rate_pct: number
  /** Average return percentage. */
  avg_return_pct: number
}

/** IV rank bucket performance from GET /api/analytics/backtest/iv-performance. */
export interface IVRankBucketResult {
  /** Lower bound of IV rank bucket. */
  iv_min: number
  /** Upper bound of IV rank bucket. */
  iv_max: number
  /** Total contracts in this bucket. */
  total: number
  /** Win rate as percentage [0.0, 100.0]. */
  win_rate_pct: number
  /** Average return percentage. */
  avg_return_pct: number
}

/** Greeks P&L decomposition from GET /api/analytics/backtest/greeks-decomposition. */
export interface GreeksDecompositionResult {
  /** Grouping label (e.g. "calls", "puts", "bullish"). */
  group_key: string
  /** P&L attributable to delta. */
  delta_pnl: number
  /** Residual P&L not explained by delta. */
  residual_pnl: number
  /** Total P&L (delta_pnl + residual_pnl). */
  total_pnl: number
  /** Number of contracts in this group. */
  count: number
}

/** Holding period comparison from GET /api/analytics/backtest/holding-comparison. */
export interface HoldingPeriodComparison {
  /** Number of trading days held. */
  holding_days: number
  /** Signal direction. */
  direction: string
  /** Average return percentage. */
  avg_return: number
  /** Median return percentage. */
  median_return: number
  /** Win rate as fraction [0.0, 1.0]. */
  win_rate: number
  /** Sharpe-like ratio (mean / std). */
  sharpe_like: number
  /** Maximum loss percentage (non-positive or zero). */
  max_loss: number
  /** Number of contracts. */
  count: number
}

/** Per-agent accuracy report from GET /api/analytics/agent-accuracy. */
export interface AgentAccuracyReport {
  agent_name: string
  /** Direction hit rate [0.0, 1.0]. */
  direction_hit_rate: number
  /** Mean confidence [0.0, 1.0]. */
  mean_confidence: number
  /** Brier score [0.0, 1.0] (lower = better). */
  brier_score: number
  sample_size: number
}

/** Single confidence calibration bucket. */
export interface CalibrationBucket {
  bucket_label: string
  bucket_low: number
  bucket_high: number
  mean_confidence: number
  actual_hit_rate: number
  count: number
}

/** Agent calibration data from GET /api/analytics/agent-calibration. */
export interface AgentCalibrationData {
  /** Null = aggregate across all agents. */
  agent_name: string | null
  buckets: CalibrationBucket[]
  sample_size: number
}

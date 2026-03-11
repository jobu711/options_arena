import type {
  PerformanceSummary,
  WinRateResult,
  ScoreCalibrationBucket,
  HoldingPeriodResult,
  DeltaPerformanceResult,
  OutcomeCollectionResult,
  EquityCurvePoint,
  DrawdownPoint,
  SectorPerformanceResult,
  DTEBucketResult,
  IVRankBucketResult,
  GreeksDecompositionResult,
  HoldingPeriodComparison,
  AgentAccuracyReport,
  AgentCalibrationData,
  AgentWeightsComparison,
  WeightSnapshot,
} from '../../../src/types'

export function buildPerformanceSummary(
  overrides: Partial<PerformanceSummary> = {},
): PerformanceSummary {
  return {
    lookback_days: 30,
    total_contracts: 142,
    total_with_outcomes: 89,
    overall_win_rate: 0.632,
    avg_stock_return_pct: 2.4,
    avg_contract_return_pct: 12.8,
    best_direction: 'bullish',
    best_holding_days: 10,
    ...overrides,
  }
}

export function buildEmptySummary(
  overrides: Partial<PerformanceSummary> = {},
): PerformanceSummary {
  return {
    lookback_days: 30,
    total_contracts: 0,
    total_with_outcomes: 0,
    overall_win_rate: null,
    avg_stock_return_pct: null,
    avg_contract_return_pct: null,
    best_direction: null,
    best_holding_days: null,
    ...overrides,
  }
}

export function buildNoOutcomesSummary(): PerformanceSummary {
  return buildPerformanceSummary({
    total_contracts: 50,
    total_with_outcomes: 0,
    overall_win_rate: null,
    avg_stock_return_pct: null,
    avg_contract_return_pct: null,
    best_direction: null,
    best_holding_days: null,
  })
}

export function buildWinRateResults(): WinRateResult[] {
  return [
    { direction: 'bullish', total_contracts: 62, winners: 45, losers: 17, win_rate: 0.726 },
    { direction: 'bearish', total_contracts: 46, winners: 30, losers: 16, win_rate: 0.652 },
    { direction: 'neutral', total_contracts: 20, winners: 9, losers: 11, win_rate: 0.45 },
  ]
}

export function buildCalibrationBuckets(): ScoreCalibrationBucket[] {
  return [
    { score_min: 0, score_max: 20, contract_count: 5, avg_return_pct: -8.2, win_rate: 0.2 },
    { score_min: 20, score_max: 40, contract_count: 12, avg_return_pct: -2.1, win_rate: 0.33 },
    { score_min: 40, score_max: 60, contract_count: 35, avg_return_pct: 3.4, win_rate: 0.54 },
    { score_min: 60, score_max: 80, contract_count: 28, avg_return_pct: 8.7, win_rate: 0.71 },
    { score_min: 80, score_max: 100, contract_count: 8, avg_return_pct: 15.3, win_rate: 0.88 },
  ]
}

export function buildHoldingPeriods(): HoldingPeriodResult[] {
  return [
    { holding_days: 1, direction: 'bullish', avg_return_pct: 1.2, median_return_pct: 0.8, win_rate: 0.55, sample_size: 45 },
    { holding_days: 5, direction: 'bullish', avg_return_pct: 3.8, median_return_pct: 2.9, win_rate: 0.62, sample_size: 42 },
    { holding_days: 10, direction: 'bullish', avg_return_pct: 6.1, median_return_pct: 4.5, win_rate: 0.68, sample_size: 38 },
    { holding_days: 20, direction: 'bullish', avg_return_pct: 8.4, median_return_pct: 5.2, win_rate: 0.72, sample_size: 30 },
  ]
}

export function buildDeltaPerformance(): DeltaPerformanceResult[] {
  return [
    { delta_min: 0.2, delta_max: 0.3, holding_days: 10, avg_return_pct: 5.2, win_rate: 0.58, sample_size: 15 },
    { delta_min: 0.3, delta_max: 0.4, holding_days: 10, avg_return_pct: 8.1, win_rate: 0.65, sample_size: 22 },
    { delta_min: 0.4, delta_max: 0.5, holding_days: 10, avg_return_pct: 6.3, win_rate: 0.62, sample_size: 18 },
    { delta_min: 0.5, delta_max: 0.6, holding_days: 10, avg_return_pct: 3.8, win_rate: 0.55, sample_size: 12 },
  ]
}

export function buildOutcomeResult(
  overrides: Partial<OutcomeCollectionResult> = {},
): OutcomeCollectionResult {
  return { outcomes_collected: 15, ...overrides }
}

// --- Backtest builders ---

export function buildEquityCurve(): EquityCurvePoint[] {
  return [
    { date: '2026-01-15', cumulative_return_pct: 1.2, trade_count: 3 },
    { date: '2026-01-22', cumulative_return_pct: 3.5, trade_count: 7 },
    { date: '2026-01-29', cumulative_return_pct: 2.8, trade_count: 12 },
    { date: '2026-02-05', cumulative_return_pct: 5.1, trade_count: 18 },
    { date: '2026-02-12', cumulative_return_pct: 7.3, trade_count: 25 },
  ]
}

export function buildDrawdown(): DrawdownPoint[] {
  return [
    { date: '2026-01-15', drawdown_pct: 0.0, peak_value: 1.2 },
    { date: '2026-01-22', drawdown_pct: 0.0, peak_value: 3.5 },
    { date: '2026-01-29', drawdown_pct: -0.7, peak_value: 3.5 },
    { date: '2026-02-05', drawdown_pct: 0.0, peak_value: 5.1 },
    { date: '2026-02-12', drawdown_pct: 0.0, peak_value: 7.3 },
  ]
}

export function buildSectorPerformance(): SectorPerformanceResult[] {
  return [
    { sector: 'Information Technology', total: 35, win_rate_pct: 68.5, avg_return_pct: 8.2 },
    { sector: 'Health Care', total: 22, win_rate_pct: 59.1, avg_return_pct: 5.4 },
    { sector: 'Financials', total: 18, win_rate_pct: 55.6, avg_return_pct: 3.8 },
    { sector: 'Consumer Discretionary', total: 14, win_rate_pct: 42.9, avg_return_pct: -1.2 },
  ]
}

export function buildDTEBuckets(): DTEBucketResult[] {
  return [
    { dte_min: 0, dte_max: 7, total: 10, win_rate_pct: 50.0, avg_return_pct: 2.1 },
    { dte_min: 7, dte_max: 14, total: 18, win_rate_pct: 61.1, avg_return_pct: 5.3 },
    { dte_min: 14, dte_max: 30, total: 32, win_rate_pct: 65.6, avg_return_pct: 7.2 },
    { dte_min: 30, dte_max: 60, total: 20, win_rate_pct: 55.0, avg_return_pct: 4.1 },
  ]
}

export function buildIVBuckets(): IVRankBucketResult[] {
  return [
    { iv_min: 0, iv_max: 25, total: 15, win_rate_pct: 53.3, avg_return_pct: 3.2 },
    { iv_min: 25, iv_max: 50, total: 28, win_rate_pct: 64.3, avg_return_pct: 6.8 },
    { iv_min: 50, iv_max: 75, total: 22, win_rate_pct: 59.1, avg_return_pct: 5.1 },
    { iv_min: 75, iv_max: 100, total: 12, win_rate_pct: 50.0, avg_return_pct: 1.9 },
  ]
}

export function buildGreeksDecomposition(): GreeksDecompositionResult[] {
  return [
    { group_key: 'calls', delta_pnl: 4.2, residual_pnl: 1.8, total_pnl: 6.0, count: 45 },
    { group_key: 'puts', delta_pnl: -2.1, residual_pnl: 3.5, total_pnl: 1.4, count: 35 },
  ]
}

export function buildHoldingComparison(): HoldingPeriodComparison[] {
  return [
    { holding_days: 1, direction: 'bullish', avg_return: 1.2, median_return: 0.8, win_rate: 0.55, sharpe_like: 0.35, max_loss: -5.2, count: 40 },
    { holding_days: 5, direction: 'bullish', avg_return: 3.8, median_return: 2.9, win_rate: 0.62, sharpe_like: 0.58, max_loss: -8.1, count: 38 },
    { holding_days: 10, direction: 'bullish', avg_return: 6.1, median_return: 4.5, win_rate: 0.68, sharpe_like: 0.72, max_loss: -12.3, count: 35 },
    { holding_days: 20, direction: 'bullish', avg_return: 8.4, median_return: 5.2, win_rate: 0.72, sharpe_like: 0.81, max_loss: -15.8, count: 28 },
    { holding_days: 5, direction: 'bearish', avg_return: 2.1, median_return: 1.5, win_rate: 0.58, sharpe_like: 0.42, max_loss: -9.4, count: 30 },
  ]
}

export function buildAgentAccuracy(): AgentAccuracyReport[] {
  return [
    { agent_name: 'trend', direction_hit_rate: 0.72, mean_confidence: 0.65, brier_score: 0.18, sample_size: 50 },
    { agent_name: 'bear', direction_hit_rate: 0.61, mean_confidence: 0.58, brier_score: 0.24, sample_size: 50 },
    { agent_name: 'risk', direction_hit_rate: 0.68, mean_confidence: 0.62, brier_score: 0.20, sample_size: 45 },
    { agent_name: 'volatility', direction_hit_rate: 0.55, mean_confidence: 0.52, brier_score: 0.28, sample_size: 42 },
  ]
}

export function buildAgentCalibration(): AgentCalibrationData {
  return {
    agent_name: null,
    buckets: [
      { bucket_label: '0.4-0.5', bucket_low: 0.4, bucket_high: 0.5, mean_confidence: 0.45, actual_hit_rate: 0.48, count: 20 },
      { bucket_label: '0.5-0.6', bucket_low: 0.5, bucket_high: 0.6, mean_confidence: 0.55, actual_hit_rate: 0.58, count: 35 },
      { bucket_label: '0.6-0.7', bucket_low: 0.6, bucket_high: 0.7, mean_confidence: 0.65, actual_hit_rate: 0.62, count: 28 },
      { bucket_label: '0.7-0.8', bucket_low: 0.7, bucket_high: 0.8, mean_confidence: 0.75, actual_hit_rate: 0.70, count: 15 },
    ],
    sample_size: 98,
  }
}

// --- Weight tuning builders ---

export function buildAgentWeightsComparisons(): AgentWeightsComparison[] {
  return [
    { agent_name: 'trend', manual_weight: 0.20, auto_weight: 0.22, brier_score: 0.15, sample_size: 45 },
    { agent_name: 'volatility', manual_weight: 0.15, auto_weight: 0.18, brier_score: 0.20, sample_size: 38 },
    { agent_name: 'risk', manual_weight: 0.15, auto_weight: 0.12, brier_score: 0.25, sample_size: 42 },
    { agent_name: 'flow', manual_weight: 0.10, auto_weight: 0.14, brier_score: 0.22, sample_size: 30 },
    { agent_name: 'fundamental', manual_weight: 0.10, auto_weight: 0.08, brier_score: 0.28, sample_size: 25 },
  ]
}

export function buildWeightHistory(): WeightSnapshot[] {
  const weights = buildAgentWeightsComparisons()
  return [
    { computed_at: '2026-03-01T00:00:00Z', window_days: 90, weights },
    { computed_at: '2026-02-15T00:00:00Z', window_days: 90, weights },
    { computed_at: '2026-02-01T00:00:00Z', window_days: 90, weights },
  ]
}

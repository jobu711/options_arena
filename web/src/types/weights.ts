/** TypeScript interfaces matching Python weight-tuning models (models/analytics.py). */

/** Manual vs auto-tuned weight comparison for a single agent. */
export interface AgentWeight {
  agent_name: string
  manual_weight: number
  auto_weight: number
  /** Brier score [0.0, 1.0] (lower = better), null if < 10 samples. */
  brier_score: number | null
  sample_size: number
}

/** A point-in-time snapshot of auto-tuned agent weights. */
export interface WeightSnapshot {
  /** UTC timestamp (ISO 8601) when these weights were computed. */
  computed_at: string
  /** Lookback window in calendar days. */
  window_days: number
  /** Per-agent weight comparisons. */
  weights: AgentWeight[]
}

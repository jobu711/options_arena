/** Recommendation types for the trading desk pipeline. */

/** Pipeline processing stage for a single ticker. */
export type PipelineStage = 'queued' | 'scored' | 'analyzing' | 'ready' | 'failed'

/** Direction type — uppercase to match pipeline protocol. */
export type Direction = 'BULLISH' | 'BEARISH' | 'NEUTRAL'

/** Ticker state within the pipeline. */
export interface PipelineTicker {
  ticker: string
  stage: PipelineStage
  composite_score: number
  direction: Direction
  direction_confidence: number | null
  sector: string | null
  company_name: string | null
  recommendation_id: number | null
  error: string | null
}

/** Desk assessment summary from a single analysis desk. */
export interface DeskAssessment {
  desk: string
  direction: Direction
  confidence: number
  summary: string
  key_findings: string[]
}

/** Position recommendation — all price fields are strings (Decimal precision). */
export interface PositionRecommendation {
  ticker: string
  direction: Direction
  confidence: number
  recommended_contract: string
  entry_price: string
  entry_criteria: string
  exit_criteria: string
  stop_loss: string | null
  take_profit: string | null
  position_size_pct: number
  position_rationale: string
  risk_reward_ratio: number
  max_loss_estimate: string
  recommended_strategy: string | null
  strategy_rationale: string
  summary: string
  key_factors: string[]
  risk_assessment: string
  agent_agreement_score: number | null
  dissenting_desks: string[]
  model_used: string
}

/** Full recommendation detail from GET /api/debate/{id}. */
export interface RecommendationDetail {
  id: number
  ticker: string
  assessments: DeskAssessment[]
  recommendation: PositionRecommendation
  is_fallback: boolean
  recommendation_protocol: string
  duration_ms: number
  total_tokens: number
  citation_density: number
  model_used: string
  created_at: string
  scan_run_id: number | null
}

/** Lightweight debate summary from GET /api/debate. */
export interface DebateResultSummary {
  id: number
  ticker: string
  direction: Direction
  confidence: number
  is_fallback: boolean
  model_name: string
  duration_ms: number
  created_at: string
}

/** Per-source prediction accuracy statistics. */
export interface PredictionAccuracy {
  source: string
  total: number
  correct: number
  accuracy: number
  sample_sufficient: boolean
}

/** Accuracy within a condition bucket (e.g. "adx_strong", "iv_rank_low"). */
export interface ConditionBucketAccuracy {
  source: string
  condition: string
  total: number
  correct: number
  accuracy: number
}

/** Learned optimal contract parameters from historical analysis. */
export interface ContractGuidance {
  optimal_delta_low: number
  optimal_delta_high: number
  optimal_dte_low: number
  optimal_dte_high: number
  delta_win_rate: number
  dte_win_rate: number
  sample_count: number
}

/** Full attribution report aggregating accuracy and contract guidance. */
export interface AttributionReport {
  window_days: number
  total_recommendations: number
  total_outcomes: number
  source_accuracy: PredictionAccuracy[]
  condition_accuracy: ConditionBucketAccuracy[]
  contract_guidance: ContractGuidance | null
}

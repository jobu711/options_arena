/** Debate summary for list endpoint. */
export interface DebateResultSummary {
  id: number
  ticker: string
  direction: string
  confidence: number
  is_fallback: boolean
  model_name: string
  duration_ms: number
  created_at: string
}

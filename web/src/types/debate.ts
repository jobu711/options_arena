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

/** Single agent's structured response. */
export interface AgentResponse {
  agent_name: string
  direction: 'bullish' | 'bearish' | 'neutral'
  confidence: number
  argument: string
  key_points: string[]
  risks_cited: string[]
  contracts_referenced: string[]
  model_used: string
}

/** Final trade recommendation from risk agent. */
export interface TradeThesis {
  ticker: string
  direction: 'bullish' | 'bearish' | 'neutral'
  confidence: number
  summary: string
  bull_score: number
  bear_score: number
  key_factors: string[]
  risk_assessment: string
  recommended_strategy: string | null
}

/** Full debate result from GET /api/debate/{id}. */
export interface DebateResult {
  id: number
  ticker: string
  is_fallback: boolean
  model_name: string
  duration_ms: number
  total_tokens: number
  created_at: string
  debate_mode: string | null
  citation_density: number | null
  bull_response?: AgentResponse
  bear_response?: AgentResponse
  thesis?: TradeThesis
  vol_response?: string // Raw JSON string (parsed on demand)
  bull_rebuttal?: string // Raw JSON string (parsed on demand)
}

/** Agent progress entry for the debate progress modal. */
export interface AgentProgressEntry {
  name: string
  status: 'pending' | 'started' | 'completed' | 'failed'
  confidence: number | null
}

/** Single point in a debate confidence trend. */
export interface DebateTrendPoint {
  ticker: string
  direction: 'bullish' | 'bearish' | 'neutral'
  confidence: number
  is_fallback: boolean
  created_at: string
}

/** Response from GET /api/debate/trend/{ticker}. */
export interface DebateTrendResponse {
  ticker: string
  points: DebateTrendPoint[]
}

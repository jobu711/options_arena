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

  // Consensus fields
  contrarian_dissent?: string | null
  agent_agreement_score?: number | null
  dissenting_agents?: string[]
  agents_completed?: number | null
  // Scan linkage
  scan_run_id?: number | null

  // Agent structured outputs (6-agent protocol)
  flow_response?: FlowThesis | null
  fundamental_response?: FundamentalThesis | null
  risk_response?: RiskAssessmentThesis | null
  contrarian_response?: ContrarianThesis | null

  // OpenBB enrichment (optional, from MarketContext)
  pe_ratio?: number | null
  forward_pe?: number | null
  peg_ratio?: number | null
  price_to_book?: number | null
  debt_to_equity?: number | null
  revenue_growth?: number | null
  profit_margin?: number | null
  net_call_premium?: number | null
  net_put_premium?: number | null
  news_sentiment_score?: number | null
  news_sentiment_label?: string | null
  enrichment_ratio?: number | null
}

/** V2 flow agent structured response. */
export interface FlowThesis {
  direction: string
  confidence: number
  gex_interpretation: string
  smart_money_signal: string
  oi_analysis: string
  volume_confirmation: string
  key_flow_factors: string[]
  model_used: string
}

/** V2 fundamental agent structured response. */
export interface FundamentalThesis {
  direction: string
  confidence: number
  catalyst_impact: string
  earnings_assessment: string
  iv_crush_risk: string
  short_interest_analysis: string | null
  dividend_impact: string | null
  key_fundamental_factors: string[]
  model_used: string
}

/** V2 risk assessment agent structured response. */
export interface RiskAssessmentThesis {
  risk_level: string
  confidence: number
  pop_estimate: number | null
  max_loss_estimate: string
  charm_decay_warning: string | null
  spread_quality_assessment: string | null
  key_risks: string[]
  risk_mitigants: string[]
  recommended_position_size: string | null
  model_used: string
}

/** V2 contrarian agent structured response. */
export interface ContrarianThesis {
  dissent_direction: string
  dissent_confidence: number
  primary_challenge: string
  overlooked_risks: string[]
  consensus_weakness: string
  alternative_scenario: string
  model_used: string
}

/** Agent progress entry for the debate progress modal. */
export interface AgentProgressEntry {
  name: string
  status: 'pending' | 'started' | 'completed' | 'failed'
  confidence: number | null
}

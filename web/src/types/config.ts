/** Routing configuration from GET /api/config. */
export interface RoutingConfig {
  enable_model_routing: boolean
  complexity_threshold_fast: number
  complexity_threshold_premium: number
  fast_model: string
  premium_model: string
  cost_per_million_tokens: Record<string, number>
  is_override: boolean
}

/** Per-desk cost breakdown. */
export interface DeskCostDetail {
  desk: string
  tier: string
  model_used: string
  input_tokens: number
  output_tokens: number
  duration_ms: number
  status: string
}

/** Recommendation cost summary with per-desk details. */
export interface RecommendationCostDetail {
  ticker: string
  created_at: string
  duration_ms: number
  total_tokens: number
  is_fallback: boolean
  desk_details: DeskCostDetail[]
}

/** Read-only safe config values from GET /api/config. */
export interface ConfigResponse {
  groq_api_key_set: boolean
  scan_preset_default: string
  agent_timeout: number
  recommendation_protocol: string
  routing: RoutingConfig | null
}

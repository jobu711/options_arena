/** Read-only safe config values from GET /api/config. */
export interface ConfigResponse {
  groq_api_key_set: boolean
  scan_preset_default: string
  enable_rebuttal: boolean
  enable_volatility_agent: boolean
  agent_timeout: number
}

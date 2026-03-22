/** Read-only safe config values from GET /api/config. */
export interface ConfigResponse {
  groq_api_key_set: boolean
  scan_preset_default: string
  agent_timeout: number
  recommendation_protocol: string
}

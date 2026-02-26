/** Health check result for an external service. */
export interface HealthStatus {
  service_name: string
  available: boolean
  latency_ms: number | null
  error: string | null
  checked_at: string // ISO 8601
}

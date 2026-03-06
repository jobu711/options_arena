import type { HealthStatus } from '../../../src/types'

export function buildHealthStatus(overrides: Partial<HealthStatus> = {}): HealthStatus {
  return {
    service_name: 'Yahoo Finance',
    available: true,
    latency_ms: 120,
    error: null,
    checked_at: '2026-02-26T14:00:00+00:00',
    ...overrides,
  }
}

export function buildAllHealthy(): HealthStatus[] {
  return [
    buildHealthStatus({ service_name: 'Yahoo Finance', latency_ms: 120 }),
    buildHealthStatus({ service_name: 'FRED', latency_ms: 85 }),
    buildHealthStatus({ service_name: 'CBOE', latency_ms: 200 }),
    buildHealthStatus({ service_name: 'Groq', latency_ms: 350 }),
  ]
}

export function buildOneDegraded(degradedService: string): HealthStatus[] {
  return buildAllHealthy().map(h =>
    h.service_name === degradedService
      ? { ...h, available: false, latency_ms: null, error: `${degradedService} is unreachable` }
      : h,
  )
}

export function buildAllDown(): HealthStatus[] {
  return buildAllHealthy().map(h => ({
    ...h,
    available: false,
    latency_ms: null,
    error: `${h.service_name} connection refused`,
  }))
}

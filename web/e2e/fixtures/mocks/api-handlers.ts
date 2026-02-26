/**
 * Reusable API mock handlers for Playwright route interception.
 *
 * Usage:
 *   await mockAllApis(page, { scanList: [buildScanRun()] })
 */

import type { Page } from '@playwright/test'
import type { ScanRun, PaginatedResponse, TickerScore } from '../../../src/types'
import type { HealthStatus } from '../../../src/types'
import { buildAllHealthy } from '../builders/health.builders'

export interface MockOverrides {
  healthServices?: HealthStatus[]
  config?: Record<string, unknown>
  universe?: { optionable_count: number; sp500_count: number }
  scanList?: ScanRun[]
  scanScores?: PaginatedResponse<TickerScore>
}

const DEFAULT_CONFIG = {
  groq_api_key_set: true,
  scan_preset_default: 'sp500',
  enable_rebuttal: false,
  enable_volatility_agent: false,
  agent_timeout: 60.0,
}

const DEFAULT_UNIVERSE = {
  optionable_count: 5286,
  sp500_count: 503,
}

/** Register all default API mock handlers for a page. */
export async function mockAllApis(
  page: Page,
  overrides: MockOverrides = {},
): Promise<void> {
  // Health — liveness
  await page.route('**/api/health', async route => {
    if (route.request().url().endsWith('/api/health')) {
      return route.fulfill({ json: { status: 'ok' } })
    }
    return route.continue()
  })

  // Health — services
  await page.route('**/api/health/services', route =>
    route.fulfill({ json: overrides.healthServices ?? buildAllHealthy() }),
  )

  // Config
  await page.route('**/api/config', route =>
    route.fulfill({ json: overrides.config ?? DEFAULT_CONFIG }),
  )

  // Universe
  await page.route('**/api/universe', async route => {
    if (route.request().method() === 'POST') {
      return route.fulfill({ json: overrides.universe ?? DEFAULT_UNIVERSE })
    }
    return route.fulfill({ json: overrides.universe ?? DEFAULT_UNIVERSE })
  })

  // Scan list (GET /api/scan)
  if (overrides.scanList !== undefined) {
    await page.route('**/api/scan', async route => {
      if (route.request().method() === 'GET') {
        return route.fulfill({ json: overrides.scanList })
      }
      return route.continue()
    })
  }

  // Scan scores (GET /api/scan/:id/scores)
  if (overrides.scanScores !== undefined) {
    await page.route('**/api/scan/*/scores*', route =>
      route.fulfill({ json: overrides.scanScores }),
    )
  }
}

/** Mock a specific POST endpoint to return a fixed response. */
export async function mockPost(
  page: Page,
  pathPattern: string,
  status: number,
  body: unknown,
): Promise<void> {
  await page.route(pathPattern, async route => {
    if (route.request().method() === 'POST') {
      return route.fulfill({ status, json: body })
    }
    return route.continue()
  })
}

/** Mock a specific GET endpoint to return a fixed response. */
export async function mockGet(
  page: Page,
  pathPattern: string,
  body: unknown,
  status: number = 200,
): Promise<void> {
  await page.route(pathPattern, route =>
    route.fulfill({ status, json: body }),
  )
}

/** Mock an endpoint to simulate a timeout (delay then abort). */
export async function mockTimeout(
  page: Page,
  pathPattern: string,
  delayMs: number = 30_000,
): Promise<void> {
  await page.route(pathPattern, async route => {
    await new Promise(resolve => setTimeout(resolve, delayMs))
    return route.abort('timedout')
  })
}

/** Mock an endpoint to return a server error. */
export async function mockServerError(
  page: Page,
  pathPattern: string,
  detail: string = 'Internal server error',
): Promise<void> {
  await page.route(pathPattern, route =>
    route.fulfill({ status: 500, json: { detail } }),
  )
}

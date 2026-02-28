/**
 * E2E tests: Scan delta view — compare dropdown, delta chips, NEW badges.
 */

import { test, expect } from '../../fixtures/base.fixture'
import { ScanResultsPage } from '../../fixtures/pages/scan-results.page'
import { mockAllApis, mockGet } from '../../fixtures/mocks/api-handlers'
import {
  buildScanRun,
  buildPaginatedScores,
  buildTickerScore,
} from '../../fixtures/builders/scan.builders'
import type { ScanDiff, TickerDelta } from '../../../src/types'

const SCAN_ID = 2
const BASE_SCAN_ID = 1

function buildTickerDelta(overrides: Partial<TickerDelta> = {}): TickerDelta {
  return {
    ticker: 'AAPL',
    current_score: 85.0,
    previous_score: 78.0,
    score_change: 7.0,
    current_direction: 'bullish',
    previous_direction: 'bullish',
    is_new: false,
    ...overrides,
  }
}

function buildScanDiff(overrides: Partial<ScanDiff> = {}): ScanDiff {
  return {
    current_scan_id: SCAN_ID,
    base_scan_id: BASE_SCAN_ID,
    added: ['NVDA'],
    removed: ['GE'],
    movers: [
      buildTickerDelta({ ticker: 'NVDA', current_score: 90.0, previous_score: 0.0, score_change: 90.0, is_new: true }),
      buildTickerDelta({ ticker: 'AAPL', score_change: 7.0 }),
      buildTickerDelta({ ticker: 'MSFT', current_score: 72.0, previous_score: 80.0, score_change: -8.0 }),
    ],
    ...overrides,
  }
}

test.describe('Scan Delta View', () => {
  test.beforeEach(async ({ page }) => {
    await mockAllApis(page)

    // Scan list for compare dropdown
    await mockGet(page, '**/api/scan?*', [
      buildScanRun({ id: SCAN_ID }),
      buildScanRun({ id: BASE_SCAN_ID }),
    ])

    // Scan metadata
    await mockGet(page, `**/api/scan/${SCAN_ID}`, buildScanRun({ id: SCAN_ID }))

    // Default scores — include AAPL, MSFT, NVDA
    await page.route(`**/api/scan/${SCAN_ID}/scores*`, route =>
      route.fulfill({
        json: buildPaginatedScores(50),
      }),
    )
  })

  test('shows compare dropdown and fetches diff on selection', async ({ page }) => {
    // Mock the diff endpoint
    await page.route(`**/api/scan/${SCAN_ID}/diff*`, route =>
      route.fulfill({ json: buildScanDiff() }),
    )

    const resultsPage = new ScanResultsPage(page)
    await resultsPage.goto(SCAN_ID)

    // Compare dropdown should exist
    const compareSelect = page.locator('[data-testid="compare-select"]')
    await expect(compareSelect).toBeVisible()

    // Select a comparison scan
    await compareSelect.click()
    const option = page.getByRole('option', { name: new RegExp(`Scan #${BASE_SCAN_ID}`) })
      .or(page.locator(`li:has-text("Scan #${BASE_SCAN_ID}")`))
    await option.waitFor({ state: 'visible' })
    await option.click()

    // Top movers panel should appear
    await expect(page.locator('[data-testid="top-movers-panel"]')).toBeVisible({ timeout: 5000 })
  })

  test('renders delta chips next to scores when comparison active', async ({ page }) => {
    // Mock the diff endpoint
    await page.route(`**/api/scan/${SCAN_ID}/diff*`, route =>
      route.fulfill({ json: buildScanDiff() }),
    )

    // Navigate with compare param in URL (to auto-load diff)
    await page.goto(`/scan/${SCAN_ID}?compare=${BASE_SCAN_ID}`)
    await page.locator('.p-datatable').waitFor({ state: 'visible' })

    // Wait for diff to load and delta chips to render
    await expect(page.locator('[data-testid="delta-chip"]').first()).toBeVisible({ timeout: 5000 })

    // Should have delta chips in the score column
    const deltaChips = page.locator('[data-testid="delta-chip"]')
    expect(await deltaChips.count()).toBeGreaterThan(0)
  })

  test('renders NEW badge for added tickers', async ({ page }) => {
    // Ensure NVDA is in the scores AND in the diff added list
    const scores = buildPaginatedScores(50)
    // Make sure NVDA is in the scores list
    const hasNvda = scores.items.some(s => s.ticker === 'NVDA')
    if (!hasNvda) {
      scores.items.push(buildTickerScore({ ticker: 'NVDA', composite_score: 90.0 }))
      scores.total = scores.items.length
    }

    await page.route(`**/api/scan/${SCAN_ID}/scores*`, route =>
      route.fulfill({ json: scores }),
    )

    await page.route(`**/api/scan/${SCAN_ID}/diff*`, route =>
      route.fulfill({ json: buildScanDiff({ added: ['NVDA'] }) }),
    )

    // Navigate with compare param to auto-load diff
    await page.goto(`/scan/${SCAN_ID}?compare=${BASE_SCAN_ID}`)
    await page.locator('.p-datatable').waitFor({ state: 'visible' })

    // Wait for diff to load
    await page.waitForTimeout(1000)

    // Find NVDA row and check for NEW badge
    const newBadges = page.locator('[data-testid="new-badge"]')
    expect(await newBadges.count()).toBeGreaterThan(0)
  })
})

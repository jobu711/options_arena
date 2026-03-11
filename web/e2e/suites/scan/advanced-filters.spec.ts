/**
 * E2E tests: Advanced filter controls in PreScanFilters.
 *
 * Covers: advanced panel toggle, confidence filter, custom tickers,
 * top_n, min_dollar_volume, max_spread_pct, delta ranges, and payload conversion.
 */

import { test, expect } from '../../fixtures/base.fixture'
import { ScanPage } from '../../fixtures/pages/scan.page'
import { mockAllApis, pathMatcher } from '../../fixtures/mocks/api-handlers'
import { buildScanRun } from '../../fixtures/builders/scan.builders'
import type { Page } from '@playwright/test'

const SCAN_ID = 77

const PRESET_INFO = [
  { preset: 'sp500', label: 'S&P 500', description: 'Large-cap U.S. equities', estimated_count: 503 },
  { preset: 'full', label: 'Full Universe', description: 'All CBOE optionable tickers', estimated_count: 5286 },
  { preset: 'etfs', label: 'ETFs', description: 'Exchange-traded funds', estimated_count: 412 },
  { preset: 'nasdaq100', label: 'NASDAQ 100', description: 'Top NASDAQ-listed companies', estimated_count: 103 },
  { preset: 'russell2000', label: 'Russell 2000', description: 'Small-cap U.S. equities', estimated_count: 2010 },
  { preset: 'most_active', label: 'Most Active', description: 'Highest options volume today', estimated_count: 250 },
]

async function setupMocks(page: Page): Promise<void> {
  await mockAllApis(page, {
    scanList: [buildScanRun({ id: SCAN_ID - 1, preset: 'sp500' })],
  })
  await page.route(pathMatcher('/api/universe/preset-info'), route =>
    route.fulfill({ json: PRESET_INFO }),
  )
  await page.route(pathMatcher('/api/universe/sectors'), route =>
    route.fulfill({ json: [] }),
  )
}

/** Capture the POST /api/scan body and return it after scan is started. */
function setupPostCapture(page: Page): { getBody: () => Record<string, unknown> | null } {
  let capturedBody: Record<string, unknown> | null = null
  void page.route(pathMatcher('/api/scan'), async route => {
    if (route.request().method() === 'POST') {
      capturedBody = route.request().postDataJSON() as Record<string, unknown>
      return route.fulfill({ status: 202, json: { scan_id: SCAN_ID } })
    }
    return route.continue()
  })
  return { getBody: () => capturedBody }
}

test.describe('Advanced Filters', () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page)
  })

  test('advanced panel is collapsed by default', async ({ page }) => {
    const scanPage = new ScanPage(page)
    await scanPage.goto()

    // Panel header should be visible
    await expect(scanPage.advancedPanel).toBeVisible()
    // Panel content (inputs) should not be visible by default
    const content = scanPage.advancedPanel.locator('.p-panel-content')
    await expect(content).toBeHidden()
  })

  test('expanding advanced panel reveals controls', async ({ page }) => {
    const scanPage = new ScanPage(page)
    await scanPage.goto()

    await scanPage.expandAdvancedPanel()

    // Controls should now be visible
    await expect(page.locator('[data-testid="top-n-filter"]')).toBeVisible()
    await expect(page.locator('[data-testid="min-dollar-vol-filter"]')).toBeVisible()
    await expect(page.locator('[data-testid="min-oi-filter"]')).toBeVisible()
    await expect(page.locator('[data-testid="min-vol-filter"]')).toBeVisible()
    await expect(page.locator('[data-testid="max-spread-filter"]')).toBeVisible()
    await expect(page.locator('[data-testid="delta-primary-min-filter"]')).toBeVisible()
    await expect(page.locator('[data-testid="delta-primary-max-filter"]')).toBeVisible()
    await expect(page.locator('[data-testid="delta-fallback-min-filter"]')).toBeVisible()
    await expect(page.locator('[data-testid="delta-fallback-max-filter"]')).toBeVisible()
  })

  test('top_n sends correct value in payload', async ({ page }) => {
    const capture = setupPostCapture(page)
    const scanPage = new ScanPage(page)
    await scanPage.goto()

    await scanPage.expandAdvancedPanel()
    const input = page.locator('[data-testid="top-n-filter"] input')
    await input.click()
    await input.fill('25')
    await input.press('Tab')

    await scanPage.startScan()

    expect(capture.getBody()).not.toBeNull()
    expect(capture.getBody()!.top_n).toBe(25)
  })

  test('min_dollar_volume converts millions to raw in payload', async ({ page }) => {
    const capture = setupPostCapture(page)
    const scanPage = new ScanPage(page)
    await scanPage.goto()

    await scanPage.expandAdvancedPanel()
    const input = page.locator('[data-testid="min-dollar-vol-filter"] input')
    await input.click()
    await input.fill('5')
    await input.press('Tab')

    await scanPage.startScan()

    expect(capture.getBody()).not.toBeNull()
    expect(capture.getBody()!.min_dollar_volume).toBe(5_000_000)
  })

  test('max_spread_pct converts percentage to decimal in payload', async ({ page }) => {
    const capture = setupPostCapture(page)
    const scanPage = new ScanPage(page)
    await scanPage.goto()

    await scanPage.expandAdvancedPanel()
    const input = page.locator('[data-testid="max-spread-filter"] input')
    await input.click()
    await input.fill('15')
    await input.press('Tab')

    await scanPage.startScan()

    expect(capture.getBody()).not.toBeNull()
    expect(capture.getBody()!.max_spread_pct).toBe(0.15)
  })

  test('delta primary range sends both min and max', async ({ page }) => {
    const capture = setupPostCapture(page)
    const scanPage = new ScanPage(page)
    await scanPage.goto()

    await scanPage.expandAdvancedPanel()

    const minInput = page.locator('[data-testid="delta-primary-min-filter"] input')
    await minInput.click()
    await minInput.fill('0.25')
    await minInput.press('Tab')

    const maxInput = page.locator('[data-testid="delta-primary-max-filter"] input')
    await maxInput.click()
    await maxInput.fill('0.45')
    await maxInput.press('Tab')

    await scanPage.startScan()

    expect(capture.getBody()).not.toBeNull()
    expect(capture.getBody()!.delta_primary_min).toBe(0.25)
    expect(capture.getBody()!.delta_primary_max).toBe(0.45)
  })

  test('min_direction_confidence converts percentage to decimal', async ({ page }) => {
    const capture = setupPostCapture(page)
    const scanPage = new ScanPage(page)
    await scanPage.goto()

    // Confidence is in the Strategy section (always visible)
    const input = page.locator('[data-testid="confidence-filter"] input')
    await input.click()
    await input.fill('60')
    await input.press('Tab')

    await scanPage.startScan()

    expect(capture.getBody()).not.toBeNull()
    expect(capture.getBody()!.min_direction_confidence).toBe(0.6)
  })

  test('existing basic filters remain visible', async ({ page }) => {
    const scanPage = new ScanPage(page)
    await scanPage.goto()

    // Basic filters should be visible without any panel expansion
    await expect(page.locator('[data-testid="preset-selector"]')).toBeVisible()
    await expect(page.locator('[data-testid="market-cap-filter"]')).toBeVisible()
    await expect(page.locator('[data-testid="direction-filter"]')).toBeVisible()
    await expect(page.locator('[data-testid="earnings-filter"]')).toBeVisible()
    await expect(page.locator('[data-testid="iv-rank-filter"]')).toBeVisible()
    await expect(page.locator('[data-testid="min-score-filter"]')).toBeVisible()
    await expect(page.locator('[data-testid="confidence-filter"]')).toBeVisible()
    await expect(page.locator('[data-testid="min-price-filter"]')).toBeVisible()
    await expect(page.locator('[data-testid="max-price-filter"]')).toBeVisible()
    await expect(page.locator('[data-testid="min-dte-filter"]')).toBeVisible()
    await expect(page.locator('[data-testid="max-dte-filter"]')).toBeVisible()
  })
})

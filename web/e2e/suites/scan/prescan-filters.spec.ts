/**
 * E2E tests: PreScanFilters component interactions.
 *
 * Covers: preset selection with ticker counts, price range controls,
 * DTE range controls, and collapsible panel state preservation.
 */

import { test, expect } from '../../fixtures/base.fixture'
import { ScanPage } from '../../fixtures/pages/scan.page'
import { mockAllApis, mockPost, pathMatcher } from '../../fixtures/mocks/api-handlers'
import { buildScanRun } from '../../fixtures/builders/scan.builders'
import type { Page } from '@playwright/test'

/** Preset info response matching backend PresetInfoResponse schema. */
const PRESET_INFO = [
  { preset: 'sp500', label: 'S&P 500', description: 'Large-cap U.S. equities', estimated_count: 503 },
  { preset: 'full', label: 'Full Universe', description: 'All CBOE optionable tickers', estimated_count: 5286 },
  { preset: 'etfs', label: 'ETFs', description: 'Exchange-traded funds', estimated_count: 412 },
  { preset: 'nasdaq100', label: 'NASDAQ 100', description: 'Top NASDAQ-listed companies', estimated_count: 103 },
  { preset: 'russell2000', label: 'Russell 2000', description: 'Small-cap U.S. equities', estimated_count: 2010 },
  { preset: 'most_active', label: 'Most Active', description: 'Highest options volume today', estimated_count: 250 },
]

const SCAN_ID = 55

/** Set up all default mocks including preset-info, sectors, and themes. */
async function setupMocks(page: Page): Promise<void> {
  await mockAllApis(page, {
    scanList: [buildScanRun({ id: SCAN_ID - 1, preset: 'sp500' })],
  })

  // Preset info endpoint
  await page.route(pathMatcher('/api/universe/preset-info'), route =>
    route.fulfill({ json: PRESET_INFO }),
  )

  // Sectors endpoint (empty for simplicity — tests focus on filters, not sector tree)
  await page.route(pathMatcher('/api/universe/sectors'), route =>
    route.fulfill({ json: [] }),
  )

  // Themes endpoint
  await page.route(pathMatcher('/api/universe/themes'), route =>
    route.fulfill({ json: [] }),
  )
}

test.describe('PreScanFilters', () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page)
  })

  test('preset selection shows ticker count badge', async ({ page }) => {
    const scanPage = new ScanPage(page)
    await scanPage.goto()

    // The default preset is S&P 500 — badge should show 503 once preset-info loads
    const presetSelector = page.locator('[data-testid="preset-selector"]')
    await expect(presetSelector).toBeVisible()

    // Wait for preset-info API to populate counts, then verify the count badge appears
    // The badge is inside the selected value template of the Select component
    const countBadge = presetSelector.locator('.p-badge').or(presetSelector.locator('[class*="badge"]'))
    await expect(countBadge).toBeVisible({ timeout: 5_000 })
    await expect(countBadge).toContainText('503')

    // Open the dropdown and select NASDAQ 100
    await presetSelector.click()
    const nasdaq100Option = page.locator('.p-select-list .p-select-option, .p-select-overlay li, .p-select-option')
      .filter({ hasText: 'NASDAQ 100' })
    await nasdaq100Option.click()

    // After selection, the displayed count should update to 103
    await expect(countBadge).toContainText('103')
  })

  test('price range controls send values in scan request payload', async ({ page }) => {
    // Capture the POST /api/scan request payload
    let capturedBody: Record<string, unknown> | null = null
    await mockPost(page, pathMatcher('/api/scan'), 202, { scan_id: SCAN_ID })
    // Override the POST handler to capture the body
    await page.route(pathMatcher('/api/scan'), async route => {
      if (route.request().method() === 'POST') {
        capturedBody = route.request().postDataJSON() as Record<string, unknown>
        return route.fulfill({ status: 202, json: { scan_id: SCAN_ID } })
      }
      return route.continue()
    })

    const scanPage = new ScanPage(page)
    await scanPage.goto()

    // Expand the "Price & Expiry" panel (it is collapsed by default)
    const pricePanel = page.locator('.p-panel').filter({ hasText: 'Price & Expiry' })
    const priceToggler = pricePanel.locator('button[data-pc-section="toggler"], .p-panel-header button, [data-pc-section="header"] button').first()
    await priceToggler.click()

    // Set min price to 50
    const minPriceInput = page.locator('[data-testid="min-price-filter"] input')
    await minPriceInput.click()
    await minPriceInput.fill('50')
    // Tab away to trigger change
    await minPriceInput.press('Tab')

    // Set max price to 200
    const maxPriceInput = page.locator('[data-testid="max-price-filter"] input')
    await maxPriceInput.click()
    await maxPriceInput.fill('200')
    await maxPriceInput.press('Tab')

    // Click Run Scan
    await scanPage.startScan()

    // Verify captured payload contains price filters
    expect(capturedBody).not.toBeNull()
    expect(capturedBody!.min_price).toBe(50)
    expect(capturedBody!.max_price).toBe(200)
  })

  test('DTE range controls send values in scan request payload', async ({ page }) => {
    // Capture the POST /api/scan request payload
    let capturedBody: Record<string, unknown> | null = null
    await page.route(pathMatcher('/api/scan'), async route => {
      if (route.request().method() === 'POST') {
        capturedBody = route.request().postDataJSON() as Record<string, unknown>
        return route.fulfill({ status: 202, json: { scan_id: SCAN_ID } })
      }
      return route.continue()
    })

    const scanPage = new ScanPage(page)
    await scanPage.goto()

    // Expand the "Price & Expiry" panel (collapsed by default)
    const pricePanel = page.locator('.p-panel').filter({ hasText: 'Price & Expiry' })
    const priceToggler = pricePanel.locator('button[data-pc-section="toggler"], .p-panel-header button, [data-pc-section="header"] button').first()
    await priceToggler.click()

    // Set min DTE to 14
    const minDteInput = page.locator('[data-testid="min-dte-filter"] input')
    await minDteInput.click()
    await minDteInput.fill('14')
    await minDteInput.press('Tab')

    // Set max DTE to 90
    const maxDteInput = page.locator('[data-testid="max-dte-filter"] input')
    await maxDteInput.click()
    await maxDteInput.fill('90')
    await maxDteInput.press('Tab')

    // Click Run Scan
    await scanPage.startScan()

    // Verify captured payload contains DTE filters
    expect(capturedBody).not.toBeNull()
    expect(capturedBody!.min_dte).toBe(14)
    expect(capturedBody!.max_dte).toBe(90)
  })

  test('score filter accepts values 0-100 with step 5', async ({ page }) => {
    // Capture the POST /api/scan request payload
    let capturedBody: Record<string, unknown> | null = null
    await page.route(pathMatcher('/api/scan'), async route => {
      if (route.request().method() === 'POST') {
        capturedBody = route.request().postDataJSON() as Record<string, unknown>
        return route.fulfill({ status: 202, json: { scan_id: SCAN_ID } })
      }
      return route.continue()
    })

    const scanPage = new ScanPage(page)
    await scanPage.goto()

    // Expand the "Quality" or score-related panel
    const scorePanel = page.locator('.p-panel').filter({ hasText: /Quality|Score/ })
    const scoreToggler = scorePanel.locator('button[data-pc-section="toggler"], .p-panel-header button, [data-pc-section="header"] button').first()
    await scoreToggler.click()

    // Find the score filter input and set it to 75 (only possible if max >= 75)
    const scoreInput = page.locator('[data-testid="min-score-filter"] input')
    await scoreInput.click()
    await scoreInput.fill('75')
    await scoreInput.press('Tab')

    // Click Run Scan
    await scanPage.startScan()

    // Verify the value 75 was sent (impossible with old max=10)
    expect(capturedBody).not.toBeNull()
    expect(capturedBody!.min_score).toBe(75)
  })

  test('panel collapse preserves filter state', async ({ page }) => {
    const scanPage = new ScanPage(page)
    await scanPage.goto()

    // Expand the "Price & Expiry" panel
    const pricePanel = page.locator('.p-panel').filter({ hasText: 'Price & Expiry' })
    const priceToggler = pricePanel.locator('button[data-pc-section="toggler"], .p-panel-header button, [data-pc-section="header"] button').first()
    await priceToggler.click()

    // Set min price to 75
    const minPriceInput = page.locator('[data-testid="min-price-filter"] input')
    await minPriceInput.click()
    await minPriceInput.fill('75')
    await minPriceInput.press('Tab')

    // Set min DTE to 30
    const minDteInput = page.locator('[data-testid="min-dte-filter"] input')
    await minDteInput.click()
    await minDteInput.fill('30')
    await minDteInput.press('Tab')

    // The filter badge on the panel header should show active filter count
    const filterBadge = pricePanel.locator('.p-badge, [class*="filter-badge"]')
    await expect(filterBadge).toBeVisible()

    // Collapse the panel
    await priceToggler.click()

    // Verify inputs are hidden (panel content collapsed)
    await expect(minPriceInput).toBeHidden()

    // Re-expand the panel
    await priceToggler.click()

    // Verify values persisted after collapse/expand
    // Price input uses currency formatting ($75.00), DTE uses suffix (30 days)
    const minPriceAfter = page.locator('[data-testid="min-price-filter"] input')
    await expect(minPriceAfter).toBeVisible()
    await expect(minPriceAfter).toHaveValue(/75/)

    const minDteAfter = page.locator('[data-testid="min-dte-filter"] input')
    await expect(minDteAfter).toHaveValue(/30/)

    // Now start a scan and verify the values were still sent correctly
    let capturedBody: Record<string, unknown> | null = null
    await page.route(pathMatcher('/api/scan'), async route => {
      if (route.request().method() === 'POST') {
        capturedBody = route.request().postDataJSON() as Record<string, unknown>
        return route.fulfill({ status: 202, json: { scan_id: SCAN_ID } })
      }
      return route.continue()
    })

    await scanPage.startScan()

    expect(capturedBody).not.toBeNull()
    expect(capturedBody!.min_price).toBe(75)
    expect(capturedBody!.min_dte).toBe(30)
  })
})

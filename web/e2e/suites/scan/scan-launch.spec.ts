/**
 * E2E tests: Scan launch workflow.
 *
 * Covers: starting a scan, preset selection, progress tracking,
 * button disable during operation, and 409 conflict handling.
 */

import { test, expect } from '../../fixtures/base.fixture'
import { ScanPage } from '../../fixtures/pages/scan.page'
import { mockAllApis, mockPost, pathMatcher } from '../../fixtures/mocks/api-handlers'
import { buildScanRun } from '../../fixtures/builders/scan.builders'
import { scanProgressSequence, scanCancelSequence } from '../../fixtures/mocks/ws-scenarios'
import { injectFakeScanWebSocket } from '../../fixtures/mocks/ws-helpers'

const SCAN_ID = 42

test.describe('Scan Launch', () => {
  test.beforeEach(async ({ page }) => {
    // Default mocks: healthy services, one past scan
    await mockAllApis(page, {
      scanList: [buildScanRun({ id: SCAN_ID - 1, preset: 'sp500' })],
    })

    // POST /api/scan returns our test scan ID
    await mockPost(page, '**/api/scan', 202, { scan_id: SCAN_ID })
  })

  test('starts scan and shows progress through 4 phases', async ({ page }) => {
    // Inject fake WebSocket that doesn't connect to the real server.
    // Uses a plain object (NOT Object.create(WebSocket.prototype)) to avoid
    // inheriting accessor properties that prevent onmessage/onopen assignment.
    const wsEvents = scanProgressSequence(SCAN_ID)
    await injectFakeScanWebSocket(page, SCAN_ID, wsEvents)

    const scanPage = new ScanPage(page)
    await scanPage.goto()

    // Start scan
    await scanPage.startScan()

    // Progress indicator should become visible
    await scanPage.expectProgressVisible()

    // After all 11 events fire (~1.7s), progress hides and toast appears
    await scanPage.expectProgressHidden()

    // Success toast should appear
    const toast = page.locator('.p-toast-message')
    await expect(toast).toBeVisible({ timeout: 5_000 })
    await expect(toast).toContainText(/scan.*complete|finished/i)
  })

  test('disables start button while scan is in progress', async ({ page }) => {
    const scanPage = new ScanPage(page)
    await scanPage.goto()

    // Start scan
    await scanPage.startScan()

    // Button should become disabled
    await scanPage.expectStartButtonDisabled()
  })

  test('shows error toast when backend returns 409 conflict', async ({ page }) => {
    // Override POST /api/scan to return 409
    await page.route(pathMatcher('/api/scan'), async route => {
      if (route.request().method() === 'POST') {
        return route.fulfill({
          status: 409,
          json: { detail: 'Another scan is already in progress' },
        })
      }
      return route.continue()
    })

    const scanPage = new ScanPage(page)
    await scanPage.goto()
    await scanPage.startScan()

    // Toast should appear with conflict message
    const toast = page.locator('.p-toast-message')
      .or(page.locator('[data-testid="error-toast"]'))
    await expect(toast).toBeVisible({ timeout: 5_000 })
    await expect(toast).toContainText(/in progress|conflict|busy/i)
  })

  test('shows past scans in the scan list', async ({ page }) => {
    const pastScans = [
      buildScanRun({ id: 10, preset: 'sp500', tickers_scanned: 503 }),
      buildScanRun({ id: 9, preset: 'full', tickers_scanned: 5286 }),
      buildScanRun({ id: 8, preset: 'etfs', tickers_scanned: 150 }),
    ]
    await mockAllApis(page, { scanList: pastScans })

    const scanPage = new ScanPage(page)
    await scanPage.goto()

    // Should display 3 past scans
    const rowCount = await scanPage.getScanListRowCount()
    expect(rowCount).toBe(3)
  })

  test('cancel button stops a running scan', async ({ page }) => {
    // Mock DELETE /api/scan/current
    await page.route('**/api/scan/current', async route => {
      if (route.request().method() === 'DELETE') {
        return route.fulfill({ json: { status: 'cancelled' } })
      }
      return route.continue()
    })

    // Inject fake WebSocket (plain object, no real connection)
    const wsEvents = scanCancelSequence(SCAN_ID)
    await injectFakeScanWebSocket(page, SCAN_ID, wsEvents, { lastEventDelay: 2000 })

    const scanPage = new ScanPage(page)
    await scanPage.goto()

    await scanPage.startScan()
    await scanPage.expectProgressVisible()

    // Cancel
    await scanPage.cancelScan()

    // Progress should eventually hide
    await scanPage.expectProgressHidden()
  })
})

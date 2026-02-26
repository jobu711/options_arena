/**
 * E2E tests: Scan launch workflow.
 *
 * Covers: starting a scan, preset selection, progress tracking,
 * button disable during operation, and 409 conflict handling.
 */

import { test, expect } from '../../fixtures/base.fixture'
import { ScanPage } from '../../fixtures/pages/scan.page'
import { ScanResultsPage } from '../../fixtures/pages/scan-results.page'
import { mockAllApis, mockPost } from '../../fixtures/mocks/api-handlers'
import { buildScanRun, buildPaginatedScores } from '../../fixtures/builders/scan.builders'
import { scanProgressSequence, scanCancelSequence } from '../../fixtures/mocks/ws-scenarios'

const SCAN_ID = 42

test.describe('Scan Launch', () => {
  test.beforeEach(async ({ page }) => {
    // Default mocks: healthy services, one past scan
    await mockAllApis(page, {
      scanList: [buildScanRun({ id: SCAN_ID - 1, preset: 'sp500' })],
    })

    // POST /api/scan returns our test scan ID
    await mockPost(page, '**/api/scan', 202, { scan_id: SCAN_ID })

    // Scan metadata for results page
    await page.route(`**/api/scan/${SCAN_ID}`, route =>
      route.fulfill({ json: buildScanRun({ id: SCAN_ID, preset: 'sp500' }) }),
    )

    // Scan scores for results page
    await page.route(`**/api/scan/${SCAN_ID}/scores*`, route =>
      route.fulfill({ json: buildPaginatedScores(50) }),
    )
  })

  test('starts scan and shows progress through 4 phases', async ({ page }) => {
    const scanPage = new ScanPage(page)
    await scanPage.goto()

    // Intercept WebSocket to inject mock events
    const wsEvents = scanProgressSequence(SCAN_ID)
    await page.evaluate(
      ({ events, scanId }) => {
        const OrigWS = window.WebSocket
        window.WebSocket = class extends OrigWS {
          constructor(url: string | URL, protocols?: string | string[]) {
            super(url, protocols)
            const urlStr = typeof url === 'string' ? url : url.toString()
            if (urlStr.includes(`/ws/scan/${scanId}`)) {
              this.addEventListener('open', () => {
                let delay = 0
                for (const event of events) {
                  delay += 150
                  setTimeout(() => {
                    Object.defineProperty(
                      new MessageEvent('message', { data: JSON.stringify(event) }),
                      'target',
                      { value: this },
                    )
                    this.dispatchEvent(
                      new MessageEvent('message', { data: JSON.stringify(event) }),
                    )
                  }, delay)
                }
              })
            }
          }
        } as typeof WebSocket
      },
      { events: wsEvents, scanId: SCAN_ID },
    )

    // Start scan
    await scanPage.startScan()

    // Progress indicator should become visible
    await scanPage.expectProgressVisible()

    // After all events fire, page should navigate to results
    await page.waitForURL(`**/scan/${SCAN_ID}`, { timeout: 15_000 })

    // Results table should render
    const resultsPage = new ScanResultsPage(page)
    const rowCount = await resultsPage.getRowCount()
    expect(rowCount).toBeGreaterThan(0)
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
    await page.route('**/api/scan', async route => {
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
    const scanPage = new ScanPage(page)
    await scanPage.goto()

    // Mock DELETE /api/scan/current
    await page.route('**/api/scan/current', async route => {
      if (route.request().method() === 'DELETE') {
        return route.fulfill({ json: { status: 'cancelled' } })
      }
      return route.continue()
    })

    // Inject cancellation WS sequence
    const wsEvents = scanCancelSequence(SCAN_ID)
    await page.evaluate(
      ({ events, scanId }) => {
        const OrigWS = window.WebSocket
        window.WebSocket = class extends OrigWS {
          constructor(url: string | URL, protocols?: string | string[]) {
            super(url, protocols)
            const urlStr = typeof url === 'string' ? url : url.toString()
            if (urlStr.includes(`/ws/scan/${scanId}`)) {
              this.addEventListener('open', () => {
                let delay = 0
                for (const event of events) {
                  delay += 200
                  setTimeout(() => {
                    this.dispatchEvent(
                      new MessageEvent('message', { data: JSON.stringify(event) }),
                    )
                  }, delay)
                }
              })
            }
          }
        } as typeof WebSocket
      },
      { events: wsEvents, scanId: SCAN_ID },
    )

    await scanPage.startScan()
    await scanPage.expectProgressVisible()

    // Cancel
    await scanPage.cancelScan()

    // Progress should eventually hide
    await scanPage.expectProgressHidden()
  })
})

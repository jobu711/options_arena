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
    await page.addInitScript(
      ({ events, scanId }) => {
        const RealWS = window.WebSocket
        window.WebSocket = function (
          this: WebSocket,
          url: string | URL,
          protocols?: string | string[],
        ) {
          const urlStr = typeof url === 'string' ? url : url.toString()
          if (urlStr.includes(`/ws/scan/${scanId}`)) {
            // Plain object — own data properties for event handlers
            const fake: Record<string, unknown> = {
              readyState: 0,
              url: urlStr,
              protocol: '',
              extensions: '',
              bufferedAmount: 0,
              binaryType: 'blob',
              onopen: null,
              onmessage: null,
              onclose: null,
              onerror: null,
              CONNECTING: 0,
              OPEN: 1,
              CLOSING: 2,
              CLOSED: 3,
              send() {},
              close() { fake.readyState = 3 },
              addEventListener() {},
              removeEventListener() {},
              dispatchEvent() { return true },
            }
            // Simulate open + message events after a short delay
            setTimeout(() => {
              fake.readyState = 1
              if (typeof fake.onopen === 'function') {
                fake.onopen(new Event('open'))
              }
              let delay = 50
              for (const event of events) {
                delay += 150
                setTimeout(() => {
                  if (fake.readyState === 1 && typeof fake.onmessage === 'function') {
                    fake.onmessage(new MessageEvent('message', {
                      data: JSON.stringify(event),
                    }))
                  }
                }, delay)
              }
            }, 50)
            return fake as unknown as WebSocket
          }
          return new RealWS(url, protocols)
        } as unknown as typeof WebSocket
        Object.assign(window.WebSocket, {
          CONNECTING: 0,
          OPEN: 1,
          CLOSING: 2,
          CLOSED: 3,
        })
      },
      { events: wsEvents, scanId: SCAN_ID },
    )

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
    await page.addInitScript(
      ({ events, scanId }) => {
        const RealWS = window.WebSocket
        window.WebSocket = function (
          this: WebSocket,
          url: string | URL,
          protocols?: string | string[],
        ) {
          const urlStr = typeof url === 'string' ? url : url.toString()
          if (urlStr.includes(`/ws/scan/${scanId}`)) {
            const fake: Record<string, unknown> = {
              readyState: 0,
              url: urlStr,
              protocol: '',
              extensions: '',
              bufferedAmount: 0,
              binaryType: 'blob',
              onopen: null,
              onmessage: null,
              onclose: null,
              onerror: null,
              CONNECTING: 0,
              OPEN: 1,
              CLOSING: 2,
              CLOSED: 3,
              send() {},
              close() { fake.readyState = 3 },
              addEventListener() {},
              removeEventListener() {},
              dispatchEvent() { return true },
            }
            setTimeout(() => {
              fake.readyState = 1
              if (typeof fake.onopen === 'function') {
                fake.onopen(new Event('open'))
              }
              // Send progress events quickly, delay last event (complete/cancelled)
              let delay = 50
              for (let i = 0; i < events.length; i++) {
                const event = events[i]
                delay += i < events.length - 1 ? 150 : 2000
                setTimeout(() => {
                  if (fake.readyState === 1 && typeof fake.onmessage === 'function') {
                    fake.onmessage(new MessageEvent('message', {
                      data: JSON.stringify(event),
                    }))
                  }
                }, delay)
              }
            }, 50)
            return fake as unknown as WebSocket
          }
          return new RealWS(url, protocols)
        } as unknown as typeof WebSocket
        Object.assign(window.WebSocket, {
          CONNECTING: 0,
          OPEN: 1,
          CLOSING: 2,
          CLOSED: 3,
        })
      },
      { events: wsEvents, scanId: SCAN_ID },
    )

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

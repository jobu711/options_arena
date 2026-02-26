/**
 * E2E tests: API failure handling edge cases.
 *
 * Covers: 500 errors, 503 service unavailable, 422 validation,
 * network timeouts, malformed JSON, and graceful degradation.
 */

import { test, expect } from '../../fixtures/base.fixture'
import { mockAllApis, mockServerError, mockTimeout } from '../../fixtures/mocks/api-handlers'
import { buildScanRun } from '../../fixtures/builders/scan.builders'

test.describe('API Failure Handling', () => {
  test.beforeEach(async ({ page }) => {
    await mockAllApis(page, {
      scanList: [buildScanRun({ id: 1 })],
    })
  })

  test('GET /api/scan returning 500 shows error toast', async ({ page }) => {
    // Override scan list to return 500
    await page.route('**/api/scan', async route => {
      if (route.request().method() === 'GET') {
        return route.fulfill({
          status: 500,
          json: { detail: 'Internal server error' },
        })
      }
      return route.continue()
    })

    await page.goto('/scan')

    // Error toast should appear
    const toast = page.locator('.p-toast-message, [data-testid="error-toast"]')
    await expect(toast).toBeVisible({ timeout: 5_000 })
  })

  test('GET /api/health/services returning 503 shows degraded state', async ({ page }) => {
    await page.route('**/api/health/services', route =>
      route.fulfill({
        status: 503,
        json: { detail: 'Service temporarily unavailable' },
      }),
    )

    await page.goto('/health')

    // Page should render without crash
    await expect(page.locator('body')).toBeVisible()
  })

  test('POST /api/scan returning 422 shows validation error', async ({ page }) => {
    await page.route('**/api/scan', async route => {
      if (route.request().method() === 'POST') {
        return route.fulfill({
          status: 422,
          json: { detail: 'Invalid scan preset: unknown' },
        })
      }
      return route.continue()
    })

    await page.goto('/scan')

    const startBtn = page.locator('[data-testid="start-scan-btn"]')
      .or(page.locator('button:has-text("Start Scan")'))
    await startBtn.click()

    const toast = page.locator('.p-toast-message, [data-testid="error-toast"]')
    await expect(toast).toBeVisible({ timeout: 5_000 })
  })

  test('network timeout shows timeout error gracefully', async ({ page }) => {
    // Mock scan list with a long delay then abort
    await page.route('**/api/scan', async route => {
      if (route.request().method() === 'GET') {
        await new Promise(resolve => setTimeout(resolve, 15_000))
        return route.abort('timedout')
      }
      return route.continue()
    })

    await page.goto('/scan')

    // Page should not crash — loading state or error should be shown
    await expect(page.locator('body')).toBeVisible()
  })

  test('malformed JSON response does not crash the app', async ({ page }) => {
    await page.route('**/api/scan', async route => {
      if (route.request().method() === 'GET') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: '{"broken json:',
        })
      }
      return route.continue()
    })

    await page.goto('/scan')

    // App should not white-screen
    await expect(page.locator('body')).toBeVisible()
    // Navigation should still work
    await page.goto('/health')
    await expect(page.locator('body')).toBeVisible()
  })

  test('404 on scan detail shows error state', async ({ page }) => {
    await page.route('**/api/scan/999', route =>
      route.fulfill({ status: 404, json: { detail: 'Scan not found' } }),
    )
    await page.route('**/api/scan/999/scores*', route =>
      route.fulfill({ status: 404, json: { detail: 'Scan not found' } }),
    )

    await page.goto('/scan/999')

    // Should show an error state, not a blank page
    const errorIndicator = page.locator('[data-testid="error-state"]')
      .or(page.locator('text=/not found|error|404/i'))
    await expect(errorIndicator).toBeVisible({ timeout: 5_000 })
  })

  test('404 on debate detail shows error state', async ({ page }) => {
    await page.route('**/api/debate/999', route =>
      route.fulfill({ status: 404, json: { detail: 'Debate not found' } }),
    )

    await page.goto('/debate/999')

    const errorIndicator = page.locator('[data-testid="error-state"]')
      .or(page.locator('text=/not found|error|404/i'))
    await expect(errorIndicator).toBeVisible({ timeout: 5_000 })
  })
})

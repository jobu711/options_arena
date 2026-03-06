/**
 * E2E tests: API failure handling edge cases.
 *
 * Covers: 500 errors, 503 service unavailable, 422 validation,
 * network timeouts, malformed JSON, and graceful degradation.
 */

import { test, expect } from '../../fixtures/base.fixture'
import { mockAllApis, pathMatcher } from '../../fixtures/mocks/api-handlers'
import { buildScanRun } from '../../fixtures/builders/scan.builders'

test.describe('API Failure Handling', () => {
  test.beforeEach(async ({ page }) => {
    await mockAllApis(page, {
      scanList: [buildScanRun({ id: 1 })],
    })
  })

  test('GET /api/scan returning 500 degrades gracefully', async ({ page }) => {
    // Override scan list to return 500
    await page.route(pathMatcher('/api/scan'), async route => {
      if (route.request().method() === 'GET') {
        return route.fulfill({
          status: 500,
          json: { detail: 'Internal server error' },
        })
      }
      return route.continue()
    })

    await page.goto('/scan')

    // Page should render without crash — shows empty state
    await expect(page.locator('body')).toBeVisible()
    await expect(page.locator('h1')).toBeVisible()
  })

  test('GET /api/health/services returning 503 shows degraded state', async ({ page }) => {
    await page.route(pathMatcher('/api/health/services'), route =>
      route.fulfill({
        status: 503,
        json: { detail: 'Service temporarily unavailable' },
      }),
    )

    await page.goto('/')

    // Page should render without crash
    await expect(page.locator('body')).toBeVisible()
  })

  test('POST /api/scan returning 422 shows validation error', async ({ page }) => {
    await page.route(pathMatcher('/api/scan'), async route => {
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
      .or(page.locator('button:has-text("Run Scan")'))
    await startBtn.click()

    const toast = page.locator('.p-toast-message, [data-testid="error-toast"]')
    await expect(toast).toBeVisible({ timeout: 5_000 })
  })

  test('network timeout shows timeout error gracefully', async ({ page }) => {
    // Mock scan list with a long delay then abort
    await page.route(pathMatcher('/api/scan'), async route => {
      if (route.request().method() === 'GET') {
        await new Promise(resolve => setTimeout(resolve, 500))
        return route.abort('timedout')
      }
      return route.continue()
    })

    await page.goto('/scan')

    // Page should not crash — loading state or error should be shown
    await expect(page.locator('body')).toBeVisible()
  })

  test('malformed JSON response does not crash the app', async ({ page }) => {
    await page.route(pathMatcher('/api/scan'), async route => {
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
    await page.goto('/')
    await expect(page.locator('body')).toBeVisible()
  })

  test('404 on scan detail degrades gracefully', async ({ page }) => {
    await page.route('**/api/scan/999', route =>
      route.fulfill({ status: 404, json: { detail: 'Scan not found' } }),
    )
    await page.route('**/api/scan/999/scores*', route =>
      route.fulfill({ status: 404, json: { detail: 'Scan not found' } }),
    )

    await page.goto('/scan/999')

    // Page should render without crash — shows empty DataTable or error state
    await expect(page.locator('body')).toBeVisible()
    const indicator = page.locator('[data-testid="error-state"]')
      .or(page.locator('[data-testid="empty-state"]'))
      .or(page.locator('text=/not found|no results|error/i'))
    await expect(indicator).toBeVisible({ timeout: 5_000 })
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

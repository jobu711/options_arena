/**
 * E2E tests: Quick Debate from Dashboard.
 *
 * Covers: ticker input submission, WebSocket progress, auto-navigation
 * to debate result, 409 busy handling, and Enter key submission.
 */

import { test, expect } from '../../fixtures/base.fixture'
import { mockAllApis, mockGet, mockPost, pathMatcher } from '../../fixtures/mocks/api-handlers'
import { buildDebateResult, buildDebateSummary } from '../../fixtures/builders/debate.builders'
import { buildScanRun } from '../../fixtures/builders/scan.builders'
import { debateProgressSequence } from '../../fixtures/mocks/ws-scenarios'

const DEBATE_ID = 789

test.describe('Quick Debate from Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    await mockAllApis(page, {
      scanList: [buildScanRun({ id: 1 })],
    })
    await mockGet(page, pathMatcher('/api/debate'), [
      buildDebateSummary({ id: 1, ticker: 'AAPL' }),
    ])
  })

  test('submit ticker shows progress modal and navigates to result', async ({ page }) => {
    // Mock POST /api/debate to return our test debate ID
    await mockPost(page, '**/api/debate', 202, { debate_id: DEBATE_ID })

    // Mock GET /api/debate/:id for the result page
    await mockGet(
      page,
      `**/api/debate/${DEBATE_ID}`,
      buildDebateResult({ id: DEBATE_ID, ticker: 'TSLA' }),
    )

    // Set up WebSocket mock to replay debate progress events
    const wsEvents = debateProgressSequence(DEBATE_ID)
    await page.routeWebSocket(`**/ws/debate/${DEBATE_ID}`, ws => {
      let delay = 100
      for (const event of wsEvents) {
        delay += 200
        setTimeout(() => ws.send(JSON.stringify(event)), delay)
      }
    })

    await page.goto('/')

    // Type ticker into quick debate input
    const input = page.locator('[data-testid="quick-debate-input"]')
    await expect(input).toBeVisible()
    await input.fill('tsla')

    // Input should auto-uppercase
    await expect(input).toHaveValue('TSLA')

    // Click the Debate button
    const debateBtn = page.locator('[data-testid="quick-debate-btn"]')
    await debateBtn.click()

    // Progress modal should appear
    const modal = page.locator('[data-testid="debate-progress-modal"]')
    await expect(modal).toBeVisible({ timeout: 5_000 })

    // Should contain the ticker name
    await expect(modal).toContainText('TSLA')

    // After WebSocket sends complete event, should navigate to debate result page
    await page.waitForURL(`**/debate/${DEBATE_ID}`, { timeout: 10_000 })
    expect(page.url()).toContain(`/debate/${DEBATE_ID}`)
  })

  test('409 busy response shows error toast', async ({ page }) => {
    // Mock POST /api/debate to return 409 (operation busy)
    await page.route('**/api/debate', async route => {
      if (route.request().method() === 'POST') {
        return route.fulfill({
          status: 409,
          json: { detail: 'Another operation is in progress' },
        })
      }
      return route.continue()
    })

    await page.goto('/')

    // Type ticker and submit
    const input = page.locator('[data-testid="quick-debate-input"]')
    await input.fill('AAPL')

    const debateBtn = page.locator('[data-testid="quick-debate-btn"]')
    await debateBtn.click()

    // Should show a toast with busy/progress message
    const toast = page.locator('.p-toast-message')
    await expect(toast).toBeVisible({ timeout: 5_000 })
    await expect(toast).toContainText(/in progress|busy/i)

    // Progress modal should NOT be visible
    const modal = page.locator('[data-testid="debate-progress-modal"]')
    await expect(modal).not.toBeVisible()
  })

  test('Enter key submits the debate form', async ({ page }) => {
    // Mock POST /api/debate to return our test debate ID
    await mockPost(page, '**/api/debate', 202, { debate_id: DEBATE_ID })

    // Mock GET /api/debate/:id for navigation target
    await mockGet(
      page,
      `**/api/debate/${DEBATE_ID}`,
      buildDebateResult({ id: DEBATE_ID, ticker: 'NVDA' }),
    )

    // Set up WebSocket mock with quick completion
    await page.routeWebSocket(`**/ws/debate/${DEBATE_ID}`, ws => {
      setTimeout(() => {
        ws.send(JSON.stringify({ type: 'agent', name: 'bull', status: 'started', confidence: null }))
      }, 100)
      setTimeout(() => {
        ws.send(JSON.stringify({ type: 'agent', name: 'bull', status: 'completed', confidence: 0.7 }))
      }, 200)
      setTimeout(() => {
        ws.send(JSON.stringify({ type: 'complete', debate_id: DEBATE_ID }))
      }, 300)
    })

    await page.goto('/')

    // Type ticker and press Enter
    const input = page.locator('[data-testid="quick-debate-input"]')
    await input.fill('NVDA')
    await input.press('Enter')

    // Progress modal should appear (form submitted via Enter)
    const modal = page.locator('[data-testid="debate-progress-modal"]')
    await expect(modal).toBeVisible({ timeout: 5_000 })

    // Should navigate to result after WebSocket complete
    await page.waitForURL(`**/debate/${DEBATE_ID}`, { timeout: 10_000 })
    expect(page.url()).toContain(`/debate/${DEBATE_ID}`)
  })
})

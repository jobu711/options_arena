/**
 * Extended Playwright test fixture with app-specific helpers.
 *
 * - Collects console errors and fails on unexpected ones after each test.
 * - Provides resilient locator factory with selector fallback chain.
 */

import { test as base, expect, type Page, type Locator } from '@playwright/test'

/** Console error collector — attached per test. */
function collectConsoleErrors(page: Page): string[] {
  const errors: string[] = []
  page.on('console', msg => {
    if (msg.type() === 'error') {
      errors.push(msg.text())
    }
  })
  return errors
}

/** Ignorable console errors (browser noise, not app bugs). */
const IGNORED_PATTERNS = [
  'favicon.ico',
  '[HMR]',
  '[vite]',
  'net::ERR_',          // Network errors from mocked routes
  'WebSocket connection', // Expected in WS disconnect tests
]

function isIgnoredError(text: string): boolean {
  return IGNORED_PATTERNS.some(p => text.includes(p))
}

/**
 * Selector fallback chain: data-testid → aria-label → text content.
 * Returns the first locator that matches at least one element.
 * If none match, returns the first (for Playwright's built-in timeout to handle).
 */
export async function resilientLocator(
  page: Page,
  selectors: string[],
): Promise<Locator> {
  for (const selector of selectors) {
    const loc = page.locator(selector)
    if ((await loc.count()) > 0) return loc
  }
  return page.locator(selectors[0])
}

/**
 * Build a locator chain using Playwright's .or() for self-healing.
 * Tries data-testid first, then aria-label, then text content.
 */
export function selfHealingLocator(
  page: Page,
  testId: string,
  ariaLabel: string,
  textContent: string,
): Locator {
  return page
    .locator(`[data-testid="${testId}"]`)
    .or(page.locator(`[aria-label="${ariaLabel}"]`))
    .or(page.locator(`button:has-text("${textContent}"), a:has-text("${textContent}")`))
}

export const test = base.extend<{
  consoleErrors: string[]
}>({
  consoleErrors: async ({ page }, use) => {
    const errors = collectConsoleErrors(page)
    await use(errors)
    // After test: fail if unexpected console errors
    const unexpected = errors.filter(e => !isIgnoredError(e))
    if (unexpected.length > 0) {
      console.error('Unexpected console errors:', unexpected)
    }
    expect(unexpected, 'Unexpected console errors detected').toHaveLength(0)
  },
})

export { expect }

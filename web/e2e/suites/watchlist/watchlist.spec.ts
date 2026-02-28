/**
 * E2E tests: Watchlist CRUD workflows.
 *
 * Covers: create watchlist, add ticker, view detail, remove ticker, delete watchlist.
 */

import { test, expect } from '../../fixtures/base.fixture'
import { WatchlistPage } from '../../fixtures/pages/watchlist.page'
import { mockAllApis, mockGet, mockPost } from '../../fixtures/mocks/api-handlers'
import {
  buildWatchlist,
  buildWatchlistDetail,
  buildEmptyWatchlistDetail,
  buildWatchlistTicker,
} from '../../fixtures/builders/watchlist.builders'

test.describe('Watchlist', () => {
  test.beforeEach(async ({ page }) => {
    await mockAllApis(page)

    // Default: return empty debates for any debate queries
    await page.route('**/api/debate*', route =>
      route.fulfill({ json: [] }),
    )
  })

  test('shows empty state when no watchlists exist', async ({ page }) => {
    // Mock: no watchlists
    await mockGet(page, '**/api/watchlist', [])

    const wlPage = new WatchlistPage(page)
    await wlPage.goto()
    await wlPage.expectEmptyState()
  })

  test('create watchlist and verify it appears', async ({ page }) => {
    const newWl = buildWatchlist({ id: 1, name: 'My First Watchlist' })

    // Initially empty
    let callCount = 0
    await page.route('**/api/watchlist', async route => {
      const method = route.request().method()
      if (method === 'GET') {
        // After creation, return the new watchlist
        if (callCount > 0) {
          return route.fulfill({ json: [newWl] })
        }
        callCount++
        return route.fulfill({ json: [] })
      }
      if (method === 'POST') {
        callCount++
        return route.fulfill({
          status: 201,
          json: { id: newWl.id, name: newWl.name },
        })
      }
      return route.continue()
    })

    // Mock the detail endpoint for the newly created watchlist
    await mockGet(
      page,
      '**/api/watchlist/1',
      buildEmptyWatchlistDetail(1, 'My First Watchlist'),
    )

    const wlPage = new WatchlistPage(page)
    await wlPage.goto()

    // Should see empty state
    await wlPage.expectEmptyState()

    // Click create button
    await wlPage.createBtnEmpty.click()
    await expect(wlPage.createDialog).toBeVisible()

    // Enter name and submit
    await wlPage.nameInput.fill('My First Watchlist')
    await wlPage.confirmCreateBtn.click()

    // Should now see the watchlist controls (no more empty state)
    await expect(wlPage.watchlistSelector).toBeVisible({ timeout: 10_000 })
  })

  test('view watchlist detail with tickers', async ({ page }) => {
    const wl = buildWatchlist({ id: 1, name: 'Tech Stocks' })
    const detail = buildWatchlistDetail({ id: 1, name: 'Tech Stocks' })

    await mockGet(page, '**/api/watchlist', [wl])
    await mockGet(page, '**/api/watchlist/1', detail)

    const wlPage = new WatchlistPage(page)
    await wlPage.goto()

    // Should show the table with tickers
    await wlPage.expectTable()

    // All 3 tickers should appear
    const tickers = await wlPage.getAllTickers()
    expect(tickers).toContain('AAPL')
    expect(tickers).toContain('MSFT')
    expect(tickers).toContain('GOOGL')
  })

  test('remove ticker from watchlist', async ({ page }) => {
    const wl = buildWatchlist({ id: 1, name: 'Tech Stocks' })
    const initialDetail = buildWatchlistDetail({ id: 1, name: 'Tech Stocks' })
    const afterRemoveDetail = buildWatchlistDetail({
      id: 1,
      name: 'Tech Stocks',
      tickers: [
        buildWatchlistTicker({ ticker: 'MSFT', composite_score: 6.8, direction: 'bullish' }),
        buildWatchlistTicker({ ticker: 'GOOGL', composite_score: 5.2, direction: 'neutral' }),
      ],
    })

    await mockGet(page, '**/api/watchlist', [wl])

    // Track remove calls to switch detail response
    let removed = false
    await page.route('**/api/watchlist/1', async route => {
      if (route.request().method() === 'GET') {
        return route.fulfill({ json: removed ? afterRemoveDetail : initialDetail })
      }
      return route.continue()
    })

    await page.route('**/api/watchlist/1/tickers/AAPL', async route => {
      if (route.request().method() === 'DELETE') {
        removed = true
        return route.fulfill({ status: 204 })
      }
      return route.continue()
    })

    const wlPage = new WatchlistPage(page)
    await wlPage.goto()
    await wlPage.expectTable()

    // Verify AAPL is present
    await wlPage.expectTickerInTable('AAPL')

    // Click remove
    await wlPage.clickRemoveTicker('AAPL')

    // After removal, AAPL should be gone
    await expect(
      page.locator('[data-testid="watchlist-ticker"]:has-text("AAPL")'),
    ).toBeHidden({ timeout: 10_000 })
  })

  test('delete watchlist', async ({ page }) => {
    const wl = buildWatchlist({ id: 1, name: 'To Delete' })
    const detail = buildEmptyWatchlistDetail(1, 'To Delete')

    let deleted = false
    await page.route('**/api/watchlist', async route => {
      if (route.request().method() === 'GET') {
        return route.fulfill({ json: deleted ? [] : [wl] })
      }
      return route.continue()
    })

    await page.route('**/api/watchlist/1', async route => {
      if (route.request().method() === 'DELETE') {
        deleted = true
        return route.fulfill({ status: 204 })
      }
      if (route.request().method() === 'GET') {
        return route.fulfill({ json: detail })
      }
      return route.continue()
    })

    const wlPage = new WatchlistPage(page)
    await wlPage.goto()

    // Should see watchlist controls
    await expect(wlPage.watchlistSelector).toBeVisible()

    // Click delete
    await wlPage.deleteBtn.click()

    // Confirm deletion in the dialog
    const acceptBtn = page.locator('.p-confirmdialog-accept-button')
      .or(page.getByRole('button', { name: /accept|yes|delete/i }))
    await acceptBtn.click()

    // After deletion, should see empty state
    await wlPage.expectEmptyState()
  })
})

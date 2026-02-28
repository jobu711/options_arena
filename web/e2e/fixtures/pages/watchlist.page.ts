import { type Page, type Locator, expect } from '@playwright/test'

export class WatchlistPage {
  readonly page: Page
  readonly emptyState: Locator
  readonly createBtnEmpty: Locator
  readonly createBtn: Locator
  readonly deleteBtn: Locator
  readonly watchlistSelector: Locator
  readonly table: Locator
  readonly tickersEmpty: Locator
  readonly createDialog: Locator
  readonly nameInput: Locator
  readonly confirmCreateBtn: Locator

  constructor(page: Page) {
    this.page = page
    this.emptyState = page.locator('[data-testid="watchlist-empty-state"]')
    this.createBtnEmpty = page.locator('[data-testid="create-watchlist-empty-btn"]')
    this.createBtn = page.locator('[data-testid="create-watchlist-btn"]')
    this.deleteBtn = page.locator('[data-testid="delete-watchlist-btn"]')
    this.watchlistSelector = page.locator('[data-testid="watchlist-selector"]')
    this.table = page.locator('[data-testid="watchlist-table"]')
    this.tickersEmpty = page.locator('[data-testid="watchlist-tickers-empty"]')
    this.createDialog = page.locator('[data-testid="create-watchlist-dialog"]')
    this.nameInput = page.locator('[data-testid="watchlist-name-input"]')
    this.confirmCreateBtn = page.locator('[data-testid="confirm-create-btn"]')
  }

  async goto(): Promise<void> {
    await this.page.goto('/watchlist')
    await this.page.waitForLoadState('networkidle')
  }

  async expectEmptyState(): Promise<void> {
    await expect(this.emptyState).toBeVisible()
  }

  async expectTable(): Promise<void> {
    await expect(this.table).toBeVisible()
  }

  async getTickerCount(): Promise<number> {
    return this.page.locator('[data-testid="watchlist-ticker"]').count()
  }

  async getAllTickers(): Promise<string[]> {
    return this.page.locator('[data-testid="watchlist-ticker"]').allInnerTexts()
  }

  async expectTickerInTable(ticker: string): Promise<void> {
    await expect(
      this.page.locator(`[data-testid="watchlist-ticker"]:has-text("${ticker}")`),
    ).toBeVisible()
  }

  async clickRemoveTicker(ticker: string): Promise<void> {
    await this.page.locator(`[data-testid="remove-ticker-${ticker}"]`).click()
  }
}

import { type Page, type Locator, expect } from '@playwright/test'

export class ScanResultsPage {
  readonly page: Page
  readonly table: Locator
  readonly searchInput: Locator
  readonly directionFilter: Locator
  readonly minScoreFilter: Locator
  readonly batchDebateBtn: Locator
  readonly rowCheckboxes: Locator
  readonly tickerDrawer: Locator

  constructor(page: Page) {
    this.page = page
    this.table = page.locator('[data-testid="scan-results-table"]').or(page.locator('.p-datatable'))
    this.searchInput = page.locator('[data-testid="ticker-search"]')
      .or(page.locator('input[placeholder*="earch"]'))
    this.directionFilter = page.locator('[data-testid="direction-filter"]')
      .or(page.locator('[aria-label="Direction Filter"]'))
    this.minScoreFilter = page.locator('[data-testid="min-score-filter"]')
      .or(page.locator('[aria-label="Min Score"]'))
    this.batchDebateBtn = page.locator('[data-testid="batch-debate-btn"]')
      .or(page.locator('button:has-text("Debate Selected")'))
    this.rowCheckboxes = page.locator('.p-datatable-tbody .p-checkbox')
    this.tickerDrawer = page.locator('[data-testid="ticker-drawer"]')
      .or(page.locator('.p-drawer'))
  }

  async goto(scanId: number): Promise<void> {
    await this.page.goto(`/scan/${scanId}`)
    await this.table.waitFor({ state: 'visible' })
  }

  async getRowCount(): Promise<number> {
    return this.page.locator('.p-datatable-tbody tr').count()
  }

  async getTickerAtRow(index: number): Promise<string> {
    const cell = this.page.locator(
      `.p-datatable-tbody tr:nth-child(${index + 1}) [data-testid="ticker-cell"]`,
    )
    return cell.innerText()
  }

  async getAllTickers(): Promise<string[]> {
    const cells = this.page.locator('[data-testid="ticker-cell"]')
    return cells.allInnerTexts()
  }

  async sortByColumn(columnHeader: string): Promise<void> {
    await this.page.locator(`.p-datatable-thead th:has-text("${columnHeader}")`).click()
  }

  async searchTicker(query: string): Promise<void> {
    await this.searchInput.fill(query)
    // Wait for debounce (300ms) + server response
    await this.page.waitForTimeout(500)
  }

  async filterByDirection(direction: 'bullish' | 'bearish' | 'neutral'): Promise<void> {
    await this.directionFilter.click()
    const label = direction.charAt(0).toUpperCase() + direction.slice(1)
    // Use role-based selector for PrimeVue Select options (works across versions)
    const option = this.page.getByRole('option', { name: label })
      .or(this.page.locator(`li:has-text("${label}")`))
    await option.waitFor({ state: 'visible' })
    await option.click()
  }

  async selectRows(indices: number[]): Promise<void> {
    for (const i of indices) {
      await this.rowCheckboxes.nth(i).click()
    }
  }

  async clickBatchDebate(): Promise<void> {
    await this.batchDebateBtn.click()
  }

  async openTickerDrawer(ticker: string): Promise<void> {
    await this.page.locator(`.p-datatable-tbody tr:has-text("${ticker}")`).click()
    await this.tickerDrawer.waitFor({ state: 'visible' })
  }

  async closeTickerDrawer(): Promise<void> {
    await this.page.locator('.p-drawer-close-button')
      .or(this.page.locator('[aria-label="Close"]'))
      .click()
    await this.tickerDrawer.waitFor({ state: 'hidden' })
  }

  async expectDirectionBadge(ticker: string, direction: string): Promise<void> {
    const row = this.page.locator(`.p-datatable-tbody tr:has-text("${ticker}")`)
    await expect(
      row.locator('[data-testid="direction-badge"]').or(row.locator('.direction-badge')),
    ).toContainText(direction, { ignoreCase: true })
  }

  async expectScoreInRange(ticker: string, min: number, max: number): Promise<void> {
    const row = this.page.locator(`.p-datatable-tbody tr:has-text("${ticker}")`)
    const scoreText = await row
      .locator('[data-testid="composite-score"]')
      .innerText()
    const score = parseFloat(scoreText)
    expect(score).toBeGreaterThanOrEqual(min)
    expect(score).toBeLessThanOrEqual(max)
  }

  async expectRowCount(expected: number): Promise<void> {
    await expect(this.page.locator('.p-datatable-tbody tr')).toHaveCount(expected)
  }

  async expectEmptyState(): Promise<void> {
    await expect(
      this.page.locator('[data-testid="empty-state"]')
        .or(this.page.getByText('No results found matching your filters.'))
        .first(),
    ).toBeVisible({ timeout: 10_000 })
  }
}

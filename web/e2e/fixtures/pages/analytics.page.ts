import { type Page, type Locator, expect } from '@playwright/test'

export class AnalyticsPage {
  readonly page: Page
  readonly pageRoot: Locator
  readonly collectBtn: Locator
  readonly lookbackSelect: Locator
  readonly summarySection: Locator
  readonly winRatePanel: Locator
  readonly calibrationPanel: Locator
  readonly holdingPanel: Locator
  readonly deltaPanel: Locator

  // Backtest tab panels
  readonly equityCurveChart: Locator
  readonly drawdownChart: Locator
  readonly sectorPerformanceChart: Locator
  readonly dtePerformanceChart: Locator
  readonly ivPerformanceChart: Locator
  readonly greeksDecompositionChart: Locator
  readonly holdingComparisonTable: Locator
  readonly agentAccuracyHeatmap: Locator

  constructor(page: Page) {
    this.page = page
    this.pageRoot = page.locator('[data-testid="analytics-page"]')
    this.collectBtn = page.locator('[data-testid="btn-collect-outcomes"]')
    this.lookbackSelect = page.locator('[data-testid="lookback-select"]')
    this.summarySection = page.locator('[data-testid="analytics-summary"]')
    this.winRatePanel = page.locator('[data-testid="analytics-win-rate"]')
    this.calibrationPanel = page.locator('[data-testid="analytics-calibration"]')
    this.holdingPanel = page.locator('[data-testid="analytics-holding"]')
    this.deltaPanel = page.locator('[data-testid="analytics-delta"]')

    // Backtest chart/table locators
    this.equityCurveChart = page.locator('[data-testid="equity-curve-chart"]')
    this.drawdownChart = page.locator('[data-testid="drawdown-chart"]')
    this.sectorPerformanceChart = page.locator('[data-testid="sector-performance-chart"]')
    this.dtePerformanceChart = page.locator('[data-testid="dte-performance-chart"]')
    this.ivPerformanceChart = page.locator('[data-testid="iv-performance-chart"]')
    this.greeksDecompositionChart = page.locator('[data-testid="greeks-decomposition-chart"]')
    this.holdingComparisonTable = page.locator('[data-testid="holding-comparison-table"]')
    this.agentAccuracyHeatmap = page.locator('[data-testid="agent-accuracy-heatmap"]')
  }

  async goto(): Promise<void> {
    await this.page.goto('/analytics')
  }

  async expectLoaded(): Promise<void> {
    await expect(this.pageRoot).toBeVisible()
  }

  async expectEmptyNoContracts(): Promise<void> {
    await expect(this.page.locator('[data-testid="empty-no-contracts"]')).toBeVisible()
  }

  async expectEmptyNoOutcomes(): Promise<void> {
    await expect(this.page.locator('[data-testid="empty-no-outcomes"]')).toBeVisible()
  }

  async expectAllPanelsVisible(): Promise<void> {
    await expect(this.summarySection).toBeVisible()
    await expect(this.winRatePanel).toBeVisible()
    await expect(this.calibrationPanel).toBeVisible()
    await expect(this.holdingPanel).toBeVisible()
    await expect(this.deltaPanel).toBeVisible()
  }

  async clickCollectOutcomes(): Promise<void> {
    await this.collectBtn.click()
  }

  /** Click a tab by its visible label text. */
  async clickTab(label: string): Promise<void> {
    await this.page.locator(`[data-pc-name="tab"]:has-text("${label}")`).click()
  }

  /** Wait for the Overview tab's backtest charts to be visible. */
  async expectOverviewChartsVisible(): Promise<void> {
    await expect(this.equityCurveChart).toBeVisible()
    await expect(this.drawdownChart).toBeVisible()
  }

  /** Wait for the Agents tab content to be visible. */
  async expectAgentsTabVisible(): Promise<void> {
    await expect(this.agentAccuracyHeatmap).toBeVisible()
  }

  /** Wait for the Segments tab content to be visible. */
  async expectSegmentsTabVisible(): Promise<void> {
    await expect(this.sectorPerformanceChart).toBeVisible()
    await expect(this.dtePerformanceChart).toBeVisible()
    await expect(this.ivPerformanceChart).toBeVisible()
  }

  /** Wait for the Greeks tab content to be visible. */
  async expectGreeksTabVisible(): Promise<void> {
    await expect(this.greeksDecompositionChart).toBeVisible()
  }

  /** Wait for the Holding tab content to be visible. */
  async expectHoldingTabVisible(): Promise<void> {
    await expect(this.holdingComparisonTable).toBeVisible()
  }
}

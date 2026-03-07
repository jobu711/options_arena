import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '@/composables/useApi'
import type { ScanRun, TickerScore, PaginatedResponse } from '@/types'

export const useScanStore = defineStore('scan', () => {
  // --- State ---
  const scans = ref<ScanRun[]>([])
  const currentScanId = ref<number | null>(null)
  const scores = ref<TickerScore[]>([])
  const totalScores = ref(0)
  const totalPages = ref(1)
  const progress = ref<{ phase: string; current: number; total: number } | null>(null)
  const loading = ref(false)
  const errors = ref<Array<{ message: string }>>([])

  // --- Getters ---
  const latestScan = computed(() => scans.value[0] ?? null)
  const isScanning = computed(() => progress.value !== null)

  // --- Actions ---
  async function fetchScans(limit = 10): Promise<void> {
    loading.value = true
    try {
      scans.value = await api<ScanRun[]>('/api/scan', { params: { limit } })
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch scans'
      errors.value.push({ message })
    } finally {
      loading.value = false
    }
  }

  async function fetchScores(
    scanId: number,
    params: {
      page?: number
      page_size?: number
      sort?: string
      order?: string
      direction?: string
      min_score?: number
      search?: string
      sectors?: string
      industry_groups?: string
      // Dimensional filters
      min_confidence?: number
      market_regime?: string
      min_trend?: number
      min_iv_vol?: number
      min_flow?: number
      min_risk?: number
      max_earnings_days?: number
      min_earnings_days?: number
    } = {},
  ): Promise<void> {
    loading.value = true
    try {
      const res = await api<PaginatedResponse<TickerScore>>(
        `/api/scan/${scanId}/scores`,
        { params: params as Record<string, string | number | undefined> },
      )
      scores.value = res.items
      totalScores.value = res.total
      totalPages.value = res.pages
    } finally {
      loading.value = false
    }
  }

  interface StartScanOptions {
    preset: string
    sectors?: string[]
    industryGroups?: string[]
    customTickers?: string[]
    source?: 'manual' | 'watchlist'
    market_cap_tiers?: string[]
    exclude_near_earnings_days?: number | null
    direction_filter?: string | null
    min_iv_rank?: number | null
    min_price?: number | null
    max_price?: number | null
    min_dte?: number | null
    max_dte?: number | null
    min_score?: number | null
  }

  async function startScan(options: StartScanOptions): Promise<number> {
    const body: Record<string, unknown> = { preset: options.preset }
    if (options.sectors && options.sectors.length > 0) {
      body.sectors = options.sectors
    }
    if (options.industryGroups && options.industryGroups.length > 0) {
      body.industry_groups = options.industryGroups
    }
    if (options.customTickers && options.customTickers.length > 0) {
      body.custom_tickers = options.customTickers
    }
    if (options.source) {
      body.source = options.source
    }
    if (options.market_cap_tiers && options.market_cap_tiers.length > 0) {
      body.market_cap_tiers = options.market_cap_tiers
    }
    if (options.exclude_near_earnings_days != null) {
      body.exclude_near_earnings_days = options.exclude_near_earnings_days
    }
    if (options.direction_filter != null) {
      body.direction_filter = options.direction_filter
    }
    if (options.min_iv_rank != null) {
      body.min_iv_rank = options.min_iv_rank
    }
    if (options.min_price != null) {
      body.min_price = options.min_price
    }
    if (options.max_price != null) {
      body.max_price = options.max_price
    }
    if (options.min_dte != null) {
      body.min_dte = options.min_dte
    }
    if (options.max_dte != null) {
      body.max_dte = options.max_dte
    }
    if (options.min_score != null) {
      body.min_score = options.min_score
    }
    const res = await api<{ scan_id: number }>('/api/scan', {
      method: 'POST',
      body,
    })
    currentScanId.value = res.scan_id
    progress.value = { phase: 'universe', current: 0, total: 0 }
    errors.value = []
    return res.scan_id
  }

  async function cancelScan(): Promise<void> {
    await api<{ status: string }>('/api/scan/current', { method: 'DELETE' })
  }

  // WebSocket callbacks
  function updateProgress(event: { phase: string; current: number; total: number }): void {
    progress.value = event
  }

  function addError(event: { message: string }): void {
    errors.value.push(event)
  }

  function setComplete(event: { scan_id: number; cancelled: boolean }): void {
    progress.value = null
    currentScanId.value = event.scan_id
  }

  function reset(): void {
    progress.value = null
    currentScanId.value = null
    errors.value = []
  }

  return {
    scans,
    currentScanId,
    scores,
    totalScores,
    totalPages,
    progress,
    loading,
    errors,
    latestScan,
    isScanning,
    fetchScans,
    fetchScores,
    startScan,
    cancelScan,
    updateProgress,
    addError,
    setComplete,
    reset,
  }
})

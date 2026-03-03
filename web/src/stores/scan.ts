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

  async function startScan(
    preset: string,
    sectors?: string[],
    filters?: {
      market_cap_tiers?: string[]
      exclude_near_earnings_days?: number | null
      direction_filter?: string | null
      min_iv_rank?: number | null
    },
  ): Promise<number> {
    const body: Record<string, unknown> = { preset }
    if (sectors && sectors.length > 0) {
      body.sectors = sectors
    }
    if (filters?.market_cap_tiers && filters.market_cap_tiers.length > 0) {
      body.market_cap_tiers = filters.market_cap_tiers
    }
    if (filters?.exclude_near_earnings_days != null) {
      body.exclude_near_earnings_days = filters.exclude_near_earnings_days
    }
    if (filters?.direction_filter != null) {
      body.direction_filter = filters.direction_filter
    }
    if (filters?.min_iv_rank != null) {
      body.min_iv_rank = filters.min_iv_rank
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

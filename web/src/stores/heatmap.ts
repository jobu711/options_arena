import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '@/composables/useApi'
import type { HeatmapTicker } from '@/types'

export const useHeatmapStore = defineStore('heatmap', () => {
  // --- State ---
  const tickers = ref<HeatmapTicker[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const lastUpdated = ref<Date | null>(null)
  /** True after the first fetch attempt completes (success or error). */
  const initialized = ref(false)

  // --- Actions ---
  async function fetchHeatmap(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const result = await api<HeatmapTicker[]>('/api/market/heatmap')
      // Preserve stale data when the API returns empty but we already have
      // good data — prevents the treemap from disappearing on transient
      // failures (timeouts, partial yfinance outages, etc.).
      if (result.length > 0 || tickers.value.length === 0) {
        tickers.value = result
      }
      lastUpdated.value = new Date()
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to fetch heatmap'
    } finally {
      loading.value = false
      initialized.value = true
    }
  }

  let intervalId: ReturnType<typeof setInterval> | null = null

  function startAutoRefresh(intervalMs = 5 * 60 * 1000): void {
    stopAutoRefresh()
    intervalId = setInterval(() => void fetchHeatmap(), intervalMs)
  }

  function stopAutoRefresh(): void {
    if (intervalId !== null) {
      clearInterval(intervalId)
      intervalId = null
    }
  }

  return {
    tickers,
    loading,
    error,
    lastUpdated,
    initialized,
    fetchHeatmap,
    startAutoRefresh,
    stopAutoRefresh,
  }
})

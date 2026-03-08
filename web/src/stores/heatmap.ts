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

  // --- Actions ---
  async function fetchHeatmap(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      tickers.value = await api<HeatmapTicker[]>('/api/market/heatmap')
      lastUpdated.value = new Date()
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to fetch heatmap'
    } finally {
      loading.value = false
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
    fetchHeatmap,
    startAutoRefresh,
    stopAutoRefresh,
  }
})

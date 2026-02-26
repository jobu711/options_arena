import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '@/composables/useApi'
import type { HealthStatus } from '@/types'

export const useHealthStore = defineStore('health', () => {
  // --- State ---
  const services = ref<HealthStatus[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const lastChecked = ref<Date | null>(null)

  // --- Getters ---
  const allHealthy = computed(() =>
    services.value.length > 0 && services.value.every((s) => s.available),
  )
  const degradedCount = computed(() => services.value.filter((s) => !s.available).length)

  // --- Actions ---
  async function fetchHealth(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      services.value = await api<HealthStatus[]>('/api/health/services')
      lastChecked.value = new Date()
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to fetch health'
    } finally {
      loading.value = false
    }
  }

  let intervalId: ReturnType<typeof setInterval> | null = null

  function startAutoRefresh(intervalMs = 60_000): void {
    stopAutoRefresh()
    intervalId = setInterval(() => void fetchHealth(), intervalMs)
  }

  function stopAutoRefresh(): void {
    if (intervalId !== null) {
      clearInterval(intervalId)
      intervalId = null
    }
  }

  return {
    services,
    loading,
    error,
    lastChecked,
    allHealthy,
    degradedCount,
    fetchHealth,
    startAutoRefresh,
    stopAutoRefresh,
  }
})

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '@/composables/useApi'
import type { RecommendationCostDetail } from '@/types'

export const useCostsStore = defineStore('costs', () => {
  // --- State ---
  const costs = ref<RecommendationCostDetail[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const loaded = ref(false)

  // --- Getters ---
  const hasCosts = computed(() => costs.value.length > 0)

  // --- Actions ---
  async function loadCosts(): Promise<void> {
    if (loaded.value || loading.value) return
    loading.value = true
    error.value = null
    try {
      costs.value = await api<RecommendationCostDetail[]>(
        '/api/analytics/recommendation-costs',
        { params: { limit: 50 } },
      )
      loaded.value = true
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to fetch recommendation costs'
    } finally {
      loading.value = false
    }
  }

  /** Force reload (e.g. after new recommendations). */
  function reset(): void {
    loaded.value = false
    costs.value = []
    error.value = null
  }

  return {
    costs,
    loading,
    error,
    loaded,
    hasCosts,
    loadCosts,
    reset,
  }
})

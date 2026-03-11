import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '@/composables/useApi'
import type { AgentWeightsComparison, WeightSnapshot } from '@/types'

export const useWeightsStore = defineStore('weights', () => {
  // --- State ---
  const weights = ref<AgentWeightsComparison[]>([])
  const weightHistory = ref<WeightSnapshot[]>([])
  const loadingWeights = ref(false)
  const loadingHistory = ref(false)
  const loading = computed(() => loadingWeights.value || loadingHistory.value)
  const tuning = ref(false)

  // --- Actions ---

  async function fetchWeights(): Promise<void> {
    loadingWeights.value = true
    try {
      weights.value = await api<AgentWeightsComparison[]>('/api/analytics/agent-weights')
    } catch {
      weights.value = []
    } finally {
      loadingWeights.value = false
    }
  }

  async function fetchWeightHistory(): Promise<void> {
    loadingHistory.value = true
    try {
      weightHistory.value = await api<WeightSnapshot[]>('/api/analytics/weights/history')
    } catch {
      weightHistory.value = []
    } finally {
      loadingHistory.value = false
    }
  }

  async function triggerAutoTune(window?: number): Promise<AgentWeightsComparison[]> {
    tuning.value = true
    try {
      const result = await api<AgentWeightsComparison[]>('/api/analytics/weights/auto-tune', {
        method: 'POST',
        params: { window: window ?? undefined },
      })
      weights.value = result
      return result
    } finally {
      tuning.value = false
    }
  }

  return {
    weights,
    weightHistory,
    loading,
    tuning,
    fetchWeights,
    fetchWeightHistory,
    triggerAutoTune,
  }
})

import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '@/composables/useApi'
import type { AgentWeight, WeightSnapshot } from '@/types'

export const useWeightsStore = defineStore('weights', () => {
  // --- State ---
  const weights = ref<AgentWeight[]>([])
  const weightHistory = ref<WeightSnapshot[]>([])
  const loading = ref(false)
  const tuning = ref(false)

  // --- Actions ---

  async function fetchWeights(): Promise<void> {
    loading.value = true
    try {
      weights.value = await api<AgentWeight[]>('/api/analytics/agent-weights')
    } finally {
      loading.value = false
    }
  }

  async function fetchWeightHistory(): Promise<void> {
    loading.value = true
    try {
      weightHistory.value = await api<WeightSnapshot[]>('/api/analytics/weights/history')
    } finally {
      loading.value = false
    }
  }

  async function triggerAutoTune(window?: number): Promise<AgentWeight[]> {
    tuning.value = true
    try {
      const result = await api<AgentWeight[]>('/api/analytics/weights/auto-tune', {
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

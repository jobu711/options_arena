/** Pinia store for interactive desk agent queries. */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api, ApiError } from '@/composables/useApi'
import type { AgencyResponse, DeskType } from '@/types/agency'

export const useAgencyStore = defineStore('agency', () => {
  // --- State ---
  const currentResponse = ref<AgencyResponse | null>(null)
  const history = ref<AgencyResponse[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  // --- Getters ---
  const hasResponse = computed(() => currentResponse.value !== null)
  const deskCount = computed(() => currentResponse.value?.desk_responses.length ?? 0)

  // --- Actions ---
  async function submitQuery(
    query: string,
    desk: DeskType | null = null,
    tickers: string[] | null = null,
  ): Promise<void> {
    loading.value = true
    error.value = null
    currentResponse.value = null

    try {
      const body: Record<string, unknown> = { query }
      if (desk) body.desk = desk
      if (tickers?.length) body.tickers = tickers

      const response = await api<AgencyResponse>('/api/agency/query', {
        method: 'POST',
        body,
        timeout: 120_000, // Desk agents can take a while
      })
      currentResponse.value = response
      // Prepend to history (most recent first)
      history.value.unshift(response)
    } catch (err) {
      if (err instanceof ApiError) {
        error.value = err.status === 409
          ? 'Another operation is in progress. Please wait.'
          : err.message
      } else {
        error.value = 'Failed to submit query'
      }
    } finally {
      loading.value = false
    }
  }

  async function fetchHistory(limit = 20): Promise<void> {
    try {
      history.value = await api<AgencyResponse[]>('/api/agency/queries', {
        params: { limit },
      })
    } catch {
      // Non-critical — history fetch can silently fail
    }
  }

  function selectFromHistory(queryId: string): void {
    const found = history.value.find((r) => r.query_id === queryId)
    if (found) currentResponse.value = found
  }

  function clear(): void {
    currentResponse.value = null
    error.value = null
  }

  return {
    currentResponse,
    history,
    loading,
    error,
    hasResponse,
    deskCount,
    submitQuery,
    fetchHistory,
    selectFromHistory,
    clear,
  }
})

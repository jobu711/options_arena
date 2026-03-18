import { defineStore } from 'pinia'
import { ref } from 'vue'
import { ApiError } from '@/composables/useApi'
import type { AgencyResponseData } from '@/api/agency'
import { submitAgencyQuery, listAgencyQueries } from '@/api/agency'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  response: AgencyResponseData | null
  timestamp: string
}

export const useAgencyStore = defineStore('agency', () => {
  // --- State ---
  const messages = ref<ChatMessage[]>([])
  const history = ref<AgencyResponseData[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  // --- Actions ---

  /** Submit a query and add user + assistant messages to the conversation. */
  async function submitQuery(
    query: string,
    desk: string | null = null,
    tickers: string[] | null = null,
  ): Promise<void> {
    // Add user message
    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: query,
      response: null,
      timestamp: new Date().toISOString(),
    }
    messages.value.push(userMsg)

    loading.value = true
    error.value = null
    try {
      const response = await submitAgencyQuery({
        query,
        desk,
        tickers,
      })

      // Add assistant message with full response
      const assistantMsg: ChatMessage = {
        id: `assistant-${response.query_id}`,
        role: 'assistant',
        content: response.synthesis,
        response,
        timestamp: response.created_at,
      }
      messages.value.push(assistantMsg)
    } catch (e: unknown) {
      if (e instanceof ApiError && e.status === 409) {
        error.value = 'Analysis in progress. Please wait for the current operation to complete.'
      } else {
        error.value = e instanceof Error ? e.message : 'Failed to submit query'
      }
    } finally {
      loading.value = false
    }
  }

  /** Load recent query history from the backend. */
  async function loadHistory(limit: number = 20): Promise<void> {
    try {
      history.value = await listAgencyQueries(limit)
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to load history'
    }
  }

  /** Clear all messages from the current conversation. */
  function clearMessages(): void {
    messages.value = []
    error.value = null
  }

  return {
    messages,
    history,
    loading,
    error,
    submitQuery,
    loadHistory,
    clearMessages,
  }
})

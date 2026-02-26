import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '@/composables/useApi'
import type {
  DebateResultSummary,
  DebateResult,
  AgentProgressEntry,
} from '@/types/debate'

export const useDebateStore = defineStore('debate', () => {
  // --- State ---
  const debates = ref<DebateResultSummary[]>([])
  const currentDebate = ref<DebateResult | null>(null)
  const currentDebateId = ref<number | null>(null)
  const agentProgress = ref<AgentProgressEntry[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  // --- Getters ---
  const isDebating = computed(() => currentDebateId.value !== null && agentProgress.value.length > 0)

  // --- Actions ---
  async function fetchDebates(limit = 20): Promise<void> {
    loading.value = true
    try {
      debates.value = await api<DebateResultSummary[]>('/api/debate', { params: { limit } })
    } finally {
      loading.value = false
    }
  }

  async function fetchDebate(id: number): Promise<void> {
    loading.value = true
    error.value = null
    try {
      currentDebate.value = await api<DebateResult>(`/api/debate/${id}`)
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to load debate'
    } finally {
      loading.value = false
    }
  }

  async function startDebate(ticker: string, scanId: number | null): Promise<number> {
    const body: { ticker: string; scan_id?: number } = { ticker }
    if (scanId !== null) body.scan_id = scanId
    const res = await api<{ debate_id: number }>('/api/debate', {
      method: 'POST',
      body,
    })
    currentDebateId.value = res.debate_id

    // Initialize agent progress with standard agents
    agentProgress.value = [
      { name: 'bull', status: 'pending', confidence: null },
      { name: 'bear', status: 'pending', confidence: null },
      { name: 'risk', status: 'pending', confidence: null },
    ]
    error.value = null
    return res.debate_id
  }

  // WebSocket callbacks
  function updateAgentProgress(event: {
    name: string
    status: string
    confidence?: number | null
  }): void {
    const existing = agentProgress.value.find((a) => a.name === event.name)
    if (existing) {
      existing.status = event.status as AgentProgressEntry['status']
      if (event.confidence !== undefined && event.confidence !== null) {
        existing.confidence = event.confidence
      }
    } else {
      // Dynamic agent (rebuttal, volatility) — add it
      agentProgress.value.push({
        name: event.name,
        status: event.status as AgentProgressEntry['status'],
        confidence: event.confidence ?? null,
      })
    }
  }

  function setDebateComplete(debateId: number): void {
    currentDebateId.value = null
  }

  function setDebateError(message: string): void {
    error.value = message
  }

  function reset(): void {
    currentDebateId.value = null
    agentProgress.value = []
    error.value = null
  }

  return {
    debates,
    currentDebate,
    currentDebateId,
    agentProgress,
    loading,
    error,
    isDebating,
    fetchDebates,
    fetchDebate,
    startDebate,
    updateAgentProgress,
    setDebateComplete,
    setDebateError,
    reset,
  }
})

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '@/composables/useApi'
import type {
  DebateResultSummary,
  DebateResult,
  AgentProgressEntry,
} from '@/types/debate'
import type { BatchTickerResultEvent } from '@/types/ws'

export interface BatchTickerProgress {
  ticker: string
  index: number
  total: number
  status: 'pending' | 'started' | 'completed' | 'failed'
  agents: AgentProgressEntry[]
  result: BatchTickerResultEvent | null
}

export const useDebateStore = defineStore('debate', () => {
  // --- State ---
  const debates = ref<DebateResultSummary[]>([])
  const currentDebate = ref<DebateResult | null>(null)
  const currentDebateId = ref<number | null>(null)
  const agentProgress = ref<AgentProgressEntry[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  // Batch state
  const batchId = ref<number | null>(null)
  const batchTickers = ref<BatchTickerProgress[]>([])
  const batchResults = ref<BatchTickerResultEvent[]>([])
  const batchComplete = ref(false)

  // --- Getters ---
  const isDebating = computed(
    () => currentDebateId.value !== null && agentProgress.value.length > 0,
  )
  const isBatching = computed(() => batchId.value !== null && !batchComplete.value)
  const batchCurrentTicker = computed(
    () => batchTickers.value.find((t) => t.status === 'started') ?? null,
  )

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

  interface DebateOptions {
    scanId?: number | null
    enableRebuttal?: boolean | null
    enableVolatilityAgent?: boolean | null
  }

  async function startDebate(ticker: string, scanId: number | null, options?: DebateOptions): Promise<number> {
    const body: Record<string, unknown> = { ticker }
    if (scanId !== null) body.scan_id = scanId
    if (options?.enableRebuttal != null) body.enable_rebuttal = options.enableRebuttal
    if (options?.enableVolatilityAgent != null) body.enable_volatility_agent = options.enableVolatilityAgent
    const res = await api<{ debate_id: number }>('/api/debate', {
      method: 'POST',
      body,
    })
    currentDebateId.value = res.debate_id

    // Initialize agent progress with standard agents
    const agents: Array<{ name: string; status: 'pending' | 'started' | 'completed' | 'failed'; confidence: number | null }> = [
      { name: 'bull', status: 'pending', confidence: null },
      { name: 'bear', status: 'pending', confidence: null },
      { name: 'risk', status: 'pending', confidence: null },
    ]
    if (options?.enableVolatilityAgent) {
      agents.push({ name: 'volatility', status: 'pending', confidence: null })
    }
    if (options?.enableRebuttal) {
      agents.push({ name: 'rebuttal', status: 'pending', confidence: null })
    }
    agentProgress.value = agents
    error.value = null
    return res.debate_id
  }

  async function startBatchDebate(
    scanId: number,
    tickers: string[] | null,
    limit: number,
  ): Promise<number> {
    const body: { scan_id: number; tickers?: string[]; limit: number } = {
      scan_id: scanId,
      limit,
    }
    if (tickers !== null) body.tickers = tickers
    const res = await api<{ batch_id: number; tickers: string[] }>('/api/debate/batch', {
      method: 'POST',
      body,
    })
    batchId.value = res.batch_id
    batchComplete.value = false
    batchResults.value = []
    error.value = null

    // Initialize ticker progress
    batchTickers.value = res.tickers.map((t, i) => ({
      ticker: t,
      index: i + 1,
      total: res.tickers.length,
      status: 'pending',
      agents: [],
      result: null,
    }))

    return res.batch_id
  }

  // WebSocket callbacks — single debate
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

  function setDebateComplete(_debateId: number): void {
    currentDebateId.value = null
    agentProgress.value = []
  }

  function setDebateError(message: string): void {
    error.value = message
  }

  // WebSocket callbacks — batch
  function updateBatchProgress(event: {
    ticker: string
    index: number
    total: number
    status: string
  }): void {
    const entry = batchTickers.value.find((t) => t.ticker === event.ticker)
    if (entry) {
      entry.status = event.status as BatchTickerProgress['status']
      entry.index = event.index
      entry.total = event.total
      // Reset agents when starting new ticker
      if (event.status === 'started') {
        entry.agents = [
          { name: 'bull', status: 'pending', confidence: null },
          { name: 'bear', status: 'pending', confidence: null },
          { name: 'risk', status: 'pending', confidence: null },
        ]
      }
    }
  }

  function updateBatchAgentProgress(event: {
    ticker: string
    name: string
    status: string
    confidence?: number | null
  }): void {
    const entry = batchTickers.value.find((t) => t.ticker === event.ticker)
    if (!entry) return
    const existing = entry.agents.find((a) => a.name === event.name)
    if (existing) {
      existing.status = event.status as AgentProgressEntry['status']
      if (event.confidence !== undefined && event.confidence !== null) {
        existing.confidence = event.confidence
      }
    } else {
      entry.agents.push({
        name: event.name,
        status: event.status as AgentProgressEntry['status'],
        confidence: event.confidence ?? null,
      })
    }
  }

  function setBatchComplete(results: BatchTickerResultEvent[]): void {
    batchResults.value = results
    batchComplete.value = true
    // Update individual ticker entries with results
    for (const r of results) {
      const entry = batchTickers.value.find((t) => t.ticker === r.ticker)
      if (entry) {
        entry.result = r
        if (r.error) entry.status = 'failed'
        else entry.status = 'completed'
      }
    }
  }

  function setBatchError(message: string): void {
    error.value = message
  }

  function reset(): void {
    currentDebateId.value = null
    agentProgress.value = []
    error.value = null
  }

  function resetBatch(): void {
    batchId.value = null
    batchTickers.value = []
    batchResults.value = []
    batchComplete.value = false
    error.value = null
  }

  return {
    debates,
    currentDebate,
    currentDebateId,
    agentProgress,
    loading,
    error,
    batchId,
    batchTickers,
    batchResults,
    batchComplete,
    isDebating,
    isBatching,
    batchCurrentTicker,
    fetchDebates,
    fetchDebate,
    startDebate,
    startBatchDebate,
    updateAgentProgress,
    setDebateComplete,
    setDebateError,
    updateBatchProgress,
    updateBatchAgentProgress,
    setBatchComplete,
    setBatchError,
    reset,
    resetBatch,
  }
})

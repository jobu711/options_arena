import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '@/composables/useApi'
import type {
  PipelineTicker,
  RecommendationDetail,
  PipelineStage,
  Direction,
} from '@/types'
import type {
  ScanCompleteEvent,
  ScanProgressEvent,
  BatchProgressEvent,
  BatchCompleteEvent,
} from '@/types/ws'

export const usePipelineStore = defineStore('pipeline', () => {
  // --- State ---
  const tickers = ref<Map<string, PipelineTicker>>(new Map())
  const selectedTicker = ref<string | null>(null)
  const currentRecommendation = ref<RecommendationDetail | null>(null)
  const scanId = ref<number | null>(null)
  const dbScanId = ref<number | null>(null)
  const batchId = ref<number | null>(null)
  const phase = ref<'idle' | 'scanning' | 'scanned'>('idle')
  const loading = ref(false)
  const errors = ref<Array<{ message: string }>>([])
  const selectedForAnalysis = ref<Set<string>>(new Set())

  // --- Getters ---
  const sortedTickers = computed<PipelineTicker[]>(() => {
    return [...tickers.value.values()].sort(
      (a, b) => b.composite_score - a.composite_score,
    )
  })

  const selectedPipelineTicker = computed<PipelineTicker | null>(() => {
    if (selectedTicker.value === null) return null
    return tickers.value.get(selectedTicker.value) ?? null
  })

  const hasReadyTickers = computed<boolean>(() => {
    return [...tickers.value.values()].some((t) => t.stage === 'ready')
  })

  const scanProgress = computed<{ current: number; total: number }>(() => {
    const all = [...tickers.value.values()]
    const total = all.length
    const current = all.filter(
      (t) => t.stage === 'ready' || t.stage === 'failed',
    ).length
    return { current, total }
  })

  const selectedCount = computed<number>(() => selectedForAnalysis.value.size)

  // --- Actions ---

  interface StartScanOptions {
    preset: string
    sectors?: string[]
    customTickers?: string[]
    source?: 'manual'
  }

  async function startScan(options: StartScanOptions): Promise<number> {
    const body: Record<string, unknown> = { preset: options.preset }
    if (options.sectors && options.sectors.length > 0) {
      body.sectors = options.sectors
    }
    if (options.customTickers && options.customTickers.length > 0) {
      body.custom_tickers = options.customTickers
    }
    if (options.source) {
      body.source = options.source
    }

    loading.value = true
    errors.value = []
    try {
      const res = await api<{ scan_id: number }>('/api/scan', {
        method: 'POST',
        body,
      })
      scanId.value = res.scan_id
      phase.value = 'scanning'
      tickers.value = new Map()
      return res.scan_id
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Failed to start scan'
      errors.value.push({ message })
      throw err
    } finally {
      loading.value = false
    }
  }

  async function analyzeTicker(ticker: string): Promise<number> {
    const entry = tickers.value.get(ticker)
    if (entry) {
      entry.stage = 'analyzing'
    }

    try {
      const body: Record<string, unknown> = { ticker }
      if (scanId.value !== null) body.scan_id = scanId.value
      const res = await api<{ debate_id: number }>('/api/debate', {
        method: 'POST',
        body,
      })
      return res.debate_id
    } catch (err) {
      if (entry) {
        entry.stage = 'failed'
        entry.error =
          err instanceof Error ? err.message : 'Analysis failed'
      }
      throw err
    }
  }

  async function analyzeBatch(tickerList: string[]): Promise<number> {
    if (scanId.value === null) {
      throw new Error('No scan ID available for batch analysis')
    }

    // Mark all tickers as analyzing
    for (const t of tickerList) {
      const entry = tickers.value.get(t)
      if (entry) {
        entry.stage = 'analyzing'
      }
    }

    try {
      const res = await api<{ batch_id: number; tickers: string[] }>(
        '/api/debate/batch',
        {
          method: 'POST',
          body: {
            scan_id: scanId.value,
            tickers: tickerList,
            limit: tickerList.length,
          },
        },
      )
      batchId.value = res.batch_id
      return res.batch_id
    } catch (err) {
      for (const t of tickerList) {
        const entry = tickers.value.get(t)
        if (entry) {
          entry.stage = 'failed'
          entry.error =
            err instanceof Error ? err.message : 'Batch analysis failed'
        }
      }
      throw err
    }
  }

  function toggleSelectedForAnalysis(ticker: string): void {
    const next = new Set(selectedForAnalysis.value)
    if (next.has(ticker)) {
      next.delete(ticker)
    } else {
      next.add(ticker)
    }
    selectedForAnalysis.value = next
  }

  function setSelectedForAnalysis(tickerList: string[]): void {
    selectedForAnalysis.value = new Set(tickerList)
  }

  function clearSelectedForAnalysis(): void {
    selectedForAnalysis.value = new Set()
  }

  function selectTicker(ticker: string | null): void {
    selectedTicker.value = ticker
    currentRecommendation.value = null
  }

  async function loadRecommendation(debateId: number): Promise<void> {
    loading.value = true
    try {
      currentRecommendation.value = await api<RecommendationDetail>(
        `/api/debate/${debateId}`,
      )
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Failed to load recommendation'
      errors.value.push({ message })
    } finally {
      loading.value = false
    }
  }

  function reset(): void {
    tickers.value = new Map()
    selectedTicker.value = null
    currentRecommendation.value = null
    scanId.value = null
    dbScanId.value = null
    batchId.value = null
    phase.value = 'idle'
    loading.value = false
    errors.value = []
    selectedForAnalysis.value = new Set()
  }

  // --- WebSocket callbacks ---

  function onScanProgress(event: ScanProgressEvent): void {
    // Only transition idle → scanning, never revert scanned → scanning
    if (phase.value === 'idle') {
      phase.value = 'scanning'
    }
  }

  function onScanComplete(event: ScanCompleteEvent): void {
    dbScanId.value = event.scan_id
    phase.value = 'scanned'
  }

  function onDebateComplete(ticker: string, debateId: number): void {
    const entry = tickers.value.get(ticker)
    if (entry) {
      entry.stage = 'ready'
      entry.recommendation_id = debateId
      entry.error = null
    }
  }

  function onBatchProgress(event: BatchProgressEvent): void {
    const entry = tickers.value.get(event.ticker)
    if (entry) {
      entry.stage =
        event.status === 'started'
          ? 'analyzing'
          : event.status === 'completed'
            ? 'ready'
            : event.status === 'failed'
              ? 'failed'
              : (entry.stage as PipelineStage)
    }
  }

  function onBatchComplete(event: BatchCompleteEvent): void {
    for (const result of event.results) {
      const entry = tickers.value.get(result.ticker)
      if (entry) {
        if (result.error) {
          entry.stage = 'failed'
          entry.error = result.error
        } else {
          entry.stage = 'ready'
          entry.recommendation_id = result.debate_id
          if (result.direction) {
            entry.direction = result.direction.toUpperCase() as Direction
          }
        }
      }
    }
    batchId.value = null
  }

  /** Populate tickers from scan results (called after scan complete). */
  function setTickersFromScores(
    scores: Array<{
      ticker: string
      composite_score: number
      direction: string
      direction_confidence?: number | null
      sector?: string | null
      company_name?: string | null
    }>,
  ): void {
    const map = new Map<string, PipelineTicker>()
    for (const s of scores) {
      map.set(s.ticker, {
        ticker: s.ticker,
        stage: 'scored',
        composite_score: s.composite_score,
        direction: s.direction.toUpperCase() as Direction,
        direction_confidence: s.direction_confidence ?? null,
        sector: s.sector ?? null,
        company_name: s.company_name ?? null,
        recommendation_id: null,
        error: null,
      })
    }
    tickers.value = map
  }

  return {
    // State
    tickers,
    selectedTicker,
    currentRecommendation,
    scanId,
    dbScanId,
    batchId,
    phase,
    loading,
    errors,
    selectedForAnalysis,
    // Getters
    sortedTickers,
    selectedPipelineTicker,
    hasReadyTickers,
    scanProgress,
    selectedCount,
    // Actions
    startScan,
    analyzeTicker,
    analyzeBatch,
    toggleSelectedForAnalysis,
    setSelectedForAnalysis,
    clearSelectedForAnalysis,
    selectTicker,
    loadRecommendation,
    reset,
    setTickersFromScores,
    // WS callbacks
    onScanProgress,
    onScanComplete,
    onDebateComplete,
    onBatchProgress,
    onBatchComplete,
  }
})

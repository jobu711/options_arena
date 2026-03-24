import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { usePipelineStore } from '@/stores/pipeline'
import type { PipelineTicker, Direction } from '@/types/recommendation'
import type {
  ScanProgressEvent,
  ScanCompleteEvent,
  BatchProgressEvent,
  BatchCompleteEvent,
} from '@/types/ws'

// Mock the API module
vi.mock('@/composables/useApi', () => ({
  api: vi.fn(),
  ApiError: class ApiError extends Error {
    status: number
    constructor(status: number, message: string) {
      super(message)
      this.name = 'ApiError'
      this.status = status
    }
  },
}))

function makeTicker(overrides: Partial<PipelineTicker> = {}): PipelineTicker {
  return {
    ticker: 'AAPL',
    stage: 'scored',
    composite_score: 8.5,
    direction: 'BULLISH' as Direction,
    direction_confidence: 0.72,
    sector: 'Technology',
    company_name: 'Apple Inc.',
    recommendation_id: null,
    error: null,
    ...overrides,
  }
}

describe('usePipelineStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('starts in idle phase with empty tickers', () => {
    const store = usePipelineStore()
    expect(store.phase).toBe('idle')
    expect(store.tickers.size).toBe(0)
    expect(store.selectedTicker).toBeNull()
    expect(store.currentRecommendation).toBeNull()
    expect(store.scanId).toBeNull()
    expect(store.batchId).toBeNull()
    expect(store.loading).toBe(false)
    expect(store.errors).toHaveLength(0)
  })

  it('transitions to scanning on startScan', async () => {
    const { api } = await import('@/composables/useApi')
    const mockApi = vi.mocked(api)
    mockApi.mockResolvedValueOnce({ scan_id: 42 })

    const store = usePipelineStore()
    const scanId = await store.startScan({ preset: 'sp500' })

    expect(scanId).toBe(42)
    expect(store.phase).toBe('scanning')
    expect(store.scanId).toBe(42)
    expect(store.tickers.size).toBe(0)
  })

  it('adds tickers via setTickersFromScores', () => {
    const store = usePipelineStore()
    store.setTickersFromScores([
      { ticker: 'AAPL', composite_score: 8.5, direction: 'BULLISH', direction_confidence: 0.72, sector: 'Technology', company_name: 'Apple Inc.' },
      { ticker: 'MSFT', composite_score: 7.2, direction: 'BEARISH', direction_confidence: 0.65, sector: 'Technology', company_name: 'Microsoft Corp.' },
    ])

    expect(store.tickers.size).toBe(2)
    expect(store.tickers.get('AAPL')?.stage).toBe('scored')
    expect(store.tickers.get('MSFT')?.composite_score).toBe(7.2)
  })

  it('does not create duplicate tickers on setTickersFromScores', () => {
    const store = usePipelineStore()
    store.setTickersFromScores([
      { ticker: 'AAPL', composite_score: 8.5, direction: 'BULLISH' },
      { ticker: 'AAPL', composite_score: 9.0, direction: 'BULLISH' },
    ])

    // Map deduplicates by key; last wins
    expect(store.tickers.size).toBe(1)
    expect(store.tickers.get('AAPL')?.composite_score).toBe(9.0)
  })

  it('transitions to scanned on onScanComplete', () => {
    const store = usePipelineStore()
    store.phase = 'scanning'

    const event: ScanCompleteEvent = {
      type: 'complete',
      scan_id: 42,
      cancelled: false,
      outcomes_collected: 10,
    }
    store.onScanComplete(event)

    expect(store.phase).toBe('scanned')
    expect(store.scanId).toBe(42)
  })

  it('sets phase to scanning on onScanProgress', () => {
    const store = usePipelineStore()
    expect(store.phase).toBe('idle')

    const event: ScanProgressEvent = {
      type: 'progress',
      phase: 'scoring',
      current: 10,
      total: 100,
    }
    store.onScanProgress(event)

    expect(store.phase).toBe('scanning')
  })

  it('sets ticker stage to analyzing on analyzeTicker', async () => {
    const { api } = await import('@/composables/useApi')
    const mockApi = vi.mocked(api)
    mockApi.mockResolvedValueOnce({ debate_id: 99 })

    const store = usePipelineStore()
    store.tickers.set('AAPL', makeTicker({ ticker: 'AAPL', stage: 'scored' }))

    const debateId = await store.analyzeTicker('AAPL')

    expect(debateId).toBe(99)
    expect(store.tickers.get('AAPL')?.stage).toBe('analyzing')
  })

  it('sets ticker stage to ready on onDebateComplete', () => {
    const store = usePipelineStore()
    store.tickers.set('AAPL', makeTicker({ ticker: 'AAPL', stage: 'analyzing' }))

    store.onDebateComplete('AAPL', 99)

    const entry = store.tickers.get('AAPL')
    expect(entry?.stage).toBe('ready')
    expect(entry?.recommendation_id).toBe(99)
    expect(entry?.error).toBeNull()
  })

  it('ignores onDebateComplete for unknown ticker', () => {
    const store = usePipelineStore()
    // No tickers set
    store.onDebateComplete('ZZZZ', 99)

    expect(store.tickers.size).toBe(0)
  })

  it('loads recommendation detail on loadRecommendation', async () => {
    const { api } = await import('@/composables/useApi')
    const mockApi = vi.mocked(api)
    const fakeDetail = { id: 99, ticker: 'AAPL', assessments: [], recommendation: {} }
    mockApi.mockResolvedValueOnce(fakeDetail)

    const store = usePipelineStore()
    await store.loadRecommendation(99)

    expect(store.currentRecommendation).toEqual(fakeDetail)
    expect(store.loading).toBe(false)
  })

  it('resets all state on reset', () => {
    const store = usePipelineStore()
    // Set some state
    store.tickers.set('AAPL', makeTicker())
    store.selectedTicker = 'AAPL'
    store.phase = 'scanned'
    store.scanId = 42
    store.batchId = 10
    store.errors = [{ message: 'test error' }]

    store.reset()

    expect(store.tickers.size).toBe(0)
    expect(store.selectedTicker).toBeNull()
    expect(store.currentRecommendation).toBeNull()
    expect(store.scanId).toBeNull()
    expect(store.batchId).toBeNull()
    expect(store.phase).toBe('idle')
    expect(store.loading).toBe(false)
    expect(store.errors).toHaveLength(0)
    expect(store.selectedForAnalysis.size).toBe(0)
  })

  it('sortedTickers returns by composite_score desc', () => {
    const store = usePipelineStore()
    store.tickers.set('MSFT', makeTicker({ ticker: 'MSFT', composite_score: 6.0 }))
    store.tickers.set('AAPL', makeTicker({ ticker: 'AAPL', composite_score: 9.0 }))
    store.tickers.set('GOOG', makeTicker({ ticker: 'GOOG', composite_score: 7.5 }))

    const sorted = store.sortedTickers
    expect(sorted[0].ticker).toBe('AAPL')
    expect(sorted[1].ticker).toBe('GOOG')
    expect(sorted[2].ticker).toBe('MSFT')
  })

  it('handles batch progress events per-ticker', () => {
    const store = usePipelineStore()
    store.tickers.set('AAPL', makeTicker({ ticker: 'AAPL', stage: 'scored' }))
    store.tickers.set('MSFT', makeTicker({ ticker: 'MSFT', stage: 'scored' }))

    const event1: BatchProgressEvent = {
      type: 'batch_progress',
      ticker: 'AAPL',
      index: 0,
      total: 2,
      status: 'started',
    }
    store.onBatchProgress(event1)
    expect(store.tickers.get('AAPL')?.stage).toBe('analyzing')

    const event2: BatchProgressEvent = {
      type: 'batch_progress',
      ticker: 'AAPL',
      index: 0,
      total: 2,
      status: 'completed',
    }
    store.onBatchProgress(event2)
    expect(store.tickers.get('AAPL')?.stage).toBe('ready')

    const event3: BatchProgressEvent = {
      type: 'batch_progress',
      ticker: 'MSFT',
      index: 1,
      total: 2,
      status: 'failed',
    }
    store.onBatchProgress(event3)
    expect(store.tickers.get('MSFT')?.stage).toBe('failed')
  })

  it('handles batch complete event', () => {
    const store = usePipelineStore()
    store.batchId = 10
    store.tickers.set('AAPL', makeTicker({ ticker: 'AAPL', stage: 'analyzing' }))
    store.tickers.set('MSFT', makeTicker({ ticker: 'MSFT', stage: 'analyzing' }))

    const event: BatchCompleteEvent = {
      type: 'batch_complete',
      results: [
        { ticker: 'AAPL', debate_id: 100, direction: 'BULLISH', confidence: 0.8, error: null },
        { ticker: 'MSFT', debate_id: null, direction: null, confidence: null, error: 'Rate limited' },
      ],
    }
    store.onBatchComplete(event)

    expect(store.tickers.get('AAPL')?.stage).toBe('ready')
    expect(store.tickers.get('AAPL')?.recommendation_id).toBe(100)
    expect(store.tickers.get('AAPL')?.direction).toBe('BULLISH')

    expect(store.tickers.get('MSFT')?.stage).toBe('failed')
    expect(store.tickers.get('MSFT')?.error).toBe('Rate limited')

    expect(store.batchId).toBeNull()
  })

  it('selectedPipelineTicker returns correct ticker', () => {
    const store = usePipelineStore()
    store.tickers.set('AAPL', makeTicker({ ticker: 'AAPL' }))
    store.tickers.set('MSFT', makeTicker({ ticker: 'MSFT' }))

    expect(store.selectedPipelineTicker).toBeNull()

    store.selectedTicker = 'AAPL'
    expect(store.selectedPipelineTicker?.ticker).toBe('AAPL')

    store.selectedTicker = 'ZZZZ'
    expect(store.selectedPipelineTicker).toBeNull()
  })

  it('hasReadyTickers returns true when ready tickers exist', () => {
    const store = usePipelineStore()
    expect(store.hasReadyTickers).toBe(false)

    store.tickers.set('AAPL', makeTicker({ ticker: 'AAPL', stage: 'scored' }))
    expect(store.hasReadyTickers).toBe(false)

    store.tickers.set('MSFT', makeTicker({ ticker: 'MSFT', stage: 'ready' }))
    expect(store.hasReadyTickers).toBe(true)
  })

  it('selectTicker sets selected and clears recommendation', () => {
    const store = usePipelineStore()
    store.currentRecommendation = { id: 1 } as never
    store.selectTicker('AAPL')

    expect(store.selectedTicker).toBe('AAPL')
    expect(store.currentRecommendation).toBeNull()
  })

  it('toggleSelectedForAnalysis adds and removes tickers', () => {
    const store = usePipelineStore()
    expect(store.selectedCount).toBe(0)

    store.toggleSelectedForAnalysis('AAPL')
    expect(store.selectedForAnalysis.has('AAPL')).toBe(true)
    expect(store.selectedCount).toBe(1)

    store.toggleSelectedForAnalysis('AAPL')
    expect(store.selectedForAnalysis.has('AAPL')).toBe(false)
    expect(store.selectedCount).toBe(0)
  })

  it('scanProgress returns correct current/total', () => {
    const store = usePipelineStore()
    store.tickers.set('AAPL', makeTicker({ ticker: 'AAPL', stage: 'ready' }))
    store.tickers.set('MSFT', makeTicker({ ticker: 'MSFT', stage: 'analyzing' }))
    store.tickers.set('GOOG', makeTicker({ ticker: 'GOOG', stage: 'failed' }))
    store.tickers.set('TSLA', makeTicker({ ticker: 'TSLA', stage: 'scored' }))

    const progress = store.scanProgress
    expect(progress.total).toBe(4)
    // ready + failed = 2
    expect(progress.current).toBe(2)
  })
})

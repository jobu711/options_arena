/**
 * Predefined WebSocket event sequences for deterministic E2E tests.
 *
 * Each function returns an array of typed events that can be replayed
 * via page.evaluate() to simulate backend WebSocket behavior.
 */

import type {
  ScanEvent,
  DebateEvent,
  BatchEvent,
  BatchTickerResultEvent,
} from '../../../src/types/ws'

// ---------------------------------------------------------------------------
// Scan scenarios
// ---------------------------------------------------------------------------

/** Complete 4-phase scan: universe → scoring → options → persist → complete. */
export function scanProgressSequence(
  scanId: number,
  outcomesCollected: number = 0,
): ScanEvent[] {
  return [
    { type: 'progress', phase: 'universe', current: 0, total: 503 },
    { type: 'progress', phase: 'universe', current: 250, total: 503 },
    { type: 'progress', phase: 'universe', current: 503, total: 503 },
    { type: 'progress', phase: 'scoring', current: 0, total: 487 },
    { type: 'progress', phase: 'scoring', current: 250, total: 487 },
    { type: 'progress', phase: 'scoring', current: 487, total: 487 },
    { type: 'progress', phase: 'options', current: 0, total: 50 },
    { type: 'progress', phase: 'options', current: 25, total: 50 },
    { type: 'progress', phase: 'options', current: 50, total: 50 },
    { type: 'progress', phase: 'persist', current: 1, total: 1 },
    { type: 'complete', scan_id: scanId, cancelled: false, outcomes_collected: outcomesCollected },
  ]
}

/** Scan that fails during scoring phase. */
export function scanErrorSequence(): ScanEvent[] {
  return [
    { type: 'progress', phase: 'universe', current: 0, total: 503 },
    { type: 'progress', phase: 'universe', current: 503, total: 503 },
    { type: 'progress', phase: 'scoring', current: 100, total: 487 },
    { type: 'error', message: 'Yahoo Finance rate limit exceeded' },
  ]
}

/** Scan cancelled by user after partial progress. */
export function scanCancelSequence(scanId: number): ScanEvent[] {
  return [
    { type: 'progress', phase: 'universe', current: 0, total: 503 },
    { type: 'progress', phase: 'universe', current: 100, total: 503 },
    { type: 'complete', scan_id: scanId, cancelled: true, outcomes_collected: 0 },
  ]
}

// ---------------------------------------------------------------------------
// Single debate scenarios
// ---------------------------------------------------------------------------

/** Complete standard debate: bull → bear → risk → complete. */
export function debateProgressSequence(debateId: number): DebateEvent[] {
  return [
    { type: 'agent', name: 'bull', status: 'started', confidence: null },
    { type: 'agent', name: 'bull', status: 'completed', confidence: 0.72 },
    { type: 'agent', name: 'bear', status: 'started', confidence: null },
    { type: 'agent', name: 'bear', status: 'completed', confidence: 0.58 },
    { type: 'agent', name: 'risk', status: 'started', confidence: null },
    { type: 'agent', name: 'risk', status: 'completed', confidence: 0.65 },
    { type: 'complete', debate_id: debateId },
  ]
}

/** Debate with rebuttal enabled: bull → bear → rebuttal + risk (parallel). */
export function debateRebuttalSequence(debateId: number): DebateEvent[] {
  return [
    { type: 'agent', name: 'bull', status: 'started', confidence: null },
    { type: 'agent', name: 'bull', status: 'completed', confidence: 0.72 },
    { type: 'agent', name: 'bear', status: 'started', confidence: null },
    { type: 'agent', name: 'bear', status: 'completed', confidence: 0.58 },
    { type: 'agent', name: 'rebuttal', status: 'started', confidence: null },
    { type: 'agent', name: 'rebuttal', status: 'completed', confidence: 0.78 },
    { type: 'agent', name: 'risk', status: 'started', confidence: null },
    { type: 'agent', name: 'risk', status: 'completed', confidence: 0.65 },
    { type: 'complete', debate_id: debateId },
  ]
}

/** Debate where bear agent fails → triggers error. */
export function debatePartialFailSequence(debateId: number): DebateEvent[] {
  return [
    { type: 'agent', name: 'bull', status: 'started', confidence: null },
    { type: 'agent', name: 'bull', status: 'completed', confidence: 0.72 },
    { type: 'agent', name: 'bear', status: 'started', confidence: null },
    { type: 'agent', name: 'bear', status: 'failed', confidence: null },
    { type: 'error', message: 'Bear agent timed out after 60s' },
  ]
}

// ---------------------------------------------------------------------------
// Batch debate scenarios
// ---------------------------------------------------------------------------

/** Batch debate with 3 tickers, all succeed. */
export function batchSuccessSequence(): BatchEvent[] {
  const tickers = ['AAPL', 'MSFT', 'GOOGL']
  const events: BatchEvent[] = []

  tickers.forEach((ticker, i) => {
    events.push({ type: 'batch_progress', ticker, index: i + 1, total: 3, status: 'started' })
    events.push({ type: 'agent', ticker, name: 'bull', status: 'started', confidence: null })
    events.push({ type: 'agent', ticker, name: 'bull', status: 'completed', confidence: 0.7 + i * 0.02 })
    events.push({ type: 'agent', ticker, name: 'bear', status: 'started', confidence: null })
    events.push({ type: 'agent', ticker, name: 'bear', status: 'completed', confidence: 0.5 + i * 0.03 })
    events.push({ type: 'agent', ticker, name: 'risk', status: 'started', confidence: null })
    events.push({ type: 'agent', ticker, name: 'risk', status: 'completed', confidence: 0.6 + i * 0.02 })
    events.push({ type: 'batch_progress', ticker, index: i + 1, total: 3, status: 'completed' })
  })

  const results: BatchTickerResultEvent[] = [
    { ticker: 'AAPL', debate_id: 101, direction: 'bullish', confidence: 0.68, error: null },
    { ticker: 'MSFT', debate_id: 102, direction: 'bearish', confidence: 0.55, error: null },
    { ticker: 'GOOGL', debate_id: 103, direction: 'bullish', confidence: 0.71, error: null },
  ]
  events.push({ type: 'batch_complete', results })

  return events
}

/** Batch where one ticker fails (GOOGL), others succeed. */
export function batchPartialFailSequence(): BatchEvent[] {
  const events: BatchEvent[] = []

  // AAPL succeeds
  events.push({ type: 'batch_progress', ticker: 'AAPL', index: 1, total: 3, status: 'started' })
  events.push({ type: 'agent', ticker: 'AAPL', name: 'bull', status: 'completed', confidence: 0.72 })
  events.push({ type: 'agent', ticker: 'AAPL', name: 'bear', status: 'completed', confidence: 0.58 })
  events.push({ type: 'agent', ticker: 'AAPL', name: 'risk', status: 'completed', confidence: 0.65 })
  events.push({ type: 'batch_progress', ticker: 'AAPL', index: 1, total: 3, status: 'completed' })

  // MSFT succeeds
  events.push({ type: 'batch_progress', ticker: 'MSFT', index: 2, total: 3, status: 'started' })
  events.push({ type: 'agent', ticker: 'MSFT', name: 'bull', status: 'completed', confidence: 0.60 })
  events.push({ type: 'agent', ticker: 'MSFT', name: 'bear', status: 'completed', confidence: 0.65 })
  events.push({ type: 'agent', ticker: 'MSFT', name: 'risk', status: 'completed', confidence: 0.55 })
  events.push({ type: 'batch_progress', ticker: 'MSFT', index: 2, total: 3, status: 'completed' })

  // GOOGL fails
  events.push({ type: 'batch_progress', ticker: 'GOOGL', index: 3, total: 3, status: 'started' })
  events.push({ type: 'agent', ticker: 'GOOGL', name: 'bull', status: 'started', confidence: null })
  events.push({ type: 'agent', ticker: 'GOOGL', name: 'bull', status: 'failed', confidence: null })
  events.push({ type: 'error', message: 'Debate failed for GOOGL', ticker: 'GOOGL' })
  events.push({ type: 'batch_progress', ticker: 'GOOGL', index: 3, total: 3, status: 'failed' })

  const results: BatchTickerResultEvent[] = [
    { ticker: 'AAPL', debate_id: 101, direction: 'bullish', confidence: 0.65, error: null },
    { ticker: 'MSFT', debate_id: 102, direction: 'bearish', confidence: 0.55, error: null },
    { ticker: 'GOOGL', debate_id: null, direction: null, confidence: null, error: 'Debate failed for GOOGL' },
  ]
  events.push({ type: 'batch_complete', results })

  return events
}

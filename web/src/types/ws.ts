/** WebSocket event discriminated unions. */

// --- Scan events (Server → Client) ---

export interface ScanProgressEvent {
  type: 'progress'
  phase: 'universe' | 'scoring' | 'options' | 'persist'
  current: number
  total: number
}

export interface ScanErrorEvent {
  type: 'error'
  message: string
}

export interface ScanCompleteEvent {
  type: 'complete'
  scan_id: number
  cancelled: boolean
}

export type ScanEvent = ScanProgressEvent | ScanErrorEvent | ScanCompleteEvent

// --- Debate events (Server → Client) ---

export interface DebateAgentEvent {
  type: 'agent'
  name: 'bull' | 'bear' | 'rebuttal' | 'volatility' | 'risk'
  status: 'started' | 'completed' | 'failed'
  confidence: number | null
}

export interface DebateCompleteEvent {
  type: 'complete'
  debate_id: number
}

export interface DebateErrorEvent {
  type: 'error'
  message: string
}

export type DebateEvent = DebateAgentEvent | DebateCompleteEvent | DebateErrorEvent

// --- Batch debate events (Server → Client) ---

export interface BatchProgressEvent {
  type: 'batch_progress'
  ticker: string
  index: number
  total: number
  status: 'started' | 'completed' | 'failed'
}

export interface BatchAgentEvent {
  type: 'agent'
  ticker: string
  name: 'bull' | 'bear' | 'rebuttal' | 'volatility' | 'risk'
  status: 'started' | 'completed' | 'failed'
  confidence: number | null
}

export interface BatchTickerResultEvent {
  ticker: string
  debate_id: number | null
  direction: string | null
  confidence: number | null
  error: string | null
}

export interface BatchCompleteEvent {
  type: 'batch_complete'
  results: BatchTickerResultEvent[]
}

export interface BatchErrorEvent {
  type: 'error'
  message: string
  ticker?: string
}

export type BatchEvent =
  | BatchProgressEvent
  | BatchAgentEvent
  | BatchCompleteEvent
  | BatchErrorEvent

// --- Client → Server ---

export interface CancelMessage {
  type: 'cancel'
}

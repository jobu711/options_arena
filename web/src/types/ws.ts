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

// --- Client → Server ---

export interface CancelMessage {
  type: 'cancel'
}

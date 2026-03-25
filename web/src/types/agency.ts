/** Types for the interactive desk agent query system. */

export type DeskType =
  | 'volatility'
  | 'risk'
  | 'trend'
  | 'flow'
  | 'fundamental'
  | 'contrarian'
  | 'research'

export interface QueryIntent {
  desks: DeskType[]
  query_type: string
  tickers: string[]
}

export interface DeskAgentResponse {
  desk: DeskType
  response: string
  tools_used: string[]
  confidence: number
}

export interface Citation {
  source: string
  content: string
  desk: DeskType
}

export interface AgencyResponse {
  query_id: string
  query_text: string
  intent: QueryIntent
  desk_responses: DeskAgentResponse[]
  synthesis: string
  citations: Citation[]
  confidence: number
  created_at: string
}

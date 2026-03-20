/** TypeScript interfaces for agency desk-related API models. */

export interface DeskInfo {
  name: string
  description: string
  tools: number
  color: string
}

export interface DeskResponseData {
  desk: string
  response: string
  tools_used: string[]
  confidence: number
}

export interface QueryIntent {
  desks: string[]
  query_type: string
  tickers: string[]
}

export interface Citation {
  source: string
  content: string
  desk: string
}

export interface AgencyResponse {
  query_id: string
  query_text: string
  intent: QueryIntent
  desk_responses: DeskResponseData[]
  synthesis: string
  citations: Citation[]
  confidence: number
  created_at: string
}

export interface AgencyQueryRequest {
  query_text: string
  ticker: string
  desk_override?: string
}

/** API client functions for agency desk queries. */
import { api } from '@/composables/useApi'

// ---------------------------------------------------------------------------
// Request / Response types
// ---------------------------------------------------------------------------

export interface AgencyQueryRequest {
  query: string
  desk?: string | null
  tickers?: string[] | null
}

export interface DeskResponseSummary {
  desk: string
  response: string
  tools_used: string[]
  confidence: number
}

export interface Citation {
  source: string
  content: string
  desk: string
}

export interface QueryIntent {
  desks: string[]
  query_type: string
  tickers: string[]
}

export interface AgencyResponseData {
  query_id: string
  query_text: string
  intent: QueryIntent
  desk_responses: DeskResponseSummary[]
  synthesis: string
  citations: Citation[]
  confidence: number
  created_at: string
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

export async function submitAgencyQuery(
  request: AgencyQueryRequest,
): Promise<AgencyResponseData> {
  return api<AgencyResponseData>('/api/agency/query', {
    method: 'POST',
    body: request,
  })
}

export async function getAgencyQuery(queryId: string): Promise<AgencyResponseData> {
  return api<AgencyResponseData>(`/api/agency/query/${queryId}`)
}

export async function listAgencyQueries(
  limit: number = 20,
): Promise<AgencyResponseData[]> {
  return api<AgencyResponseData[]>('/api/agency/queries', {
    params: { limit },
  })
}

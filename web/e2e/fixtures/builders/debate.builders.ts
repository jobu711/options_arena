import type {
  DebateResult,
  AgentResponse,
  TradeThesis,
  DebateResultSummary,
} from '../../../src/types'

export function buildAgentResponse(overrides: Partial<AgentResponse> = {}): AgentResponse {
  return {
    agent_name: 'bull',
    direction: 'bullish',
    confidence: 0.72,
    argument: 'AAPL shows strong momentum with RSI at 55 and positive MACD crossover. '
      + 'Institutional accumulation on rising OBV supports the bullish thesis.',
    key_points: [
      'Strong earnings momentum with 15% YoY revenue growth',
      'Technical breakout above 200-day SMA',
      'Institutional accumulation on rising OBV',
    ],
    risks_cited: [
      'Extended P/E ratio at 28x forward earnings',
      'Potential sector rotation out of mega-cap tech',
    ],
    contracts_referenced: ['AAPL 2026-03-21 $195 Call'],
    model_used: 'llama-3.3-70b-versatile',
    ...overrides,
  }
}

export function buildTradeThesis(overrides: Partial<TradeThesis> = {}): TradeThesis {
  return {
    ticker: 'AAPL',
    direction: 'bullish',
    confidence: 0.68,
    summary: 'Moderately bullish outlook supported by technical momentum and earnings growth.',
    bull_score: 7.2,
    bear_score: 4.8,
    key_factors: [
      'Positive MACD crossover with expanding histogram',
      'Above 200-day SMA with rising volume',
      'Options flow showing institutional call buying',
    ],
    risk_assessment: 'Moderate risk. P/E is stretched but justified by growth. Key risk is macro.',
    recommended_strategy: 'Bull call spread: Buy $190C / Sell $200C, Mar 21 expiry',
    ...overrides,
  }
}

export function buildDebateResult(overrides: Partial<DebateResult> = {}): DebateResult {
  return {
    id: 1,
    ticker: 'AAPL',
    is_fallback: false,
    model_name: 'llama-3.3-70b-versatile',
    duration_ms: 12500,
    total_tokens: 4200,
    created_at: '2026-02-26T14:10:00+00:00',
    debate_mode: 'standard',
    citation_density: 0.85,
    bull_response: buildAgentResponse({
      agent_name: 'bull',
      direction: 'bullish',
      confidence: 0.72,
    }),
    bear_response: buildAgentResponse({
      agent_name: 'bear',
      direction: 'bearish',
      confidence: 0.58,
      argument: 'AAPL faces headwinds from elevated valuation and macro uncertainty.',
      key_points: [
        'P/E at 28x exceeds 5-year average',
        'Services revenue growth decelerating',
      ],
      risks_cited: [
        'Federal Reserve tightening cycle',
        'iPhone demand softening in China',
      ],
    }),
    thesis: buildTradeThesis(),
    ...overrides,
  }
}

export function buildFallbackDebateResult(
  overrides: Partial<DebateResult> = {},
): DebateResult {
  return buildDebateResult({
    is_fallback: true,
    debate_mode: null,
    citation_density: null,
    bull_response: undefined,
    bear_response: undefined,
    thesis: buildTradeThesis({ confidence: 0.3 }),
    ...overrides,
  })
}

export function buildDebateSummary(
  overrides: Partial<DebateResultSummary> = {},
): DebateResultSummary {
  return {
    id: 1,
    ticker: 'AAPL',
    direction: 'bullish',
    confidence: 0.68,
    is_fallback: false,
    model_name: 'llama-3.3-70b-versatile',
    duration_ms: 12500,
    created_at: '2026-02-26T14:10:00+00:00',
    ...overrides,
  }
}

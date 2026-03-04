<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import Button from 'primevue/button'
import Tag from 'primevue/tag'
import AgentCard from '@/components/AgentCard.vue'
import DirectionBadge from '@/components/DirectionBadge.vue'
import ConfidenceBadge from '@/components/ConfidenceBadge.vue'
import { useDebateStore } from '@/stores/debate'
import type { AgentResponse } from '@/types/debate'

const route = useRoute()
const debateStore = useDebateStore()
const debateId = Number(route.params.id)

/** Shorthand for the current debate result. */
const debate = computed(() => debateStore.currentDebate)

function tryParseAgent(json: string | undefined): AgentResponse | null {
  if (!json) return null
  try {
    return JSON.parse(json) as AgentResponse
  } catch {
    return null
  }
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString()
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)
}

function formatRatio(value: number): string {
  return value.toFixed(2)
}

function sentimentColorClass(label: string | null): string {
  if (!label) return ''
  const lower = label.toLowerCase()
  if (lower === 'positive' || lower === 'bullish') return 'sentiment-positive'
  if (lower === 'negative' || lower === 'bearish') return 'sentiment-negative'
  return ''
}

/** True when any fundamental enrichment field is populated. */
const hasFundamentalEnrichment = computed(() => {
  const d = debate.value
  if (!d) return false
  return [
    d.pe_ratio, d.forward_pe, d.peg_ratio, d.price_to_book,
    d.debt_to_equity, d.revenue_growth, d.profit_margin,
  ].some((v) => v != null)
})

/** True when any unusual flow enrichment field is populated. */
const hasFlowEnrichment = computed(() => {
  const d = debate.value
  return d != null && (d.net_call_premium != null || d.net_put_premium != null)
})

function exportDebate(fmt: 'md' | 'pdf'): void {
  window.open(`/api/debate/${debateId}/export?format=${fmt}`, '_blank')
}

onMounted(() => void debateStore.fetchDebate(debateId))
</script>

<template>
  <div class="page">
    <!-- Loading State -->
    <div v-if="debateStore.loading" class="loading-msg" data-testid="loading-skeleton">Loading debate...</div>

    <!-- Error State -->
    <div v-else-if="debateStore.error" class="error-msg" data-testid="error-state">{{ debateStore.error }}</div>

    <!-- Debate Content -->
    <template v-else-if="debateStore.currentDebate">
      <div class="page-header">
        <div class="header-left">
          <h1>{{ debateStore.currentDebate.ticker }} Debate</h1>
          <Tag
            v-if="debateStore.currentDebate.is_fallback"
            value="Fallback"
            severity="warn"
            data-testid="fallback-badge"
          />
        </div>
        <div class="header-actions">
          <Button
            label="Export MD"
            icon="pi pi-download"
            severity="secondary"
            size="small"
            data-testid="debate-export-md"
            @click="exportDebate('md')"
          />
          <Button
            label="Export PDF"
            icon="pi pi-file-pdf"
            severity="secondary"
            size="small"
            data-testid="debate-export-pdf"
            @click="exportDebate('pdf')"
          />
        </div>
      </div>

      <!-- Thesis Banner -->
      <div v-if="debateStore.currentDebate.thesis" class="thesis-banner" data-testid="thesis-card">
        <div class="thesis-main">
          <div class="thesis-verdict">
            <span class="verdict-label">Verdict</span>
            <DirectionBadge
              :direction="debateStore.currentDebate.thesis.direction as 'bullish' | 'bearish' | 'neutral'"
              data-testid="thesis-direction"
            />
          </div>
          <div class="thesis-confidence">
            <span class="verdict-label">Confidence</span>
            <ConfidenceBadge :value="debateStore.currentDebate.thesis.confidence" />
          </div>
          <div class="thesis-scores">
            <span class="score-item">
              <span class="score-label">Bull</span>
              <span class="score-value mono">{{ debateStore.currentDebate.thesis.bull_score.toFixed(1) }}</span>
            </span>
            <span class="score-item">
              <span class="score-label">Bear</span>
              <span class="score-value mono">{{ debateStore.currentDebate.thesis.bear_score.toFixed(1) }}</span>
            </span>
          </div>
          <div v-if="debateStore.currentDebate.thesis.recommended_strategy" class="thesis-strategy">
            <span class="verdict-label">Strategy</span>
            <span class="strategy-value">{{ debateStore.currentDebate.thesis.recommended_strategy }}</span>
          </div>
        </div>
        <p class="thesis-summary" data-testid="thesis-summary">{{ debateStore.currentDebate.thesis.summary }}</p>
        <div v-if="debateStore.currentDebate.thesis.key_factors.length > 0" class="thesis-factors">
          <span class="factors-label">Key Factors:</span>
          <span
            v-for="(f, i) in debateStore.currentDebate.thesis.key_factors"
            :key="i"
            class="factor-tag"
          >{{ f }}</span>
        </div>
        <p class="thesis-risk">{{ debateStore.currentDebate.thesis.risk_assessment }}</p>
      </div>

      <!-- Agent Cards Grid -->
      <div class="agents-grid">
        <AgentCard
          v-if="debateStore.currentDebate.bull_response"
          agent-name="Bull Agent"
          :response="debateStore.currentDebate.bull_response"
          color="#22c55e"
          data-testid="agent-card-bull"
        />
        <AgentCard
          v-if="debateStore.currentDebate.bear_response"
          agent-name="Bear Agent"
          :response="debateStore.currentDebate.bear_response"
          color="#ef4444"
          data-testid="agent-card-bear"
        />
        <AgentCard
          v-if="tryParseAgent(debateStore.currentDebate.bull_rebuttal)"
          agent-name="Bull Rebuttal"
          :response="tryParseAgent(debateStore.currentDebate.bull_rebuttal)!"
          color="#86efac"
          data-testid="agent-card-rebuttal"
        />
        <AgentCard
          v-if="tryParseAgent(debateStore.currentDebate.vol_response)"
          agent-name="Volatility Agent"
          :response="tryParseAgent(debateStore.currentDebate.vol_response)!"
          color="#a855f7"
          data-testid="agent-card-volatility"
        />
      </div>

      <!-- Fundamental Profile (OpenBB enrichment) -->
      <div v-if="hasFundamentalEnrichment" class="enrichment-section" data-testid="fundamental-profile">
        <h3 class="enrichment-header">Fundamental Profile</h3>
        <div class="enrichment-grid">
          <div v-if="debate?.pe_ratio != null" class="meta-item">
            <span class="meta-label">P/E Ratio</span>
            <span class="meta-value mono">{{ formatRatio(debate.pe_ratio) }}</span>
          </div>
          <div v-if="debate?.forward_pe != null" class="meta-item">
            <span class="meta-label">Forward P/E</span>
            <span class="meta-value mono">{{ formatRatio(debate.forward_pe) }}</span>
          </div>
          <div v-if="debate?.peg_ratio != null" class="meta-item">
            <span class="meta-label">PEG Ratio</span>
            <span class="meta-value mono">{{ formatRatio(debate.peg_ratio) }}</span>
          </div>
          <div v-if="debate?.price_to_book != null" class="meta-item">
            <span class="meta-label">Price/Book</span>
            <span class="meta-value mono">{{ formatRatio(debate.price_to_book) }}</span>
          </div>
          <div v-if="debate?.debt_to_equity != null" class="meta-item">
            <span class="meta-label">Debt/Equity</span>
            <span class="meta-value mono">{{ formatRatio(debate.debt_to_equity) }}</span>
          </div>
          <div v-if="debate?.revenue_growth != null" class="meta-item">
            <span class="meta-label">Revenue Growth</span>
            <span class="meta-value mono">{{ formatPercent(debate.revenue_growth) }}</span>
          </div>
          <div v-if="debate?.profit_margin != null" class="meta-item">
            <span class="meta-label">Profit Margin</span>
            <span class="meta-value mono">{{ formatPercent(debate.profit_margin) }}</span>
          </div>
        </div>
      </div>

      <!-- Unusual Flow (OpenBB enrichment) -->
      <div v-if="hasFlowEnrichment" class="enrichment-section" data-testid="unusual-flow">
        <h3 class="enrichment-header">Unusual Flow</h3>
        <div class="enrichment-grid">
          <div class="meta-item">
            <span class="meta-label">Net Call Premium</span>
            <span class="meta-value mono">{{ formatCurrency(debate!.net_call_premium!) }}</span>
          </div>
          <div v-if="debate?.net_put_premium != null" class="meta-item">
            <span class="meta-label">Net Put Premium</span>
            <span class="meta-value mono">{{ formatCurrency(debate!.net_put_premium!) }}</span>
          </div>
        </div>
      </div>

      <!-- News Sentiment (OpenBB enrichment) -->
      <div v-if="debate?.news_sentiment_score != null" class="enrichment-section" data-testid="news-sentiment">
        <h3 class="enrichment-header">News Sentiment</h3>
        <div class="enrichment-grid">
          <div class="meta-item">
            <span class="meta-label">Sentiment Score</span>
            <span
              class="meta-value mono"
              :class="sentimentColorClass(debate?.news_sentiment_label ?? null)"
            >{{ debate!.news_sentiment_score!.toFixed(2) }}</span>
          </div>
          <div v-if="debate?.news_sentiment_label != null" class="meta-item">
            <span class="meta-label">Sentiment Label</span>
            <span
              class="meta-value"
              :class="sentimentColorClass(debate!.news_sentiment_label!)"
            >{{ debate!.news_sentiment_label }}</span>
          </div>
        </div>
      </div>

      <!-- Metadata Strip -->
      <div class="metadata-strip">
        <div class="meta-item">
          <span class="meta-label">Model</span>
          <span class="meta-value">{{ debateStore.currentDebate.model_name }}</span>
        </div>
        <div class="meta-item">
          <span class="meta-label">Duration</span>
          <span class="meta-value mono">{{ formatDuration(debateStore.currentDebate.duration_ms) }}</span>
        </div>
        <div class="meta-item">
          <span class="meta-label">Tokens</span>
          <span class="meta-value mono">{{ debateStore.currentDebate.total_tokens.toLocaleString() }}</span>
        </div>
        <div v-if="debateStore.currentDebate.citation_density !== null" class="meta-item">
          <span class="meta-label">Citation Density</span>
          <span class="meta-value mono">{{ (debateStore.currentDebate.citation_density * 100).toFixed(0) }}%</span>
        </div>
        <div v-if="debate?.enrichment_ratio != null" class="meta-item">
          <span class="meta-label">Enrichment</span>
          <span class="meta-value mono">{{ (debate.enrichment_ratio * 100).toFixed(0) }}%</span>
        </div>
        <div v-if="debateStore.currentDebate.debate_mode" class="meta-item">
          <span class="meta-label">Mode</span>
          <span class="meta-value">{{ debateStore.currentDebate.debate_mode }}</span>
        </div>
        <div class="meta-item">
          <span class="meta-label">Date</span>
          <span class="meta-value">{{ formatDate(debateStore.currentDebate.created_at) }}</span>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1.5rem;
  flex-wrap: wrap;
  gap: 0.75rem;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.header-left h1 {
  margin: 0;
}

.header-actions {
  display: flex;
  gap: 0.5rem;
}

/* Thesis Banner */
.thesis-banner {
  background: var(--p-surface-800, #1a1a1a);
  border: 1px solid var(--p-surface-700, #333);
  border-radius: 0.5rem;
  padding: 1.25rem;
  margin-bottom: 1.5rem;
}

.thesis-main {
  display: flex;
  align-items: center;
  gap: 1.5rem;
  flex-wrap: wrap;
  margin-bottom: 0.75rem;
}

.thesis-verdict,
.thesis-confidence,
.thesis-strategy {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.verdict-label {
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--p-surface-400, #888);
}

.thesis-scores {
  display: flex;
  gap: 1rem;
}

.score-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.1rem;
}

.score-label {
  font-size: 0.7rem;
  text-transform: uppercase;
  color: var(--p-surface-400, #888);
}

.score-value {
  font-size: 1.1rem;
  font-weight: 600;
}

.strategy-value {
  text-transform: capitalize;
  font-weight: 500;
}

.thesis-summary {
  font-size: 0.9rem;
  color: var(--p-surface-200, #ccc);
  line-height: 1.5;
  margin: 0 0 0.5rem 0;
}

.thesis-factors {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem;
  margin-bottom: 0.5rem;
}

.factors-label {
  font-size: 0.8rem;
  color: var(--p-surface-400, #888);
}

.factor-tag {
  font-size: 0.75rem;
  background: var(--p-surface-700, #333);
  padding: 0.15rem 0.5rem;
  border-radius: 0.25rem;
  color: var(--p-surface-200, #ccc);
}

.thesis-risk {
  font-size: 0.85rem;
  color: var(--p-surface-400, #888);
  margin: 0;
  font-style: italic;
}

/* Agent Cards Grid */
.agents-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 1rem;
  margin-bottom: 1.5rem;
}

/* Metadata Strip */
.metadata-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 1.5rem;
  padding: 0.75rem 1rem;
  background: var(--p-surface-800, #1a1a1a);
  border: 1px solid var(--p-surface-700, #333);
  border-radius: 0.375rem;
}

.meta-item {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}

.meta-label {
  font-size: 0.7rem;
  text-transform: uppercase;
  color: var(--p-surface-500, #666);
}

.meta-value {
  font-size: 0.85rem;
  color: var(--p-surface-200, #ccc);
}

.mono {
  font-family: var(--font-mono);
}

/* Enrichment Sections (OpenBB) */
.enrichment-section {
  background: var(--p-surface-800, #1a1a1a);
  border: 1px solid var(--p-surface-700, #333);
  border-radius: 8px;
  padding: 1rem;
  margin-bottom: 1rem;
}

.enrichment-header {
  color: var(--p-text-muted-color, var(--p-surface-400, #888));
  font-size: 0.85rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin: 0 0 0.75rem 0;
  font-weight: 600;
}

.enrichment-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
}

.sentiment-positive {
  color: var(--accent-green, #22c55e);
}

.sentiment-negative {
  color: var(--accent-red, #ef4444);
}

.loading-msg,
.error-msg {
  padding: 2rem;
  text-align: center;
}

.error-msg {
  color: var(--accent-red);
}

.loading-msg {
  color: var(--p-surface-400, #888);
}
</style>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Button from 'primevue/button'
import Tag from 'primevue/tag'
import DirectionBadge from '@/components/DirectionBadge.vue'
import ScoreHistoryChart from '@/components/ScoreHistoryChart.vue'
import { api } from '@/composables/useApi'
import { formatPrice, formatDateShort, formatDateOnly, formatDateTime } from '@/utils/formatters'
import type { HistoryPoint, DebateResultSummary, TickerInfoResponse, RecommendedContract } from '@/types'

const route = useRoute()
const router = useRouter()

const ticker = String(route.params.ticker).toUpperCase()
const history = ref<HistoryPoint[]>([])
const debates = ref<DebateResultSummary[]>([])
const tickerInfo = ref<TickerInfoResponse | null>(null)
const contracts = ref<RecommendedContract[]>([])
const loading = ref(true)

const latestPoint = ref<HistoryPoint | null>(null)

function formatConfidence(val: number): string {
  return `${(val * 100).toFixed(0)}%`
}

function formatMarketCap(cap: number): string {
  if (cap >= 1_000_000_000_000) return `$${(cap / 1_000_000_000_000).toFixed(1)}T`
  if (cap >= 1_000_000_000) return `$${(cap / 1_000_000_000).toFixed(1)}B`
  if (cap >= 1_000_000) return `$${(cap / 1_000_000).toFixed(0)}M`
  return `$${cap.toLocaleString()}`
}

async function loadData(): Promise<void> {
  loading.value = true
  try {
    const [historyData, debateData, infoData, contractData] = await Promise.allSettled([
      api<HistoryPoint[]>(`/api/ticker/${ticker}/history`, { params: { limit: 20 } }),
      api<DebateResultSummary[]>('/api/debate', { params: { ticker, limit: 10 } }),
      api<TickerInfoResponse>(`/api/ticker/${ticker}/info`),
      api<RecommendedContract[]>(`/api/analytics/ticker/${ticker}/contracts`, { params: { limit: 20 } }),
    ])
    history.value = historyData.status === 'fulfilled' ? historyData.value : []
    debates.value = debateData.status === 'fulfilled' ? debateData.value : []
    tickerInfo.value = infoData.status === 'fulfilled' ? infoData.value : null
    contracts.value = contractData.status === 'fulfilled' ? contractData.value : []
    latestPoint.value = history.value.length > 0 ? history.value[history.value.length - 1] : null
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void loadData()
})
</script>

<template>
  <div class="page">
    <div class="page-header">
      <Button
        icon="pi pi-arrow-left"
        severity="secondary"
        size="small"
        text
        @click="router.back()"
      />
      <h1>{{ ticker }}</h1>
      <span v-if="tickerInfo" class="company-name">{{ tickerInfo.company_name }}</span>
    </div>

    <div v-if="loading" class="loading-msg">Loading...</div>

    <template v-else>
      <!-- Company Info Card -->
      <section v-if="tickerInfo" class="section info-card" data-testid="ticker-info">
        <div class="info-grid">
          <div class="info-item">
            <span class="info-label">Price</span>
            <span class="info-value mono">{{ formatPrice(tickerInfo.current_price) }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">Sector</span>
            <span class="info-value">{{ tickerInfo.sector }}</span>
          </div>
          <div v-if="tickerInfo.market_cap" class="info-item">
            <span class="info-label">Market Cap</span>
            <span class="info-value mono">{{ formatMarketCap(tickerInfo.market_cap) }}</span>
          </div>
          <div v-if="tickerInfo.market_cap_tier" class="info-item">
            <span class="info-label">Tier</span>
            <Tag :value="tickerInfo.market_cap_tier" severity="info" />
          </div>
          <div class="info-item">
            <span class="info-label">52W High</span>
            <span class="info-value mono">{{ formatPrice(tickerInfo.fifty_two_week_high) }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">52W Low</span>
            <span class="info-value mono">{{ formatPrice(tickerInfo.fifty_two_week_low) }}</span>
          </div>
          <div v-if="tickerInfo.dividend_yield > 0" class="info-item">
            <span class="info-label">Div Yield</span>
            <span class="info-value mono">{{ (tickerInfo.dividend_yield * 100).toFixed(2) }}%</span>
          </div>
        </div>
      </section>

      <!-- Latest Score Summary -->
      <section v-if="latestPoint" class="section" data-testid="ticker-latest-score">
        <div class="latest-summary">
          <span class="score-value mono">{{ latestPoint.composite_score.toFixed(1) }}</span>
          <DirectionBadge :direction="latestPoint.direction" />
          <span class="score-date">as of {{ formatDateShort(latestPoint.scan_date) }}</span>
        </div>
      </section>

      <!-- Score History Chart -->
      <section class="section">
        <h2>Score History</h2>
        <ScoreHistoryChart :history="history" />
      </section>

      <!-- Contract History -->
      <section v-if="contracts.length > 0" class="section" data-testid="ticker-contracts">
        <h2>Recent Contracts</h2>
        <div class="contract-list">
          <div v-for="c in contracts" :key="c.id ?? `${c.ticker}-${c.strike}-${c.expiration}`" class="contract-row">
            <Tag :value="c.option_type.toUpperCase()" :severity="c.option_type === 'call' ? 'success' : 'danger'" />
            <span class="mono contract-strike">{{ formatPrice(c.strike) }}</span>
            <span class="contract-exp">{{ formatDateOnly(c.expiration) }}</span>
            <DirectionBadge :direction="c.direction" />
            <span class="mono contract-score">{{ c.composite_score.toFixed(1) }}</span>
            <span v-if="c.delta != null" class="mono contract-delta">&delta; {{ c.delta.toFixed(2) }}</span>
            <span class="mono contract-mid">Mid {{ formatPrice(c.entry_mid) }}</span>
            <span class="contract-date">{{ formatDateShort(c.created_at) }}</span>
          </div>
        </div>
      </section>

      <!-- Past Debates -->
      <section class="section">
        <h2>Past Debates</h2>
        <div v-if="debates.length === 0" class="muted">No debates for this ticker yet.</div>
        <div v-else class="debate-list" data-testid="ticker-debates">
          <div
            v-for="d in debates"
            :key="d.id"
            class="debate-row"
            @click="router.push(`/debate/${d.id}`)"
          >
            <DirectionBadge :direction="d.direction as 'bullish' | 'bearish' | 'neutral'" />
            <span class="mono debate-conf">{{ formatConfidence(d.confidence) }}</span>
            <span class="debate-model">{{ d.model_name }}</span>
            <span class="debate-date">{{ formatDateShort(d.created_at) }}</span>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 1rem;
}

.page-header h1 {
  margin: 0;
  font-family: var(--font-mono);
}

.company-name {
  font-size: 0.9rem;
  color: var(--p-surface-400, #888);
}

.section {
  margin-bottom: 2rem;
}

.section h2 {
  font-size: 1.1rem;
  margin-bottom: 0.75rem;
  color: var(--p-surface-200, #ccc);
}

.info-card {
  background: var(--p-surface-800, #1a1a1a);
  border: 1px solid var(--p-surface-700, #333);
  border-radius: 0.5rem;
  padding: 1rem;
}

.info-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 1.25rem;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}

.info-label {
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--p-surface-500, #666);
}

.info-value {
  font-size: 0.95rem;
  color: var(--p-surface-100, #eee);
}

.latest-summary {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.score-value {
  font-size: 2rem;
  font-weight: 700;
}

.score-date {
  font-size: 0.85rem;
  color: var(--p-surface-500, #666);
}

.contract-list {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.contract-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 0.75rem;
  background: var(--p-surface-800, #1a1a1a);
  border: 1px solid var(--p-surface-700, #333);
  border-radius: 0.375rem;
  font-size: 0.85rem;
}

.contract-strike {
  font-weight: 600;
}

.contract-exp,
.contract-date {
  color: var(--p-surface-400, #888);
  font-size: 0.75rem;
}

.contract-score {
  color: var(--p-surface-300, #aaa);
}

.contract-delta {
  color: var(--accent-blue);
  font-size: 0.75rem;
}

.contract-mid {
  color: var(--p-surface-300, #aaa);
  font-size: 0.75rem;
}

.contract-date {
  margin-left: auto;
}

.debate-list {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.debate-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 0.75rem;
  background: var(--p-surface-800, #1a1a1a);
  border: 1px solid var(--p-surface-700, #333);
  border-radius: 0.375rem;
  cursor: pointer;
  transition: border-color 0.15s;
}

.debate-row:hover {
  border-color: var(--p-surface-500, #666);
}

.debate-conf {
  font-size: 0.875rem;
  color: var(--p-surface-300, #aaa);
}

.debate-model {
  font-size: 0.75rem;
  color: var(--p-surface-500, #666);
}

.debate-date {
  margin-left: auto;
  font-size: 0.75rem;
  color: var(--p-surface-500, #666);
}

.mono {
  font-family: var(--font-mono);
}

.muted {
  font-size: 0.85rem;
  color: var(--p-surface-500, #666);
}

.loading-msg {
  color: var(--p-surface-400, #888);
  padding: 2rem 0;
}
</style>

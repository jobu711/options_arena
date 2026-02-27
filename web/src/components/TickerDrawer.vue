<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import Drawer from 'primevue/drawer'
import Button from 'primevue/button'
import DirectionBadge from './DirectionBadge.vue'
import DebateTrendChart from './DebateTrendChart.vue'
import { api } from '@/composables/useApi'
import { useDebateStore } from '@/stores/debate'
import type { TickerScore, TickerDetail, OptionContract, DebateResultSummary } from '@/types'

interface Props {
  visible: boolean
  score: TickerScore | null
  scanId: number
}

const props = defineProps<Props>()
const emit = defineEmits<{ 'update:visible': [value: boolean] }>()
const router = useRouter()

const debateStore = useDebateStore()
const debates = ref<DebateResultSummary[]>([])
const contracts = ref<OptionContract[]>([])
const loadingDebates = ref(false)
const nextEarnings = ref<string | null>(null)

const earningsDaysAway = computed<number | null>(() => {
  if (!nextEarnings.value) return null
  const today = new Date()
  const earnings = new Date(nextEarnings.value)
  const diffMs = earnings.getTime() - today.getTime()
  return Math.ceil(diffMs / (1000 * 60 * 60 * 24))
})

function formatEarningsDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

watch(
  () => props.score?.ticker,
  async (ticker) => {
    if (!ticker) {
      debates.value = []
      contracts.value = []
      return
    }
    loadingDebates.value = true
    try {
      debates.value = await api<DebateResultSummary[]>('/api/debate', {
        params: { ticker, limit: 5 },
      })
    } catch {
      debates.value = []
    } finally {
      loadingDebates.value = false
    }
    // Fetch recommended contracts
    try {
      const detail = await api<TickerDetail>(
        `/api/scan/${props.scanId}/scores/${ticker}`,
      )
      contracts.value = detail.contracts
    } catch {
      contracts.value = []
    }
    // Fetch trend data for chart
    void debateStore.fetchTrend(ticker)
  },
)

/** Format signal names for display: rsi → RSI, bb_width → BB Width */
function formatSignalName(key: string): string {
  return key
    .split('_')
    .map((w) => w.toUpperCase())
    .join(' ')
}

function formatSignalValue(val: number | null): string {
  if (val === null) return '--'
  return val.toFixed(2)
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString()
}

function formatPrice(price: string): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(price))
}

function formatExpiration(iso: string): string {
  return new Date(iso + 'T00:00:00').toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
  })
}
</script>

<template>
  <Drawer
    :visible="visible"
    position="right"
    :header="score?.ticker ?? 'Ticker Detail'"
    :style="{ width: '400px' }"
    data-testid="ticker-drawer"
    @update:visible="emit('update:visible', $event)"
  >
    <template v-if="score">
      <div class="drawer-section">
        <h3>Score</h3>
        <div class="score-row">
          <span class="score-value mono">{{ score.composite_score.toFixed(1) }}</span>
          <DirectionBadge :direction="score.direction" />
        </div>
      </div>

      <div class="drawer-section">
        <h3>Indicators</h3>
        <div class="signal-grid">
          <div
            v-for="(val, key) in score.signals"
            :key="key"
            class="signal-row"
          >
            <span class="signal-name">{{ formatSignalName(String(key)) }}</span>
            <span class="signal-value mono">{{ formatSignalValue(val as number | null) }}</span>
          </div>
        </div>
      </div>

      <div class="drawer-section" v-if="contracts.length > 0">
        <h3>Recommended Contracts</h3>
        <div class="contract-list">
          <div
            v-for="(c, i) in contracts"
            :key="i"
            class="contract-card"
          >
            <div class="contract-header">
              <span class="contract-type" :class="c.option_type">
                {{ c.option_type.toUpperCase() }}
              </span>
              <span class="mono">{{ formatPrice(c.strike) }}</span>
              <span class="contract-exp">
                {{ formatExpiration(c.expiration) }}
                <span class="dte-badge">{{ c.dte }}d</span>
              </span>
            </div>
            <div class="contract-details">
              <span>Bid {{ formatPrice(c.bid) }}</span>
              <span>Ask {{ formatPrice(c.ask) }}</span>
              <span>Vol {{ c.volume.toLocaleString() }}</span>
              <span>OI {{ c.open_interest.toLocaleString() }}</span>
            </div>
            <div v-if="c.greeks" class="contract-greeks">
              <span>&delta; {{ c.greeks.delta.toFixed(3) }}</span>
              <span>&gamma; {{ c.greeks.gamma.toFixed(4) }}</span>
              <span>&theta; {{ c.greeks.theta.toFixed(4) }}</span>
              <span>&nu; {{ c.greeks.vega.toFixed(4) }}</span>
            </div>
          </div>
        </div>
      </div>

      <div class="drawer-section">
        <h3>Next Earnings</h3>
        <div class="earnings-info">
          <span v-if="nextEarnings" class="earnings-date">
            {{ formatEarningsDate(nextEarnings) }}
            <span
              class="earnings-countdown"
              :class="{ 'earnings-warning': earningsDaysAway !== null && earningsDaysAway < 7 }"
            >
              ({{ earningsDaysAway }} days)
            </span>
          </span>
          <span v-else class="muted">N/A</span>
        </div>
      </div>

      <div class="drawer-section">
        <h3>Past Debates</h3>
        <div v-if="loadingDebates" class="muted">Loading...</div>
        <div v-else-if="debates.length === 0" class="muted">No debates for this ticker.</div>
        <div v-else class="debate-list">
          <div
            v-for="d in debates"
            :key="d.id"
            class="debate-item"
            @click="router.push(`/debate/${d.id}`)"
          >
            <DirectionBadge :direction="d.direction as 'bullish' | 'bearish' | 'neutral'" />
            <span class="mono">{{ (d.confidence * 100).toFixed(0) }}%</span>
            <span class="debate-date">{{ formatDate(d.created_at) }}</span>
          </div>
        </div>
      </div>

      <div v-if="debateStore.trendData.length >= 2" class="drawer-section">
        <h3>Confidence Trend</h3>
        <DebateTrendChart :points="debateStore.trendData" :height="150" />
      </div>

      <div class="drawer-actions">
        <Button
          label="Debate This Ticker"
          icon="pi pi-comments"
          severity="info"
          size="small"
          disabled
        />
      </div>
    </template>
  </Drawer>
</template>

<style scoped>
.drawer-section {
  margin-bottom: 1.25rem;
}

.drawer-section h3 {
  font-size: 0.9rem;
  margin: 0 0 0.5rem 0;
  color: var(--p-surface-300, #aaa);
}

.score-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.score-value {
  font-size: 1.5rem;
  font-weight: 700;
}

.signal-grid {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 0.25rem 1rem;
}

.signal-row {
  display: contents;
}

.signal-name {
  font-size: 0.8rem;
  color: var(--p-surface-400, #888);
}

.signal-value {
  font-size: 0.8rem;
  text-align: right;
}

.earnings-info {
  font-size: 0.9rem;
}

.earnings-date {
  color: var(--p-surface-200, #ccc);
}

.earnings-countdown {
  color: var(--p-surface-400, #888);
  font-size: 0.8rem;
}

.earnings-warning {
  color: var(--accent-yellow);
  font-weight: 600;
}

.debate-list {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.debate-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.35rem 0.5rem;
  border-radius: 0.25rem;
  cursor: pointer;
  font-size: 0.8rem;
}

.debate-item:hover {
  background: var(--p-surface-700, #333);
}

.debate-date {
  margin-left: auto;
  color: var(--p-surface-500, #666);
  font-size: 0.75rem;
}

.contract-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.contract-card {
  padding: 0.5rem;
  border: 1px solid var(--p-surface-700, #333);
  border-radius: 0.375rem;
  font-size: 0.8rem;
}

.contract-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.25rem;
}

.contract-type {
  padding: 0.1rem 0.35rem;
  border-radius: 0.2rem;
  font-weight: 600;
  font-size: 0.7rem;
}

.contract-type.call {
  background: rgba(34, 197, 94, 0.15);
  color: var(--accent-green);
}

.contract-type.put {
  background: rgba(239, 68, 68, 0.15);
  color: var(--accent-red);
}

.contract-exp {
  margin-left: auto;
  color: var(--p-surface-400, #888);
  font-size: 0.75rem;
}

.dte-badge {
  font-family: var(--font-mono);
  color: var(--p-surface-300, #aaa);
}

.contract-details {
  display: flex;
  gap: 0.75rem;
  color: var(--p-surface-400, #888);
  font-size: 0.75rem;
  font-family: var(--font-mono);
}

.contract-greeks {
  display: flex;
  gap: 0.75rem;
  margin-top: 0.2rem;
  color: var(--p-surface-400, #888);
  font-size: 0.7rem;
  font-family: var(--font-mono);
}

.muted {
  font-size: 0.85rem;
  color: var(--p-surface-500, #666);
}

.mono {
  font-family: var(--font-mono);
}

.drawer-actions {
  margin-top: 1.5rem;
  padding-top: 1rem;
  border-top: 1px solid var(--p-surface-700, #333);
}
</style>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { computed } from 'vue'
import Drawer from 'primevue/drawer'
import Button from 'primevue/button'
import Select from 'primevue/select'
import Message from 'primevue/message'
import Tag from 'primevue/tag'
import DirectionBadge from './DirectionBadge.vue'
import ScoreHistoryChart from './ScoreHistoryChart.vue'
import DimensionalScoreBars from './DimensionalScoreBars.vue'
import DebateProgressModal from './DebateProgressModal.vue'
import { api, ApiError } from '@/composables/useApi'
import { formatPrice, formatDateTime, formatDateOnly } from '@/utils/formatters'
import { useWebSocket } from '@/composables/useWebSocket'
import { useWatchlistStore } from '@/stores/watchlist'
import { useDebateStore } from '@/stores/debate'
import { useOperationStore } from '@/stores/operation'
import { useToast } from 'primevue/usetoast'
import type { TickerScore, DebateResultSummary, HistoryPoint, TickerInfoResponse, RecommendedContract } from '@/types'
import type { DebateEvent } from '@/types/ws'

interface Props {
  visible: boolean
  score: TickerScore | null
  scanId: number
}

const props = defineProps<Props>()
const emit = defineEmits<{ 'update:visible': [value: boolean] }>()
const router = useRouter()

const debates = ref<DebateResultSummary[]>([])
const loadingDebates = ref(false)
const history = ref<HistoryPoint[]>([])
const loadingHistory = ref(false)
const contracts = ref<RecommendedContract[]>([])
const contractsLoading = ref(false)
const fetchedCompanyName = ref<string | null>(null)
const watchlistStore = useWatchlistStore()
const debateStore = useDebateStore()
const operationStore = useOperationStore()
const toastService = useToast()
const debateModalVisible = ref(false)
const debatingTicker = ref('')
const isDebating = ref(false)
let debateWsClose: (() => void) | null = null
const selectedWatchlistId = ref<number | null>(null)
const addingToWatchlist = ref(false)

function watchlistOptions(): Array<{ label: string; value: number }> {
  return watchlistStore.watchlists.map((w) => ({
    label: w.name,
    value: w.id,
  }))
}

async function onAddToWatchlist(): Promise<void> {
  if (selectedWatchlistId.value === null || !props.score?.ticker) return
  addingToWatchlist.value = true
  const added = await watchlistStore.addTicker(selectedWatchlistId.value, props.score.ticker)
  addingToWatchlist.value = false
  if (added) {
    toastService.add({
      severity: 'success',
      summary: 'Added',
      detail: `${props.score.ticker} added to watchlist.`,
      life: 3000,
    })
  } else {
    toastService.add({
      severity: 'error',
      summary: 'Error',
      detail: watchlistStore.error ?? 'Failed to add ticker',
      life: 5000,
    })
  }
}

async function startDebate(): Promise<void> {
  if (!props.score || isDebating.value) return
  const ticker = props.score.ticker
  try {
    debatingTicker.value = ticker
    debateModalVisible.value = true
    isDebating.value = true
    const debateId = await debateStore.startDebate(ticker, props.scanId)

    const { close } = useWebSocket<DebateEvent>({
      url: `/ws/debate/${debateId}`,
      onMessage(event) {
        switch (event.type) {
          case 'agent':
            debateStore.updateAgentProgress(event)
            break
          case 'error':
            debateStore.setDebateError(event.message)
            break
          case 'complete':
            debateStore.setDebateComplete(event.debate_id)
            close()
            debateModalVisible.value = false
            isDebating.value = false
            router.push(`/debate/${event.debate_id}`)
            break
        }
      },
    })
    debateWsClose = close
  } catch (e) {
    debateModalVisible.value = false
    isDebating.value = false
    debateStore.reset()
    const msg = e instanceof ApiError ? e.message : 'Failed to start debate'
    toastService.add({ severity: 'error', summary: 'Error', detail: msg, life: 5000 })
  }
}

onUnmounted(() => {
  debateWsClose?.()
})

onMounted(() => {
  void watchlistStore.fetchWatchlists()
})

watch(
  () => props.score?.ticker,
  async (ticker) => {
    fetchedCompanyName.value = null
    if (!ticker) {
      debates.value = []
      history.value = []
      contracts.value = []
      return
    }
    loadingDebates.value = true
    loadingHistory.value = true
    contractsLoading.value = true

    // Fire company name fetch separately to preserve type safety on the main Promise.all
    if (!props.score?.company_name) {
      api<TickerInfoResponse>(`/api/ticker/${ticker}/info`)
        .then((info) => {
          // Guard against stale response from a previous ticker
          if (props.score?.ticker === ticker) {
            fetchedCompanyName.value = info.company_name
          }
        })
        .catch(() => { /* leave as null — graceful fallback */ })
    }

    const fetches: Promise<unknown>[] = [
      api<DebateResultSummary[]>('/api/debate', {
        params: { ticker, limit: 5 },
      }).catch(() => [] as DebateResultSummary[]),
      api<HistoryPoint[]>(`/api/ticker/${ticker}/history`, {
        params: { limit: 20 },
      }).catch(() => [] as HistoryPoint[]),
      api<RecommendedContract[]>(`/api/analytics/ticker/${ticker}/contracts`, {
        params: { limit: 3 },
      }).catch(() => [] as RecommendedContract[]),
    ]

    try {
      const [debateData, historyData, contractData] = await Promise.all(fetches) as [
        DebateResultSummary[],
        HistoryPoint[],
        RecommendedContract[],
      ]
      debates.value = debateData
      history.value = historyData
      contracts.value = contractData
    } catch {
      debates.value = []
      history.value = []
      contracts.value = []
    } finally {
      loadingDebates.value = false
      loadingHistory.value = false
      contractsLoading.value = false
    }
  },
)

/** Compute days to next earnings from the score's next_earnings field. */
const earningsDays = computed<number | null>(() => {
  if (!props.score?.next_earnings) return null
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const earnings = new Date(props.score.next_earnings + 'T00:00:00')
  const diffMs = earnings.getTime() - today.getTime()
  return Math.round(diffMs / (1000 * 60 * 60 * 24))
})

/** Whether earnings warning banner should be shown (< 7 days). */
const showEarningsWarning = computed(() => earningsDays.value !== null && earningsDays.value < 7 && earningsDays.value >= 0)

interface SignalClassification {
  label: string
  severity: 'success' | 'danger' | 'warn' | 'info'
}

function classifySignal(key: string, value: number | null): SignalClassification | null {
  if (value === null) return null
  switch (key) {
    case 'rsi':
      if (value < 30) return { label: 'Oversold', severity: 'success' }
      if (value > 70) return { label: 'Overbought', severity: 'danger' }
      return null
    case 'stochastic_rsi':
      if (value < 20) return { label: 'Oversold', severity: 'success' }
      if (value > 80) return { label: 'Overbought', severity: 'danger' }
      return null
    case 'adx':
      if (value < 30) return { label: 'Weak', severity: 'warn' }
      if (value > 60) return { label: 'Strong Trend', severity: 'success' }
      return null
    case 'sma_alignment':
      if (value < 40) return { label: 'Bearish', severity: 'danger' }
      if (value > 60) return { label: 'Bullish', severity: 'success' }
      return null
    case 'relative_volume':
      if (value < 30) return { label: 'Low Vol', severity: 'info' }
      if (value > 70) return { label: 'High Vol', severity: 'warn' }
      return null
    case 'bb_width':
      if (value < 20) return { label: 'Compressed', severity: 'info' }
      if (value > 80) return { label: 'Expanded', severity: 'warn' }
      return null
    default:
      return null
  }
}

/** Pre-computed signal rows with classification (avoids calling classifySignal multiple times per row). */
const signalRows = computed(() => {
  if (!props.score?.signals) return []
  const signals = props.score.signals as Record<string, number | null>
  return Object.entries(signals).map(([key, value]) => ({
    key,
    value,
    classification: classifySignal(key, value),
  }))
})

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

function formatConfidence(val: number | null | undefined): string {
  if (val === null || val === undefined) return '--'
  return `${(val * 100).toFixed(0)}%`
}

const REGIME_LABELS: Record<string, string> = {
  trending: 'Trending',
  mean_reverting: 'Mean Reverting',
  volatile: 'Volatile',
  crisis: 'Crisis',
}

function regimeLabel(regime: string | null | undefined): string {
  if (!regime) return '--'
  return REGIME_LABELS[regime] ?? regime
}

function regimeClass(regime: string | null | undefined): string {
  if (!regime) return 'regime-badge--null'
  return `regime-badge--${regime.replace('_', '-')}`
}
</script>

<template>
  <Drawer
    :visible="visible"
    position="right"
    :style="{ width: '400px', maxWidth: '100vw' }"
    data-testid="ticker-drawer"
    @update:visible="emit('update:visible', $event)"
  >
    <template #header>
      <div class="drawer-header">
        <span class="drawer-ticker">{{ score?.ticker ?? 'Ticker Detail' }}</span>
        <span class="drawer-company-name" data-testid="drawer-company-name">
          {{ score?.company_name ?? fetchedCompanyName ?? '\u2014' }}
        </span>
      </div>
    </template>
    <template v-if="score">
      <Message
        v-if="showEarningsWarning"
        severity="warn"
        :closable="false"
        data-testid="earnings-warning"
      >
        Earnings in {{ earningsDays }} days &mdash; IV crush risk
      </Message>

      <div class="drawer-section">
        <h3>Score</h3>
        <div class="score-row">
          <span class="score-value mono">{{ score.composite_score.toFixed(1) }}</span>
          <DirectionBadge :direction="score.direction" />
        </div>
      </div>

      <div class="drawer-section" data-testid="drawer-score-history">
        <h3>Score History</h3>
        <div v-if="loadingHistory" class="muted"><i class="pi pi-spin pi-spinner" /> Loading history...</div>
        <ScoreHistoryChart v-else :history="history" />
      </div>

      <div class="drawer-section" data-testid="drawer-dimensional-scores">
        <h3>Dimensional Scores</h3>
        <div class="dim-meta-row">
          <span class="dim-meta-label">Confidence:</span>
          <span class="mono">{{ formatConfidence(score.direction_confidence) }}</span>
          <span class="dim-meta-label regime-meta-label">Regime:</span>
          <span
            class="regime-badge"
            :class="regimeClass(score.market_regime)"
          >{{ regimeLabel(score.market_regime) }}</span>
        </div>
        <DimensionalScoreBars :scores="score.dimensional_scores" />
      </div>

      <div class="drawer-section">
        <h3>Indicators</h3>
        <div class="signal-grid">
          <template
            v-for="{ key, value, classification } in signalRows"
            :key="key"
          >
            <span class="signal-name">{{ formatSignalName(key) }}</span>
            <span class="signal-value mono">{{ formatSignalValue(value) }}</span>
            <Tag
              v-if="classification"
              :value="classification.label"
              :severity="classification.severity"
              class="signal-tag"
            />
            <span v-else class="signal-tag-placeholder" />
          </template>
        </div>
      </div>

      <div class="drawer-section">
        <h3>Past Debates</h3>
        <div v-if="loadingDebates" class="muted"><i class="pi pi-spin pi-spinner" /> Loading...</div>
        <div v-else-if="debates.length === 0" class="muted">No debates for this ticker.</div>
        <div v-else class="debate-list">
          <div
            v-for="d in debates"
            :key="d.id"
            class="debate-item"
            tabindex="0"
            @click="router.push(`/debate/${d.id}`)"
            @keydown.enter="router.push(`/debate/${d.id}`)"
          >
            <DirectionBadge :direction="d.direction as 'bullish' | 'bearish' | 'neutral'" />
            <span class="mono">{{ (d.confidence * 100).toFixed(0) }}%</span>
            <span class="debate-date">{{ formatDateTime(d.created_at) }}</span>
          </div>
        </div>
      </div>

      <div v-if="contractsLoading || contracts.length > 0" class="drawer-section" data-testid="drawer-contracts">
        <h3>Recommended Contracts</h3>
        <div v-if="contractsLoading" class="muted"><i class="pi pi-spin pi-spinner" /> Loading contracts...</div>
        <div v-else class="contract-list">
          <div
            v-for="c in contracts"
            :key="`${c.option_type}-${c.strike}-${c.expiration}`"
            class="contract-item"
          >
            <div class="contract-header">
              <Tag :value="c.option_type" :severity="c.option_type === 'call' ? 'success' : 'danger'" />
              <span class="strike mono">{{ formatPrice(c.strike) }}</span>
              <span class="expiration">{{ formatDateOnly(c.expiration) }}</span>
            </div>
            <div class="contract-details">
              <DirectionBadge v-if="c.direction" :direction="c.direction" />
              <span v-if="c.delta != null" class="delta mono">&#916; {{ c.delta.toFixed(2) }}</span>
              <span class="score mono">Score: {{ c.composite_score.toFixed(1) }}</span>
            </div>
          </div>
        </div>
      </div>

      <div class="drawer-actions">
        <Button
          label="Debate This Ticker"
          icon="pi pi-comments"
          severity="info"
          size="small"
          :disabled="operationStore.inProgress || isDebating"
          v-tooltip="operationStore.inProgress ? 'Operation in progress' : undefined"
          @click="startDebate"
        />
      </div>

      <div class="drawer-section watchlist-section">
        <h3>Add to Watchlist</h3>
        <div v-if="watchlistStore.watchlists.length > 0" class="watchlist-add-row">
          <Select
            v-model="selectedWatchlistId"
            :options="watchlistOptions()"
            optionLabel="label"
            optionValue="value"
            placeholder="Select watchlist"
            size="small"
            data-testid="drawer-watchlist-select"
            class="watchlist-add-select"
          />
          <Button
            label="Add"
            icon="pi pi-plus"
            severity="success"
            size="small"
            :loading="addingToWatchlist"
            :disabled="selectedWatchlistId === null"
            data-testid="drawer-add-to-watchlist-btn"
            @click="onAddToWatchlist"
          />
        </div>
        <div v-else class="muted">
          No watchlists yet. Create one from the Watchlists page.
        </div>
      </div>
    </template>

    <DebateProgressModal
      v-model:visible="debateModalVisible"
      :ticker="debatingTicker"
      :agents="debateStore.agentProgress"
      :error="debateStore.error"
    />
  </Drawer>
</template>

<style scoped>
.drawer-header {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.drawer-ticker {
  font-size: 1.1rem;
  font-weight: 700;
  font-family: var(--font-mono);
}

.drawer-company-name {
  font-size: 0.85rem;
  color: var(--p-surface-400, #888);
  font-weight: 400;
}

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
  grid-template-columns: 1fr auto auto;
  gap: 0.25rem 1rem;
}

.signal-name {
  font-size: 0.8rem;
  color: var(--p-surface-400, #888);
}

.signal-value {
  font-size: 0.8rem;
  text-align: right;
}

.signal-tag {
  font-size: 0.7rem;
  padding: 0.1rem 0.4rem;
}

.signal-tag-placeholder {
  /* Empty spacer to maintain 3-column grid alignment */
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

.debate-item:focus-visible {
  outline: 2px solid var(--accent-blue, #3b82f6);
  outline-offset: -2px;
  background: var(--p-surface-700, #333);
}

.debate-date {
  margin-left: auto;
  color: var(--p-surface-500, #666);
  font-size: 0.75rem;
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

.watchlist-section {
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid var(--p-surface-700, #333);
}

.watchlist-add-row {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.watchlist-add-select {
  flex: 1;
}

.dim-meta-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
  font-size: 0.8rem;
}

.dim-meta-label {
  color: var(--p-surface-400, #888);
}

.regime-meta-label {
  margin-left: 0.5rem;
}

.regime-badge {
  display: inline-block;
  padding: 0.1rem 0.4rem;
  border-radius: 0.25rem;
  font-size: 0.75rem;
  font-weight: 500;
}

.regime-badge--trending {
  background: var(--accent-emerald, #10b981);
  color: #fff;
}

.regime-badge--mean-reverting {
  background: var(--accent-blue, #3b82f6);
  color: #fff;
}

.regime-badge--volatile {
  background: var(--accent-amber, #f59e0b);
  color: #111;
}

.regime-badge--crisis {
  background: var(--accent-red, #ef4444);
  color: #fff;
}

.regime-badge--null {
  background: var(--p-surface-700, #333);
  color: var(--p-surface-400, #888);
}

.contract-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.contract-item {
  padding: 0.5rem;
  border-radius: 0.25rem;
  background: var(--p-surface-800, #1e1e1e);
}

.contract-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.85rem;
}

.contract-details {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.35rem;
  font-size: 0.8rem;
}

.strike {
  font-weight: 600;
}

.expiration {
  margin-left: auto;
  color: var(--p-surface-400, #888);
  font-size: 0.75rem;
}

.delta {
  color: var(--p-surface-300, #aaa);
}

.score {
  margin-left: auto;
  color: var(--p-surface-300, #aaa);
}
</style>

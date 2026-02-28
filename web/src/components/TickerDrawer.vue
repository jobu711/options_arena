<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { computed } from 'vue'
import Drawer from 'primevue/drawer'
import Button from 'primevue/button'
import Message from 'primevue/message'
import DirectionBadge from './DirectionBadge.vue'
import { api } from '@/composables/useApi'
import type { TickerScore, DebateResultSummary } from '@/types'

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

watch(
  () => props.score?.ticker,
  async (ticker) => {
    if (!ticker) {
      debates.value = []
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

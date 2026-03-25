<script setup lang="ts">
import { ref, computed, onUnmounted, watch } from 'vue'
import { useToast } from 'primevue/usetoast'
import ScanControlBar from '@/components/ScanControlBar.vue'
import ScanProgressCard from '@/components/ScanProgressCard.vue'
import OpportunityTable from '@/components/OpportunityTable.vue'
import AgentConsensus from '@/components/AgentConsensus.vue'
import PositionCard from '@/components/PositionCard.vue'
import DeskAssessmentCard from '@/components/DeskAssessmentCard.vue'
import DeskCard from '@/components/DeskCard.vue'
import MarketHeatmap from '@/components/MarketHeatmap.vue'
import RegimeBanner from '@/components/RegimeBanner.vue'
import { usePipelineStore } from '@/stores/pipeline'
import { useScanStore } from '@/stores/scan'
import { useWebSocket } from '@/composables/useWebSocket'
import { api } from '@/composables/useApi'
import type {
  ScanEvent,
  DebateEvent,
  BatchEvent,
} from '@/types/ws'

const toast = useToast()
const pipelineStore = usePipelineStore()
const scanStore = useScanStore()

// --- Computed state ---
const isScanning = computed(() => pipelineStore.phase === 'scanning')
const scanPhase = computed(() => scanStore.progress?.phase ?? 'universe')
const scanCurrent = computed(() => scanStore.progress?.current ?? 0)
const scanTotal = computed(() => scanStore.progress?.total ?? 0)
const sortedTickers = computed(() => pipelineStore.sortedTickers)
const selectedTicker = computed(() => pipelineStore.selectedTicker)
const currentRecommendation = computed(() => pipelineStore.currentRecommendation)

// --- Scan started timestamp ---
const scanStartedAt = ref(new Date())

// --- WebSocket management ---
type WsHandle = { close: () => void }
const activeConnections = ref<WsHandle[]>([])

function trackConnection(handle: WsHandle): void {
  activeConnections.value.push(handle)
}

function closeAllConnections(): void {
  for (const conn of activeConnections.value) {
    conn.close()
  }
  activeConnections.value = []
}

// --- Scan WebSocket + completion poll ---
let completionPoll: ReturnType<typeof setInterval> | null = null

function stopCompletionPoll(): void {
  if (completionPoll !== null) {
    clearInterval(completionPoll)
    completionPoll = null
  }
}

watch(
  () => pipelineStore.scanId,
  (newScanId) => {
    if (newScanId === null) return
    scanStartedAt.value = new Date()

    // Connect WS for real-time progress
    const handle = useWebSocket<ScanEvent>({
      url: `/ws/scan/${newScanId}`,
      onMessage(event) {
        switch (event.type) {
          case 'progress':
            scanStore.updateProgress(event)
            pipelineStore.onScanProgress(event)
            break
          case 'error':
            scanStore.addError(event)
            toast.add({
              severity: 'error',
              summary: 'Scan Error',
              detail: event.message,
              life: 5000,
            })
            break
          case 'complete':
            stopCompletionPoll()
            pipelineStore.onScanComplete(event)
            void loadScoresIntoPipeline(event.scan_id)
            break
        }
      },
      onError() {
        // WS error is non-fatal — completion poll is the safety net
      },
      maxReconnectAttempts: 3,
    })
    trackConnection(handle)

    // Completion poll: checks /api/status every 5s. When busy=false and we're
    // still in 'scanning' phase, the scan finished but WS missed the event.
    stopCompletionPoll()
    completionPoll = setInterval(() => void checkScanCompletion(), 5000)
  },
)

async function checkScanCompletion(): Promise<void> {
  if (pipelineStore.phase !== 'scanning') {
    stopCompletionPoll()
    return
  }
  try {
    const status = await api<{ busy: boolean }>('/api/status')
    if (!status.busy) {
      stopCompletionPoll()
      // Scan finished — find the latest completed scan and load its scores
      const scans = await api<Array<{ id: number; completed_at: string | null }>>(
        '/api/scan', { params: { limit: 1 } },
      )
      const latest = scans[0]
      if (latest?.completed_at) {
        pipelineStore.onScanComplete({
          type: 'complete', scan_id: latest.id, cancelled: false, outcomes_collected: 0,
        })
        void loadScoresIntoPipeline(latest.id)
      }
    }
  } catch {
    // Poll failure is non-fatal
  }
}

async function loadScoresIntoPipeline(dbScanId: number): Promise<void> {
  try {
    await scanStore.fetchScores(dbScanId, { page_size: 200 })
    pipelineStore.setTickersFromScores(scanStore.scores)
  } catch (err) {
    toast.add({
      severity: 'error',
      summary: 'Failed to Load Scores',
      detail: err instanceof Error ? err.message : 'Could not fetch scan scores',
      life: 5000,
    })
  }
}

// --- Action handlers ---

function onSelectTicker(ticker: string): void {
  pipelineStore.selectTicker(ticker)
  const entry = pipelineStore.tickers.get(ticker)
  if (entry?.stage === 'ready' && entry.recommendation_id !== null) {
    void pipelineStore.loadRecommendation(entry.recommendation_id)
  }
}

function onSelectionChange(tickers: string[]): void {
  pipelineStore.setSelectedForAnalysis(tickers)
}

async function onAnalyzeTicker(ticker: string): Promise<void> {
  try {
    const debateId = await pipelineStore.analyzeTicker(ticker)
    connectDebateWs(ticker, debateId)
    startDebatePoll(ticker)
  } catch (err) {
    toast.add({
      severity: 'error',
      summary: 'Analysis Failed',
      detail: err instanceof Error ? err.message : 'Failed to start analysis',
      life: 5000,
    })
  }
}

// --- Debate completion poll (same pattern as scan) ---
let debatePollTimer: ReturnType<typeof setInterval> | null = null
let debatePollTicker: string | null = null

function startDebatePoll(ticker: string): void {
  stopDebatePoll()
  debatePollTicker = ticker
  debatePollTimer = setInterval(() => void checkDebateCompletion(), 5000)
}

function stopDebatePoll(): void {
  if (debatePollTimer !== null) {
    clearInterval(debatePollTimer)
    debatePollTimer = null
  }
  debatePollTicker = null
}

async function checkDebateCompletion(): Promise<void> {
  const ticker = debatePollTicker
  if (!ticker) { stopDebatePoll(); return }
  const entry = pipelineStore.tickers.get(ticker)
  if (!entry || entry.stage !== 'analyzing') { stopDebatePoll(); return }
  try {
    const status = await api<{ busy: boolean }>('/api/status')
    if (!status.busy) {
      stopDebatePoll()
      // Find the latest debate for this ticker
      const debates = await api<Array<{ id: number; ticker: string }>>(
        '/api/debate', { params: { limit: 5 } },
      )
      const match = debates.find((d) => d.ticker === ticker)
      if (match) {
        pipelineStore.onDebateComplete(ticker, match.id)
        void pipelineStore.loadRecommendation(match.id)
      }
    }
  } catch {
    // Non-fatal
  }
}

function connectDebateWs(ticker: string, debateId: number): void {
  const handle = useWebSocket<DebateEvent>({
    url: `/ws/debate/${debateId}`,
    onMessage(event) {
      switch (event.type) {
        case 'agent':
          break
        case 'complete':
          stopDebatePoll()
          pipelineStore.onDebateComplete(ticker, event.debate_id)
          if (selectedTicker.value === ticker) {
            void pipelineStore.loadRecommendation(event.debate_id)
          }
          break
        case 'error':
          toast.add({
            severity: 'error',
            summary: `Analysis Error (${ticker})`,
            detail: event.message,
            life: 5000,
          })
          break
      }
    },
    onError() {
      // Non-fatal — debate poll is the safety net
    },
    maxReconnectAttempts: 3,
  })
  trackConnection(handle)
}

async function onAnalyzeSelected(): Promise<void> {
  const tickerList = [...pipelineStore.selectedForAnalysis]
  if (tickerList.length === 0) return

  try {
    const batchId = await pipelineStore.analyzeBatch(tickerList)
    connectBatchWs(batchId)
  } catch (err) {
    toast.add({
      severity: 'error',
      summary: 'Batch Analysis Failed',
      detail: err instanceof Error ? err.message : 'Failed to start batch analysis',
      life: 5000,
    })
  }
}

async function onAnalyzeTopN(limit: number): Promise<void> {
  const topTickers = sortedTickers.value.slice(0, limit).map((t) => t.ticker)
  if (topTickers.length === 0) return

  try {
    const batchId = await pipelineStore.analyzeBatch(topTickers)
    connectBatchWs(batchId)
  } catch (err) {
    toast.add({
      severity: 'error',
      summary: 'Batch Analysis Failed',
      detail: err instanceof Error ? err.message : 'Failed to start batch analysis',
      life: 5000,
    })
  }
}

function connectBatchWs(batchId: number): void {
  const handle = useWebSocket<BatchEvent>({
    url: `/ws/batch/${batchId}`,
    onMessage(event) {
      switch (event.type) {
        case 'batch_progress':
          pipelineStore.onBatchProgress(event)
          break
        case 'agent':
          // Per-ticker agent progress — no dedicated store action
          break
        case 'batch_complete':
          pipelineStore.onBatchComplete(event)
          break
        case 'error':
          toast.add({
            severity: 'error',
            summary: 'Batch Error',
            detail: event.message,
            life: 5000,
          })
          break
      }
    },
    onError() {
      toast.add({
        severity: 'error',
        summary: 'Connection Error',
        detail: 'Lost connection to batch WebSocket',
        life: 5000,
      })
    },
    maxReconnectAttempts: 3,
  })
  trackConnection(handle)
}

// --- Cleanup ---
onUnmounted(() => {
  closeAllConnections()
  stopCompletionPoll()
  stopDebatePoll()
})
</script>

<template>
  <div class="trading-desk">
    <ScanControlBar
      @analyzeSelected="onAnalyzeSelected"
      @analyzeTopN="onAnalyzeTopN"
    />

    <div class="desk-grid">
      <!-- Market context -->
      <DeskCard title="MARKET CONTEXT">
        <MarketHeatmap />
        <RegimeBanner :scores="[...pipelineStore.tickers.values()].map(t => ({
          ticker: t.ticker,
          composite_score: t.composite_score,
          direction: t.direction,
          signals: {},
          next_earnings: null,
          scan_run_id: pipelineStore.scanId ?? 0,
          sector: t.sector,
          company_name: t.company_name,
          industry_group: null,
        }))" />
      </DeskCard>

      <!-- Scan progress (only during active scan) -->
      <ScanProgressCard
        v-if="isScanning"
        :phase="scanPhase"
        :current="scanCurrent"
        :total="scanTotal"
        :startedAt="scanStartedAt"
      />

      <!-- Pipeline table — full width -->
      <OpportunityTable
        :tickers="sortedTickers"
        @selectTicker="onSelectTicker"
        @analyzeTicker="onAnalyzeTicker"
        @selectionChange="onSelectionChange"
      />

      <!-- Recommendation detail cards (when ticker selected + ready) -->
      <template v-if="currentRecommendation">
        <AgentConsensus
          :ticker="selectedTicker ?? ''"
          :assessments="currentRecommendation.assessments"
          :overallDirection="currentRecommendation.recommendation.direction"
          :overallConfidence="currentRecommendation.recommendation.confidence"
        />
        <PositionCard
          :recommendation="currentRecommendation.recommendation"
          :spread="currentRecommendation.spread"
        />
        <DeskAssessmentCard
          v-for="a in currentRecommendation.assessments"
          :key="a.desk"
          :assessment="a"
        />
      </template>
    </div>
  </div>
</template>

<style scoped>
.trading-desk {
  padding: 0;
}

.desk-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
  grid-auto-rows: min-content;
  gap: 1rem;
  padding: 1rem;
}
</style>

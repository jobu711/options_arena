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

// --- Scan WebSocket ---
watch(
  () => scanStore.currentScanId,
  (newScanId) => {
    if (newScanId === null) return
    scanStartedAt.value = new Date()

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
            scanStore.setComplete(event)
            pipelineStore.onScanComplete(event)
            // Load scores into pipeline after scan completes
            void loadScoresIntoPipeline(event.scan_id)
            break
        }
      },
      onError() {
        toast.add({
          severity: 'error',
          summary: 'Connection Error',
          detail: 'Lost connection to scan WebSocket',
          life: 5000,
        })
      },
      maxReconnectAttempts: 3,
    })
    trackConnection(handle)
  },
)

async function loadScoresIntoPipeline(scanId: number): Promise<void> {
  await scanStore.fetchScores(scanId, { page_size: 500 })
  pipelineStore.setTickersFromScores(scanStore.scores)
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
  } catch (err) {
    toast.add({
      severity: 'error',
      summary: 'Analysis Failed',
      detail: err instanceof Error ? err.message : 'Failed to start analysis',
      life: 5000,
    })
  }
}

function connectDebateWs(ticker: string, debateId: number): void {
  const handle = useWebSocket<DebateEvent>({
    url: `/ws/debate/${debateId}`,
    onMessage(event) {
      switch (event.type) {
        case 'agent':
          // Agent progress — no store action needed for individual agent events
          break
        case 'complete':
          pipelineStore.onDebateComplete(ticker, event.debate_id)
          // Auto-select and load if this is the currently selected ticker
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
      toast.add({
        severity: 'error',
        summary: 'Connection Error',
        detail: `Lost connection to debate WebSocket for ${ticker}`,
        life: 5000,
      })
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
        <PositionCard :recommendation="currentRecommendation.recommendation" />
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

import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '@/composables/useApi'
import type {
  EquityCurvePoint,
  DrawdownPoint,
  SectorPerformanceResult,
  DTEBucketResult,
  IVRankBucketResult,
  GreeksDecompositionResult,
  HoldingPeriodComparison,
  AgentAccuracyReport,
  AgentCalibrationData,
} from '@/types'

export const useBacktestStore = defineStore('backtest', () => {
  // --- State ---
  const equityCurve = ref<EquityCurvePoint[]>([])
  const drawdown = ref<DrawdownPoint[]>([])
  const sectorPerformance = ref<SectorPerformanceResult[]>([])
  const dtePerformance = ref<DTEBucketResult[]>([])
  const ivPerformance = ref<IVRankBucketResult[]>([])
  const greeksDecomposition = ref<GreeksDecompositionResult[]>([])
  const holdingComparison = ref<HoldingPeriodComparison[]>([])
  const agentAccuracy = ref<AgentAccuracyReport[]>([])
  const agentCalibration = ref<AgentCalibrationData | null>(null)

  // Loading states
  const loading = ref(false)
  const error = ref<string | null>(null)

  // Filter state
  const direction = ref<string | null>(null)
  const holdingDays = ref(20)
  const period = ref<number | null>(null)

  // Track which tabs have been loaded
  const loadedTabs = ref<Set<string>>(new Set())

  // --- Actions ---

  async function fetchEquityCurve(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      equityCurve.value = await api<EquityCurvePoint[]>(
        '/api/analytics/backtest/equity-curve',
        {
          params: {
            direction: direction.value ?? undefined,
            period: period.value ?? undefined,
          },
        },
      )
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to fetch equity curve'
    } finally {
      loading.value = false
    }
  }

  async function fetchDrawdown(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      drawdown.value = await api<DrawdownPoint[]>(
        '/api/analytics/backtest/drawdown',
        {
          params: {
            period: period.value ?? undefined,
          },
        },
      )
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to fetch drawdown'
    } finally {
      loading.value = false
    }
  }

  async function fetchSectorPerformance(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      sectorPerformance.value = await api<SectorPerformanceResult[]>(
        '/api/analytics/backtest/sector-performance',
        { params: { holding_days: holdingDays.value } },
      )
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to fetch sector performance'
    } finally {
      loading.value = false
    }
  }

  async function fetchDTEPerformance(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      dtePerformance.value = await api<DTEBucketResult[]>(
        '/api/analytics/backtest/dte-performance',
        { params: { holding_days: holdingDays.value } },
      )
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to fetch DTE performance'
    } finally {
      loading.value = false
    }
  }

  async function fetchIVPerformance(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      ivPerformance.value = await api<IVRankBucketResult[]>(
        '/api/analytics/backtest/iv-performance',
        { params: { holding_days: holdingDays.value } },
      )
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to fetch IV performance'
    } finally {
      loading.value = false
    }
  }

  async function fetchGreeksDecomposition(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      greeksDecomposition.value = await api<GreeksDecompositionResult[]>(
        '/api/analytics/backtest/greeks-decomposition',
        { params: { holding_days: holdingDays.value, groupby: 'direction' } },
      )
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to fetch Greeks decomposition'
    } finally {
      loading.value = false
    }
  }

  async function fetchHoldingComparison(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      holdingComparison.value = await api<HoldingPeriodComparison[]>(
        '/api/analytics/backtest/holding-comparison',
      )
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to fetch holding comparison'
    } finally {
      loading.value = false
    }
  }

  async function fetchAgentAccuracy(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      agentAccuracy.value = await api<AgentAccuracyReport[]>(
        '/api/analytics/agent-accuracy',
      )
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to fetch agent accuracy'
    } finally {
      loading.value = false
    }
  }

  async function fetchAgentCalibration(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      agentCalibration.value = await api<AgentCalibrationData>(
        '/api/analytics/agent-calibration',
      )
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to fetch agent calibration'
    } finally {
      loading.value = false
    }
  }

  /** Load all data for the Overview tab. */
  async function loadOverviewTab(): Promise<void> {
    if (loadedTabs.value.has('overview')) return
    await Promise.all([fetchEquityCurve(), fetchDrawdown()])
    loadedTabs.value.add('overview')
  }

  /** Load all data for the Agents tab. */
  async function loadAgentsTab(): Promise<void> {
    if (loadedTabs.value.has('agents')) return
    await Promise.all([fetchAgentAccuracy(), fetchAgentCalibration()])
    loadedTabs.value.add('agents')
  }

  /** Load all data for the Segments tab. */
  async function loadSegmentsTab(): Promise<void> {
    if (loadedTabs.value.has('segments')) return
    await Promise.all([
      fetchSectorPerformance(),
      fetchDTEPerformance(),
      fetchIVPerformance(),
    ])
    loadedTabs.value.add('segments')
  }

  /** Load all data for the Greeks tab. */
  async function loadGreeksTab(): Promise<void> {
    if (loadedTabs.value.has('greeks')) return
    await fetchGreeksDecomposition()
    loadedTabs.value.add('greeks')
  }

  /** Load all data for the Holding tab. */
  async function loadHoldingTab(): Promise<void> {
    if (loadedTabs.value.has('holding')) return
    await fetchHoldingComparison()
    loadedTabs.value.add('holding')
  }

  /** Reset all loaded tabs (e.g. when filters change). */
  function resetLoadedTabs(): void {
    loadedTabs.value.clear()
  }

  return {
    // State
    equityCurve,
    drawdown,
    sectorPerformance,
    dtePerformance,
    ivPerformance,
    greeksDecomposition,
    holdingComparison,
    agentAccuracy,
    agentCalibration,
    loading,
    error,
    direction,
    holdingDays,
    period,
    loadedTabs,

    // Individual fetchers
    fetchEquityCurve,
    fetchDrawdown,
    fetchSectorPerformance,
    fetchDTEPerformance,
    fetchIVPerformance,
    fetchGreeksDecomposition,
    fetchHoldingComparison,
    fetchAgentAccuracy,
    fetchAgentCalibration,

    // Tab loaders
    loadOverviewTab,
    loadAgentsTab,
    loadSegmentsTab,
    loadGreeksTab,
    loadHoldingTab,
    resetLoadedTabs,
  }
})

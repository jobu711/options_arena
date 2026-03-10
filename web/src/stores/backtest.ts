import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
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

  // Loading counter — incremented on fetch start, decremented on finish.
  // loading is true when any fetch is in-flight.
  const pendingRequests = ref(0)
  const loading = computed(() => pendingRequests.value > 0)

  // Per-dataset error tracking — errors accumulate and are not cleared by other fetches.
  const errors = ref<Map<string, string>>(new Map())
  /** First error message (for simple display) or null if no errors. */
  const error = computed(() => {
    const first = errors.value.values().next()
    return first.done ? null : first.value
  })

  // Filter state
  const direction = ref<string | null>(null)
  const holdingDays = ref(20)
  const period = ref<number | null>(null)

  // Track which tabs have been loaded
  const loadedTabs = ref<Set<string>>(new Set())

  // --- Helpers ---

  function clearErrors(): void {
    errors.value = new Map()
  }

  // --- Actions ---

  async function fetchEquityCurve(): Promise<void> {
    pendingRequests.value++
    errors.value.delete('equityCurve')
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
      errors.value.set(
        'equityCurve',
        e instanceof Error ? e.message : 'Failed to fetch equity curve',
      )
    } finally {
      pendingRequests.value--
    }
  }

  async function fetchDrawdown(): Promise<void> {
    pendingRequests.value++
    errors.value.delete('drawdown')
    try {
      drawdown.value = await api<DrawdownPoint[]>(
        '/api/analytics/backtest/drawdown',
        {
          params: {
            direction: direction.value ?? undefined,
            period: period.value ?? undefined,
          },
        },
      )
    } catch (e) {
      errors.value.set(
        'drawdown',
        e instanceof Error ? e.message : 'Failed to fetch drawdown',
      )
    } finally {
      pendingRequests.value--
    }
  }

  async function fetchSectorPerformance(): Promise<void> {
    pendingRequests.value++
    errors.value.delete('sectorPerformance')
    try {
      sectorPerformance.value = await api<SectorPerformanceResult[]>(
        '/api/analytics/backtest/sector-performance',
        { params: { holding_days: holdingDays.value } },
      )
    } catch (e) {
      errors.value.set(
        'sectorPerformance',
        e instanceof Error ? e.message : 'Failed to fetch sector performance',
      )
    } finally {
      pendingRequests.value--
    }
  }

  async function fetchDTEPerformance(): Promise<void> {
    pendingRequests.value++
    errors.value.delete('dtePerformance')
    try {
      dtePerformance.value = await api<DTEBucketResult[]>(
        '/api/analytics/backtest/dte-performance',
        { params: { holding_days: holdingDays.value } },
      )
    } catch (e) {
      errors.value.set(
        'dtePerformance',
        e instanceof Error ? e.message : 'Failed to fetch DTE performance',
      )
    } finally {
      pendingRequests.value--
    }
  }

  async function fetchIVPerformance(): Promise<void> {
    pendingRequests.value++
    errors.value.delete('ivPerformance')
    try {
      ivPerformance.value = await api<IVRankBucketResult[]>(
        '/api/analytics/backtest/iv-performance',
        { params: { holding_days: holdingDays.value } },
      )
    } catch (e) {
      errors.value.set(
        'ivPerformance',
        e instanceof Error ? e.message : 'Failed to fetch IV performance',
      )
    } finally {
      pendingRequests.value--
    }
  }

  async function fetchGreeksDecomposition(): Promise<void> {
    pendingRequests.value++
    errors.value.delete('greeksDecomposition')
    try {
      greeksDecomposition.value = await api<GreeksDecompositionResult[]>(
        '/api/analytics/backtest/greeks-decomposition',
        { params: { holding_days: holdingDays.value, groupby: 'direction' } },
      )
    } catch (e) {
      errors.value.set(
        'greeksDecomposition',
        e instanceof Error ? e.message : 'Failed to fetch Greeks decomposition',
      )
    } finally {
      pendingRequests.value--
    }
  }

  async function fetchHoldingComparison(): Promise<void> {
    pendingRequests.value++
    errors.value.delete('holdingComparison')
    try {
      holdingComparison.value = await api<HoldingPeriodComparison[]>(
        '/api/analytics/backtest/holding-comparison',
      )
    } catch (e) {
      errors.value.set(
        'holdingComparison',
        e instanceof Error ? e.message : 'Failed to fetch holding comparison',
      )
    } finally {
      pendingRequests.value--
    }
  }

  async function fetchAgentAccuracy(): Promise<void> {
    pendingRequests.value++
    errors.value.delete('agentAccuracy')
    try {
      agentAccuracy.value = await api<AgentAccuracyReport[]>(
        '/api/analytics/agent-accuracy',
      )
    } catch (e) {
      errors.value.set(
        'agentAccuracy',
        e instanceof Error ? e.message : 'Failed to fetch agent accuracy',
      )
    } finally {
      pendingRequests.value--
    }
  }

  async function fetchAgentCalibration(): Promise<void> {
    pendingRequests.value++
    errors.value.delete('agentCalibration')
    try {
      agentCalibration.value = await api<AgentCalibrationData>(
        '/api/analytics/agent-calibration',
      )
    } catch (e) {
      errors.value.set(
        'agentCalibration',
        e instanceof Error ? e.message : 'Failed to fetch agent calibration',
      )
    } finally {
      pendingRequests.value--
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
    clearErrors()
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
    errors,
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
    clearErrors,
  }
})

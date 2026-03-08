<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import Button from 'primevue/button'
import Skeleton from 'primevue/skeleton'
import { useHeatmapStore } from '@/stores/heatmap'
import type { HeatmapTicker } from '@/types'

const store = useHeatmapStore()
const router = useRouter()

// Container dimensions
const containerWidth = 1200
const containerHeight = 500

// ---------------------------------------------------------------------------
// Squarify algorithm (standard Bruls-Huizing-van Wijk 2000)
// ---------------------------------------------------------------------------

interface Rect {
  x: number
  y: number
  w: number
  h: number
}

interface LayoutItem {
  rect: Rect
  item: { weight: number; key: string }
}

function squarify<T extends { weight: number; key: string }>(
  items: T[],
  container: Rect,
): Array<{ rect: Rect; item: T }> {
  if (items.length === 0) return []

  const totalWeight = items.reduce((s, it) => s + it.weight, 0)
  if (totalWeight <= 0) return []

  // Sort descending by weight for better aspect ratios
  const sorted = [...items].sort((a, b) => b.weight - a.weight)

  const result: Array<{ rect: Rect; item: T }> = []
  let remaining = { ...container }
  let remainingWeight = totalWeight

  let i = 0
  while (i < sorted.length) {
    const isVertical = remaining.w >= remaining.h
    const side = isVertical ? remaining.h : remaining.w

    // Greedily add items to current row until aspect ratio worsens
    const row: T[] = [sorted[i]]
    let rowWeight = sorted[i].weight
    i++

    while (i < sorted.length) {
      const candidate = sorted[i]
      const testWeight = rowWeight + candidate.weight
      if (worstAspect(row, rowWeight, side, remainingWeight) <=
          worstAspect([...row, candidate], testWeight, side, remainingWeight)) {
        break
      }
      row.push(candidate)
      rowWeight = testWeight
      i++
    }

    // Lay out the row
    const rowFraction = rowWeight / remainingWeight
    const rowThickness = isVertical
      ? remaining.w * rowFraction
      : remaining.h * rowFraction

    let offset = 0
    for (const item of row) {
      const itemFraction = item.weight / rowWeight
      const itemLength = side * itemFraction

      const rect: Rect = isVertical
        ? { x: remaining.x, y: remaining.y + offset, w: rowThickness, h: itemLength }
        : { x: remaining.x + offset, y: remaining.y, w: itemLength, h: rowThickness }

      result.push({ rect, item })
      offset += itemLength
    }

    // Shrink remaining area
    if (isVertical) {
      remaining = { x: remaining.x + rowThickness, y: remaining.y, w: remaining.w - rowThickness, h: remaining.h }
    } else {
      remaining = { x: remaining.x, y: remaining.y + rowThickness, w: remaining.w, h: remaining.h - rowThickness }
    }
    remainingWeight -= rowWeight
  }

  return result
}

function worstAspect<T extends { weight: number }>(
  row: T[],
  rowWeight: number,
  side: number,
  totalWeight: number,
): number {
  if (totalWeight <= 0 || rowWeight <= 0 || side <= 0) return Infinity
  const rowArea = (rowWeight / totalWeight) * side * side
  const rowThickness = rowArea / side
  let worst = 0
  for (const item of row) {
    const itemLength = (item.weight / rowWeight) * side
    const aspect = Math.max(itemLength / rowThickness, rowThickness / itemLength)
    if (aspect > worst) worst = aspect
  }
  return worst
}

// ---------------------------------------------------------------------------
// Color encoding
// ---------------------------------------------------------------------------

function changePctToColor(changePct: number | null): string {
  if (changePct === null) return '#374151'
  // Clamp to ±5% for full saturation
  const t = Math.max(-1, Math.min(1, changePct / 5.0))
  if (t >= 0) {
    // Neutral (#374151) → Green (#22c55e)
    return lerpColor(0x37, 0x41, 0x51, 0x22, 0xc5, 0x5e, t)
  } else {
    // Neutral (#374151) → Red (#ef4444)
    return lerpColor(0x37, 0x41, 0x51, 0xef, 0x44, 0x44, -t)
  }
}

function lerpColor(
  r1: number, g1: number, b1: number,
  r2: number, g2: number, b2: number,
  t: number,
): string {
  const r = Math.round(r1 + (r2 - r1) * t)
  const g = Math.round(g1 + (g2 - g1) * t)
  const b = Math.round(b1 + (b2 - b1) * t)
  return `rgb(${r}, ${g}, ${b})`
}

// ---------------------------------------------------------------------------
// Layout computation
// ---------------------------------------------------------------------------

interface CellData {
  ticker: HeatmapTicker
  rect: Rect
  fontSize: number
  showTicker: boolean
  showChange: boolean
  color: string
}

interface SectorGroup {
  sector: string
  tickers: HeatmapTicker[]
  totalWeight: number
}

const layout = computed(() => {
  const data = store.tickers
  if (data.length === 0) return { cells: [] as CellData[], sectors: [] as Array<{ name: string; rect: Rect }> }

  // Group by sector
  const sectorMap = new Map<string, HeatmapTicker[]>()
  for (const t of data) {
    const group = sectorMap.get(t.sector) ?? []
    group.push(t)
    sectorMap.set(t.sector, group)
  }

  const sectorGroups: SectorGroup[] = []
  for (const [sector, tickers] of sectorMap) {
    sectorGroups.push({
      sector,
      tickers,
      totalWeight: tickers.reduce((s, t) => s + t.market_cap_weight, 0),
    })
  }

  // Level 1: squarify sectors
  const sectorItems = sectorGroups.map(sg => ({
    weight: sg.totalWeight,
    key: sg.sector,
    group: sg,
  }))

  const sectorRects = squarify(sectorItems, { x: 0, y: 0, w: containerWidth, h: containerHeight })

  const cells: CellData[] = []
  const sectorLabels: Array<{ name: string; rect: Rect }> = []

  for (const sr of sectorRects) {
    sectorLabels.push({ name: sr.item.key, rect: sr.rect })

    // Level 2: squarify tickers within this sector
    const tickerItems = sr.item.group.tickers.map(t => ({
      weight: t.market_cap_weight,
      key: t.ticker,
      ticker: t,
    }))

    const tickerRects = squarify(tickerItems, sr.rect)

    for (const tr of tickerRects) {
      const area = tr.rect.w * tr.rect.h
      const fontSize = Math.max(8, Math.min(16, Math.sqrt(area) / 4))
      cells.push({
        ticker: tr.item.ticker,
        rect: tr.rect,
        fontSize,
        showTicker: area >= 2000,
        showChange: area >= 4000,
        color: changePctToColor(tr.item.ticker.change_pct),
      })
    }
  }

  return { cells, sectors: sectorLabels }
})

// ---------------------------------------------------------------------------
// Tooltip
// ---------------------------------------------------------------------------

const tooltip = ref<{ visible: boolean; x: number; y: number; ticker: HeatmapTicker | null }>({
  visible: false,
  x: 0,
  y: 0,
  ticker: null,
})

function onCellMouseMove(event: MouseEvent, ticker: HeatmapTicker): void {
  tooltip.value = {
    visible: true,
    x: event.clientX + 12,
    y: event.clientY + 12,
    ticker,
  }
}

function onCellMouseLeave(): void {
  tooltip.value = { visible: false, x: 0, y: 0, ticker: null }
}

function onCellClick(ticker: string): void {
  void router.push(`/ticker/${ticker}`)
}

function formatVolume(vol: number): string {
  if (vol >= 1_000_000) return `${(vol / 1_000_000).toFixed(1)}M`
  if (vol >= 1_000) return `${(vol / 1_000).toFixed(1)}K`
  return String(vol)
}

function formatChange(pct: number | null): string {
  if (pct === null) return '--'
  return `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`
}

function timeSince(date: Date | null): string {
  if (!date) return ''
  const seconds = Math.floor((Date.now() - date.getTime()) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  return `${hours}h ago`
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

onMounted(() => {
  void store.fetchHeatmap()
  store.startAutoRefresh()
})

onUnmounted(() => {
  store.stopAutoRefresh()
})
</script>

<template>
  <div class="heatmap-section">
    <!-- Header -->
    <div class="heatmap-header">
      <div class="heatmap-title">
        <h3>Market Overview</h3>
        <span v-if="store.lastUpdated" class="heatmap-updated">
          Last updated: {{ timeSince(store.lastUpdated) }}
        </span>
      </div>
      <Button
        icon="pi pi-refresh"
        text
        rounded
        :loading="store.loading"
        @click="() => void store.fetchHeatmap()"
        aria-label="Refresh heatmap"
      />
    </div>

    <!-- Loading -->
    <div v-if="store.loading && store.tickers.length === 0" class="heatmap-skeleton">
      <Skeleton width="100%" height="500px" />
    </div>

    <!-- Error -->
    <div v-else-if="store.error && store.tickers.length === 0" class="heatmap-error">
      <p>{{ store.error }}</p>
      <Button label="Retry" icon="pi pi-refresh" @click="() => void store.fetchHeatmap()" />
    </div>

    <!-- Empty -->
    <div v-else-if="store.tickers.length === 0 && !store.loading" class="heatmap-empty">
      <p>No heatmap data available.</p>
    </div>

    <!-- Treemap -->
    <div
      v-else
      class="heatmap-container"
      :style="{ width: `${containerWidth}px`, height: `${containerHeight}px` }"
    >
      <!-- Sector labels -->
      <div
        v-for="sector in layout.sectors"
        :key="`sector-${sector.name}`"
        class="heatmap-sector-label"
        :style="{
          left: `${sector.rect.x}px`,
          top: `${sector.rect.y}px`,
        }"
      >
        {{ sector.name }}
      </div>

      <!-- Ticker cells -->
      <div
        v-for="cell in layout.cells"
        :key="cell.ticker.ticker"
        class="heatmap-cell"
        :style="{
          left: `${cell.rect.x}px`,
          top: `${cell.rect.y}px`,
          width: `${cell.rect.w}px`,
          height: `${cell.rect.h}px`,
          backgroundColor: cell.color,
          fontSize: `${cell.fontSize}px`,
        }"
        @mousemove="(e) => onCellMouseMove(e, cell.ticker)"
        @mouseleave="onCellMouseLeave"
        @click="onCellClick(cell.ticker.ticker)"
      >
        <span v-if="cell.showTicker" class="cell-ticker">{{ cell.ticker.ticker }}</span>
        <span v-if="cell.showChange" class="cell-change">
          {{ formatChange(cell.ticker.change_pct) }}
        </span>
      </div>
    </div>

    <!-- Tooltip -->
    <div
      v-if="tooltip.visible && tooltip.ticker"
      class="heatmap-tooltip"
      :style="{ left: `${tooltip.x}px`, top: `${tooltip.y}px` }"
    >
      <div class="tooltip-ticker">{{ tooltip.ticker.ticker }}</div>
      <div class="tooltip-name">{{ tooltip.ticker.company_name }}</div>
      <div class="tooltip-row">
        <span>Sector:</span>
        <span>{{ tooltip.ticker.sector }}</span>
      </div>
      <div class="tooltip-row">
        <span>Change:</span>
        <span :class="{ 'text-green': (tooltip.ticker.change_pct ?? 0) > 0, 'text-red': (tooltip.ticker.change_pct ?? 0) < 0 }">
          {{ formatChange(tooltip.ticker.change_pct) }}
        </span>
      </div>
      <div class="tooltip-row">
        <span>Price:</span>
        <span>${{ tooltip.ticker.price.toFixed(2) }}</span>
      </div>
      <div class="tooltip-row">
        <span>Volume:</span>
        <span>{{ formatVolume(tooltip.ticker.volume) }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.heatmap-section {
  width: 100%;
  max-width: 1200px;
}

.heatmap-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.75rem;
}

.heatmap-title {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
}

.heatmap-title h3 {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--p-text-color);
}

.heatmap-updated {
  font-size: 0.8rem;
  color: var(--p-text-muted-color);
}

.heatmap-skeleton,
.heatmap-error,
.heatmap-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  color: var(--p-text-muted-color);
  gap: 1rem;
}

.heatmap-container {
  position: relative;
  border-radius: 0.5rem;
  overflow: hidden;
  background: var(--p-surface-800, #1e1e2e);
}

.heatmap-cell {
  position: absolute;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  overflow: hidden;
  border: 1px solid rgba(0, 0, 0, 0.3);
  transition: filter 0.15s ease;
  box-sizing: border-box;
  user-select: none;
}

.heatmap-cell:hover {
  filter: brightness(1.2);
  z-index: 10;
}

.cell-ticker {
  font-weight: 700;
  color: #fff;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.5);
  line-height: 1.2;
}

.cell-change {
  font-size: 0.7em;
  color: rgba(255, 255, 255, 0.85);
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.5);
}

.heatmap-sector-label {
  position: absolute;
  font-size: 0.65rem;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.8);
  background: rgba(0, 0, 0, 0.45);
  padding: 1px 5px;
  border-radius: 0 0 4px 0;
  pointer-events: none;
  z-index: 20;
  white-space: nowrap;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.heatmap-tooltip {
  position: fixed;
  z-index: 50;
  pointer-events: none;
  background: var(--p-surface-900, #111827);
  border: 1px solid var(--p-surface-600, #4b5563);
  border-radius: 0.5rem;
  padding: 0.75rem;
  font-size: 0.85rem;
  color: var(--p-text-color);
  min-width: 180px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
}

.tooltip-ticker {
  font-weight: 700;
  font-size: 1rem;
  margin-bottom: 0.15rem;
}

.tooltip-name {
  color: var(--p-text-muted-color);
  font-size: 0.8rem;
  margin-bottom: 0.5rem;
}

.tooltip-row {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.1rem 0;
}

.tooltip-row span:first-child {
  color: var(--p-text-muted-color);
}

.text-green {
  color: var(--accent-green, #22c55e);
}

.text-red {
  color: var(--accent-red, #ef4444);
}
</style>

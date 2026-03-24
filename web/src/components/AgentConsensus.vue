<script setup lang="ts">
import { computed } from 'vue'
import type { DeskAssessment, Direction } from '@/types/recommendation'
import DeskCard from '@/components/DeskCard.vue'

interface Props {
  ticker: string
  assessments: DeskAssessment[]
  overallDirection: Direction
  overallConfidence: number
}

const props = defineProps<Props>()

/** All six expected desks in display order. */
const ALL_DESKS: string[] = ['trend', 'volatility', 'flow', 'fundamental', 'risk', 'contrarian']

/** Map desk names to accent colors for the mini-summary dots. */
const DESK_COLORS: Record<string, string> = {
  trend: '#3b82f6',
  volatility: '#a855f7',
  flow: '#06b6d4',
  fundamental: '#f59e0b',
  risk: '#ef4444',
  contrarian: '#10b981',
}

/** Direction arrow character for compact display. */
function directionArrow(direction: Direction): string {
  switch (direction) {
    case 'BULLISH':
      return '\u25B2'
    case 'BEARISH':
      return '\u25BC'
    case 'NEUTRAL':
      return '\u25BA'
  }
}

/** CSS class for direction-colored arrow. */
function directionClass(direction: Direction): string {
  switch (direction) {
    case 'BULLISH':
      return 'arrow--bullish'
    case 'BEARISH':
      return 'arrow--bearish'
    case 'NEUTRAL':
      return 'arrow--neutral'
  }
}

/** Header text: "AAPL -- BULLISH (72%)" */
const headerText = computed(() => {
  const pct = Math.round(props.overallConfidence * 100)
  return `${props.ticker} \u2014 ${props.overallDirection} (${pct}%)`
})

/** Look up assessment by desk name, returns null if missing. */
function findDesk(desk: string): DeskAssessment | null {
  return props.assessments.find((a) => a.desk.toLowerCase() === desk) ?? null
}
</script>

<template>
  <DeskCard title="AGENT CONSENSUS" :full-width="true" data-testid="agent-consensus">
    <template #status>
      <span class="consensus-header-text" :class="directionClass(overallDirection)">
        {{ headerText }}
      </span>
    </template>

    <div class="consensus-grid">
      <div
        v-for="desk in ALL_DESKS"
        :key="desk"
        class="consensus-cell"
        :style="{ '--cell-accent': DESK_COLORS[desk] ?? '#6b7280' }"
        data-testid="consensus-cell"
      >
        <div class="consensus-cell__header">
          <span
            class="consensus-cell__dot"
            :style="{ background: DESK_COLORS[desk] ?? '#6b7280' }"
          />
          <span class="consensus-cell__name">{{ desk }}</span>
        </div>

        <template v-if="findDesk(desk)">
          <span
            class="consensus-cell__arrow"
            :class="directionClass(findDesk(desk)!.direction)"
          >
            {{ directionArrow(findDesk(desk)!.direction) }}
          </span>
          <span class="consensus-cell__confidence mono">
            {{ Math.round(findDesk(desk)!.confidence * 100) }}%
          </span>
        </template>
        <template v-else>
          <span class="consensus-cell__placeholder">--</span>
          <span class="consensus-cell__placeholder">--</span>
        </template>
      </div>
    </div>
  </DeskCard>
</template>

<style scoped>
.consensus-header-text {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  font-weight: 600;
}

.consensus-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0.75rem;
}

@media (max-width: 640px) {
  .consensus-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

.consensus-cell {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  background: var(--p-surface-900, #111);
  border-radius: 0.5rem;
  border-left: 3px solid var(--cell-accent, #6b7280);
}

.consensus-cell__header {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  flex: 1;
  min-width: 0;
}

.consensus-cell__dot {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
  flex-shrink: 0;
}

.consensus-cell__name {
  font-size: 0.75rem;
  font-weight: 500;
  text-transform: capitalize;
  color: var(--p-surface-300, #aaa);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.consensus-cell__arrow {
  font-size: 0.85rem;
  flex-shrink: 0;
}

.consensus-cell__confidence {
  font-size: 0.8rem;
  font-weight: 600;
  flex-shrink: 0;
}

.mono {
  font-family: var(--font-mono);
}

.arrow--bullish,
.consensus-header-text.arrow--bullish {
  color: var(--accent-green, #22c55e);
}

.arrow--bearish,
.consensus-header-text.arrow--bearish {
  color: var(--accent-red, #ef4444);
}

.arrow--neutral,
.consensus-header-text.arrow--neutral {
  color: var(--accent-yellow, #eab308);
}

.consensus-cell__placeholder {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: var(--p-surface-500, #666);
}
</style>

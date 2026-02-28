<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  scores: number[]
  direction?: 'bullish' | 'bearish' | 'neutral'
}

const props = withDefaults(defineProps<Props>(), {
  direction: 'neutral',
})

const WIDTH = 80
const HEIGHT = 24
const PADDING = 2

const directionColor = computed<string>(() => {
  switch (props.direction) {
    case 'bullish':
      return 'var(--accent-green, #22c55e)'
    case 'bearish':
      return 'var(--accent-red, #ef4444)'
    default:
      return 'var(--accent-yellow, #eab308)'
  }
})

const polylinePoints = computed<string>(() => {
  const data = props.scores
  if (data.length < 2) return ''

  const minScore = Math.min(...data)
  const maxScore = Math.max(...data)
  const range = maxScore - minScore || 1

  const usableWidth = WIDTH - PADDING * 2
  const usableHeight = HEIGHT - PADDING * 2

  return data
    .map((score, i) => {
      const x = PADDING + (i / (data.length - 1)) * usableWidth
      const y = PADDING + usableHeight - ((score - minScore) / range) * usableHeight
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
})
</script>

<template>
  <svg
    v-if="scores.length >= 2"
    :viewBox="`0 0 ${WIDTH} ${HEIGHT}`"
    preserveAspectRatio="xMidYMid meet"
    class="sparkline"
    data-testid="sparkline-chart"
  >
    <polyline
      :points="polylinePoints"
      fill="none"
      :stroke="directionColor"
      stroke-width="1.5"
      stroke-linecap="round"
      stroke-linejoin="round"
    />
  </svg>
  <span v-else class="sparkline-empty">&mdash;</span>
</template>

<style scoped>
.sparkline {
  width: 80px;
  height: 24px;
  display: inline-block;
  vertical-align: middle;
}

.sparkline-empty {
  color: var(--p-surface-500, #666);
  font-size: 0.8rem;
}
</style>

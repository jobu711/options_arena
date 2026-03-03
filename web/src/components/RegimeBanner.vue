<script setup lang="ts">
import { computed } from 'vue'
import type { TickerScore } from '@/types'

type MarketRegime = 'trending' | 'mean_reverting' | 'volatile' | 'crisis'

interface Props {
  scores: TickerScore[]
}

const props = defineProps<Props>()

interface RegimeDisplay {
  label: string
  hint: string
  cssClass: string
}

const REGIME_MAP: Record<MarketRegime, RegimeDisplay> = {
  trending: {
    label: 'Trending',
    hint: 'favor directional plays',
    cssClass: 'regime--trending',
  },
  mean_reverting: {
    label: 'Mean Reverting',
    hint: 'favor range-bound strategies',
    cssClass: 'regime--mean-reverting',
  },
  volatile: {
    label: 'Volatile',
    hint: 'favor premium selling',
    cssClass: 'regime--volatile',
  },
  crisis: {
    label: 'Crisis',
    hint: 'reduce position sizes, favor hedges',
    cssClass: 'regime--crisis',
  },
}

/** Compute the mode (most frequent) market regime across all tickers. */
const dominantRegime = computed<MarketRegime | null>(() => {
  const counts = new Map<MarketRegime, number>()
  for (const score of props.scores) {
    const regime = score.market_regime
    if (regime) {
      counts.set(regime, (counts.get(regime) ?? 0) + 1)
    }
  }
  if (counts.size === 0) return null

  let best: MarketRegime | null = null
  let bestCount = 0
  for (const [regime, count] of counts) {
    if (count > bestCount) {
      best = regime
      bestCount = count
    }
  }
  return best
})

const display = computed<RegimeDisplay | null>(() => {
  if (!dominantRegime.value) return null
  return REGIME_MAP[dominantRegime.value]
})
</script>

<template>
  <div
    v-if="display"
    class="regime-banner"
    :class="display.cssClass"
    data-testid="regime-banner"
  >
    <span class="regime-label">{{ display.label }}</span>
    <span class="regime-separator">&mdash;</span>
    <span class="regime-hint">{{ display.hint }}</span>
  </div>
</template>

<style scoped>
.regime-banner {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.6rem 1rem;
  border-radius: 0.5rem;
  margin-bottom: 1rem;
  font-size: 0.9rem;
  color: #fff;
}

.regime-label {
  font-weight: 600;
}

.regime-hint {
  font-weight: 400;
  opacity: 0.9;
}

.regime--trending {
  background: var(--accent-emerald, #10b981);
}

.regime--mean-reverting {
  background: var(--accent-blue, #3b82f6);
}

.regime--volatile {
  background: var(--accent-amber, #f59e0b);
  color: #111;
}

.regime--crisis {
  background: var(--accent-red, #ef4444);
}
</style>

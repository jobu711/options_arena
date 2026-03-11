<script setup lang="ts">
import { computed } from 'vue'
import type { PreScanFilterPayload } from '@/types'

interface FilterChip {
  key: string
  label: string
}

const props = defineProps<{
  filters: PreScanFilterPayload
  sectorCount: number
  industryGroupCount: number
  disabled: boolean
}>()

const emit = defineEmits<{
  'clear-filter': [key: string]
  'clear-all': []
}>()

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1)
}

const currencyFmt = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

const chips = computed<FilterChip[]>(() => {
  const result: FilterChip[] = []
  const f = props.filters

  if (f.direction_filter != null) {
    result.push({ key: 'direction_filter', label: `${capitalize(f.direction_filter)} Only` })
  }

  if (f.market_cap_tiers && f.market_cap_tiers.length > 0) {
    const label = f.market_cap_tiers.map(capitalize).join(', ')
    result.push({ key: 'market_cap_tiers', label })
  }

  if (f.min_iv_rank != null) {
    result.push({ key: 'min_iv_rank', label: `IV Rank > ${f.min_iv_rank}%` })
  }

  if (f.min_score != null) {
    result.push({ key: 'min_score', label: `Score > ${f.min_score}` })
  }

  if (f.exclude_near_earnings_days != null) {
    result.push({
      key: 'exclude_near_earnings_days',
      label: `Exclude ${f.exclude_near_earnings_days}d Earnings`,
    })
  }

  // Price range: combine min/max into single chip
  if (f.min_price != null || f.max_price != null) {
    let label: string
    if (f.min_price != null && f.max_price != null) {
      label = `${currencyFmt.format(f.min_price)} - ${currencyFmt.format(f.max_price)}`
    } else if (f.min_price != null) {
      label = `Min ${currencyFmt.format(f.min_price)}`
    } else {
      label = `Max ${currencyFmt.format(f.max_price!)}`
    }
    result.push({ key: 'price_range', label })
  }

  // DTE range: combine min/max into single chip
  if (f.min_dte != null || f.max_dte != null) {
    let label: string
    if (f.min_dte != null && f.max_dte != null) {
      label = `DTE ${f.min_dte}d - ${f.max_dte}d`
    } else if (f.min_dte != null) {
      label = `DTE > ${f.min_dte}d`
    } else {
      label = `DTE < ${f.max_dte}d`
    }
    result.push({ key: 'dte_range', label })
  }

  if (props.sectorCount > 0) {
    result.push({
      key: 'sectors',
      label: `${props.sectorCount} ${props.sectorCount === 1 ? 'Sector' : 'Sectors'}`,
    })
  }

  if (props.industryGroupCount > 0) {
    result.push({
      key: 'industryGroups',
      label: `${props.industryGroupCount} ${props.industryGroupCount === 1 ? 'Industry Group' : 'Industry Groups'}`,
    })
  }

  if (f.min_direction_confidence != null) {
    result.push({
      key: 'min_direction_confidence',
      label: `Confidence > ${Math.round(f.min_direction_confidence * 100)}%`,
    })
  }

  if (f.custom_tickers && f.custom_tickers.length > 0) {
    result.push({
      key: 'custom_tickers',
      label: `${f.custom_tickers.length} Custom Ticker${f.custom_tickers.length !== 1 ? 's' : ''}`,
    })
  }

  if (f.top_n != null) {
    result.push({ key: 'top_n', label: `Top ${f.top_n}` })
  }

  if (f.min_dollar_volume != null) {
    const millions = f.min_dollar_volume / 1_000_000
    result.push({ key: 'min_dollar_volume', label: `$Vol > ${millions}M` })
  }

  if (f.min_oi != null) {
    result.push({ key: 'min_oi', label: `OI > ${f.min_oi}` })
  }

  if (f.min_volume != null) {
    result.push({ key: 'min_volume', label: `Vol > ${f.min_volume}` })
  }

  if (f.max_spread_pct != null) {
    result.push({
      key: 'max_spread_pct',
      label: `Spread < ${Math.round(f.max_spread_pct * 100)}%`,
    })
  }

  if (f.delta_primary_min != null || f.delta_primary_max != null) {
    const min = f.delta_primary_min?.toFixed(2) ?? '0.00'
    const max = f.delta_primary_max?.toFixed(2) ?? '1.00'
    result.push({ key: 'delta_primary', label: `\u0394 Primary ${min}-${max}` })
  }

  if (f.delta_fallback_min != null || f.delta_fallback_max != null) {
    const min = f.delta_fallback_min?.toFixed(2) ?? '0.00'
    const max = f.delta_fallback_max?.toFixed(2) ?? '1.00'
    result.push({ key: 'delta_fallback', label: `\u0394 Fallback ${min}-${max}` })
  }

  return result
})

function onClearFilter(key: string): void {
  if (props.disabled) return
  emit('clear-filter', key)
}

function onClearAll(): void {
  if (props.disabled) return
  emit('clear-all')
}
</script>

<template>
  <div v-if="chips.length > 0" class="chip-row" :class="{ disabled }">
    <span
      v-for="chip in chips"
      :key="chip.key"
      class="filter-chip"
    >
      {{ chip.label }}
      <button
        type="button"
        class="chip-close"
        :aria-label="`Clear ${chip.label}`"
        @click="onClearFilter(chip.key)"
      >&times;</button>
    </span>
    <button
      v-if="chips.length >= 2"
      type="button"
      class="clear-all"
      @click="onClearAll"
    >Clear All</button>
  </div>
</template>

<style scoped>
.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
}

.chip-row.disabled {
  opacity: 0.5;
  pointer-events: none;
}

.filter-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.25rem 0.5rem;
  background: var(--p-surface-700, #333);
  border: 1px solid var(--p-surface-600, #444);
  border-radius: 1rem;
  font-size: 0.8rem;
  color: var(--p-surface-200, #ccc);
}

.chip-close {
  cursor: pointer;
  color: var(--p-surface-400, #888);
  font-size: 0.7rem;
  background: none;
  border: none;
  padding: 0;
  line-height: 1;
}

.chip-close:hover {
  color: var(--p-surface-100, #eee);
}

.clear-all {
  font-size: 0.8rem;
  color: var(--accent-blue, #3b82f6);
  cursor: pointer;
  text-decoration: underline;
  background: none;
  border: none;
  padding: 0;
}

.clear-all:hover {
  color: var(--accent-blue, #60a5fa);
}
</style>

<script setup lang="ts">
import type { PositionRecommendation } from '@/types/recommendation'
import DeskCard from '@/components/DeskCard.vue'
import DirectionBadge from '@/components/DirectionBadge.vue'
import ConfidenceBadge from '@/components/ConfidenceBadge.vue'
import { formatPrice } from '@/utils/formatters'

interface Props {
  recommendation: PositionRecommendation
}

const props = defineProps<Props>()

/** Format risk/reward ratio to 1dp, or '--' for null/non-finite. */
function formatRatio(value: number | null): string {
  if (value == null || !Number.isFinite(value)) return '--'
  return `${value.toFixed(1)}:1`
}

/** Format position size as percentage, or '--' for null/non-finite. */
function formatSizePct(value: number): string {
  if (!Number.isFinite(value)) return '--'
  return `${value.toFixed(1)}%`
}

/** Display price string with $ prefix, or '--' for null. */
function displayPrice(price: string | null): string {
  if (price == null) return '--'
  return formatPrice(price)
}
</script>

<template>
  <DeskCard title="POSITION DETAIL" :full-width="true" data-testid="position-card">
    <template #status>
      <DirectionBadge :direction="recommendation.direction" />
      <ConfidenceBadge :value="recommendation.confidence" />
    </template>

    <div class="position-detail">
      <!-- Contract Description -->
      <div class="position-detail__contract">
        <span class="position-detail__contract-label">Contract</span>
        <span class="position-detail__contract-value mono">
          {{ recommendation.recommended_contract }}
        </span>
      </div>

      <!-- Key-Value Grid -->
      <div class="position-detail__grid">
        <div class="position-detail__kv">
          <span class="position-detail__key">Entry</span>
          <span class="position-detail__value mono">{{ displayPrice(recommendation.entry_price) }}</span>
        </div>
        <div class="position-detail__kv">
          <span class="position-detail__key">Stop</span>
          <span class="position-detail__value mono">{{ displayPrice(recommendation.stop_loss) }}</span>
        </div>
        <div class="position-detail__kv">
          <span class="position-detail__key">Target</span>
          <span class="position-detail__value mono">{{ displayPrice(recommendation.take_profit) }}</span>
        </div>
        <div class="position-detail__kv">
          <span class="position-detail__key">R/R</span>
          <span class="position-detail__value mono">{{ formatRatio(recommendation.risk_reward_ratio) }}</span>
        </div>
        <div class="position-detail__kv">
          <span class="position-detail__key">Size</span>
          <span class="position-detail__value mono">{{ formatSizePct(recommendation.position_size_pct) }}</span>
        </div>
        <div class="position-detail__kv">
          <span class="position-detail__key">Strategy</span>
          <span class="position-detail__value">{{ recommendation.recommended_strategy ?? '--' }}</span>
        </div>
      </div>

      <!-- Max Loss -->
      <div class="position-detail__kv position-detail__kv--wide">
        <span class="position-detail__key">Max Loss</span>
        <span class="position-detail__value mono risk-value">
          {{ displayPrice(recommendation.max_loss_estimate) }}
        </span>
      </div>

      <!-- Rationale -->
      <div class="position-detail__rationale">
        <span class="position-detail__section-label">Rationale</span>
        <p class="position-detail__text">{{ recommendation.position_rationale }}</p>
      </div>

      <!-- Strategy Rationale -->
      <div v-if="recommendation.strategy_rationale" class="position-detail__rationale">
        <span class="position-detail__section-label">Strategy Rationale</span>
        <p class="position-detail__text">{{ recommendation.strategy_rationale }}</p>
      </div>

      <!-- Entry / Exit Criteria -->
      <div class="position-detail__criteria">
        <div class="position-detail__criterion">
          <span class="position-detail__section-label">Entry Criteria</span>
          <p class="position-detail__text">{{ recommendation.entry_criteria }}</p>
        </div>
        <div class="position-detail__criterion">
          <span class="position-detail__section-label">Exit Criteria</span>
          <p class="position-detail__text">{{ recommendation.exit_criteria }}</p>
        </div>
      </div>

      <!-- Risk Assessment -->
      <div v-if="recommendation.risk_assessment" class="position-detail__rationale">
        <span class="position-detail__section-label">Risk Assessment</span>
        <p class="position-detail__text">{{ recommendation.risk_assessment }}</p>
      </div>
    </div>
  </DeskCard>
</template>

<style scoped>
.position-detail {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.position-detail__contract {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 0.75rem;
  background: var(--p-surface-900, #111);
  border-radius: 0.5rem;
}

.position-detail__contract-label {
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--p-surface-400, #888);
}

.position-detail__contract-value {
  font-size: 1rem;
  font-weight: 600;
  color: var(--p-surface-100, #eee);
}

.position-detail__grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0.5rem;
}

@media (max-width: 480px) {
  .position-detail__grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

.position-detail__kv {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  padding: 0.4rem 0.6rem;
  background: var(--p-surface-900, #111);
  border-radius: 0.375rem;
}

.position-detail__kv--wide {
  max-width: 10rem;
}

.position-detail__key {
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--p-surface-400, #888);
}

.position-detail__value {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--p-surface-200, #ccc);
}

.mono {
  font-family: var(--font-mono);
}

.risk-value {
  color: var(--accent-red, #ef4444);
}

.position-detail__rationale,
.position-detail__criteria {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.position-detail__criteria {
  gap: 0.75rem;
}

.position-detail__criterion {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.position-detail__section-label {
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--p-surface-400, #888);
  font-weight: 600;
}

.position-detail__text {
  margin: 0;
  font-size: 0.85rem;
  line-height: 1.5;
  color: var(--p-surface-200, #ccc);
}
</style>

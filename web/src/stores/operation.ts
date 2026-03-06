import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '@/composables/useApi'

export type OperationType = 'scan' | 'batch_debate' | null

interface StatusResponse {
  busy: boolean
  active_scan_ids: number[]
  active_debate_ids: number[]
}

export const useOperationStore = defineStore('operation', () => {
  const operationType = ref<OperationType>(null)

  const inProgress = computed(() => operationType.value !== null)

  function start(type: 'scan' | 'batch_debate'): void {
    operationType.value = type
  }

  function finish(): void {
    operationType.value = null
  }

  async function syncFromServer(): Promise<void> {
    try {
      const status = await api<StatusResponse>('/api/status')
      if (!status.busy) {
        operationType.value = null
      } else if (status.active_scan_ids.length > 0) {
        operationType.value = 'scan'
      } else if (status.active_debate_ids.length > 0) {
        operationType.value = 'batch_debate'
      }
    } catch {
      // Server unreachable — keep current state
    }
  }

  return { operationType, inProgress, start, finish, syncFromServer }
})

import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '@/composables/useApi'
import type { Watchlist, WatchlistDetail } from '@/types'

export const useWatchlistStore = defineStore('watchlist', () => {
  // --- State ---
  const watchlists = ref<Watchlist[]>([])
  const currentWatchlist = ref<WatchlistDetail | null>(null)
  const loading = ref(false)

  // --- Actions ---
  async function fetchWatchlists(): Promise<void> {
    loading.value = true
    try {
      watchlists.value = await api<Watchlist[]>('/api/watchlists')
    } finally {
      loading.value = false
    }
  }

  async function fetchWatchlist(id: number): Promise<void> {
    loading.value = true
    try {
      currentWatchlist.value = await api<WatchlistDetail>(`/api/watchlists/${id}`)
    } finally {
      loading.value = false
    }
  }

  async function createWatchlist(name: string, description?: string): Promise<Watchlist> {
    const created = await api<Watchlist>('/api/watchlists', {
      method: 'POST',
      body: { name, description: description ?? null },
    })
    await fetchWatchlists()
    return created
  }

  async function updateWatchlist(
    id: number,
    data: { name?: string; description?: string },
  ): Promise<Watchlist> {
    const updated = await api<Watchlist>(`/api/watchlists/${id}`, {
      method: 'PUT',
      body: data,
    })
    await fetchWatchlists()
    if (currentWatchlist.value?.id === id) {
      await fetchWatchlist(id)
    }
    return updated
  }

  async function deleteWatchlist(id: number): Promise<void> {
    await api<undefined>(`/api/watchlists/${id}`, { method: 'DELETE' })
    if (currentWatchlist.value?.id === id) {
      currentWatchlist.value = null
    }
    await fetchWatchlists()
  }

  async function addTicker(watchlistId: number, ticker: string): Promise<void> {
    await api<{ id: number; watchlist_id: number; ticker: string; added_at: string }>(
      `/api/watchlists/${watchlistId}/tickers`,
      {
        method: 'POST',
        body: { ticker: ticker.toUpperCase().trim() },
      },
    )
    if (currentWatchlist.value?.id === watchlistId) {
      await fetchWatchlist(watchlistId)
    }
  }

  async function removeTicker(watchlistId: number, ticker: string): Promise<void> {
    await api<undefined>(`/api/watchlists/${watchlistId}/tickers/${ticker}`, {
      method: 'DELETE',
    })
    if (currentWatchlist.value?.id === watchlistId) {
      await fetchWatchlist(watchlistId)
    }
  }

  return {
    watchlists,
    currentWatchlist,
    loading,
    fetchWatchlists,
    fetchWatchlist,
    createWatchlist,
    updateWatchlist,
    deleteWatchlist,
    addTicker,
    removeTicker,
  }
})

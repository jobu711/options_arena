import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '@/composables/useApi'
import type { Watchlist, WatchlistDetail } from '@/types'

export const useWatchlistStore = defineStore('watchlist', () => {
  // --- State ---
  const watchlists = ref<Watchlist[]>([])
  const activeWatchlist = ref<WatchlistDetail | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  // --- Actions ---
  async function fetchWatchlists(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      watchlists.value = await api<Watchlist[]>('/api/watchlist')
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to load watchlists'
    } finally {
      loading.value = false
    }
  }

  async function createWatchlist(name: string): Promise<Watchlist | null> {
    error.value = null
    try {
      const res = await api<{ id: number; name: string }>('/api/watchlist', {
        method: 'POST',
        body: { name },
      })
      // Refresh the list after creation
      await fetchWatchlists()
      return { id: res.id, name: res.name, created_at: new Date().toISOString() }
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to create watchlist'
      return null
    }
  }

  async function deleteWatchlist(id: number): Promise<boolean> {
    error.value = null
    try {
      await api<void>(`/api/watchlist/${id}`, { method: 'DELETE' })
      // Clear active if it was the deleted one
      if (activeWatchlist.value?.id === id) {
        activeWatchlist.value = null
      }
      await fetchWatchlists()
      return true
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to delete watchlist'
      return false
    }
  }

  async function fetchWatchlistDetail(id: number): Promise<void> {
    loading.value = true
    error.value = null
    try {
      activeWatchlist.value = await api<WatchlistDetail>(`/api/watchlist/${id}`)
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to load watchlist details'
    } finally {
      loading.value = false
    }
  }

  async function addTicker(watchlistId: number, ticker: string): Promise<boolean> {
    error.value = null
    try {
      await api<{ status: string; ticker: string }>(
        `/api/watchlist/${watchlistId}/tickers`,
        {
          method: 'POST',
          body: { ticker },
        },
      )
      // Refresh detail if active
      if (activeWatchlist.value?.id === watchlistId) {
        await fetchWatchlistDetail(watchlistId)
      }
      return true
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to add ticker'
      return false
    }
  }

  async function removeTicker(watchlistId: number, ticker: string): Promise<boolean> {
    error.value = null
    try {
      await api<void>(`/api/watchlist/${watchlistId}/tickers/${ticker}`, {
        method: 'DELETE',
      })
      // Refresh detail if active
      if (activeWatchlist.value?.id === watchlistId) {
        await fetchWatchlistDetail(watchlistId)
      }
      return true
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to remove ticker'
      return false
    }
  }

  function reset(): void {
    watchlists.value = []
    activeWatchlist.value = null
    loading.value = false
    error.value = null
  }

  return {
    watchlists,
    activeWatchlist,
    loading,
    error,
    fetchWatchlists,
    createWatchlist,
    deleteWatchlist,
    fetchWatchlistDetail,
    addTicker,
    removeTicker,
    reset,
  }
})

/** Generic typed WebSocket composable with auto-reconnect. */

import { ref, onUnmounted } from 'vue'

interface UseWebSocketOptions<T> {
  url: string
  onMessage: (event: T) => void
  onError?: (error: Event) => void
  reconnectInterval?: number
  maxReconnectAttempts?: number
}

export function useWebSocket<T>(options: UseWebSocketOptions<T>) {
  const connected = ref(false)
  const reconnecting = ref(false)
  let ws: WebSocket | null = null
  let reconnectCount = 0

  function connect(): void {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = options.url.startsWith('ws')
      ? options.url
      : `${protocol}//${window.location.host}${options.url}`

    ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      connected.value = true
      reconnecting.value = false
      reconnectCount = 0
    }

    ws.onmessage = (e: MessageEvent) => {
      options.onMessage(JSON.parse(e.data as string) as T)
    }

    ws.onclose = () => {
      connected.value = false
      const max = options.maxReconnectAttempts ?? 5
      if (reconnectCount < max) {
        reconnecting.value = true
        const delay = (options.reconnectInterval ?? 2000) * Math.pow(2, reconnectCount)
        setTimeout(connect, Math.min(delay, 30_000))
        reconnectCount++
      } else {
        reconnecting.value = false
      }
    }

    if (options.onError) {
      ws.onerror = options.onError
    }
  }

  function send(data: unknown): void {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(data))
    }
  }

  function close(): void {
    reconnectCount = Infinity // prevent reconnect
    ws?.close()
  }

  connect()
  onUnmounted(close)

  return { connected, reconnecting, send, close }
}

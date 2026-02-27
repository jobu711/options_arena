/**
 * Inject a fake WebSocket via addInitScript that intercepts connections
 * matching `/ws/scan/{scanId}` and replays the given events.
 *
 * Uses a plain object (NOT Object.create(WebSocket.prototype)) to avoid
 * inheriting accessor properties that prevent onmessage/onopen assignment.
 */
import type { Page } from '@playwright/test'

export async function injectFakeScanWebSocket(
  page: Page,
  scanId: number,
  events: unknown[],
  options?: { lastEventDelay?: number },
): Promise<void> {
  const lastEventDelay = options?.lastEventDelay
  await page.addInitScript(
    ({ events, scanId, lastEventDelay }) => {
      const RealWS = window.WebSocket
      window.WebSocket = function (
        this: WebSocket,
        url: string | URL,
        protocols?: string | string[],
      ) {
        const urlStr = typeof url === 'string' ? url : url.toString()
        if (urlStr.includes(`/ws/scan/${scanId}`)) {
          const fake: Record<string, unknown> = {
            readyState: 0,
            url: urlStr,
            protocol: '',
            extensions: '',
            bufferedAmount: 0,
            binaryType: 'blob',
            onopen: null,
            onmessage: null,
            onclose: null,
            onerror: null,
            CONNECTING: 0,
            OPEN: 1,
            CLOSING: 2,
            CLOSED: 3,
            send() {},
            close() { fake.readyState = 3 },
            addEventListener() {},
            removeEventListener() {},
            dispatchEvent() { return true },
          }
          setTimeout(() => {
            fake.readyState = 1
            if (typeof fake.onopen === 'function') {
              fake.onopen(new Event('open'))
            }
            let delay = 50
            for (let i = 0; i < events.length; i++) {
              const isLast = i === events.length - 1
              delay += isLast && lastEventDelay ? lastEventDelay : 150
              const event = events[i]
              setTimeout(() => {
                if (fake.readyState === 1 && typeof fake.onmessage === 'function') {
                  fake.onmessage(new MessageEvent('message', {
                    data: JSON.stringify(event),
                  }))
                }
              }, delay)
            }
          }, 50)
          return fake as unknown as WebSocket
        }
        return new RealWS(url, protocols)
      } as unknown as typeof WebSocket
      Object.assign(window.WebSocket, {
        CONNECTING: 0,
        OPEN: 1,
        CLOSING: 2,
        CLOSED: 3,
      })
    },
    { events, scanId, lastEventDelay: lastEventDelay ?? null },
  )
}

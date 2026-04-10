const WS_URL = `ws://${window.location.host}/ws/events`
const RECONNECT_DELAY_MS = 3000

export function createWebSocket({ onOpen, onClose, onEvent }) {
  let ws = null
  let closed = false

  function connect() {
    if (closed) return

    ws = new WebSocket(WS_URL)

    ws.onopen = () => {
      console.log('[MCPSec WS] Connected')
      onOpen?.()
    }

    ws.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data)
        onEvent?.(event)
      } catch {
        // ignore malformed messages
      }
    }

    ws.onclose = () => {
      console.log('[MCPSec WS] Disconnected — reconnecting in 3s...')
      onClose?.()
      if (!closed) {
        setTimeout(connect, RECONNECT_DELAY_MS)
      }
    }

    ws.onerror = () => {
      ws.close()
    }
  }

  connect()

  return {
    close() {
      closed = true
      ws?.close()
    },
  }
}

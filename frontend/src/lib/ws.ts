type WsHandler = (event: Record<string, unknown>) => void

class XillionWebSocket {
  private ws: WebSocket | null = null
  private handlers: WsHandler[] = []
  private reconnectDelay = 2000

  connect() {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${proto}//${window.location.host}/ws`
    this.ws = new WebSocket(url)

    this.ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data)
        this.handlers.forEach((h) => h(data))
      } catch {
        // ignore non-JSON messages
      }
    }

    this.ws.onclose = () => {
      setTimeout(() => this.connect(), this.reconnectDelay)
    }

    this.ws.onerror = () => {
      this.ws?.close()
    }
  }

  subscribe(handler: WsHandler): () => void {
    this.handlers.push(handler)
    return () => {
      this.handlers = this.handlers.filter((h) => h !== handler)
    }
  }

  ping() {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send('ping')
    }
  }
}

export const wsClient = new XillionWebSocket()

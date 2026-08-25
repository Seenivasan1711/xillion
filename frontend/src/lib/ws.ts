type WsHandler = (event: Record<string, unknown>) => void
type WsStatus = 'connecting' | 'open' | 'closed'
type StatusHandler = (status: WsStatus) => void

class XillionWebSocket {
  private ws: WebSocket | null = null
  private handlers: WsHandler[] = []
  private statusHandlers: StatusHandler[] = []
  private reconnectDelay = 2000
  private status: WsStatus = 'closed'

  private setStatus(s: WsStatus) {
    this.status = s
    this.statusHandlers.forEach((h) => h(s))
  }

  connect() {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${proto}//${window.location.host}/ws`
    this.setStatus('connecting')
    this.ws = new WebSocket(url)

    this.ws.onopen = () => this.setStatus('open')

    this.ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data)
        this.handlers.forEach((h) => h(data))
      } catch {
        // ignore non-JSON messages
      }
    }

    this.ws.onclose = () => {
      this.setStatus('closed')
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

  // Reports real connection state -- callers shouldn't infer "live" purely
  // from having once called connect(); a dropped connection reconnects
  // automatically but there's a gap where nothing is flowing, and no
  // caller (e.g. Logs' "tailing" badge) should silently claim otherwise.
  onStatus(handler: StatusHandler): () => void {
    this.statusHandlers.push(handler)
    handler(this.status)
    return () => {
      this.statusHandlers = this.statusHandlers.filter((h) => h !== handler)
    }
  }

  getStatus(): WsStatus {
    return this.status
  }

  ping() {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send('ping')
    }
  }
}

export const wsClient = new XillionWebSocket()

import { createContext, useCallback, useContext, useRef, useState } from 'react'
import { CheckCircle, XCircle, Info, X } from 'lucide-react'

type ToastTone = 'ok' | 'error' | 'info'
interface ToastItem { id: number; tone: ToastTone; message: string }

const ToastContext = createContext<(tone: ToastTone, message: string) => void>(() => {})

export function useToast() {
  return useContext(ToastContext)
}

const ICONS: Record<ToastTone, typeof CheckCircle> = { ok: CheckCircle, error: XCircle, info: Info }

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])
  const nextId = useRef(0)

  const push = useCallback((tone: ToastTone, message: string) => {
    const id = nextId.current++
    setItems((cur) => [...cur, { id, tone, message }])
    setTimeout(() => setItems((cur) => cur.filter((t) => t.id !== id)), 5000)
  }, [])

  const dismiss = (id: number) => setItems((cur) => cur.filter((t) => t.id !== id))

  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="toast-stack">
        {items.map((t) => {
          const Icon = ICONS[t.tone]
          return (
            <div key={t.id} className={`toast toast-${t.tone}`}>
              <Icon size={15} className="ico" />
              <span>{t.message}</span>
              <button className="toast-close" onClick={() => dismiss(t.id)}><X size={13} /></button>
            </div>
          )
        })}
      </div>
    </ToastContext.Provider>
  )
}

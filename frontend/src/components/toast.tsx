import { CheckCircle2, XCircle } from 'lucide-react'
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'

type Toast = { id: number; tone: 'success' | 'error'; text: string }
const ToastContext = createContext<{ success: (t: string) => void; error: (t: string | unknown) => void } | null>(null)

let nextId = 1

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const push = useCallback((tone: Toast['tone'], text: string) => {
    const id = nextId++
    setToasts((t) => [...t, { id, tone, text }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), tone === 'error' ? 6000 : 3500)
  }, [])
  const api = useMemo(() => ({
    success: (t: string) => push('success', t),
    error: (e: string | unknown) => push('error', typeof e === 'string' ? e : e instanceof Error ? e.message : 'Something went wrong.'),
  }), [push])
  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-4 z-[60] flex flex-col items-center gap-2 px-4 sm:items-end sm:right-4 sm:left-auto" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className="animate-in pointer-events-auto flex max-w-sm items-start gap-2 rounded-lg border border-line bg-surface px-3 py-2.5 text-sm shadow-lg">
            {t.tone === 'success' ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-teal" /> : <XCircle className="mt-0.5 size-4 shrink-0 text-red" />}
            <span>{t.text}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast outside provider')
  return ctx
}

import { useMutation } from '@tanstack/react-query'
import { Bot, Loader2, Send, Sparkles, X } from 'lucide-react'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { api } from '../lib/api'
import { useUser } from '../lib/auth'
import type { Role } from '../lib/types'
import { AIBadge, cx, IconButton } from './ui'

type Msg = { role: 'user' | 'assistant'; content: string; tools?: string[]; ok?: boolean }
type ChatResponse = { ok: boolean; answer: string; tools_used: string[]; ai_generated: boolean }

const SUGGESTIONS: Record<Role, string[]> = {
  admin: ['What is the current headcount by department?', 'What was the payroll cost last month?', 'What is this month\'s attendance rate?'],
  hr: ['Who is on leave today?', 'Who came late most often this month?', 'What is this month\'s attendance rate?'],
  employee: ['How many sick leaves do I have left this year?', 'What is the late arrival rule?', 'How many days was I late this month?'],
}

export function AIChat() {
  const user = useUser()
  const [open, setOpen] = useState(false)
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<Msg[]>([])
  const endRef = useRef<HTMLDivElement>(null)

  const chat = useMutation({
    mutationFn: (text: string) => api.post<ChatResponse>('/ai/chat/', {
      message: text,
      history: messages.filter((m) => m.ok !== false).slice(-10).map(({ role, content }) => ({ role, content })),
    }),
    onSuccess: (r) => setMessages((m) => [...m, { role: 'assistant', content: r.answer, tools: r.tools_used, ok: r.ok }]),
    onError: (e) => setMessages((m) => [...m, { role: 'assistant', content: e instanceof Error ? e.message : 'The assistant failed.', ok: false }]),
  })

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, chat.isPending])

  const send = (text: string) => {
    const t = text.trim()
    if (!t || chat.isPending) return
    setMessages((m) => [...m, { role: 'user', content: t }])
    setInput('')
    chat.mutate(t)
  }
  const submit = (e: FormEvent) => { e.preventDefault(); send(input) }

  return (
    <>
      {!open && (
        <button onClick={() => setOpen(true)}
          className="fixed right-4 bottom-4 z-30 flex items-center gap-2 rounded-full bg-violet px-4 py-3 text-sm font-medium text-white shadow-lg hover:opacity-90 dark:text-navy">
          <Sparkles className="size-4" /> <span className="hidden sm:inline">Ask the assistant</span>
        </button>
      )}
      {open && (
        <div role="dialog" aria-label="HR assistant"
          className="animate-in fixed inset-x-0 bottom-0 z-40 flex h-[80vh] flex-col border border-line bg-surface shadow-2xl sm:inset-x-auto sm:right-4 sm:bottom-4 sm:h-[34rem] sm:w-[24rem] sm:rounded-2xl">
          <header className="flex items-center justify-between rounded-t-2xl border-b border-line px-4 py-3">
            <div className="flex items-center gap-2">
              <span className="rounded-lg bg-violet-soft p-1.5 text-violet"><Bot className="size-4" /></span>
              <div>
                <p className="text-sm font-semibold">HR assistant</p>
                <p className="text-[11px] text-muted">{user.role === 'employee' ? 'Your data and company policy' : 'Answers from live HR data'}</p>
              </div>
            </div>
            <IconButton label="Close assistant" onClick={() => setOpen(false)}><X className="size-4" /></IconButton>
          </header>
          <div className="flex-1 space-y-3 overflow-y-auto px-4 py-3">
            {!messages.length && (
              <div className="space-y-2">
                <p className="text-sm text-muted">Ask about attendance, leave, payroll or policy. Answers come from the same data as your dashboards. Roman Urdu works too.</p>
                {SUGGESTIONS[user.role].map((s) => (
                  <button key={s} onClick={() => send(s)}
                    className="block w-full rounded-lg border border-line px-3 py-2 text-left text-sm hover:bg-surface-2">{s}</button>
                ))}
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} className={cx('flex', m.role === 'user' ? 'justify-end' : 'justify-start')}>
                <div className={cx('max-w-[85%] rounded-2xl px-3 py-2 text-sm whitespace-pre-wrap',
                  m.role === 'user' ? 'bg-navy-2 text-white dark:bg-teal dark:text-navy' : m.ok === false ? 'bg-red-soft text-red' : 'bg-surface-2 text-ink')}>
                  {m.content}
                  {m.role === 'assistant' && m.ok && (
                    <div className="mt-1.5 flex flex-wrap items-center gap-1">
                      <AIBadge />
                      {m.tools?.map((t, j) => <span key={j} className="rounded bg-surface px-1.5 py-0.5 font-mono text-[10px] text-muted">{t}</span>)}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {chat.isPending && <div className="flex items-center gap-2 text-sm text-muted"><Loader2 className="size-4 animate-spin" /> Checking the records…</div>}
            <div ref={endRef} />
          </div>
          <form onSubmit={submit} className="flex gap-2 border-t border-line p-3">
            <label htmlFor="ai-input" className="sr-only">Message</label>
            <input id="ai-input" value={input} onChange={(e) => setInput(e.target.value)} maxLength={1000}
              placeholder="Type a question…" autoComplete="off"
              className="h-10 flex-1 rounded-lg border border-line bg-surface px-3 text-sm focus:border-teal focus:outline-none" />
            <button type="submit" disabled={!input.trim() || chat.isPending} aria-label="Send"
              className="flex size-10 items-center justify-center rounded-lg bg-violet text-white disabled:opacity-40 dark:text-navy"><Send className="size-4" /></button>
          </form>
        </div>
      )}
    </>
  )
}

import { AlertTriangle, ChevronLeft, ChevronRight, Inbox, Loader2, X } from 'lucide-react'
import {
  useEffect, useId, useRef, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode,
  type SelectHTMLAttributes, type TextareaHTMLAttributes,
} from 'react'
import { ApiError } from '../lib/api'
import { label as humanize } from '../lib/format'

export function cx(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(' ')
}

/* ---------- buttons ---------- */

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'success'
const VARIANTS: Record<Variant, string> = {
  primary: 'bg-navy-2 text-white hover:bg-navy dark:bg-teal dark:text-navy dark:hover:opacity-90',
  secondary: 'bg-surface text-ink border border-line hover:bg-surface-2',
  ghost: 'text-muted hover:text-ink hover:bg-surface-2',
  danger: 'bg-red text-white hover:opacity-90 dark:text-navy',
  success: 'bg-teal text-white hover:opacity-90 dark:text-navy',
}

export function Button({ variant = 'primary', loading, size = 'md', className, children, disabled, ...rest }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; loading?: boolean; size?: 'sm' | 'md' }) {
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={cx('inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors',
        'disabled:cursor-not-allowed disabled:opacity-50 whitespace-nowrap',
        size === 'sm' ? 'h-8 px-3 text-xs' : 'h-10 px-4 text-sm', VARIANTS[variant], className)}
    >
      {loading && <Loader2 className="size-4 animate-spin" aria-hidden />}
      {children}
    </button>
  )
}

export function IconButton({ label, className, children, ...rest }:
  ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button {...rest} aria-label={label} title={label}
      className={cx('inline-flex size-9 items-center justify-center rounded-lg text-muted hover:bg-surface-2 hover:text-ink', className)}>
      {children}
    </button>
  )
}

/* ---------- form fields ---------- */

const inputCls = 'w-full rounded-lg border border-line bg-surface px-3 h-10 text-sm text-ink placeholder:text-muted/70 ' +
  'focus:border-teal focus:outline-none focus:ring-2 focus:ring-teal/20 disabled:opacity-60'

export function Field({ label, error, hint, children, required, htmlFor }:
  { label: string; error?: string; hint?: string; children: ReactNode; required?: boolean; htmlFor?: string }) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={htmlFor} className="block text-xs font-medium text-muted">
        {label}{required && <span className="text-red"> *</span>}
      </label>
      {children}
      {error ? <p className="text-xs text-red" role="alert">{error}</p> : hint ? <p className="text-xs text-muted">{hint}</p> : null}
    </div>
  )
}

type WithField = { label: string; error?: string; hint?: string }

export function Input({ label, error, hint, className, ...rest }: InputHTMLAttributes<HTMLInputElement> & WithField) {
  const id = useId()
  return (
    <Field label={label} error={error} hint={hint} required={rest.required} htmlFor={id}>
      <input id={id} {...rest} aria-invalid={Boolean(error)} className={cx(inputCls, error && 'border-red', className)} />
    </Field>
  )
}

export function Select({ label, error, hint, children, className, ...rest }:
  SelectHTMLAttributes<HTMLSelectElement> & WithField) {
  const id = useId()
  return (
    <Field label={label} error={error} hint={hint} required={rest.required} htmlFor={id}>
      <select id={id} {...rest} aria-invalid={Boolean(error)} className={cx(inputCls, 'pr-8', error && 'border-red', className)}>
        {children}
      </select>
    </Field>
  )
}

export function Textarea({ label, error, hint, className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement> & WithField) {
  const id = useId()
  return (
    <Field label={label} error={error} hint={hint} required={rest.required} htmlFor={id}>
      <textarea id={id} {...rest} aria-invalid={Boolean(error)}
        className={cx(inputCls, 'h-auto min-h-20 py-2', error && 'border-red', className)} />
    </Field>
  )
}

export function FilterSelect({ value, onChange, children, label }:
  { value: string; onChange: (v: string) => void; children: ReactNode; label: string }) {
  return (
    <select aria-label={label} value={value} onChange={(e) => onChange(e.target.value)}
      className={cx(inputCls, 'w-auto min-w-36 h-9')}>{children}</select>
  )
}

/* ---------- layout pieces ---------- */

export function Card({ title, action, children, className, bodyClass }:
  { title?: ReactNode; action?: ReactNode; children: ReactNode; className?: string; bodyClass?: string }) {
  return (
    <section className={cx('rounded-xl border border-line bg-surface', className)}>
      {(title || action) && (
        <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
          <h2 className="text-sm font-semibold text-ink">{title}</h2>
          {action}
        </header>
      )}
      <div className={cx('p-4', bodyClass)}>{children}</div>
    </section>
  )
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  useEffect(() => { document.title = `${title} · AR&MS HCM Lite` }, [title])
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-ink sm:text-2xl">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

export function Kpi({ label, value, hint, tone = 'teal', icon }:
  { label: string; value: ReactNode; hint?: ReactNode; tone?: 'teal' | 'amber' | 'violet' | 'red' | 'blue'; icon?: ReactNode }) {
  const tones = { teal: 'text-teal bg-teal-soft', amber: 'text-amber bg-amber-soft', violet: 'text-violet bg-violet-soft',
    red: 'text-red bg-red-soft', blue: 'text-blue bg-blue-soft' }
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-medium text-muted">{label}</p>
        {icon && <span className={cx('rounded-lg p-1.5', tones[tone])}>{icon}</span>}
      </div>
      <p className="tabular mt-2 text-2xl font-semibold text-ink">{value}</p>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </div>
  )
}

/* ---------- states ---------- */

export function Spinner({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-10 text-sm text-muted" role="status">
      <Loader2 className="size-4 animate-spin" aria-hidden /> {label}
    </div>
  )
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx('animate-pulse rounded-lg bg-surface-2', className)} />
}

export function EmptyState({ title, body, action, icon }: { title: string; body?: ReactNode; action?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center px-4 py-10 text-center">
      <span className="mb-3 rounded-full bg-surface-2 p-3 text-muted">{icon ?? <Inbox className="size-5" />}</span>
      <p className="text-sm font-medium text-ink">{title}</p>
      {body && <p className="mt-1 max-w-sm text-sm text-muted">{body}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function ErrorState({ error, retry }: { error: unknown; retry?: () => void }) {
  const msg = error instanceof Error ? error.message : 'Something went wrong.'
  const denied = error instanceof ApiError && error.status === 403
  return (
    <div className="flex flex-col items-center justify-center px-4 py-10 text-center" role="alert">
      <span className="mb-3 rounded-full bg-red-soft p-3 text-red"><AlertTriangle className="size-5" /></span>
      <p className="text-sm font-medium text-ink">{denied ? 'Access denied' : 'Could not load this'}</p>
      <p className="mt-1 max-w-md text-sm text-muted">{msg}</p>
      {retry && !denied && <Button variant="secondary" size="sm" className="mt-4" onClick={retry}>Try again</Button>}
    </div>
  )
}

export function Alert({ tone = 'red', children }: { tone?: 'red' | 'amber' | 'teal' | 'blue'; children: ReactNode }) {
  const tones = { red: 'bg-red-soft text-red', amber: 'bg-amber-soft text-amber', teal: 'bg-teal-soft text-teal', blue: 'bg-blue-soft text-blue' }
  return <div className={cx('rounded-lg px-3 py-2 text-sm', tones[tone])} role={tone === 'red' ? 'alert' : 'status'}>{children}</div>
}

/* ---------- badges ---------- */

const STATUS_TONE: Record<string, string> = {
  present: 'teal', approved: 'teal', active: 'teal', finalized: 'teal', ok: 'teal',
  late: 'amber', pending: 'amber', probation: 'amber', half_day: 'amber', draft: 'amber', not_marked: 'gray',
  missing_checkout: 'violet', on_leave: 'blue', camera: 'blue', correction: 'violet', ai: 'violet',
  absent: 'red', rejected: 'red', exited: 'red', inactive: 'red', error: 'red', timeout: 'red', invalid_output: 'red',
  cancelled: 'gray', weekend: 'gray', holiday: 'gray', future: 'gray', not_employed: 'gray', unconfigured: 'gray',
}
const TONE_CLS: Record<string, string> = {
  teal: 'bg-teal-soft text-teal', amber: 'bg-amber-soft text-amber', violet: 'bg-violet-soft text-violet',
  blue: 'bg-blue-soft text-blue', red: 'bg-red-soft text-red', gray: 'bg-surface-2 text-muted border border-line',
}

export function Badge({ children, tone = 'gray' }: { children: ReactNode; tone?: string }) {
  return <span className={cx('inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap', TONE_CLS[tone] ?? TONE_CLS.gray)}>{children}</span>
}

export function StatusBadge({ status, text }: { status: string; text?: string }) {
  return <Badge tone={STATUS_TONE[status] ?? 'gray'}>{text ?? humanize(status)}</Badge>
}

export function AIBadge() {
  return <Badge tone="violet">AI-generated</Badge>
}

/* ---------- table ---------- */

export interface Column<T> { key: string; header: ReactNode; cell: (row: T) => ReactNode; className?: string }

export function Table<T>({ columns, rows, rowKey, empty, onRowClick }:
  { columns: Column<T>[]; rows: T[]; rowKey: (r: T) => string | number; empty?: ReactNode; onRowClick?: (r: T) => void }) {
  if (!rows.length) return <>{empty ?? <EmptyState title="Nothing here yet" />}</>
  return (
    <div className="-mx-4 overflow-x-auto">
      <table className="w-full text-left text-sm" style={{ minWidth: Math.min(640, columns.length * 130) }}>
        <thead>
          <tr className="border-b border-line text-xs text-muted">
            {columns.map((c) => <th key={c.key} scope="col" className={cx('px-4 py-2 font-medium', c.className)}>{c.header}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={rowKey(r)} onClick={onRowClick ? () => onRowClick(r) : undefined}
              className={cx('border-b border-line last:border-0', onRowClick && 'cursor-pointer hover:bg-surface-2')}>
              {columns.map((c) => <td key={c.key} className={cx('px-4 py-2.5 align-middle', c.className)}>{c.cell(r)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function Pagination({ page, count, pageSize = 20, onPage }: { page: number; count: number; pageSize?: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(count / pageSize))
  if (count <= pageSize) return null
  return (
    <div className="mt-3 flex items-center justify-between text-xs text-muted">
      <span>{(page - 1) * pageSize + 1}–{Math.min(page * pageSize, count)} of {count}</span>
      <div className="flex gap-1">
        <IconButton label="Previous page" disabled={page <= 1} onClick={() => onPage(page - 1)} className="disabled:opacity-40"><ChevronLeft className="size-4" /></IconButton>
        <span className="self-center px-2">Page {page} / {pages}</span>
        <IconButton label="Next page" disabled={page >= pages} onClick={() => onPage(page + 1)} className="disabled:opacity-40"><ChevronRight className="size-4" /></IconButton>
      </div>
    </div>
  )
}

/* ---------- dialog ---------- */

export function Modal({ open, onClose, title, children, footer, wide }:
  { open: boolean; onClose: () => void; title: string; children: ReactNode; footer?: ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const prev = document.activeElement as HTMLElement | null
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    setTimeout(() => ref.current?.querySelector<HTMLElement>('input,select,textarea,button')?.focus(), 0)
    return () => { document.removeEventListener('keydown', onKey); prev?.focus() }
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-navy/50 p-0 backdrop-blur-[1px] sm:items-center sm:p-4"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div ref={ref} role="dialog" aria-modal="true" aria-label={title}
        className={cx('animate-in flex max-h-[92vh] w-full flex-col rounded-t-2xl border border-line bg-surface shadow-xl sm:rounded-2xl',
          wide ? 'sm:max-w-3xl' : 'sm:max-w-lg')}>
        <header className="flex items-center justify-between border-b border-line px-5 py-3">
          <h2 className="text-base font-semibold">{title}</h2>
          <IconButton label="Close" onClick={onClose}><X className="size-4" /></IconButton>
        </header>
        <div className="overflow-y-auto px-5 py-4">{children}</div>
        {footer && <footer className="flex justify-end gap-2 border-t border-line px-5 py-3">{footer}</footer>}
      </div>
    </div>
  )
}

export function ConfirmDialog({ open, title, body, confirmLabel = 'Confirm', tone = 'primary', loading, onConfirm, onClose }:
  { open: boolean; title: string; body: ReactNode; confirmLabel?: string; tone?: Variant; loading?: boolean; onConfirm: () => void; onClose: () => void }) {
  return (
    <Modal open={open} onClose={onClose} title={title}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button>
        <Button variant={tone} loading={loading} onClick={onConfirm}>{confirmLabel}</Button></>}>
      <div className="text-sm text-muted">{body}</div>
    </Modal>
  )
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { id: T; label: string }[]; value: T; onChange: (t: T) => void }) {
  return (
    <div role="tablist" className="mb-4 flex gap-1 overflow-x-auto border-b border-line">
      {tabs.map((t) => (
        <button key={t.id} role="tab" aria-selected={value === t.id} onClick={() => onChange(t.id)}
          className={cx('-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium',
            value === t.id ? 'border-teal text-ink' : 'border-transparent text-muted hover:text-ink')}>
          {t.label}
        </button>
      ))}
    </div>
  )
}

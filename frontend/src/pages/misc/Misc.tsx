import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Megaphone, Plus, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useToast } from '../../components/toast'
import {
  Alert, Badge, Button, Card, ConfirmDialog, EmptyState, ErrorState, FilterSelect, IconButton, Input, Modal, PageHeader, Pagination,
  Spinner, StatusBadge, Table, Textarea,
} from '../../components/ui'
import { api, fieldError, qs } from '../../lib/api'
import { useUser } from '../../lib/auth'
import { fmtDateTime, label } from '../../lib/format'
import type { Announcement, Employee, Page } from '../../lib/types'
import { ChangePasswordForm } from '../auth/AuthPages'

export function AnnouncementsPage() {
  const user = useUser()
  const qc = useQueryClient()
  const toast = useToast()
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ title: '', body: '' })
  const [deleting, setDeleting] = useState<Announcement | null>(null)
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ['announcements', page], queryFn: () => api.get<Page<Announcement>>(`/announcements/?page=${page}`) })
  const post = useMutation({
    mutationFn: () => api.post('/announcements/', form),
    onSuccess: () => { setOpen(false); setForm({ title: '', body: '' }); qc.invalidateQueries({ queryKey: ['announcements'] }); toast.success('Announcement posted. Everyone was notified.') },
  })
  const remove = useMutation({
    mutationFn: (a: Announcement) => api.del(`/announcements/${a.id}/`),
    onSuccess: () => { setDeleting(null); qc.invalidateQueries({ queryKey: ['announcements'] }); toast.success('Announcement removed.') },
    onError: (e) => { setDeleting(null); toast.error(e) },
  })
  const canPost = user.role !== 'employee'
  return (
    <>
      <PageHeader title="Announcements" subtitle="Company news shown on every dashboard."
        actions={canPost && <Button onClick={() => { post.reset(); setOpen(true) }}><Plus className="size-4" /> New announcement</Button>} />
      {error ? <ErrorState error={error} retry={refetch} /> : isLoading ? <Spinner /> : !data?.results.length ? (
        <Card><EmptyState icon={<Megaphone className="size-5" />} title="No announcements yet" body={canPost ? 'Post the first update for the team.' : undefined} /></Card>
      ) : (
        <div className="space-y-3">
          {data.results.map((a) => (
            <Card key={a.id}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h2 className="font-semibold">{a.title}</h2>
                  <p className="mt-1 text-xs text-muted">{a.created_by_name} · {label(a.created_by_role === 'hr' ? 'HR' : a.created_by_role)} · {fmtDateTime(a.created_at)}</p>
                  <p className="mt-3 text-sm whitespace-pre-line">{a.body}</p>
                </div>
                {(user.role === 'admin' || (canPost && a.created_by_name === user.full_name)) && (
                  <IconButton label="Delete announcement" onClick={() => setDeleting(a)}><Trash2 className="size-4" /></IconButton>
                )}
              </div>
            </Card>
          ))}
          <Pagination page={page} count={data.count} onPage={setPage} />
        </div>
      )}
      <Modal open={open} onClose={() => setOpen(false)} title="New announcement"
        footer={<><Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button><Button loading={post.isPending} onClick={() => post.mutate()}>Post</Button></>}>
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); post.mutate() }}>
          <Input label="Title" required maxLength={200} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} error={fieldError(post.error, 'title')} />
          <Textarea label="Message" required rows={6} value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} error={fieldError(post.error, 'body')} />
          <button type="submit" hidden />
        </form>
      </Modal>
      <ConfirmDialog open={deleting !== null} onClose={() => setDeleting(null)} title="Delete announcement?" tone="danger" confirmLabel="Delete"
        loading={remove.isPending} onConfirm={() => deleting && remove.mutate(deleting)} body={<>“{deleting?.title}” will be removed for everyone.</>} />
    </>
  )
}

interface AuditEntry { id: number; actor_email: string; actor_role: string; action: string; entity_type: string; entity_id: string; summary: string; before: unknown; after: unknown; ip_address: string; created_at: string }

export function AuditLogPage() {
  const [search, setSearch] = useState('')
  const [debounced, setDebounced] = useState('')
  const [entity, setEntity] = useState('')
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState<AuditEntry | null>(null)
  useEffect(() => { const t = setTimeout(() => { setDebounced(search); setPage(1) }, 300); return () => clearTimeout(t) }, [search])
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['audit', debounced, entity, page],
    queryFn: () => api.get<Page<AuditEntry>>(`/audit-logs/${qs({ search: debounced, entity_type: entity, page })}`),
    placeholderData: (p) => p,
  })
  const entities = ['user', 'employee', 'company_settings', 'department', 'designation', 'leave_type', 'holiday', 'attendance', 'attendance_correction', 'leave_request', 'salary_structure', 'payroll_run', 'announcement']
  return (
    <>
      <PageHeader title="Audit log" subtitle="Every important action with who did it and what changed. Entries cannot be edited or deleted." />
      <Card>
        <div className="mb-3 flex flex-wrap gap-2">
          <input aria-label="Search audit log" placeholder="Search action or summary" value={search} onChange={(e) => setSearch(e.target.value)}
            className="h-9 w-full max-w-xs rounded-lg border border-line bg-surface px-3 text-sm focus:border-teal focus:outline-none" />
          <FilterSelect label="Entity" value={entity} onChange={(v) => { setEntity(v); setPage(1) }}>
            <option value="">All entities</option>{entities.map((e) => <option key={e} value={e}>{label(e)}</option>)}
          </FilterSelect>
        </div>
        {error ? <ErrorState error={error} retry={refetch} /> : isLoading ? <Spinner /> : (
          <>
            <Table rows={data?.results ?? []} rowKey={(a) => a.id} onRowClick={setOpen} empty={<EmptyState title="No matching entries" />}
              columns={[
                { key: 't', header: 'When', cell: (a) => <span className="whitespace-nowrap">{fmtDateTime(a.created_at)}</span> },
                { key: 'a', header: 'Actor', cell: (a) => <div><p>{a.actor_email || 'system'}</p>{a.actor_role && <p className="text-xs text-muted">{a.actor_role.toUpperCase()}</p>}</div> },
                { key: 'x', header: 'Action', cell: (a) => <code className="text-xs">{a.action}</code> },
                { key: 'e', header: 'Entity', cell: (a) => `${label(a.entity_type)}${a.entity_id ? ` #${a.entity_id}` : ''}` },
                { key: 's', header: 'Summary', cell: (a) => <p className="max-w-sm">{a.summary}</p> },
              ]} />
            <Pagination page={page} count={data?.count ?? 0} onPage={setPage} />
          </>
        )}
      </Card>
      <Modal open={open !== null} onClose={() => setOpen(null)} title="Audit entry" wide>
        {open && (
          <div className="space-y-3 text-sm">
            <p><code>{open.action}</code> · {label(open.entity_type)} #{open.entity_id} · {fmtDateTime(open.created_at)}</p>
            <p className="text-muted">{open.actor_email || 'system'} {open.ip_address && `from ${open.ip_address}`}</p>
            <div className="grid gap-3 md:grid-cols-2">
              {(['before', 'after'] as const).map((k) => (
                <div key={k}>
                  <p className="mb-1 text-xs font-medium text-muted">{k === 'before' ? 'Before' : 'After'}</p>
                  <pre className="max-h-80 overflow-auto rounded-lg bg-surface-2 p-3 text-xs">{open[k] ? JSON.stringify(open[k], null, 2) : '—'}</pre>
                </div>
              ))}
            </div>
          </div>
        )}
      </Modal>
    </>
  )
}

interface AILogEntry { id: number; user_email: string; role: string; feature: string; prompt: string; tools_called: { name: string; error: boolean }[]; response: string; outcome: string; error: string; provider: string; model: string; latency_ms: number; created_at: string }

export function AILogsPage() {
  const [page, setPage] = useState(1)
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ['ai-logs', page], queryFn: () => api.get<Page<AILogEntry>>(`/ai/logs/?page=${page}`) })
  const status = useQuery({ queryKey: ['ai-status'], queryFn: () => api.get<{ configured: boolean; provider: string; rate_limit_per_hour: number }>('/ai/status/') })
  return (
    <>
      <PageHeader title="AI logs" subtitle="Every assistant call: who asked, which tools ran, outcome and latency." />
      {status.data && !status.data.configured && <div className="mb-4"><Alert tone="amber">The AI provider is not configured. Set AI_API_KEY on the server (see README).</Alert></div>}
      {status.data?.configured && <p className="mb-4 text-sm text-muted">Provider: <b>{status.data.provider}</b> · limit {status.data.rate_limit_per_hour} requests per user per hour.</p>}
      <Card>
        {error ? <ErrorState error={error} retry={refetch} /> : isLoading ? <Spinner /> : (
          <>
            <Table rows={data?.results ?? []} rowKey={(l) => l.id} empty={<EmptyState title="No AI calls yet" />}
              columns={[
                { key: 't', header: 'When', cell: (l) => <span className="whitespace-nowrap">{fmtDateTime(l.created_at)}</span> },
                { key: 'u', header: 'User', cell: (l) => <div><p>{l.user_email}</p><p className="text-xs text-muted">{l.role.toUpperCase()}</p></div> },
                { key: 'f', header: 'Feature', cell: (l) => <Badge tone="violet">{label(l.feature)}</Badge> },
                { key: 'p', header: 'Prompt', cell: (l) => <p className="line-clamp-2 max-w-xs">{l.prompt}</p> },
                { key: 'x', header: 'Tools', cell: (l) => l.tools_called.map((t) => t.name).join(', ') || '—' },
                { key: 'o', header: 'Outcome', cell: (l) => <div><StatusBadge status={l.outcome} />{l.error && <p className="mt-1 line-clamp-1 max-w-48 text-xs text-muted" title={l.error}>{l.error}</p>}</div> },
                { key: 'l', header: 'Latency', cell: (l) => `${(l.latency_ms / 1000).toFixed(1)} s` },
              ]} />
            <Pagination page={page} count={data?.count ?? 0} onPage={setPage} />
          </>
        )}
      </Card>
    </>
  )
}

export function ProfilePage() {
  const user = useUser()
  const qc = useQueryClient()
  const toast = useToast()
  const me = useQuery({ queryKey: ['me-employee'], queryFn: () => api.get<Employee>('/employees/me/'), enabled: Boolean(user.employee_id) })
  const [contact, setContact] = useState({ phone: '', address: '' })
  useEffect(() => { if (me.data) setContact({ phone: me.data.phone, address: me.data.address }) }, [me.data])
  const save = useMutation({
    mutationFn: () => api.patch<Employee>('/employees/me/', contact),
    onSuccess: (d) => { qc.setQueryData(['me-employee'], d); toast.success('Contact details updated.') },
  })
  return (
    <>
      <PageHeader title="My profile" subtitle={`${user.email} · ${user.role.toUpperCase()}`} />
      <div className="grid gap-5 lg:grid-cols-2">
        {user.employee_id && (
          <Card title="Contact details" action={<Link className="text-xs text-teal hover:underline" to={`/employees/${user.employee_id}`}>View full profile</Link>}>
            {me.isLoading ? <Spinner /> : me.data && (
              <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); save.mutate() }}>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div><p className="text-xs text-muted">Employee code</p><p>{me.data.employee_code}</p></div>
                  <div><p className="text-xs text-muted">Department</p><p>{me.data.department_name}</p></div>
                </div>
                <Input label="Phone" value={contact.phone} onChange={(e) => setContact({ ...contact, phone: e.target.value })} error={fieldError(save.error, 'phone')} />
                <Textarea label="Address" value={contact.address} onChange={(e) => setContact({ ...contact, address: e.target.value })} maxLength={300} />
                <p className="text-xs text-muted">Other details (name, department, salary) are managed by HR.</p>
                <Button type="submit" loading={save.isPending}>Save</Button>
              </form>
            )}
          </Card>
        )}
        <Card title="Change password"><ChangePasswordForm onDone={() => toast.success('Password changed. Other sessions were signed out.')} /></Card>
      </div>
    </>
  )
}

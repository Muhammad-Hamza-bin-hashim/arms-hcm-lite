import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { MapPin, Pencil, Plus, Trash2 } from 'lucide-react'
import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useToast } from '../../components/toast'
import {
  Alert, Badge, Button, Card, ConfirmDialog, ErrorState, IconButton, Input, Modal, PageHeader, Spinner, Table, Tabs,
} from '../../components/ui'
import { api, fieldError } from '../../lib/api'
import { useUser } from '../../lib/auth'
import { fmtDate, WEEKDAYS } from '../../lib/format'
import { useCompanySettings } from '../../lib/queries'
import type { CompanySettings } from '../../lib/types'

type Tab = 'company' | 'departments' | 'designations' | 'leave-types' | 'holidays'

export function OrganizationPage() {
  const user = useUser()
  const [params] = useSearchParams()
  const [tab, setTab] = useState<Tab>('company')
  const canEdit = user.role === 'admin'
  return (
    <>
      <PageHeader title="Organization" subtitle={canEdit ? 'Company rules, structure and calendar. Rule changes apply to new records only.' : 'Read-only view of company rules and structure.'} />
      {params.get('welcome') && (
        <div className="mb-4"><Alert tone="teal">Company created. Next: check office hours and location, add departments and designations, then create an HR login under Users &amp; logins.</Alert></div>
      )}
      <Tabs<Tab> value={tab} onChange={setTab} tabs={[
        { id: 'company', label: 'Company & rules' }, { id: 'departments', label: 'Departments' },
        { id: 'designations', label: 'Designations' }, { id: 'leave-types', label: 'Leave types' }, { id: 'holidays', label: 'Public holidays' },
      ]} />
      {tab === 'company' && <CompanyForm canEdit={canEdit} />}
      {tab === 'departments' && (
        <SimpleCrud endpoint="/departments/" queryKey="departments" entity="department" canEdit={canEdit}
          blank={{ name: '', code: '', is_active: true }}
          columns={[{ key: 'name', header: 'Name' }, { key: 'code', header: 'Code' },
            { key: 'employee_count', header: 'Employees', render: (r) => String(r.employee_count ?? 0) },
            { key: 'is_active', header: 'Status', render: (r) => r.is_active ? <Badge tone="teal">Active</Badge> : <Badge>Inactive</Badge> }]}
          fields={[{ key: 'name', label: 'Name', required: true }, { key: 'code', label: 'Code', required: true, hint: 'Short code, e.g. IT, FIN' },
            { key: 'is_active', label: 'Active', type: 'checkbox' }]} />
      )}
      {tab === 'designations' && (
        <SimpleCrud endpoint="/designations/" queryKey="designations" entity="designation" canEdit={canEdit}
          blank={{ name: '', is_active: true }}
          columns={[{ key: 'name', header: 'Name' }, { key: 'is_active', header: 'Status', render: (r) => r.is_active ? <Badge tone="teal">Active</Badge> : <Badge>Inactive</Badge> }]}
          fields={[{ key: 'name', label: 'Name', required: true }, { key: 'is_active', label: 'Active', type: 'checkbox' }]} />
      )}
      {tab === 'leave-types' && (
        <SimpleCrud endpoint="/leave-types/" queryKey="leave-types" entity="leave type" canEdit={canEdit} extraInvalidate="leave-type-options"
          blank={{ code: '', name: '', yearly_quota: '', is_paid: true, is_active: true }}
          columns={[{ key: 'name', header: 'Name' }, { key: 'code', header: 'Code' },
            { key: 'yearly_quota', header: 'Yearly quota', render: (r) => r.yearly_quota == null ? 'Unlimited' : String(r.yearly_quota) },
            { key: 'is_paid', header: 'Paid', render: (r) => r.is_paid ? 'Paid' : <Badge tone="amber">Unpaid</Badge> },
            { key: 'is_active', header: 'Status', render: (r) => r.is_active ? <Badge tone="teal">Active</Badge> : <Badge>Inactive</Badge> }]}
          fields={[{ key: 'name', label: 'Name', required: true }, { key: 'code', label: 'Code', required: true, hint: 'lowercase, e.g. annual' },
            { key: 'yearly_quota', label: 'Yearly quota (days)', type: 'number', hint: 'Leave empty for unlimited' },
            { key: 'is_paid', label: 'Paid leave', type: 'checkbox' }, { key: 'is_active', label: 'Active', type: 'checkbox' }]} />
      )}
      {tab === 'holidays' && (
        <SimpleCrud endpoint="/holidays/" queryKey="holidays" entity="holiday" canEdit={canEdit}
          blank={{ date: '', name: '' }}
          columns={[{ key: 'date', header: 'Date', render: (r) => fmtDate(r.date as string) }, { key: 'name', header: 'Name' }]}
          fields={[{ key: 'date', label: 'Date', type: 'date', required: true }, { key: 'name', label: 'Name', required: true }]} />
      )}
    </>
  )
}

/* ---------- company settings ---------- */

function CompanyForm({ canEdit }: { canEdit: boolean }) {
  const qc = useQueryClient()
  const toast = useToast()
  const { data, isLoading, error, refetch } = useCompanySettings()
  const [form, setForm] = useState<CompanySettings | null>(null)
  useEffect(() => { if (data) setForm(data) }, [data])
  const save = useMutation({
    mutationFn: (body: Partial<CompanySettings>) => api.patch<CompanySettings>('/settings/', body),
    onSuccess: (d) => { qc.setQueryData(['settings'], d); qc.invalidateQueries({ queryKey: ['setup-status'] }); toast.success('Settings saved. They apply to new records.') },
    onError: toast.error,
  })
  if (error) return <ErrorState error={error} retry={refetch} />
  if (isLoading || !form) return <Spinner />
  const set = <K extends keyof CompanySettings>(k: K, v: CompanySettings[K]) => setForm({ ...form, [k]: v })
  const toggleWeekend = (d: number) => set('weekend_days', form.weekend_days.includes(d) ? form.weekend_days.filter((x) => x !== d) : [...form.weekend_days, d].sort())
  const useMyLocation = () => navigator.geolocation?.getCurrentPosition(
    (p) => setForm({ ...form, office_lat: p.coords.latitude.toFixed(6), office_lng: p.coords.longitude.toFixed(6) }),
    () => toast.error('Could not read your location.'), { enableHighAccuracy: true })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    const { updated_at: _ignored, ...body } = form
    void _ignored
    save.mutate({ ...body, office_lat: body.office_lat || null, office_lng: body.office_lng || null })
  }
  const err = save.error
  return (
    <form onSubmit={submit} className="grid gap-5 lg:grid-cols-2">
      <fieldset disabled={!canEdit} className="contents">
        <Card title="Company profile">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2"><Input label="Company name" required value={form.company_name} onChange={(e) => set('company_name', e.target.value)} error={fieldError(err, 'company_name')} /></div>
            <Input label="Timezone" value={form.timezone} onChange={(e) => set('timezone', e.target.value)} error={fieldError(err, 'timezone')} hint="e.g. Asia/Karachi" />
            <Input label="Currency" value={form.currency} onChange={(e) => set('currency', e.target.value)} maxLength={8} />
          </div>
        </Card>
        <Card title="Attendance rules">
          <div className="grid gap-4 sm:grid-cols-2">
            <Input label="Office start" type="time" value={form.office_start.slice(0, 5)} onChange={(e) => set('office_start', e.target.value)} />
            <Input label="Office end" type="time" value={form.office_end.slice(0, 5)} onChange={(e) => set('office_end', e.target.value)} error={fieldError(err, 'office_end')} />
            <Input label="Grace time (minutes)" type="number" min={0} max={180} value={form.grace_minutes} onChange={(e) => set('grace_minutes', Number(e.target.value))} error={fieldError(err, 'grace_minutes')} />
            <Input label="Half day under (hours)" type="number" step="0.5" min={0.5} max={12} value={form.half_day_hours} onChange={(e) => set('half_day_hours', e.target.value)} error={fieldError(err, 'half_day_hours')} />
          </div>
          <fieldset className="mt-4">
            <legend className="mb-1.5 text-xs font-medium text-muted">Weekend days</legend>
            <div className="flex flex-wrap gap-1.5">
              {WEEKDAYS.map((d, i) => (
                <button type="button" key={d} onClick={() => toggleWeekend(i)} aria-pressed={form.weekend_days.includes(i)}
                  className={`h-8 rounded-lg border px-2.5 text-xs font-medium ${form.weekend_days.includes(i) ? 'border-teal bg-teal-soft text-teal' : 'border-line text-muted'}`}>{d.slice(0, 3)}</button>
              ))}
            </div>
            {fieldError(err, 'weekend_days') && <p className="mt-1 text-xs text-red">{fieldError(err, 'weekend_days')}</p>}
          </fieldset>
          <label className="mt-4 flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-0.5 accent-[var(--teal)]" checked={form.late_penalty_enabled} onChange={(e) => set('late_penalty_enabled', e.target.checked)} />
            <span>Late penalty: every 3 late arrivals deduct half a day in payroll.</span>
          </label>
        </Card>
        <Card title="Office location (camera attendance)" className="lg:col-span-2">
          <div className="grid gap-4 sm:grid-cols-4">
            <Input label="Latitude" value={form.office_lat ?? ''} onChange={(e) => set('office_lat', e.target.value)} error={fieldError(err, 'office_lat')} placeholder="24.860700" />
            <Input label="Longitude" value={form.office_lng ?? ''} onChange={(e) => set('office_lng', e.target.value)} error={fieldError(err, 'office_lng')} placeholder="67.001100" />
            <Input label="Radius (metres)" type="number" min={10} max={5000} value={form.office_radius_m} onChange={(e) => set('office_radius_m', Number(e.target.value))} error={fieldError(err, 'office_radius_m')} />
            <div className="flex items-end"><Button type="button" variant="secondary" className="w-full" onClick={useMyLocation}><MapPin className="size-4" /> Use my location</Button></div>
          </div>
          <p className="mt-3 text-xs text-muted">Employees can check in with the camera only inside this radius. The server computes the distance; phones only send coordinates.</p>
        </Card>
      </fieldset>
      {canEdit && <div className="lg:col-span-2"><Button type="submit" loading={save.isPending}>Save settings</Button></div>}
    </form>
  )
}

/* ---------- generic CRUD list ---------- */

type Row = Record<string, unknown> & { id: number }
type FieldDef = { key: string; label: string; required?: boolean; type?: 'text' | 'number' | 'date' | 'checkbox'; hint?: string }

function SimpleCrud({ endpoint, queryKey, entity, columns, fields, blank, canEdit, extraInvalidate }: {
  endpoint: string; queryKey: string; entity: string; canEdit: boolean; extraInvalidate?: string
  columns: { key: string; header: string; render?: (r: Row) => ReactNode }[]
  fields: FieldDef[]; blank: Record<string, unknown>
}) {
  const qc = useQueryClient()
  const toast = useToast()
  const { data, isLoading, error, refetch } = useQuery({ queryKey: [queryKey], queryFn: () => api.get<Row[]>(endpoint) })
  const [editing, setEditing] = useState<Record<string, unknown> | null>(null)
  const [deleting, setDeleting] = useState<Row | null>(null)
  const invalidate = () => { qc.invalidateQueries({ queryKey: [queryKey] }); if (extraInvalidate) qc.invalidateQueries({ queryKey: [extraInvalidate] }) }
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) => {
      const payload = { ...body }
      for (const f of fields) if (f.type === 'number') payload[f.key] = payload[f.key] === '' || payload[f.key] === null ? null : Number(payload[f.key])
      return body.id ? api.patch(`${endpoint}${body.id}/`, payload) : api.post(endpoint, payload)
    },
    onSuccess: () => { invalidate(); setEditing(null); toast.success(`${entity[0].toUpperCase() + entity.slice(1)} saved.`) },
  })
  const remove = useMutation({
    mutationFn: (r: Row) => api.del(`${endpoint}${r.id}/`),
    onSuccess: () => { invalidate(); setDeleting(null); toast.success(`${entity} deleted.`) },
    onError: (e) => { setDeleting(null); toast.error(e) },
  })
  if (error) return <ErrorState error={error} retry={refetch} />
  return (
    <Card title={`${entity[0].toUpperCase() + entity.slice(1)}s`}
      action={canEdit && <Button size="sm" onClick={() => { save.reset(); setEditing({ ...blank }) }}><Plus className="size-4" /> Add {entity}</Button>}>
      {isLoading ? <Spinner /> : (
        <Table rows={data ?? []} rowKey={(r) => r.id}
          empty={<div className="py-8 text-center text-sm text-muted">No {entity}s yet.{canEdit && ` Add the first ${entity}.`}</div>}
          columns={[
            ...columns.map((c) => ({ key: c.key, header: c.header, cell: (r: Row) => c.render ? c.render(r) : String(r[c.key] ?? '—') })),
            ...(canEdit ? [{ key: '_a', header: '', className: 'text-right w-24', cell: (r: Row) => (
              <div className="flex justify-end gap-1">
                <IconButton label={`Edit ${entity}`} onClick={() => { save.reset(); setEditing({ ...r, yearly_quota: r.yearly_quota ?? '' }) }}><Pencil className="size-4" /></IconButton>
                <IconButton label={`Delete ${entity}`} onClick={() => setDeleting(r)}><Trash2 className="size-4" /></IconButton>
              </div>) }] : []),
          ]} />
      )}
      <Modal open={editing !== null} onClose={() => setEditing(null)} title={`${editing?.id ? 'Edit' : 'Add'} ${entity}`}
        footer={<><Button variant="secondary" onClick={() => setEditing(null)}>Cancel</Button>
          <Button loading={save.isPending} onClick={() => editing && save.mutate(editing)}>Save</Button></>}>
        {editing && (
          <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); save.mutate(editing) }}>
            {fields.map((f) => f.type === 'checkbox' ? (
              <label key={f.key} className="flex items-center gap-2 text-sm">
                <input type="checkbox" className="accent-[var(--teal)]" checked={Boolean(editing[f.key])} onChange={(e) => setEditing({ ...editing, [f.key]: e.target.checked })} />
                {f.label}
              </label>
            ) : (
              <Input key={f.key} label={f.label} required={f.required} type={f.type ?? 'text'} hint={f.hint}
                value={String(editing[f.key] ?? '')} onChange={(e) => setEditing({ ...editing, [f.key]: e.target.value })}
                error={fieldError(save.error, f.key)} />
            ))}
            {save.error && !fields.some((f) => fieldError(save.error, f.key)) && <Alert>{(save.error as Error).message}</Alert>}
            <button type="submit" hidden />
          </form>
        )}
      </Modal>
      <ConfirmDialog open={deleting !== null} onClose={() => setDeleting(null)} title={`Delete ${entity}?`} tone="danger" confirmLabel="Delete"
        loading={remove.isPending} onConfirm={() => deleting && remove.mutate(deleting)}
        body={<>This removes <b>{String(deleting?.name ?? deleting?.date ?? '')}</b>. Items that are in use cannot be deleted; deactivate them instead.</>} />
    </Card>
  )
}


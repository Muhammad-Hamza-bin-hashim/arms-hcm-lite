import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { KeyRound, Plus, Power } from 'lucide-react'
import { useState } from 'react'
import { useToast } from '../../components/toast'
import {
  Alert, Badge, Button, Card, ConfirmDialog, ErrorState, FilterSelect, IconButton, Input, Modal, PageHeader, Pagination, Spinner,
  StatusBadge, Table,
} from '../../components/ui'
import { api, fieldError, qs } from '../../lib/api'
import { fmtDateTime } from '../../lib/format'
import type { Page, User } from '../../lib/types'

export function TempPasswordNotice({ email, password }: { email: string; password: string }) {
  return (
    <div className="space-y-3">
      <Alert tone="teal">Login created for <b>{email}</b>.</Alert>
      <div className="rounded-lg border border-dashed border-line p-3">
        <p className="text-xs text-muted">Temporary password (shown once — share it securely)</p>
        <p className="mt-1 font-mono text-lg font-semibold select-all">{password}</p>
      </div>
      <p className="text-xs text-muted">They must choose a new password the first time they sign in.</p>
    </div>
  )
}

export function UsersPage() {
  const qc = useQueryClient()
  const toast = useToast()
  const [role, setRole] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState({ email: '', first_name: '', last_name: '' })
  const [issued, setIssued] = useState<{ email: string; password: string } | null>(null)
  const [confirm, setConfirm] = useState<{ user: User; action: 'deactivate' | 'activate' | 'reset-password' } | null>(null)
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['users', role, search, page],
    queryFn: () => api.get<Page<User>>(`/users/${qs({ role, search, page })}`),
    placeholderData: (p) => p,
  })
  const create = useMutation({
    mutationFn: () => api.post<{ user: User; temporary_password: string }>('/users/', form),
    onSuccess: (r) => { setCreating(false); setIssued({ email: r.user.email, password: r.temporary_password }); setForm({ email: '', first_name: '', last_name: '' }); qc.invalidateQueries({ queryKey: ['users'] }) },
  })
  const act = useMutation({
    mutationFn: ({ user, action }: { user: User; action: string }) => api.post<{ temporary_password?: string; user: User }>(`/users/${user.id}/${action}/`),
    onSuccess: (r, v) => {
      setConfirm(null)
      qc.invalidateQueries({ queryKey: ['users'] })
      if (r.temporary_password) setIssued({ email: v.user.email, password: r.temporary_password })
      else toast.success(`${v.user.email} ${v.action === 'activate' ? 'activated' : 'deactivated'}.`)
    },
    onError: (e) => { setConfirm(null); toast.error(e) },
  })
  return (
    <>
      <PageHeader title="Users & logins" subtitle="Admin creates HR logins. Employee logins are created when HR registers an employee."
        actions={<Button onClick={() => { create.reset(); setCreating(true) }}><Plus className="size-4" /> New HR login</Button>} />
      <Card>
        <div className="mb-3 flex flex-wrap gap-2">
          <input aria-label="Search users" placeholder="Search name or email" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1) }}
            className="h-9 w-full max-w-xs rounded-lg border border-line bg-surface px-3 text-sm focus:border-teal focus:outline-none" />
          <FilterSelect label="Role" value={role} onChange={(v) => { setRole(v); setPage(1) }}>
            <option value="">All roles</option><option value="admin">Admin</option><option value="hr">HR</option><option value="employee">Employee</option>
          </FilterSelect>
        </div>
        {error ? <ErrorState error={error} retry={refetch} /> : isLoading ? <Spinner /> : (
          <>
            <Table rows={data?.results ?? []} rowKey={(u) => u.id}
              columns={[
                { key: 'n', header: 'Name', cell: (u) => <div><p className="font-medium">{u.full_name}</p><p className="text-xs text-muted">{u.email}</p></div> },
                { key: 'r', header: 'Role', cell: (u) => <Badge tone={u.role === 'admin' ? 'violet' : u.role === 'hr' ? 'teal' : 'gray'}>{u.role.toUpperCase()}</Badge> },
                { key: 's', header: 'Status', cell: (u) => <StatusBadge status={u.is_active ? 'active' : 'inactive'} text={u.is_active ? (u.must_change_password ? 'Awaiting first sign-in' : 'Active') : 'Deactivated'} /> },
                { key: 'l', header: 'Last sign-in', cell: (u) => fmtDateTime(u.last_login) },
                { key: 'a', header: '', className: 'text-right', cell: (u) => u.role === 'admin' ? null : (
                  <div className="flex justify-end gap-1">
                    <IconButton label="Reset password" onClick={() => setConfirm({ user: u, action: 'reset-password' })}><KeyRound className="size-4" /></IconButton>
                    <IconButton label={u.is_active ? 'Deactivate' : 'Activate'} onClick={() => setConfirm({ user: u, action: u.is_active ? 'deactivate' : 'activate' })}
                      className={u.is_active ? 'hover:text-red' : 'hover:text-teal'}><Power className="size-4" /></IconButton>
                  </div>) },
              ]} />
            <Pagination page={page} count={data?.count ?? 0} onPage={setPage} />
          </>
        )}
      </Card>

      <Modal open={creating} onClose={() => setCreating(false)} title="New HR login"
        footer={<><Button variant="secondary" onClick={() => setCreating(false)}>Cancel</Button><Button loading={create.isPending} onClick={() => create.mutate()}>Create login</Button></>}>
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); create.mutate() }}>
          <div className="grid grid-cols-2 gap-3">
            <Input label="First name" required value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} error={fieldError(create.error, 'first_name')} />
            <Input label="Last name" value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} />
          </div>
          <Input label="Work email" type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} error={fieldError(create.error, 'email')} />
          {create.error && !fieldError(create.error, 'email') && !fieldError(create.error, 'first_name') && <Alert>{(create.error as Error).message}</Alert>}
          <button type="submit" hidden />
        </form>
      </Modal>

      <Modal open={issued !== null} onClose={() => setIssued(null)} title="Temporary password" footer={<Button onClick={() => setIssued(null)}>Done</Button>}>
        {issued && <TempPasswordNotice email={issued.email} password={issued.password} />}
      </Modal>

      <ConfirmDialog open={confirm !== null} onClose={() => setConfirm(null)} loading={act.isPending}
        tone={confirm?.action === 'deactivate' ? 'danger' : 'primary'}
        title={confirm?.action === 'reset-password' ? 'Reset password?' : confirm?.action === 'deactivate' ? 'Deactivate login?' : 'Activate login?'}
        confirmLabel={confirm?.action === 'reset-password' ? 'Reset password' : confirm?.action === 'deactivate' ? 'Deactivate' : 'Activate'}
        onConfirm={() => confirm && act.mutate(confirm)}
        body={confirm?.action === 'reset-password'
          ? <>A new temporary password will be issued for <b>{confirm?.user.email}</b> and all their sessions will be signed out.</>
          : confirm?.action === 'deactivate' ? <><b>{confirm?.user.email}</b> will be signed out immediately and cannot sign in until reactivated.</>
            : <><b>{confirm?.user.email}</b> will be able to sign in again.</>} />
    </>
  )
}

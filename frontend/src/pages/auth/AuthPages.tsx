import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState, type FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { Alert, Button, Input } from '../../components/ui'
import { api, ApiError, fieldError } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import type { User } from '../../lib/types'
import { AuthShell } from './AuthShell'

export function SetupPage() {
  const { acceptTokens } = useAuth()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [form, setForm] = useState({ company_name: 'AR&MS Management Company', first_name: '', last_name: '', email: '', password: '', confirm: '' })
  const [mismatch, setMismatch] = useState(false)
  useEffect(() => { document.title = 'Set up · AR&MS HCM Lite' }, [])
  const setup = useMutation({
    mutationFn: () => api.post<{ access: string; refresh: string; user: User }>('/setup/', form),
    onSuccess: (payload) => { acceptTokens(payload); qc.invalidateQueries({ queryKey: ['setup-status'] }); navigate('/settings?welcome=1') },
  })
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }))
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (form.password !== form.confirm) { setMismatch(true); return }
    setMismatch(false)
    setup.mutate()
  }
  const err = setup.error
  return (
    <AuthShell title="Set up your company" subtitle="First run: create the company profile and the Admin account. This screen is shown only once.">
      <form onSubmit={submit} className="space-y-4" noValidate>
        <Input label="Company name" required value={form.company_name} onChange={set('company_name')} error={fieldError(err, 'company_name')} />
        <div className="grid grid-cols-2 gap-3">
          <Input label="Admin first name" value={form.first_name} onChange={set('first_name')} autoComplete="given-name" />
          <Input label="Last name" value={form.last_name} onChange={set('last_name')} autoComplete="family-name" />
        </div>
        <Input label="Admin email" type="email" required value={form.email} onChange={set('email')} error={fieldError(err, 'email')} autoComplete="email" />
        <Input label="Password" type="password" required value={form.password} onChange={set('password')} autoComplete="new-password"
          error={fieldError(err, 'password') ?? fieldError(err, 'non_field_errors')} hint="At least 8 characters, not only numbers, not a common password." />
        <Input label="Confirm password" type="password" required value={form.confirm} onChange={set('confirm')} autoComplete="new-password"
          error={mismatch ? 'Passwords do not match.' : undefined} />
        {err && !(err instanceof ApiError && err.errors) && <Alert>{(err as Error).message}</Alert>}
        <Button type="submit" className="w-full" loading={setup.isPending}>Create company and Admin</Button>
      </form>
    </AuthShell>
  )
}

export function LoginPage() {
  const { login, sessionExpired } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  useEffect(() => { document.title = 'Sign in · AR&MS HCM Lite' }, [])
  const m = useMutation({
    mutationFn: () => login(email, password),
    onSuccess: (u) => navigate(u.must_change_password ? '/change-password' : '/dashboard', { replace: true }),
  })
  return (
    <AuthShell title="Sign in" subtitle="Use the email and password from your administrator or HR.">
      <form onSubmit={(e) => { e.preventDefault(); m.mutate() }} className="space-y-4">
        {sessionExpired && !m.error && <Alert tone="amber">Your session ended. Please sign in again.</Alert>}
        <Input label="Email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" autoFocus />
        <Input label="Password" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
        {m.error && <Alert>{(m.error as Error).message}</Alert>}
        <Button type="submit" className="w-full" loading={m.isPending}>Sign in</Button>
        <p className="text-center text-xs text-muted">Forgot your password? Ask your Admin to reset it.</p>
      </form>
    </AuthShell>
  )
}

export function ChangePasswordForm({ forced, onDone }: { forced?: boolean; onDone?: () => void }) {
  const { acceptTokens } = useAuth()
  const [form, setForm] = useState({ current_password: '', new_password: '', confirm: '' })
  const [mismatch, setMismatch] = useState(false)
  const m = useMutation({
    mutationFn: () => api.post<{ access: string; refresh: string; user: User }>('/auth/change-password/', form),
    onSuccess: (p) => { acceptTokens(p); setForm({ current_password: '', new_password: '', confirm: '' }); onDone?.() },
  })
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }))
  return (
    <form className="space-y-4" onSubmit={(e) => {
      e.preventDefault()
      if (form.new_password !== form.confirm) { setMismatch(true); return }
      setMismatch(false); m.mutate()
    }}>
      <Input label={forced ? 'Temporary password' : 'Current password'} type="password" required autoComplete="current-password"
        value={form.current_password} onChange={set('current_password')} error={fieldError(m.error, 'current_password')} />
      <Input label="New password" type="password" required autoComplete="new-password" value={form.new_password} onChange={set('new_password')}
        error={fieldError(m.error, 'new_password') ?? fieldError(m.error, 'non_field_errors')} hint="At least 8 characters; avoid common passwords." />
      <Input label="Confirm new password" type="password" required autoComplete="new-password" value={form.confirm} onChange={set('confirm')}
        error={mismatch ? 'Passwords do not match.' : undefined} />
      {m.error && !(m.error instanceof ApiError && m.error.errors) && <Alert>{(m.error as Error).message}</Alert>}
      <Button type="submit" loading={m.isPending} className={forced ? 'w-full' : ''}>Change password</Button>
    </form>
  )
}

export function ForcedChangePasswordPage() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  if (!user) return <Navigate to="/login" replace />
  if (!user.must_change_password) return <Navigate to="/dashboard" replace />
  return (
    <AuthShell title="Choose a new password" subtitle={<>Welcome, {user.full_name}. You signed in with a temporary password; set your own to continue.</>}>
      <ChangePasswordForm forced onDone={() => navigate('/dashboard', { replace: true })} />
      <button onClick={() => logout()} className="mt-4 w-full text-center text-xs text-muted hover:underline">Sign out</button>
    </AuthShell>
  )
}

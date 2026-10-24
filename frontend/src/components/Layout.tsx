import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Banknote, Bell, Building2, CalendarCheck, CalendarDays, ClipboardCheck, FileText, LayoutDashboard, LogOut, Megaphone,
  Menu, Moon, ScrollText, Sparkles, Sun, UserCircle, Users, UserCog, Wallet, X,
} from 'lucide-react'
import { useEffect, useState, type ComponentType, type ReactNode } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth, useUser } from '../lib/auth'
import { fmtDateTime } from '../lib/format'
import type { Notification, Page, Role } from '../lib/types'
import { AIChat } from './AIChat'
import { Logo } from './Logo'
import { cx, IconButton } from './ui'

type NavItem = { to: string; label: string; icon: ComponentType<{ className?: string }>; roles: Role[]; needsProfile?: boolean }

const NAV: { section: string; items: NavItem[] }[] = [
  { section: 'Overview', items: [
    { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard, roles: ['admin', 'hr', 'employee'] },
  ] },
  { section: 'People', items: [
    { to: '/employees', label: 'Employees', icon: Users, roles: ['admin', 'hr'] },
    { to: '/attendance', label: 'Attendance board', icon: CalendarCheck, roles: ['admin', 'hr'] },
    { to: '/attendance/corrections', label: 'Corrections', icon: ClipboardCheck, roles: ['admin', 'hr'] },
    { to: '/leave/requests', label: 'Leave requests', icon: CalendarDays, roles: ['admin', 'hr'] },
  ] },
  { section: 'Payroll', items: [
    { to: '/salaries', label: 'Salary structures', icon: Wallet, roles: ['admin', 'hr'] },
    { to: '/payroll', label: 'Payroll runs', icon: Banknote, roles: ['admin', 'hr'] },
    { to: '/payslips', label: 'Payslips', icon: FileText, roles: ['admin', 'hr', 'employee'] },
  ] },
  { section: 'My work', items: [
    { to: '/me/attendance', label: 'My attendance', icon: CalendarCheck, roles: ['hr', 'employee'], needsProfile: true },
    { to: '/me/leave', label: 'My leave', icon: CalendarDays, roles: ['hr', 'employee'], needsProfile: true },
  ] },
  { section: 'Company', items: [
    { to: '/announcements', label: 'Announcements', icon: Megaphone, roles: ['admin', 'hr', 'employee'] },
    { to: '/settings', label: 'Organization', icon: Building2, roles: ['admin', 'hr'] },
    { to: '/users', label: 'Users & logins', icon: UserCog, roles: ['admin'] },
    { to: '/audit', label: 'Audit log', icon: ScrollText, roles: ['admin'] },
    { to: '/ai-logs', label: 'AI logs', icon: Sparkles, roles: ['admin'] },
  ] },
]

const ROLE_LABEL: Record<Role, string> = { admin: 'Admin', hr: 'HR', employee: 'Employee' }

function useTheme() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains('dark'))
  const toggle = () => {
    const next = !dark
    setDark(next)
    document.documentElement.classList.toggle('dark', next)
    try { localStorage.setItem('theme', next ? 'dark' : 'light') } catch { /* ignore */ }
  }
  return { dark, toggle }
}

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const user = useUser()
  return (
    <nav aria-label="Main" className="flex h-full flex-col bg-navy-2 text-white dark:bg-navy">
      <div className="px-5 py-5"><Logo inverted /></div>
      <div className="flex-1 space-y-5 overflow-y-auto px-3 pb-6">
        {NAV.map((group) => {
          const items = group.items.filter((i) => i.roles.includes(user.role) && (!i.needsProfile || user.employee_id))
          if (!items.length) return null
          return (
            <div key={group.section}>
              <p className="px-2 pb-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-white/40">{group.section}</p>
              <ul className="space-y-0.5">
                {items.map((item) => (
                  <li key={item.to}>
                    <NavLink to={item.to} end={item.to === '/attendance'} onClick={onNavigate}
                      className={({ isActive }) => cx('flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition-colors',
                        isActive ? 'bg-white/10 font-medium text-white' : 'text-white/70 hover:bg-white/5 hover:text-white')}>
                      {({ isActive }) => (<>
                        <item.icon className={cx('size-4', isActive && 'text-[#2DD4BF]')} />
                        {item.label}
                      </>)}
                    </NavLink>
                  </li>
                ))}
              </ul>
            </div>
          )
        })}
      </div>
      <div className="border-t border-white/10 px-5 py-3 text-[11px] text-white/40">Signed in as {ROLE_LABEL[user.role]}</div>
    </nav>
  )
}

function Notifications() {
  const [open, setOpen] = useState(false)
  const qc = useQueryClient()
  const navigate = useNavigate()
  const { data } = useQuery({
    queryKey: ['notifications'],
    queryFn: () => api.get<Page<Notification> & { unread_count: number }>('/notifications/'),
    refetchInterval: 60_000,
  })
  const readAll = useMutation({ mutationFn: () => api.post('/notifications/read-all/'), onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications'] }) })
  const readOne = useMutation({ mutationFn: (id: number) => api.post(`/notifications/${id}/read/`), onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications'] }) })
  const unread = data?.unread_count ?? 0
  return (
    <div className="relative">
      <IconButton label={`Notifications${unread ? ` (${unread} unread)` : ''}`} onClick={() => setOpen((o) => !o)}>
        <Bell className="size-4" />
        {unread > 0 && <span className="absolute top-1.5 right-1.5 flex size-4 items-center justify-center rounded-full bg-red text-[9px] font-bold text-white">{unread > 9 ? '9+' : unread}</span>}
      </IconButton>
      {open && (
        <>
          <div className="fixed inset-0 z-30" onClick={() => setOpen(false)} />
          <div className="animate-in absolute right-0 z-40 mt-2 w-[min(22rem,calc(100vw-2rem))] rounded-xl border border-line bg-surface shadow-xl">
            <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
              <p className="text-sm font-semibold">Notifications</p>
              {unread > 0 && <button className="text-xs text-teal hover:underline" onClick={() => readAll.mutate()}>Mark all read</button>}
            </div>
            <ul className="max-h-96 overflow-y-auto">
              {!data?.results.length && <li className="px-4 py-8 text-center text-sm text-muted">You're all caught up.</li>}
              {data?.results.map((n) => (
                <li key={n.id}>
                  <button onClick={() => { if (!n.is_read) readOne.mutate(n.id); setOpen(false); if (n.link) navigate(n.link) }}
                    className={cx('w-full border-b border-line px-4 py-2.5 text-left last:border-0 hover:bg-surface-2', !n.is_read && 'bg-teal-soft/40')}>
                    <p className="flex items-center gap-2 text-sm font-medium">{!n.is_read && <span className="size-1.5 rounded-full bg-teal" />}{n.title}</p>
                    {n.body && <p className="mt-0.5 line-clamp-2 text-xs text-muted">{n.body}</p>}
                    <p className="mt-1 text-[11px] text-muted">{fmtDateTime(n.created_at)}</p>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </>
      )}
    </div>
  )
}

export function Layout({ children }: { children?: ReactNode }) {
  const user = useUser()
  const { logout } = useAuth()
  const { dark, toggle } = useTheme()
  const [drawer, setDrawer] = useState(false)
  const location = useLocation()
  const { data: company } = useQuery({ queryKey: ['setup-status'], queryFn: () => api.get<{ company_name: string }>('/setup/status/'), staleTime: Infinity })
  useEffect(() => setDrawer(false), [location.pathname])

  return (
    <div className="flex h-full">
      <aside className="hidden w-60 shrink-0 lg:block"><div className="fixed inset-y-0 w-60"><Sidebar /></div></aside>
      {drawer && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-navy/60" onClick={() => setDrawer(false)} />
          <div className="animate-in absolute inset-y-0 left-0 w-64"><Sidebar onNavigate={() => setDrawer(false)} /></div>
          <IconButton label="Close menu" onClick={() => setDrawer(false)} className="absolute top-3 left-[17rem] text-white"><X className="size-5" /></IconButton>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-14 items-center gap-2 border-b border-line bg-surface/90 px-4 backdrop-blur">
          <IconButton label="Open menu" className="lg:hidden" onClick={() => setDrawer(true)}><Menu className="size-5" /></IconButton>
          <div className="lg:hidden"><Logo compact /></div>
          <p className="hidden truncate text-sm font-medium text-muted sm:block">{company?.company_name || 'AR&MS Management Company'}</p>
          <div className="ml-auto flex items-center gap-1">
            <IconButton label={dark ? 'Switch to light mode' : 'Switch to dark mode'} onClick={toggle}>
              {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
            </IconButton>
            <Notifications />
            <Link to="/profile" className="ml-1 flex items-center gap-2 rounded-lg px-2 py-1 hover:bg-surface-2">
              <UserCircle className="size-6 text-muted" />
              <span className="hidden text-left leading-tight md:block">
                <span className="block text-sm font-medium">{user.full_name}</span>
                <span className="block text-[11px] text-muted">{ROLE_LABEL[user.role]}</span>
              </span>
            </Link>
            <IconButton label="Sign out" onClick={() => logout()}><LogOut className="size-4" /></IconButton>
          </div>
        </header>
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 pt-6 pb-24 sm:px-6">
          {children ?? <Outlet />}
        </main>
      </div>
      <AIChat />
    </div>
  )
}

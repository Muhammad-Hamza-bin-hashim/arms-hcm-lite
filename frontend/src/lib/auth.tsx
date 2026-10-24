import { useQueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, setSessionExpiredHandler, tokens } from './api'
import type { User } from './types'

interface AuthPayload { access: string; refresh: string; user: User }

interface AuthState {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<User>
  acceptTokens: (payload: AuthPayload) => void
  logout: () => Promise<void>
  sessionExpired: boolean
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(Boolean(tokens.access))
  const [sessionExpired, setSessionExpired] = useState(false)
  const queryClient = useQueryClient()

  useEffect(() => {
    setSessionExpiredHandler(() => { setUser(null); setSessionExpired(true); queryClient.clear() })
    if (!tokens.access) return
    api.get<User>('/auth/me/').then(setUser).catch(() => tokens.clear()).finally(() => setLoading(false))
  }, [queryClient])

  const acceptTokens = useCallback((payload: AuthPayload) => {
    tokens.set(payload.access, payload.refresh)
    setSessionExpired(false)
    setUser(payload.user)
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const payload = await api.post<AuthPayload>('/auth/login/', { email, password })
    queryClient.clear()
    acceptTokens(payload)
    return payload.user
  }, [acceptTokens, queryClient])

  const logout = useCallback(async () => {
    try { await api.post('/auth/logout/') } catch { /* already invalid */ }
    tokens.clear()
    queryClient.clear()
    setUser(null)
  }, [queryClient])

  const value = useMemo(() => ({ user, loading, login, acceptTokens, logout, sessionExpired }),
    [user, loading, login, acceptTokens, logout, sessionExpired])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}

export function useUser(): User {
  const { user } = useAuth()
  if (!user) throw new Error('No signed-in user')
  return user
}

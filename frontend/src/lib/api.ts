/** Thin fetch wrapper: JWT auth, one transparent refresh on 401, structured errors. */

export type FieldErrors = Record<string, unknown>

export class ApiError extends Error {
  status: number
  code: string
  errors?: FieldErrors
  constructor(status: number, detail: string, code = 'error', errors?: FieldErrors) {
    super(detail)
    this.status = status
    this.code = code
    this.errors = errors
  }
}

const ACCESS = 'hcm.access'
const REFRESH = 'hcm.refresh'

function read(key: string) {
  try { return localStorage.getItem(key) } catch { return null }
}
function write(key: string, value: string | null) {
  try { value === null ? localStorage.removeItem(key) : localStorage.setItem(key, value) } catch { /* private mode */ }
}

export const tokens = {
  get access() { return read(ACCESS) },
  get refresh() { return read(REFRESH) },
  set(access: string, refresh: string) { write(ACCESS, access); write(REFRESH, refresh) },
  clear() { write(ACCESS, null); write(REFRESH, null) },
}

let onSessionExpired: () => void = () => {}
export function setSessionExpiredHandler(fn: () => void) { onSessionExpired = fn }

let refreshing: Promise<boolean> | null = null
async function tryRefresh(): Promise<boolean> {
  const refresh = tokens.refresh
  if (!refresh) return false
  refreshing ??= fetch('/api/auth/refresh/', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refresh }),
  }).then(async (r) => {
    if (!r.ok) return false
    const data = await r.json()
    tokens.set(data.access, data.refresh)
    return true
  }).catch(() => false).finally(() => { refreshing = null })
  return refreshing
}

type Options = { method?: string; body?: unknown; form?: FormData; raw?: boolean; auth?: boolean }

export async function request<T = unknown>(path: string, opts: Options = {}, retry = true): Promise<T> {
  const headers: Record<string, string> = {}
  if (opts.auth !== false && tokens.access) headers.Authorization = `Bearer ${tokens.access}`
  let body: BodyInit | undefined
  if (opts.form) body = opts.form
  else if (opts.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(opts.body)
  }
  let res: Response
  try {
    res = await fetch(`/api${path}`, { method: opts.method ?? (body ? 'POST' : 'GET'), headers, body })
  } catch {
    throw new ApiError(0, 'Cannot reach the server. Check your connection and try again.', 'network')
  }
  if (res.status === 401 && opts.auth !== false && retry && tokens.refresh) {
    if (await tryRefresh()) return request<T>(path, opts, false)
    tokens.clear()
    onSessionExpired()
  }
  if (!res.ok) {
    let data: { detail?: string; code?: string; errors?: FieldErrors } = {}
    try { data = await res.json() } catch { /* not JSON */ }
    if (res.status === 401 && opts.auth !== false && path !== '/auth/login/') { tokens.clear(); onSessionExpired() }
    throw new ApiError(res.status, data.detail || defaultMessage(res.status), data.code, data.errors)
  }
  if (opts.raw) return res as unknown as T
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

function defaultMessage(status: number) {
  if (status === 403) return 'You do not have permission to do that.'
  if (status === 404) return 'Not found.'
  if (status === 429) return 'Too many requests. Please wait a moment.'
  if (status >= 500) return 'The server had a problem. Please try again.'
  return 'Something went wrong.'
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: 'POST', body: body ?? {} }),
  patch: <T>(path: string, body: unknown) => request<T>(path, { method: 'PATCH', body }),
  del: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
  upload: <T>(path: string, form: FormData) => request<T>(path, { method: 'POST', form }),
}

/** Downloads an authenticated file (PDF / CSV). */
export async function download(path: string, fallbackName: string) {
  const res = await request<Response>(path, { raw: true })
  const blob = await res.blob()
  const disposition = res.headers.get('Content-Disposition') || ''
  const name = /filename="?([^"]+)"?/.exec(disposition)?.[1] || fallbackName
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function qs(params: object) {
  const s = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== '') s.set(k, String(v))
  const out = s.toString()
  return out ? `?${out}` : ''
}

export function fieldError(err: unknown, field: string): string | undefined {
  if (!(err instanceof ApiError) || !err.errors) return undefined
  const v = err.errors[field]
  if (Array.isArray(v)) return v.map(String).join(' ')
  if (typeof v === 'string') return v
  return undefined
}

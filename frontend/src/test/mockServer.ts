import { vi } from 'vitest'

type Reply = { status?: number; body?: unknown } | ((init?: RequestInit) => { status?: number; body?: unknown })

/** Replaces global fetch with a router keyed by "METHOD /api/path" (query string ignored). */
export function mockServer(routes: Record<string, Reply>) {
  const calls: { key: string; init?: RequestInit }[] = []
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input).split('?')[0]
    const key = `${(init?.method ?? 'GET').toUpperCase()} ${url}`
    calls.push({ key, init })
    const route = routes[key] ?? routes[`ANY ${url}`]
    const reply = typeof route === 'function' ? route(init) : route ?? { status: 404, body: { detail: 'Not found.' } }
    const status = reply.status ?? 200
    return new Response(status === 204 ? null : JSON.stringify(reply.body ?? {}), {
      status, headers: { 'Content-Type': 'application/json' },
    })
  })
  vi.stubGlobal('fetch', fetchMock)
  return { calls, fetchMock }
}

export const page = <T,>(results: T[]) => ({ count: results.length, next: null, previous: null, results })

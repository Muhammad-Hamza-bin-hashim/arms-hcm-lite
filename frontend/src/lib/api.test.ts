import { describe, expect, it, vi } from 'vitest'
import { mockServer } from '../test/mockServer'
import { api, ApiError, fieldError, setSessionExpiredHandler, tokens } from './api'

describe('api client', () => {
  it('sends the bearer token and returns JSON', async () => {
    tokens.set('access-1', 'refresh-1')
    const { calls } = mockServer({ 'GET /api/auth/me/': { body: { id: 1 } } })
    await expect(api.get('/auth/me/')).resolves.toEqual({ id: 1 })
    expect((calls[0].init?.headers as Record<string, string>).Authorization).toBe('Bearer access-1')
  })

  it('turns error envelopes into ApiError with code and field errors', async () => {
    mockServer({
      'POST /api/leave/requests/': { status: 422, body: { detail: 'Overlaps your pending leave.', code: 'overlap', errors: { start_date: ['Overlaps an existing request.'] } } },
    })
    const err = (await api.post('/leave/requests/', {}).catch((e: unknown) => e)) as ApiError
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(422)
    expect(err.code).toBe('overlap')
    expect(err.message).toBe('Overlaps your pending leave.')
    expect(fieldError(err, 'start_date')).toBe('Overlaps an existing request.')
  })

  it('refreshes an expired access token once and retries', async () => {
    tokens.set('old', 'refresh-1')
    let first = true
    mockServer({
      'GET /api/dashboard/employee/': (init) => {
        const auth = (init?.headers as Record<string, string>).Authorization
        if (first) { first = false; return { status: 401, body: { detail: 'expired' } } }
        return { body: { ok: auth } }
      },
      'POST /api/auth/refresh/': { body: { access: 'new', refresh: 'refresh-2', user: {} } },
    })
    await expect(api.get('/dashboard/employee/')).resolves.toEqual({ ok: 'Bearer new' })
    expect(tokens.access).toBe('new')
  })

  it('clears tokens and signals session expiry when refresh fails', async () => {
    tokens.set('old', 'bad-refresh')
    const expired = vi.fn()
    setSessionExpiredHandler(expired)
    mockServer({
      'GET /api/auth/me/': { status: 401, body: { detail: 'expired' } },
      'POST /api/auth/refresh/': { status: 401, body: { detail: 'Session expired.' } },
    })
    await expect(api.get('/auth/me/')).rejects.toBeInstanceOf(ApiError)
    expect(tokens.access).toBeNull()
    expect(expired).toHaveBeenCalled()
  })

  it('reports network failures in plain words', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    const err = (await api.get('/auth/me/').catch((e: unknown) => e)) as ApiError
    expect(err.code).toBe('network')
    expect(err.message).toMatch(/Cannot reach the server/)
  })
})

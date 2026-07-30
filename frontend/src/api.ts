import type { User } from './types'

const API_BASE = import.meta.env.VITE_API_BASE || '/api/v1'
const TOKEN_KEY = 'support_pilot_token'
const USER_KEY = 'support_pilot_user'
export const SESSION_SYNC_KEY = 'support_pilot_session_sync'
export const SESSION_EVENT = 'support-pilot-session'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function getStoredUser(): User | null {
  const value = localStorage.getItem(USER_KEY)
  if (!value) return null
  try {
    const user = JSON.parse(value) as Partial<User>
    if (!user.id || !user.email || !['CUSTOMER', 'SUPPORT'].includes(user.role || '')) {
      throw new Error('invalid stored user')
    }
    return user as User
  } catch {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
    return null
  }
}

export function setSession(token: string, user: User) {
  localStorage.setItem(TOKEN_KEY, token)
  localStorage.setItem(USER_KEY, JSON.stringify(user))
  localStorage.setItem(SESSION_SYNC_KEY, crypto.randomUUID())
  window.dispatchEvent(new CustomEvent(SESSION_EVENT, { detail: user }))
}

export function clearSession(notify = true) {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
  localStorage.setItem(SESSION_SYNC_KEY, crypto.randomUUID())
  if (notify) window.dispatchEvent(new CustomEvent(SESSION_EVENT, { detail: null }))
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken()
  const headers = new Headers(options.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers })
  if (response.status === 401) clearSession()
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    const detail = typeof body.detail === 'string' ? body.detail : '请求失败，请稍后重试'
    throw new Error(detail)
  }
  return response.json()
}

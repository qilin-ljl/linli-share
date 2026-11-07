export const API_BASE = import.meta.env.VITE_API_URL || `${window.location.protocol}//${window.location.hostname}:8000`
export const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true'
export type CurrentLocation = { latitude: number; longitude: number; accuracy: number }
let currentLocation: CurrentLocation | null = null
export function setApiLocation(location: CurrentLocation | null) { currentLocation = location }

export async function api<T>(path: string, userId = 0, init?: RequestInit): Promise<T> {
  const demoId = DEMO_MODE ? Number(localStorage.getItem('neighloop-demo-user-id')) : 0
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(demoId > 0 && demoId === userId ? { 'X-Demo-User-Id': String(demoId) } : {}),
      ...(currentLocation && (/^\/api\/(items|recommendations|community\/map)/.test(path)) ? {
        'X-Location-Latitude': String(currentLocation.latitude),
        'X-Location-Longitude': String(currentLocation.longitude),
      } : {}),
      ...((init?.method || 'GET').toUpperCase() !== 'GET' ? { 'X-NeighLoop-Request': '1' } : {}),
      'X-Community-Id': localStorage.getItem('neighloop-community-id') || '1',
      ...(init?.headers || {}),
    },
  })
  if (!response.ok) {
    let message = `请求失败（${response.status}）`
    try {
      const body = await response.json()
      message = typeof body.detail === 'string' ? body.detail : message
    } catch { /* retain HTTP error */ }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}

export const jsonBody = (value: unknown) => JSON.stringify(value)

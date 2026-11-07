import { createContext, useContext } from 'react'
import type { AuthResponse, AuthUser, Bootstrap, UserPreference } from './types'
import type { CurrentLocation } from './api'

export type AppState = {
  bootstrap: Bootstrap
  userId: number
  setUserId: (id: number) => void
  communityId: number
  setCommunityId: (id: number) => void
  notify: (message: string) => void
  authUser: AuthUser | null
  preferences: UserPreference | null
  isAuthenticated: boolean
  demoMode: boolean
  requestAuth: (returnTo?: string) => void
  onAuthenticated: (response: AuthResponse) => void
  refreshSession: () => Promise<void>
  setPreferences: (preferences: UserPreference) => void
  logout: () => Promise<void>
  currentLocation: CurrentLocation | null
  setCurrentLocation: (location: CurrentLocation | null) => void
}

export const AppContext = createContext<AppState | null>(null)
export function useApp(): AppState {
  const value = useContext(AppContext)
  if (!value) throw new Error('Missing app context')
  return value
}

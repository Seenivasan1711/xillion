import { createContext, useContext, useEffect, useState } from 'react'
import { api, type User } from '../lib/api'

interface AuthState {
  user: User | null
  loading: boolean
  needsSetup: boolean
  login: (username: string, password: string, totpCode?: string) => Promise<{ requires_totp?: boolean }>
  logout: () => Promise<void>
  refresh: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [needsSetup, setNeedsSetup] = useState(false)

  const refresh = async () => {
    try {
      const status = await api.auth.setupStatus()
      if (status.needs_setup) {
        setNeedsSetup(true)
        setUser(null)
        return
      }
      setNeedsSetup(false)
      const me = await api.auth.me()
      setUser(me)
    } catch {
      setUser(null)
    }
  }

  useEffect(() => {
    refresh().finally(() => setLoading(false))
  }, [])

  const login = async (username: string, password: string, totpCode?: string) => {
    const result = await api.auth.login(username, password, totpCode)
    if (!result.requires_totp) {
      await refresh()
    }
    return result
  }

  const logout = async () => {
    await api.auth.logout()
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, needsSetup, login, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}

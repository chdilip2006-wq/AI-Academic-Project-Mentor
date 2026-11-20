import { createContext, useContext, useEffect, useState } from 'react'
import { api } from '../services/api'

const Context = createContext(null)
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [authError, setAuthError] = useState('')
  useEffect(() => {
    const expired = () => { setUser(null); setAuthError('Your session expired. Please sign in again.') }
    const refreshRole = () => {
      if (!sessionStorage.getItem('accessToken')) return
      api('/auth/me').then(result => setUser(result.user)).catch(error => {
        if (error.message.toLowerCase().includes('session') || error.message.toLowerCase().includes('token')) {
          sessionStorage.removeItem('accessToken'); setUser(null); setAuthError(error.message)
        }
      })
    }
    window.addEventListener('auth-expired', expired)
    window.addEventListener('focus', refreshRole)
    if (!sessionStorage.getItem('accessToken')) { setLoading(false) }
    else api('/auth/me').then(result => setUser(result.user)).catch(error => { sessionStorage.removeItem('accessToken'); setAuthError(error.message) }).finally(() => setLoading(false))
    return () => { window.removeEventListener('auth-expired', expired); window.removeEventListener('focus', refreshRole) }
  }, [])
  const authenticate = async (path, payload) => {
    const result = await api(path, { method: 'POST', body: JSON.stringify(payload) })
    sessionStorage.setItem('accessToken', result.token); setUser(result.user); setAuthError('')
    return result.user
  }
  const login = payload => authenticate('/auth/login', payload)
  const register = payload => authenticate('/auth/register', payload)
  const logout = () => { sessionStorage.removeItem('accessToken'); setUser(null); setAuthError('') }
  return <Context.Provider value={{ user, loading, logout, login, register, configured: true, authError }}>{children}</Context.Provider>
}
export const useAuth = () => useContext(Context)

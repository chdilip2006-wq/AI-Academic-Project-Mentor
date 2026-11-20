const base = import.meta.env.VITE_API_URL || 'http://localhost:5000/api'

export async function api(path, options = {}) {
  const token = sessionStorage.getItem('accessToken')
  const response = await fetch(`${base}${path}`, {
    ...options,
    headers: { ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), ...(token ? { Authorization: `Bearer ${token}` } : {}), ...options.headers },
  })
  const type = response.headers.get('content-type') || ''
  const data = type.includes('application/json') ? await response.json() : await response.text()
  if (response.status === 401) { sessionStorage.removeItem('accessToken'); window.dispatchEvent(new Event('auth-expired')) }
  if (!response.ok) throw new Error(data?.error || 'The request could not be completed.')
  return data
}
export const json = (method, body) => ({ method, body: JSON.stringify(body) })

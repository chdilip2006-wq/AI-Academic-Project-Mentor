import { useState } from 'react'
import { Navigate } from 'react-router-dom'
import { ArrowRight, BookOpen, Check, Sparkles } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'

export default function Login() {
  const { user, login, register, authError } = useAuth()
  const [mode, setMode] = useState('login')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [requestFaculty, setRequestFaculty] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  if (user) return <Navigate to="/" replace />

  async function submit(event) {
    event.preventDefault(); setError(''); setBusy(true)
    try {
      if (mode === 'register') await register({ name, email, password, requestFacultyAccess: requestFaculty })
      else await login({ email, password })
    } catch (e) { setError(e.message || 'The request could not be completed.') }
    finally { setBusy(false) }
  }

  return <div className="auth-screen"><section className="auth-story"><div className="brand brand-light"><div className="brand-mark"><BookOpen size={19}/></div><div><strong>Project Mentor</strong><span>ACADEMIC WORKSPACE</span></div></div><div className="story-content"><span className="story-kicker"><Sparkles size={15}/> YOUR PROJECT, WITH A PLAN</span><h1>Turn your idea<br/>into <em>real progress.</em></h1><p>A calmer way to plan, build, and document academic projects—with guidance at every step.</p><div className="story-checks"><span><Check size={16}/> A clear project blueprint</span><span><Check size={16}/> Milestones that keep you moving</span><span><Check size={16}/> One place for your work</span></div></div><div className="story-bottom">Thoughtful progress, one week at a time <span>✳</span></div></section>
    <section className="auth-form-wrap"><div className="auth-form"><div className="auth-mobile-brand"><div className="brand-mark"><BookOpen size={19}/></div><strong>Project Mentor</strong></div><span className="eyebrow">WELCOME TO YOUR WORKSPACE</span><h2>{mode === 'login' ? 'Good to have you back' : 'Start your workspace'}</h2><p className="muted">{mode === 'login' ? 'Sign in to pick up where your project left off.' : 'Create a student account and bring your project idea along.'}</p>
      {authError && <div className="alert alert-error">{authError}</div>}{error && <div className="alert alert-error">{error}</div>}
      <form onSubmit={submit}>{mode === 'register' && <label>Your name<input required maxLength={120} value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Aisha Kumar"/></label>}<label>University email<input required type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@university.edu"/></label><label>Password<input required minLength={8} maxLength={72} type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="At least 8 characters"/></label>{mode === 'register' && <label className="toggle-setting"><input type="checkbox" checked={requestFaculty} onChange={e => setRequestFaculty(e.target.checked)}/><span>Request Faculty access (requires admin approval)</span></label>}<button className="button button-primary button-full" disabled={busy}>{busy ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create student account'}<ArrowRight size={16}/></button></form>
      <p className="auth-toggle">{mode === 'login' ? 'New to Project Mentor?' : 'Already have an account?'} <button onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError('') }}>{mode === 'login' ? 'Create account' : 'Sign in'}</button></p><div className="auth-note">Faculty access requires admin approval. Admin accounts are managed securely.</div></div></section></div>
}

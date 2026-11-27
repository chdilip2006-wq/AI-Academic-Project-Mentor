import { useState } from 'react'
import { Navigate } from 'react-router-dom'
import { ArrowRight, BookOpen, Check, Plus, Sparkles, Trash2 } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'

const emptyProfile = {
  rollNumber: '', department: '', program: '', year: '', bio: '', interests: '',
  github: '', previousProjectExperience: '', skills: [], programmingLanguages: [],
}

export default function Login() {
  const { user, login, register, authError } = useAuth()
  const [mode, setMode] = useState('login')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [profile, setProfile] = useState(emptyProfile)
  const [skillName, setSkillName] = useState('')
  const [skillLevel, setSkillLevel] = useState('Beginner')
  const [languageName, setLanguageName] = useState('')
  const [requestFaculty, setRequestFaculty] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  if (user) return <Navigate to="/" replace />

  const changeProfile = (key, value) => setProfile(current => ({ ...current, [key]: value }))
  function addSkill() {
    const value = skillName.trim()
    if (value && !profile.skills.some(skill => skill.name.toLowerCase() === value.toLowerCase())) {
      changeProfile('skills', [...profile.skills, { name: value, level: skillLevel }])
      setSkillName('')
    }
  }
  function addLanguage() {
    const value = languageName.trim()
    if (value && !profile.programmingLanguages.some(language => language.toLowerCase() === value.toLowerCase())) {
      changeProfile('programmingLanguages', [...profile.programmingLanguages, value])
      setLanguageName('')
    }
  }

  async function submit(event) {
    event.preventDefault(); setError(''); setBusy(true)
    try {
      if (mode === 'register') await register({ name, email, password, requestFacultyAccess: requestFaculty, profile })
      else await login({ email, password })
    } catch (e) { setError(e.message || 'The request could not be completed.') }
    finally { setBusy(false) }
  }

  const field = (label, key, props = {}) => <label className="field"><span>{label}</span><input required value={profile[key]} onChange={event => changeProfile(key, event.target.value)} {...props}/></label>

  return <div className="auth-screen"><section className="auth-story"><div className="brand brand-light"><div className="brand-mark"><BookOpen size={19}/></div><div><strong>Project Mentor</strong><span>ACADEMIC WORKSPACE</span></div></div><div className="story-content"><span className="story-kicker"><Sparkles size={15}/> YOUR PROJECT, WITH A PLAN</span><h1>Turn your idea<br/>into <em>real progress.</em></h1><p>A calmer way to plan, build, and document academic projects—with guidance at every step.</p><div className="story-checks"><span><Check size={16}/> A clear project blueprint</span><span><Check size={16}/> Milestones that keep you moving</span><span><Check size={16}/> One place for your work</span></div></div><div className="story-bottom">Thoughtful progress, one week at a time <span>✳</span></div></section>
    <section className={`auth-form-wrap ${mode === 'register' ? 'auth-form-wrap-register' : ''}`}><div className={`auth-form ${mode === 'register' ? 'auth-form-register' : ''}`}><div className="auth-mobile-brand"><div className="brand-mark"><BookOpen size={19}/></div><strong>Project Mentor</strong></div><span className="eyebrow">WELCOME TO YOUR WORKSPACE</span><h2>{mode === 'login' ? 'Good to have you back' : 'Build your student profile'}</h2><p className="muted">{mode === 'login' ? 'Sign in to pick up where your project left off.' : 'Add your academic details and skills. After account creation, complete a short skill assessment so project guidance can fit your experience.'}</p>
      {authError && <div className="alert alert-error">{authError}</div>}{error && <div className="alert alert-error">{error}</div>}
      <form onSubmit={submit}>
        {mode === 'register' && <label>Your name<input required maxLength={120} value={name} onChange={event => setName(event.target.value)} placeholder="e.g. Aisha Kumar"/></label>}
        <label>University email<input required type="email" value={email} onChange={event => setEmail(event.target.value)} placeholder="you@university.edu"/></label>
        <label>Password<input required minLength={8} maxLength={72} type="password" value={password} onChange={event => setPassword(event.target.value)} placeholder="At least 8 characters"/></label>
        {mode === 'register' && <>
          <div className="signup-section-heading"><span>01</span><div><b>Academic details</b><small>Required to personalize project guidance</small></div></div>
          <div className="field-grid signup-profile-grid">
            {field('Roll number', 'rollNumber', { maxLength: 40, placeholder: 'e.g. 24CS102' })}
            {field('Department', 'department', { maxLength: 120, placeholder: 'e.g. Computer Science' })}
            {field('Program', 'program', { maxLength: 120, placeholder: 'e.g. B.Tech' })}
            <label className="field"><span>Academic year</span><select required value={profile.year} onChange={event => changeProfile('year', event.target.value)}><option value="">Select year</option>{[1, 2, 3, 4, 5].map(year => <option key={year} value={year}>{`Year ${year}`}</option>)}</select></label>
          </div>
          <label className="field"><span>Short bio</span><textarea required maxLength={1000} rows="2" value={profile.bio} onChange={event => changeProfile('bio', event.target.value)} placeholder="What do you enjoy learning?"/></label>
          <label className="field"><span>Areas of interest</span><input required maxLength={500} value={profile.interests} onChange={event => changeProfile('interests', event.target.value)} placeholder="e.g. AI, accessibility, climate"/></label>

          <div className="signup-section-heading"><span>02</span><div><b>Skills</b><small>Add at least one skill you know and choose your self-assessed level</small></div></div>
          <div className="skill-add signup-skill-add"><input aria-label="Skill name" value={skillName} onChange={event => setSkillName(event.target.value)} onKeyDown={event => event.key === 'Enter' && (event.preventDefault(), addSkill())} placeholder="e.g. Data visualization"/><select aria-label="Skill level" value={skillLevel} onChange={event => setSkillLevel(event.target.value)}><option>Beginner</option><option>Intermediate</option><option>Advanced</option></select><button type="button" className="button button-secondary" onClick={addSkill}><Plus size={14}/> Add skill</button></div>
          <div className="skill-list">{profile.skills.map((skill, index) => <div className="skill-chip" key={`${skill.name}-${index}`}><b>{skill.name}</b><span>{skill.level}</span><button type="button" aria-label={`Remove ${skill.name}`} onClick={() => changeProfile('skills', profile.skills.filter((_, itemIndex) => itemIndex !== index))}><Trash2 size={13}/></button></div>)}</div>
          {profile.skills.length === 0 && <small className="muted">Add at least one skill before creating your account.</small>}

          <div className="signup-section-heading"><span>03</span><div><b>Programming languages</b><small>Optional</small></div></div>
          <div className="skill-add signup-skill-add"><input aria-label="Programming language" value={languageName} onChange={event => setLanguageName(event.target.value)} onKeyDown={event => event.key === 'Enter' && (event.preventDefault(), addLanguage())} placeholder="e.g. Python"/><button type="button" className="button button-secondary" onClick={addLanguage}><Plus size={14}/> Add language</button></div>
          <div className="skill-list">{profile.programmingLanguages.map((language, index) => <div className="skill-chip" key={`${language}-${index}`}><b>{language}</b><button type="button" aria-label={`Remove ${language}`} onClick={() => changeProfile('programmingLanguages', profile.programmingLanguages.filter((_, itemIndex) => itemIndex !== index))}><Trash2 size={13}/></button></div>)}</div>
          <label className="field"><span>Previous project experience <small>(optional)</small></span><textarea maxLength={2000} rows="2" value={profile.previousProjectExperience} onChange={event => changeProfile('previousProjectExperience', event.target.value)} placeholder="Projects you have worked on"/></label>
          <label className="field"><span>GitHub profile <small>(optional)</small></span><input maxLength={250} value={profile.github} onChange={event => changeProfile('github', event.target.value)} placeholder="https://github.com/you"/></label>
          <label className="toggle-setting"><input type="checkbox" checked={requestFaculty} onChange={event => setRequestFaculty(event.target.checked)}/><span>Request Faculty access (requires admin approval)</span></label>
        </>}
        <button className="button button-primary button-full" disabled={busy || (mode === 'register' && profile.skills.length === 0)}>{busy ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'}<ArrowRight size={16}/></button>
      </form>
      <p className="auth-toggle">{mode === 'login' ? 'New to Project Mentor?' : 'Already have an account?'} <button onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError('') }}>{mode === 'login' ? 'Create account' : 'Sign in'}</button></p><div className="auth-note">Faculty access requires admin approval. Admin accounts are managed securely.</div></div></section></div>
}

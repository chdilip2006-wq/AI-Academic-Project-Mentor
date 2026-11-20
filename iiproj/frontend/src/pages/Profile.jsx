import { useEffect, useState } from 'react'
import { Plus, Save, Trash2, UserRound } from 'lucide-react'
import { api, json } from '../services/api'

const blank = { rollNumber: '', department: '', year: '', program: '', bio: '', interests: '', github: '', skills: [], programmingLanguages: [], previousProjectExperience: '' }

export default function Profile() {
  const [form, setForm] = useState(blank)
  const [skillName, setSkillName] = useState('')
  const [skillLevel, setSkillLevel] = useState('Beginner')
  const [languageName, setLanguageName] = useState('')
  const [busy, setBusy] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    api('/profile').then(result => setForm({ ...blank, ...result.profile })).catch(e => setError(e.message)).finally(() => setBusy(false))
  }, [])

  const change = (key, value) => setForm(current => ({ ...current, [key]: value }))
  const addSkill = () => {
    const name = skillName.trim()
    if (name && !form.skills.some(skill => skill.name.toLowerCase() === name.toLowerCase())) {
      change('skills', [...form.skills, { name, level: skillLevel }]); setSkillName('')
    }
  }
  const addLanguage = () => {
    const name = languageName.trim()
    if (name && !form.programmingLanguages.some(language => language.toLowerCase() === name.toLowerCase())) {
      change('programmingLanguages', [...form.programmingLanguages, name]); setLanguageName('')
    }
  }
  async function save(event) {
    event.preventDefault(); setSaving(true); setError(''); setMessage('')
    try { const result = await api('/profile', json('PUT', form)); setForm({ ...blank, ...result.profile }); setMessage('Profile saved successfully.') }
    catch (e) { setError(e.message) } finally { setSaving(false) }
  }

  if (busy) return <div className="loading-card">Loading your profile…</div>
  return <div className="page-stack narrow-page">
    <div className="page-intro"><div className="intro-icon"><UserRound size={19}/></div><div><h2>A little about you</h2><p>Your mentor uses this to make project suggestions that fit your experience.</p></div></div>
    {error && <div className="alert alert-error">{error}</div>}{message && <div className="alert alert-success">{message}</div>}
    <form className="form-card" onSubmit={save}>
      <Section number="01" title="Academic details" subtitle="Help us understand your context"/>
      <div className="field-grid"><Field label="Roll number" value={form.rollNumber} onChange={value => change('rollNumber', value)}/><Field label="Department" value={form.department} onChange={value => change('department', value)} placeholder="e.g. Computer Science"/><Field label="Program" value={form.program} onChange={value => change('program', value)} placeholder="e.g. B.Tech"/><label className="field"><span>Academic year</span><select value={form.year} onChange={e => change('year', e.target.value)}><option value="">Select year</option>{[1, 2, 3, 4, 5].map(year => <option key={year} value={year}>Year {year}</option>)}</select></label></div>
      <div className="field-grid"><Field label="Areas of interest" value={form.interests} onChange={value => change('interests', value)} placeholder="e.g. AI, accessibility, climate"/><Field label="GitHub profile" value={form.github} onChange={value => change('github', value)} placeholder="https://github.com/you"/></div>
      <label className="field"><span>Short bio</span><textarea rows="3" maxLength="1000" value={form.bio} onChange={e => change('bio', e.target.value)} placeholder="Tell your mentor what you enjoy learning"/></label>
      <label className="field"><span>Previous project experience</span><textarea rows="3" maxLength="2000" value={form.previousProjectExperience} onChange={e => change('previousProjectExperience', e.target.value)} placeholder="Projects you have worked on and what you learned"/></label>

      <Section number="02" title="Your skills" subtitle="Choose a level that feels right"/>
      <div className="skill-add"><input value={skillName} onChange={e => setSkillName(e.target.value)} onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), addSkill())} placeholder="Add a skill (e.g. data visualization)"/><select value={skillLevel} onChange={e => setSkillLevel(e.target.value)}><option>Beginner</option><option>Intermediate</option><option>Advanced</option></select><button type="button" className="button button-secondary" onClick={addSkill}><Plus size={15}/> Add</button></div>
      <div className="skill-list">{form.skills.map((skill, index) => <div className="skill-chip" key={`${skill.name}-${index}`}><b>{skill.name}</b><span>{skill.level}</span><button type="button" aria-label={`Remove ${skill.name}`} onClick={() => change('skills', form.skills.filter((_, i) => i !== index))}><Trash2 size={13}/></button></div>)}</div>

      <Section number="03" title="Programming languages" subtitle="Helps tailor technology recommendations"/>
      <div className="skill-add"><input value={languageName} onChange={e => setLanguageName(e.target.value)} onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), addLanguage())} placeholder="Add a language (e.g. Python)"/><button type="button" className="button button-secondary" onClick={addLanguage}><Plus size={15}/> Add</button></div>
      <div className="skill-list">{form.programmingLanguages.map((language, index) => <div className="skill-chip" key={`${language}-${index}`}><b>{language}</b><button type="button" aria-label={`Remove ${language}`} onClick={() => change('programmingLanguages', form.programmingLanguages.filter((_, i) => i !== index))}><Trash2 size={13}/></button></div>)}</div>

      <div className="form-actions"><span className="muted small">Your profile is visible to you and assigned faculty.</span><button className="button button-primary" disabled={saving}>{saving ? 'Saving…' : <><Save size={15}/> Save profile</>}</button></div>
    </form>
  </div>
}

function Section({ number, title, subtitle }) { return <div className="form-section-title section-divider"><span>{number}</span><div><b>{title}</b><small>{subtitle}</small></div></div> }
function Field({ label, value, onChange, placeholder = '' }) { return <label className="field"><span>{label}</span><input value={value || ''} onChange={e => onChange(e.target.value)} placeholder={placeholder}/></label> }

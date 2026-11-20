import { useEffect, useState } from 'react'
import { ArrowLeft, Check, Clock3, Sparkles, TriangleAlert } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../services/api'

export default function FacultyProject() {
  const { id } = useParams()
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [summaryBusy, setSummaryBusy] = useState(false)
  useEffect(() => { api(`/faculty/projects/${id}`).then(setData).catch(e => setError(e.message)) }, [id])

  async function createSummary() {
    setSummaryBusy(true); setError('')
    try { const result = await api(`/faculty/projects/${id}/summary`, { method: 'POST' }); setData(current => ({ ...current, aiSummary: result.aiSummary, summaryGeneratedAt: result.summaryGeneratedAt })) }
    catch (e) { setError(e.message) } finally { setSummaryBusy(false) }
  }

  if (error && !data) return <div className="alert alert-error">{error}</div>
  if (!data) return <div className="loading-card">Loading project report…</div>
  const { project, milestones, progressUpdates, aiSummary } = data
  return <div className="page-stack">
    <Link to="/faculty" className="back-link"><ArrowLeft size={15}/> Assigned projects</Link>
    {error && <div className="alert alert-error">{error}</div>}
    <div className="faculty-welcome"><div><span className="eyebrow">{project.student?.name || project.student?.email || 'Student'} · PROJECT REVIEW</span><h2>{project.title}</h2><p>{project.idea}</p></div><div className="faculty-mark"><span>{project.overallProgress || 0}%</span></div></div>
    <div className="faculty-detail-grid"><section className="form-card"><div className="side-card-heading"><div><div className="eyebrow">AI-GENERATED SUMMARY</div><small className="muted">Generated only when you request it; saved for later reviews.</small></div><button className="button button-secondary" onClick={createSummary} disabled={summaryBusy}><Sparkles size={14}/>{summaryBusy ? 'Generating…' : 'Generate summary'}</button></div><p className="summary-copy">{aiSummary}</p>{data.summaryGeneratedAt && <small className="muted">Last updated {String(data.summaryGeneratedAt).slice(0, 10)}</small>}</section><section className="form-card"><div className="eyebrow">PROJECT HEALTH</div><h3>{project.health || 'On Track'}</h3><div className="progress-track"><span style={{ width: `${project.overallProgress || 0}%` }}/></div><p className="muted small">{project.overallProgress || 0}% overall completion</p></section></div>
    <div className="faculty-detail-grid"><section className="form-card"><div className="side-card-heading"><div><span className="eyebrow">MILESTONE STATUS</span><h3>Project plan</h3></div><span className="count-badge">{milestones.length}</span></div>{milestones.length ? milestones.map((milestone, index) => <div className="detail-row" key={milestone.id}><span className={`milestone-number ${milestone.status === 'Completed' ? 'done' : ''}`}>{milestone.status === 'Completed' ? <Check size={13}/> : index + 1}</span><div><b>{milestone.title}</b><small>Week {milestone.week} · {milestone.status} · {milestone.progress || 0}%</small><p>{milestone.deliverables?.join(' · ')}</p>{milestone.challenges && <p><TriangleAlert size={12}/> {milestone.challenges}</p>}</div></div>) : <p className="muted small">No milestones generated yet.</p>}</section>
      <section className="form-card"><div className="eyebrow">RECENT STUDENT UPDATES</div><h3>Progress reports</h3>{progressUpdates.length ? progressUpdates.map(update => <div className="detail-row" key={update.id}><span className="update-dot"><Clock3 size={14}/></span><div><b>{update.week ? `Week ${update.week}` : 'Progress check-in'}</b><small>{update.createdAt?.slice?.(0, 10) || 'Recently submitted'}</small><p>{update.summary}</p>{update.challenges && <p><TriangleAlert size={12}/> Blocker: {update.challenges}</p>}</div></div>) : <p className="muted small">No progress updates have been submitted yet.</p>}</section>
    </div>
  </div>
}

import { useEffect, useState } from 'react'
import { ArrowLeft, RefreshCw, TriangleAlert } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../services/api'

export default function Risks() {
  const { id } = useParams()
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  useEffect(() => { api(`/projects/${id}/risks`).then(setData).catch(e => setError(e.message)) }, [id])

  async function reassess() {
    setBusy(true); setError(''); setNotice('')
    try {
      const result = await api(`/projects/${id}/risks/assess`, { method: 'POST' })
      setData(current => ({ ...current, assessments: [result.assessment, ...(current?.assessments || [])] }))
      setNotice('Risk assessment saved. It is based on the project record and progress updates.')
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  if (!data && !error) return <div className="loading-card">Loading project risks…</div>
  return <div className="page-stack narrow-page">
    <Link to={`/projects/${id}`} className="back-link"><ArrowLeft size={15}/> Back to project</Link>
    <div className="page-intro"><div className="intro-icon intro-warm"><TriangleAlert size={19}/></div><div><span className="eyebrow">RISK MANAGEMENT</span><h2>Risks and challenges</h2><p>Review blueprint risks and track challenges reported during project work.</p></div></div>
    {error && <div className="alert alert-error">{error}</div>}{notice && <div className="alert alert-success">{notice}</div>}
    {data && <>
      <section className="form-card"><div className="side-card-heading"><div><span className="eyebrow">BLUEPRINT RISKS</span><h3>Original risk assessment</h3></div><span className="count-badge">{data.risks.length}</span></div>
        {data.risks.length ? data.risks.map((risk, index) => <RiskCard key={`${risk.category}-${index}`} risk={risk}/>) : <div className="side-empty"><p>Generate a project blueprint to receive an initial risk assessment.</p></div>}
      </section>
      <section className="form-card"><div className="side-card-heading"><div><span className="eyebrow">EXECUTION RISKS</span><h3>Reassess current progress</h3></div><button className="button button-primary" onClick={reassess} disabled={busy || data.risks.length === 0}>{busy ? 'Reviewing…' : <><RefreshCw size={14}/> Update assessment</>}</button></div>
        {data.assessments?.length ? data.assessments.map(item => <article className="risk-assessment" key={item.id}><p>{item.summary}</p><small className="muted">Updated {item.createdAt?.slice?.(0, 10) || 'recently'}</small>{item.risks?.map((risk, index) => <RiskCard key={`${risk.category}-${index}`} risk={risk}/>)}</article>) : <p className="muted">An updated analysis runs only when you select the button. It uses stored risks, milestones, and progress reports.</p>}
      </section>
      <section className="form-card"><div className="side-card-heading"><div><span className="eyebrow">STUDENT-REPORTED</span><h3>Challenges from progress reports</h3></div><span className="count-badge">{data.reportedChallenges.length}</span></div>
        {data.reportedChallenges.length ? data.reportedChallenges.map(report => <div className="detail-row" key={report.id}><span className="update-dot"><TriangleAlert size={14}/></span><div><b>{report.week ? `Week ${report.week}` : 'Progress update'}</b><small>{report.createdAt?.slice?.(0, 10) || ''}</small><p>{report.challenges}</p></div></div>) : <p className="muted">Challenges you add in weekly project check-ins will appear here.</p>}
        <Link className="button button-secondary" to={`/projects/${id}`}>Report a challenge in progress check-in</Link>
      </section>
    </>}
  </div>
}

function RiskCard({ risk }) {
  return <article className="risk-item"><div><TriangleAlert size={15}/><b>{risk.description}</b><span className={`badge ${risk.severity === 'High' ? 'badge-orange' : 'badge-green'}`}>{risk.severity}</span></div><p>{risk.mitigation}</p><small>{risk.category} · Likelihood: {risk.probability}</small></article>
}

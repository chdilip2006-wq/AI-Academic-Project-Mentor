import { useEffect, useState } from 'react'
import { ArrowRight, BookOpen, Check, CircleAlert, Clock3, FolderKanban, Search, Users } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api } from '../services/api'

export default function Faculty() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  useEffect(() => { api('/faculty/dashboard').then(setData).catch(e => setError(e.message)) }, [])
  if (error) return <div className="alert alert-error">{error}</div>
  if (!data) return <div className="loading-card">Loading assigned projects…</div>
  const projects = data.projects.filter(project => `${project.title} ${project.student?.name || ''}`.toLowerCase().includes(query.toLowerCase()))
  return <div className="page-stack">
    <div className="faculty-welcome"><div><span className="eyebrow">FACULTY OVERVIEW</span><h2>Student progress, at a glance</h2><p>See how assigned projects are moving and where students may need support.</p></div><div className="faculty-mark"><Users size={23}/></div></div>
    <div className="stats-grid faculty-stats"><Stat icon={FolderKanban} label="Assigned projects" value={data.summary.assignedProjects} color="blue"/><Stat icon={Users} label="Assigned students" value={data.summary.assignedStudents} color="blue"/><Stat icon={BookOpen} label="In progress" value={data.summary.inProgress} color="green"/><Stat icon={Check} label="Completed" value={data.summary.completed} color="green"/><Stat icon={Clock3} label="Delayed" value={data.summary.delayed} color="orange"/><Stat icon={CircleAlert} label="At risk" value={data.summary.atRisk} color="orange"/></div>
    <div className="section-heading"><div><span className="eyebrow">YOUR STUDENTS</span><h2>Assigned projects</h2></div><label className="search-box"><Search size={15}/><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search projects"/></label></div>
    {projects.length === 0 ? <div className="empty-card"><div className="empty-icon"><Users size={22}/></div><h3>{data.projects.length ? 'No matching projects' : 'No assigned projects yet'}</h3><p>{data.projects.length ? 'Try another search.' : 'An administrator can assign student projects to your faculty account.'}</p></div> : <div className="faculty-project-list">{projects.map(project => <Link className="faculty-project-card" to={`/faculty/projects/${project.id}`} key={project.id}><div className="student-avatar">{(project.student?.name || 'S')[0]}</div><div className="faculty-project-info"><span className="eyebrow">{project.student?.name || project.student?.email || 'Student'} · {project.domain || 'Academic project'}</span><h3>{project.title}</h3><p>{project.idea}</p><div className="faculty-progress"><div className="progress-track"><span style={{ width: `${project.overallProgress || 0}%` }}/></div><small>{project.overallProgress || 0}% complete</small></div></div><div className="faculty-project-end"><span className={`badge ${['At Risk', 'Needs Attention'].includes(project.health) ? 'badge-orange' : 'badge-green'}`}>{project.health || 'On Track'}</span><ArrowRight size={17}/></div></Link>)}</div>}
  </div>
}

function Stat({ icon: Icon, label, value, color }) { return <div className="stat-card"><div className={`stat-icon ${color}`}><Icon size={18}/></div><span>{label}</span><strong>{value}</strong><small>Assigned to you</small></div> }

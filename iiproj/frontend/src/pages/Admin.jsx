import { useEffect, useState } from 'react'
import { Activity, Check, FolderKanban, Settings, Shield, Trash2, Users, X } from 'lucide-react'
import { api, json } from '../services/api'
import { useAuth } from '../contexts/AuthContext'

export default function Admin() {
  const { user: currentUser } = useAuth()
  const [users, setUsers] = useState([])
  const [facultyRequests, setFacultyRequests] = useState([])
  const [projects, setProjects] = useState([])
  const [assignments, setAssignments] = useState([])
  const [settings, setSettings] = useState({})
  const [overview, setOverview] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [facultyId, setFacultyId] = useState('')
  const [projectId, setProjectId] = useState('')
  const [busy, setBusy] = useState(false)

  async function load() {
    try {
      const [userData, projectData, settingsData, overviewData, assignmentData, facultyRequestData] = await Promise.all([
        api('/admin/users'), api('/projects'), api('/admin/settings'), api('/admin/overview'), api('/admin/assignments'), api('/admin/faculty-requests'),
      ])
      setUsers(userData.users); setProjects(projectData.projects); setSettings(settingsData.settings); setOverview(overviewData.overview); setAssignments(assignmentData.assignments); setFacultyRequests(facultyRequestData.requests)
    } catch (e) { setError(e.message) }
  }
  useEffect(() => { load() }, [])

  async function role(uid, value) {
    setError('')
    try { await api(`/admin/users/${uid}/role`, json('PATCH', { role: value })); setNotice('User role updated.'); await load() }
    catch (e) { setError(e.message) }
  }
  async function reviewFacultyRequest(id, decision) {
    setError(''); setBusy(true)
    try { await api(`/admin/faculty-requests/${id}/review`, json('POST', { decision })); setNotice(`Faculty request ${decision.toLowerCase()}.`); await load() }
    catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  async function assign(event) {
    event.preventDefault(); setBusy(true); setError('')
    try { await api('/admin/assignments', json('POST', { facultyId, projectId })); setNotice('Faculty assignment saved.'); await load() }
    catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  async function removeAssignment(id) {
    setError('')
    try { await api(`/admin/assignments/${id}`, { method: 'DELETE' }); setNotice('Faculty assignment removed.'); await load() }
    catch (e) { setError(e.message) }
  }
  async function saveSettings() {
    setBusy(true); setError('')
    try { const result = await api('/admin/settings', json('PUT', settings)); setSettings(result.settings); setNotice('Platform settings saved.') }
    catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  return <div className="page-stack">
    <div className="faculty-welcome"><div><span className="eyebrow">ADMINISTRATION</span><h2>Platform management</h2><p>Monitor workspace activity, manage access, and assign faculty to projects.</p></div><div className="faculty-mark"><Shield size={22}/></div></div>
    {error && <div className="alert alert-error">{error}</div>}{notice && <div className="alert alert-success">{notice}<button onClick={() => setNotice('')}>Dismiss</button></div>}
    {overview && <><div className="section-heading"><div><span className="eyebrow">PLATFORM OVERVIEW</span><h2>Workspace statistics</h2></div></div><div className="stats-grid"><Stat icon={Users} label="Users" value={overview.totalUsers} color="blue"/><Stat icon={Users} label="Students" value={overview.students} color="green"/><Stat icon={Shield} label="Faculty" value={overview.faculty} color="blue"/><Stat icon={FolderKanban} label="Projects" value={overview.totalProjects} color="green"/><Stat icon={Activity} label="At risk" value={overview.atRisk} color="orange"/></div></>}
    <div className="admin-grid">
      <section className="form-card"><div className="side-card-heading"><div><span className="eyebrow">FACULTY ACCESS</span><h3>Faculty requests</h3></div><span className="count-badge">{facultyRequests.filter(item => item.status === 'PENDING').length} pending</span></div>{facultyRequests.filter(item => item.status === 'PENDING').length === 0 ? <p className="muted">No faculty requests are waiting for review.</p> : facultyRequests.filter(item => item.status === 'PENDING').map(item => <div className="detail-row" key={item.id}><span className="update-dot"><Users size={14}/></span><div><b>{item.name}</b><small>{item.email} · Requested {item.createdAt?.slice?.(0, 10) || 'recently'}</small></div><button className="button button-secondary" onClick={() => reviewFacultyRequest(item.id, 'REJECTED')} disabled={busy}><X size={14}/> Reject</button><button className="button button-primary" onClick={() => reviewFacultyRequest(item.id, 'APPROVED')} disabled={busy}><Check size={14}/> Approve</button></div>)}</section>
      <section className="form-card admin-users"><div className="side-card-heading"><div><span className="eyebrow">ACCESS CONTROL</span><h3><Users size={17}/> User roles</h3></div><span className="count-badge">{users.length}</span></div>{users.length === 0 ? <p className="muted">No user accounts are registered yet.</p> : <div className="table-wrap"><table><thead><tr><th>User</th><th>Email</th><th>Role</th></tr></thead><tbody>{users.map(user => <tr key={user.uid}><td>{user.name || '—'}</td><td>{user.email}</td><td><select value={user.role} disabled={user.uid === currentUser?.uid} title={user.uid === currentUser?.uid ? 'You cannot change your own role' : 'Only an approved faculty request grants Faculty access'} onChange={event => role(user.uid, event.target.value)}><option value="student">Student</option>{user.role === 'faculty'&&<option value="faculty">Faculty</option>}<option value="admin">Admin</option></select></td></tr>)}</tbody></table></div>}<small className="muted">Faculty status is granted through request approval. Administrators can promote another account to Admin; your own role is locked.</small></section>
      <section className="form-card"><div className="eyebrow">FACULTY ASSIGNMENT</div><h3>Assign a project</h3><form className="admin-assign" onSubmit={assign}><label className="field"><span>Faculty member</span><select required value={facultyId} onChange={event => setFacultyId(event.target.value)}><option value="">Choose faculty</option>{users.filter(user => user.role === 'faculty').map(user => <option value={user.uid} key={user.uid}>{user.name || user.email}</option>)}</select></label><label className="field"><span>Project</span><select required value={projectId} onChange={event => setProjectId(event.target.value)}><option value="">Choose project</option>{projects.map(project => <option value={project.id} key={project.id}>{project.title}</option>)}</select></label><button className="button button-primary button-full" disabled={busy}><Check size={15}/> Save assignment</button></form></section>
      <section className="form-card"><div className="side-card-heading"><div><div className="eyebrow">FACULTY ASSIGNMENTS</div><h3>Current assignments</h3></div><span className="count-badge">{assignments.length}</span></div>{assignments.length ? assignments.map(item => <div className="detail-row" key={item.id}><span className="update-dot"><Users size={14}/></span><div><b>{item.faculty} → {item.student}</b><small>{item.project}</small></div><button className="icon-button" title="Remove assignment" onClick={() => removeAssignment(item.id)}><Trash2 size={15}/></button></div>) : <p className="muted">No faculty assignments yet.</p>}</section>
      <section className="form-card"><div className="side-card-heading"><div><span className="eyebrow">PROJECT OVERVIEW</span><h3>Projects at a glance</h3></div><span className="count-badge">{projects.length}</span></div>{projects.length ? projects.map(project => <div className="detail-row" key={project.id}><span className="project-icon"><FolderKanban size={16}/></span><div><b>{project.title}</b><small>{project.status} · {project.overallProgress || 0}% · {project.health}</small></div></div>) : <p className="muted">No projects have been submitted yet.</p>}</section>
      <section className="form-card"><div className="eyebrow"><Settings size={13}/> PLATFORM SETTINGS</div><h3>Workspace preferences</h3><label className="field"><span>Platform name</span><input value={settings.platformName || ''} onChange={event => setSettings({ ...settings, platformName: event.target.value })}/></label><label className="field"><span>Support email</span><input type="email" value={settings.supportEmail || ''} onChange={event => setSettings({ ...settings, supportEmail: event.target.value })}/></label><label className="toggle-setting"><input type="checkbox" checked={!!settings.maintenanceMode} onChange={event => setSettings({ ...settings, maintenanceMode: event.target.checked })}/> Maintenance mode</label><button className="button button-primary" onClick={saveSettings} disabled={busy}>{busy ? 'Saving…' : 'Save settings'}</button></section>
    </div>
  </div>
}

function Stat({ icon: Icon, label, value, color }) { return <div className="stat-card"><div className={`stat-icon ${color}`}><Icon size={18}/></div><span>{label}</span><strong>{value}</strong><small>Across the workspace</small></div> }

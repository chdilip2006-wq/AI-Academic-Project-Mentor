import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { BookOpen, Bot, ClipboardList, FileText, FolderKanban, LayoutDashboard, LogOut, Menu, UserRound, Users, X } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { useState } from 'react'

export default function AppLayout() {
  const { user, logout } = useAuth()
  const [open, setOpen] = useState(false)
  const location = useLocation()
  const links = user?.role === 'faculty'
    ? [{ to: '/', label: 'Dashboard', icon: LayoutDashboard }, { to: '/faculty', label: 'Assigned projects', icon: Users }]
    : user?.role === 'admin'
      ? [{ to: '/', label: 'Dashboard', icon: LayoutDashboard }, { to: '/admin', label: 'User management', icon: Users }]
      : [{ to: '/', label: 'Dashboard', icon: LayoutDashboard }, { to: '/profile', label: 'My profile', icon: UserRound }, { to: '/projects/new', label: 'New project idea', icon: BookOpen }]
  const title = location.pathname.includes('/mentor') ? 'AI Mentor' : location.pathname.includes('/documents') ? 'Documentation' : location.pathname.includes('/risks') ? 'Risk management' : location.pathname.includes('/projects/') ? 'Project workspace' : location.pathname === '/profile' ? 'My profile' : 'Workspace'
  return <div className="app-shell">
    <button className="mobile-menu" onClick={() => setOpen(!open)} aria-label="Toggle navigation">{open ? <X /> : <Menu />}</button>
    {open && <button className="sidebar-scrim" aria-label="Close navigation" onClick={() => setOpen(false)} />}
    <aside className={`sidebar ${open ? 'sidebar-open' : ''}`}>
      <div className="brand"><div className="brand-mark"><BookOpen size={19} /></div><div><strong>Project Mentor</strong><span>ACADEMIC WORKSPACE</span></div></div>
      <div className="workspace-switch"><span className="switch-dot" /> Academic Workspace <span className="chevron">⌄</span></div>
      <p className="nav-label">WORKSPACE</p>
      <nav>{links.map(({ to, label, icon: Icon }) => <NavLink onClick={() => setOpen(false)} key={to} end={to === '/'} to={to} className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}><Icon size={17} /><span>{label}</span>{to === '/projects/new' && <span className="nav-plus">+</span>}</NavLink>)}</nav>
      {user?.role === 'student' && <><p className="nav-label nav-label-spaced">YOUR LEARNING</p><div className="nav-hint"><ClipboardList size={16}/><span>Milestones and project tools<br/><small>Open a project to continue</small></span></div></>}
      <div className="sidebar-bottom"><div className="user-card"><div className="avatar">{(user?.name || user?.email || 'U')[0].toUpperCase()}</div><div className="user-copy"><strong>{user?.name || 'Welcome'}</strong><span>{user?.role || 'student'}</span></div><button className="icon-button" onClick={logout} title="Sign out"><LogOut size={16}/></button></div><div className="sidebar-foot">Made for meaningful project work <span>✳</span></div></div>
    </aside>
    <main className="main-area"><header className="topbar"><div><span className="eyebrow">{title.toUpperCase()}</span><h1>{title}</h1></div><div className="topbar-right"><span className="status-pill"><span className="status-dot"/>Workspace ready</span><div className="avatar avatar-small">{(user?.name || user?.email || 'U')[0].toUpperCase()}</div></div></header><div className="page-content"><Outlet /></div></main>
  </div>
}

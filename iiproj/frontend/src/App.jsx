import { Navigate, Route, Routes } from 'react-router-dom'
import ProtectedRoute from './routes/ProtectedRoute'
import AppLayout from './layouts/AppLayout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Profile from './pages/Profile'
import NewProject from './pages/NewProject'
import Project from './pages/Project'
import Mentor from './pages/Mentor'
import Documents from './pages/Documents'
import Faculty from './pages/Faculty'
import Admin from './pages/Admin'
import FacultyProject from './pages/FacultyProject'
import PlanAdjustments from './pages/PlanAdjustments'
import Risks from './pages/Risks'
import { useAuth } from './contexts/AuthContext'

function Home() {
  const { user } = useAuth()
  if (user?.role === 'faculty') return <Faculty />
  if (user?.role === 'admin') return <Admin />
  return <Dashboard />
}
export default function App() {
  return <Routes><Route path="/login" element={<Login />} /><Route path="/" element={<ProtectedRoute><AppLayout /></ProtectedRoute>}><Route index element={<Home />} /><Route path="profile" element={<Profile />} /><Route path="projects/new" element={<NewProject />} /><Route path="projects/:id" element={<Project />} /><Route path="projects/:id/mentor" element={<Mentor />} /><Route path="projects/:id/risks" element={<Risks />} /><Route path="projects/:id/documents" element={<Documents />} /><Route path="projects/:id/adjust-plan" element={<PlanAdjustments />} /><Route path="faculty" element={<ProtectedRoute roles={['faculty','admin']}><Faculty /></ProtectedRoute>} /><Route path="faculty/projects/:id" element={<ProtectedRoute roles={['faculty','admin']}><FacultyProject /></ProtectedRoute>} /><Route path="admin" element={<ProtectedRoute roles={['admin']}><Admin /></ProtectedRoute>} /><Route path="*" element={<Navigate to="/" replace />} /></Route></Routes>
}

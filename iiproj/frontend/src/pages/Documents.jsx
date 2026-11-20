import { useEffect, useState } from 'react'
import { ArrowLeft, Download, FileText, Sparkles, Trash2, Upload } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { api, json } from '../services/api'

const types = [
  ['synopsis', 'Project synopsis', 'A concise academic overview of your project.'],
  ['problem-statement', 'Problem statement', 'A focused description of the problem and its context.'],
  ['objectives', 'Objectives', 'Clear and measurable project objectives.'],
  ['literature-review-outline', 'Literature review outline', 'A structure for your review. Add verified sources yourself.'],
  ['methodology', 'Proposed methodology', 'A proposed approach based on your project plan.'],
  ['system-requirements', 'System requirements', 'Functional and non-functional requirements.'],
  ['progress-report', 'Progress report', 'A report based only on your recorded progress updates.'],
  ['final-report-outline', 'Final report outline', 'A report structure with placeholders for results and references.'],
]

export default function Documents() {
  const { id } = useParams()
  const [docs, setDocs] = useState([])
  const [project, setProject] = useState(null)
  const [selected, setSelected] = useState('synopsis')
  const [preview, setPreview] = useState(null)
  const [file, setFile] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  useEffect(() => {
    Promise.all([api(`/projects/${id}/documents`), api(`/projects/${id}`)])
      .then(([documents, result]) => { setDocs(documents.documents); setProject(result.project) })
      .catch(e => setError(e.message))
  }, [id])

  async function generate() {
    setBusy(true); setError(''); setNotice('')
    try {
      const result = await api(`/projects/${id}/documents`, json('POST', { type: selected }))
      setDocs(items => [result.document, ...items]); setPreview(result.document); setNotice('Your document is ready to preview.')
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  async function upload() {
    if (!file) return
    setBusy(true); setError(''); setNotice('')
    try {
      const body = new FormData(); body.append('file', file)
      const result = await api(`/projects/${id}/files`, { method: 'POST', body })
      setDocs(items => [result.document, ...items]); setFile(null); setNotice('File uploaded successfully.')
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  async function download(doc) {
    try {
      const { downloadUrl } = await api(`/projects/${id}/documents/${doc.id}/download`)
      const apiBase = import.meta.env.VITE_API_URL || 'http://localhost:5000/api'
      if (downloadUrl.startsWith('/')) {
        const response = await fetch(`${apiBase}${downloadUrl.slice(4)}`, { headers: { Authorization: `Bearer ${sessionStorage.getItem('accessToken')}` } })
        if (!response.ok) throw new Error('The document download could not be completed.')
        const url = URL.createObjectURL(await response.blob()); const link = document.createElement('a'); link.href = url; link.download = doc.filename || 'project-document'; link.click(); URL.revokeObjectURL(url)
      } else window.open(downloadUrl, '_blank', 'noopener,noreferrer')
    } catch (e) { setError(e.message) }
  }

  async function remove(doc) {
    try {
      await api(`/projects/${id}/documents/${doc.id}`, { method: 'DELETE' })
      setDocs(items => items.filter(item => item.id !== doc.id))
      if (preview?.id === doc.id) setPreview(null)
      setNotice('Document deleted.')
    } catch (e) { setError(e.message) }
  }

  return <div className="page-stack">
    <Link to={`/projects/${id}`} className="back-link"><ArrowLeft size={15}/> Back to project</Link>
    <div className="page-intro"><div className="intro-icon"><FileText size={19}/></div><div><span className="eyebrow">PROJECT DOCUMENTATION</span><h2>{project?.title || 'Your project documents'}</h2><p>Draft useful academic documents from your project record. Generated drafts do not invent findings or references.</p></div></div>
    {error && <div className="alert alert-error">{error}</div>}{notice && <div className="alert alert-success">{notice}</div>}
    <div className="docs-layout">
      <section className="form-card"><span className="eyebrow">GENERATE A DOCUMENT</span><h3>What would you like to prepare?</h3>
        <div className="doc-type-list">{types.map(([value, title, desc]) => <label key={value} className={`doc-type ${selected === value ? 'selected' : ''}`}><input type="radio" name="doctype" value={value} checked={selected === value} onChange={() => setSelected(value)}/><span className="radio-dot"/><span><b>{title}</b><small>{desc}</small></span></label>)}</div>
        <button className="button button-primary button-full" onClick={generate} disabled={busy}><Sparkles size={15}/>{busy ? 'Preparing your document…' : 'Generate document'}</button><small className="muted document-note">Uses your stored project information · Groq AI</small>
        <label className="field"><span>Supporting file (PDF, DOC, DOCX, TXT, Markdown, PNG, or JPEG; max 10 MB)</span><input type="file" accept=".pdf,.doc,.docx,.txt,.md,.png,.jpg,.jpeg" onChange={e => setFile(e.target.files?.[0] || null)}/></label>
        <button className="button button-secondary button-full" onClick={upload} disabled={busy || !file}><Upload size={15}/>{busy ? 'Uploading…' : 'Upload supporting file'}</button>
      </section>
      <section className="form-card saved-docs"><div className="side-card-heading"><div><span className="eyebrow">YOUR LIBRARY</span><h3>Saved documents</h3></div><span className="count-badge">{docs.length}</span></div>
        {docs.length === 0 ? <div className="side-empty"><FileText size={20}/><p>Your project documents will show up here.</p></div> : docs.map(doc => <div className="saved-doc" key={doc.id}><div className="doc-file-icon"><FileText size={17}/></div><div><b>{doc.title || doc.filename}</b><small>{doc.type?.replaceAll('-', ' ')} · {doc.filename?.split('.').pop()?.toUpperCase()}</small></div>{doc.preview && <button className="icon-button" title="Preview" onClick={() => setPreview(doc)}><FileText size={15}/></button>}<button className="icon-button" title="Download" onClick={() => download(doc)}><Download size={15}/></button><button className="icon-button" title="Delete" onClick={() => remove(doc)}><Trash2 size={15}/></button></div>)}
      </section>
    </div>
    {preview && <div className="modal-backdrop" onClick={() => setPreview(null)}><section className="preview-modal" onClick={e => e.stopPropagation()}><div className="preview-head"><div><span className="eyebrow">DOCUMENT PREVIEW</span><h3>{preview.title}</h3></div><button className="button button-secondary" onClick={() => download(preview)}><Download size={14}/> Download</button></div><pre>{preview.preview || 'Download this file to view its contents.'}</pre><button className="button button-primary" onClick={() => setPreview(null)}>Done</button></section></div>}
  </div>
}


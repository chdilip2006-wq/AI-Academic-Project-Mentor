import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, Brain, CheckCircle2, ClipboardList, RotateCcw } from 'lucide-react'
import { api, json } from '../services/api'

export default function SkillAssessment() {
  const [questions, setQuestions] = useState([])
  const [answers, setAnswers] = useState({})
  const [assessment, setAssessment] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    Promise.all([api('/profile/skill-assessment/questions'), api('/profile')])
      .then(([questionResult, profileResult]) => {
        setQuestions(questionResult.questions)
        setAssessment(profileResult.profile?.skillAssessment || null)
      })
      .catch(problem => setError(problem.message))
      .finally(() => setLoading(false))
  }, [])

  const answeredCount = useMemo(() => Object.keys(answers).length, [answers])
  async function submit(event) {
    event.preventDefault(); setError(''); setSaving(true)
    try {
      const result = await api('/profile/skill-assessment', json('POST', { answers }))
      setAssessment(result.assessment)
      window.dispatchEvent(new CustomEvent('skill-assessment-complete', { detail: result.assessment }))
    } catch (problem) { setError(problem.message) }
    finally { setSaving(false) }
  }

  if (loading) return <div className="loading-card">Loading your assessment…</div>
  if (error && questions.length === 0) return <div className="page-stack narrow-page"><div className="alert alert-error">{error}</div></div>

  if (assessment) return <div className="page-stack narrow-page">
    <div className="page-intro"><div className="intro-icon"><CheckCircle2 size={19}/></div><div><h2>Assessment complete</h2><p>Your answers give the project planner an additional signal about areas where you may want more guidance.</p></div></div>
    <section className="assessment-summary form-card">
      <div className="assessment-score"><strong>{assessment.totalCorrect}<span>/{assessment.totalQuestions}</span></strong><small>correct answers</small></div>
      <div className="assessment-domain-list">{assessment.domains?.map(item => <div className="assessment-domain" key={item.domain}><div><b>{item.domain}</b><small>{item.correct} of {item.total} correct</small></div><span className={`assessment-signal ${item.correct === item.total ? 'signal-strong' : item.correct ? 'signal-growing' : 'signal-foundation'}`}>{item.signal}</span></div>)}</div>
      <p className="assessment-disclaimer">This short quiz is a planning aid, not a formal measure or certification of your skills. You can retake it whenever you like.</p>
      <div className="form-actions"><button className="button button-secondary" onClick={() => { setAssessment(null); setAnswers({}); setError('') }}><RotateCcw size={14}/> Retake assessment</button><button className="button button-primary" onClick={() => navigate('/')} >Continue to workspace <ArrowRight size={14}/></button></div>
    </section>
  </div>

  const groupedQuestions = questions.reduce((groups, question) => {
    groups[question.domain] = [...(groups[question.domain] || []), question]
    return groups
  }, {})

  return <div className="page-stack narrow-page">
    <div className="page-intro"><div className="intro-icon"><Brain size={19}/></div><div><h2>Skill assessment</h2><p>Answer these short questions so your AI project planner can tailor its recommendations and learning steps. Choose the best answer; this is a planning aid, not a graded exam.</p></div></div>
    <div className="assessment-progress"><ClipboardList size={16}/><span>{answeredCount} of {questions.length} answered</span><div className="progress-track"><span style={{ width: `${questions.length ? answeredCount / questions.length * 100 : 0}%` }}/></div></div>
    {error && <div className="alert alert-error">{error}</div>}
    <form className="assessment-form" onSubmit={submit}>
      {Object.entries(groupedQuestions).map(([domain, items], domainIndex) => <section className="form-card assessment-group" key={domain}>
        <div className="form-section-title"><span>{String(domainIndex + 1).padStart(2, '0')}</span><div><b>{domain}</b><small>{items.length} questions</small></div></div>
        {items.map((question, questionIndex) => <fieldset className="assessment-question" key={question.id}>
          <legend>{questionIndex + 1}. {question.prompt}</legend>
          <div className="assessment-options">{question.options.map(option => <label className={`assessment-option ${answers[question.id] === option.id ? 'selected' : ''}`} key={option.id}><input type="radio" name={question.id} value={option.id} checked={answers[question.id] === option.id} onChange={() => setAnswers(current => ({ ...current, [question.id]: option.id }))}/><span>{option.text}</span></label>)}</div>
        </fieldset>)}
      </section>)}
      <div className="assessment-submit"><small>{answeredCount < questions.length ? `Answer all ${questions.length} questions to continue.` : 'You can review your answers before submitting.'}</small><button className="button button-primary" disabled={saving || answeredCount !== questions.length}>{saving ? 'Saving…' : 'Submit assessment'} <ArrowRight size={14}/></button></div>
    </form>
  </div>
}

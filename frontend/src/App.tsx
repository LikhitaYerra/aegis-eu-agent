import { useEffect, useRef, useState, type FormEvent } from 'react'
import {
  Activity, ArrowRight, Asterisk, BookOpen, BrainCircuit, Check, ChevronRight,
  CircleAlert, FileSearch, Fingerprint, LoaderCircle, LockKeyhole, Network,
  Shield, Sparkles,
} from 'lucide-react'
import { assess, type Assessment } from './api'
import { ResultWorkspace } from './components/ResultWorkspace'
import './App.css'

const examples = [
  {
    label: 'AI hiring',
    question: 'Is an AI tool that filters and ranks CVs high-risk under the EU AI Act, and what controls are required?',
  },
  {
    label: 'Support chatbot',
    question: 'What EU AI Act obligations should a startup consider before deploying an AI customer-support chatbot?',
  },
  {
    label: 'Emotion recognition',
    question: 'Can an EU employer use AI emotion recognition to monitor workers?',
  },
  {
    label: 'GPAI provider',
    question: 'What documentation and transparency duties apply to a provider of a general-purpose AI model in the EU?',
  },
]

const loadingSteps = [
  { label: 'Searching official sources', icon: FileSearch },
  { label: 'Reranking legal evidence', icon: Network },
  { label: 'Running three syntheses', icon: BrainCircuit },
  { label: 'Independent critic review', icon: Shield },
]

function App() {
  const [question, setQuestion] = useState(examples[1].question)
  const [assessment, setAssessment] = useState<Assessment | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [loadingStep, setLoadingStep] = useState(0)
  const controllerRef = useRef<AbortController | null>(null)

  useEffect(() => {
    if (!loading) {
      setLoadingStep(0)
      return
    }
    const timer = window.setInterval(() => {
      setLoadingStep((current) => Math.min(current + 1, loadingSteps.length - 1))
    }, 4500)
    return () => window.clearInterval(timer)
  }, [loading])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const cleanQuestion = question.trim()
    if (!cleanQuestion || loading) return
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    setError('')
    setAssessment(null)
    setLoading(true)
    try {
      const result = await assess(cleanQuestion, controller.signal)
      setAssessment(result)
      window.setTimeout(() => {
        document.getElementById('results')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }, 80)
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === 'AbortError') return
      setError(caught instanceof Error ? caught.message : 'The assessment failed safely.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="app-shell">
      <header className="site-header">
        <a className="brand" href="#top" aria-label="Aegis EU home">
          <span className="brand-mark"><Asterisk size={19} strokeWidth={2.4} /></span>
          <span>Aegis EU</span>
        </a>
        <nav className="main-nav" aria-label="Main navigation">
          <a href="#how-it-works">How it works</a>
          <a href="#assessment">Assessment</a>
          <a href="#evidence-standard">Evidence standard</a>
        </nav>
        <div className="header-status"><span className="status-dot" />Agent online</div>
      </header>

      <main id="top">
        <section className="hero-section">
          <div className="hero-copy">
            <div className="hero-badge"><Sparkles size={15} />Production AI governance research</div>
            <h1>Know where your AI stands.<span> Before regulators ask.</span></h1>
            <p className="hero-lead">
              Turn a product description into a source-grounded EU compliance brief, with
              hybrid legal retrieval, three-way synthesis, and an independent critic.
            </p>
            <div className="hero-proof">
              <div><strong>0.975</strong><span>RAGAS faithfulness</span></div>
              <div><strong>k=3</strong><span>Self-consistency</span></div>
              <div><strong>Curated</strong><span>EUR-Lex-derived corpus</span></div>
            </div>
          </div>

          <div className="intelligence-card" aria-label="Agent pipeline overview">
            <div className="intelligence-top">
              <span>Compliance intelligence</span><span className="live-chip">Live</span>
            </div>
            <div className="signal-orbit">
              <div className="orbit orbit-one" /><div className="orbit orbit-two" />
              <div className="orbit-node node-one"><BookOpen size={15} /></div>
              <div className="orbit-node node-two"><Fingerprint size={15} /></div>
              <div className="orbit-node node-three"><BrainCircuit size={15} /></div>
              <div className="signal-core"><Shield size={30} /><span>Guarded</span></div>
            </div>
            <div className="pipeline-list">
              <div><span><Check size={13} /> Retrieval</span><strong>Hybrid + RRF</strong></div>
              <div><span><Check size={13} /> Reasoning</span><strong>Evidence first</strong></div>
              <div><span><Check size={13} /> Review</span><strong>Critic enabled</strong></div>
            </div>
          </div>
        </section>

        <aside className="ai-disclosure-banner" aria-label="AI interaction disclosure">
          <Shield size={20} aria-hidden="true" />
          <div>
            <strong>You are interacting with an AI system.</strong>
            <span>
              Outputs are preliminary regulatory research, not legal advice. Validate conclusions
              with qualified counsel before acting.
            </span>
          </div>
        </aside>

        <section className="assessment-section" id="assessment">
          <div className="assessment-heading">
            <span className="eyebrow">Start a review</span>
            <h2>Describe the AI system you plan to deploy</h2>
            <p>Include its users, purpose, data, and any decisions it influences.</p>
          </div>

          <form className="composer" onSubmit={handleSubmit}>
            <div className="composer-topline">
              <span>Use case or compliance question</span><span>{question.length} / 4,000</span>
            </div>
            <textarea
              aria-label="AI system description"
              maxLength={4000}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Example: We rank job applicants using their CV and interview transcript…"
              value={question}
            />
            <div className="example-row">
              <span>Try an example</span>
              <div>
                {examples.map((example) => (
                  <button
                    className={question === example.question ? 'selected' : ''}
                    key={example.label}
                    onClick={() => setQuestion(example.question)}
                    type="button"
                  >
                    {example.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="composer-footer">
              <div className="privacy-note">
                <LockKeyhole size={15} />Guardrails inspect every request before model access
              </div>
              <button className="primary-button" disabled={!question.trim() || loading} type="submit">
                {loading ? (
                  <><LoaderCircle className="spin" size={18} />Assessing</>
                ) : (
                  <>Run assessment<ArrowRight size={18} /></>
                )}
              </button>
            </div>
          </form>

          {loading && (
            <div className="loading-panel" role="status">
              <div className="loading-heading">
                <div className="loader-mark"><LoaderCircle className="spin" size={22} /></div>
                <div><strong>Building your grounded brief</strong><span>This typically takes 25–60 seconds.</span></div>
              </div>
              <div className="loading-steps">
                {loadingSteps.map(({ label, icon: Icon }, index) => (
                  <div className={index < loadingStep ? 'done' : index === loadingStep ? 'active' : ''} key={label}>
                    <span>{index < loadingStep ? <Check size={14} /> : <Icon size={14} />}</span>{label}
                  </div>
                ))}
              </div>
            </div>
          )}

          {error && (
            <div className="error-panel" role="alert">
              <CircleAlert size={20} />
              <div><strong>Assessment could not be completed</strong><span>{error}</span></div>
            </div>
          )}
        </section>

        {assessment && <ResultWorkspace assessment={assessment} />}

        <section className="method-section" id="how-it-works">
          <div className="method-heading">
            <span className="eyebrow">Built for defensible research</span>
            <h2>One inspectable production agent</h2>
          </div>
          <div className="method-grid">
            <article>
              <span>Retrieval</span><FileSearch size={23} />
              <h3>Advanced RAG</h3>
              <p>BM25 and dense retrieval are fused, then a cross-encoder reranks the evidence.</p>
            </article>
            <article>
              <span>Security</span><Shield size={23} />
              <h3>Security &amp; guardrails</h3>
              <p>L1–L4 controls inspect input, evidence, output, and every tool action.</p>
            </article>
            <article>
              <span>Reasoning</span><BrainCircuit size={23} />
              <h3>Reasoning ensemble</h3>
              <p>Independent evidence-grounded drafts reduce one-shot variance before selection.</p>
            </article>
            <article>
              <span>Operations</span><Activity size={23} />
              <h3>Production controls</h3>
              <p>Prompt hashing, cost and latency telemetry, tracing, and a final critic verdict.</p>
            </article>
          </div>
        </section>

        <section className="evidence-band" id="evidence-standard">
          <div>
            <Shield size={25} />
            <span><strong>Research support, clearly disclosed.</strong>
              Every brief shows sources, uncertainty, a critic verdict, and run measurements.
            </span>
          </div>
          <a href="https://eur-lex.europa.eu/eli/reg/2024/1689/oj/eng" target="_blank" rel="noreferrer">
            View EU AI Act<ChevronRight size={17} />
          </a>
        </section>
      </main>

      <footer className="site-footer">
        <div className="brand compact">
          <span className="brand-mark"><Asterisk size={17} /></span><span>Aegis EU</span>
        </div>
        <p>Production AI governance research agent</p>
        <div><span>EU AI Act</span><span>GDPR</span><span>Agent v0.1.0</span></div>
      </footer>
    </div>
  )
}

export default App

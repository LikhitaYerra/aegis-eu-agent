import { useState } from 'react'
import {
  BadgeCheck,
  BookOpenCheck,
  BrainCircuit,
  CircleDollarSign,
  Clock3,
  Database,
  Fingerprint,
  Gauge,
  GitBranch,
  Scale,
  ShieldCheck,
  Workflow,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import type { Assessment } from '../api'
import { MetricCard } from './MetricCard'
import { SourceList } from './SourceList'

type ResultWorkspaceProps = {
  assessment: Assessment
}

type Tab = 'conclusion' | 'evidence' | 'analysis' | 'sources' | 'trace'

const tabs: { id: Tab; label: string; icon: typeof Scale }[] = [
  { id: 'conclusion', label: 'Decision brief', icon: Scale },
  { id: 'evidence', label: 'Evidence', icon: BookOpenCheck },
  { id: 'analysis', label: 'Analysis', icon: BrainCircuit },
  { id: 'sources', label: 'Sources', icon: Database },
  { id: 'trace', label: 'Agent trace', icon: Workflow },
]

function costLabel(cost: number) {
  if (cost === 0) return '$0.0000'
  return `$${cost.toFixed(4)}`
}

function percentageLabel(score: number) {
  return `${(score * 100).toFixed(1)}%`
}

export function ResultWorkspace({ assessment }: ResultWorkspaceProps) {
  const [activeTab, setActiveTab] = useState<Tab>('conclusion')
  const passed = assessment.critic_status === 'PASS'
  const confidence = assessment.sections.confidence.split(/[—-]/)[0].trim()

  return (
    <section className="results-section" id="results" aria-live="polite">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Assessment complete</span>
          <h2>Your regulatory research brief</h2>
        </div>
        <div className={`critic-pill ${passed ? 'pass' : 'revise'}`}>
          {passed ? <BadgeCheck size={18} /> : <ShieldCheck size={18} />}
          Critic {assessment.critic_status}
        </div>
      </div>

      <div className="metric-group-heading">
        <span>Current assessment</span>
        <small>Measurements and verdict for this run</small>
      </div>
      <div className="metric-grid">
        <MetricCard
          icon={ShieldCheck}
          label="Confidence"
          value={confidence}
          detail="model-reported level"
        />
        <MetricCard
          icon={Clock3}
          label="Run latency"
          value={`${assessment.latency_seconds.toFixed(1)}s`}
          detail="retrieval to verdict"
        />
        <MetricCard
          icon={CircleDollarSign}
          label="Estimated cost"
          value={costLabel(assessment.estimated_cost_usd)}
          detail={assessment.mode}
        />
        <MetricCard
          icon={Database}
          label="Evidence set"
          value={`${assessment.sources.length} sources`}
          detail="hybrid ranked"
        />
      </div>

      {assessment.ragas_metrics && (
        <>
          <div className="metric-group-heading ragas-heading">
            <span>RAGAS quality benchmark</span>
            <small>
              Final pipeline evaluation across {assessment.ragas_metrics.question_count} test questions
            </small>
          </div>
          <div className="metric-grid ragas-metric-grid">
            <MetricCard
              icon={Database}
              label="Context recall"
              value={percentageLabel(assessment.ragas_metrics.context_recall)}
              detail="relevant evidence retrieved"
            />
            <MetricCard
              icon={Gauge}
              label="Context precision"
              value={percentageLabel(assessment.ragas_metrics.context_precision)}
              detail="retrieved evidence precision"
            />
            <MetricCard
              icon={BadgeCheck}
              label="Faithfulness"
              value={percentageLabel(assessment.ragas_metrics.faithfulness)}
              detail="claims grounded in context"
            />
            <MetricCard
              icon={BrainCircuit}
              label="Answer relevancy"
              value={percentageLabel(assessment.ragas_metrics.answer_relevancy)}
              detail="response addresses question"
            />
          </div>
        </>
      )}

      <div className="workspace">
        <nav className="result-tabs" aria-label="Assessment sections">
          {tabs.map(({ id, label, icon: Icon }) => (
            <button
              className={activeTab === id ? 'active' : ''}
              key={id}
              onClick={() => setActiveTab(id)}
              type="button"
            >
              <Icon size={16} aria-hidden="true" />
              {label}
            </button>
          ))}
        </nav>

        <div className="result-content">
          {activeTab === 'conclusion' && (
            <div className="brief-layout">
              <div className="markdown-content conclusion-copy">
                <span className="content-label">Recommended position</span>
                <ReactMarkdown>{assessment.sections.conclusion}</ReactMarkdown>
              </div>
              <aside className="confidence-panel">
                <span>Model confidence</span>
                <div className="confidence-mark">
                  <ShieldCheck size={22} aria-hidden="true" />
                  {confidence}
                </div>
                <p>{assessment.sections.confidence}</p>
                <div className="review-note">
                  <Scale size={16} aria-hidden="true" />
                  Preliminary research, not legal advice.
                </div>
              </aside>
            </div>
          )}
          {activeTab === 'evidence' && (
            <div className="markdown-content">
              <span className="content-label">Grounded findings</span>
              <ReactMarkdown>{assessment.sections.evidence}</ReactMarkdown>
            </div>
          )}
          {activeTab === 'analysis' && (
            <div className="markdown-content">
              <span className="content-label">Regulatory reasoning</span>
              <ReactMarkdown>{assessment.sections.analysis}</ReactMarkdown>
            </div>
          )}
          {activeTab === 'sources' && <SourceList sources={assessment.sources} />}
          {activeTab === 'trace' && (
            <div className="trace-view">
              <div className="trace-intro">
                <div>
                  <span className="content-label">Execution trace</span>
                  <h3>Every production stage is inspectable</h3>
                  <p>
                    This run exposes each guarded stage of the research pipeline.
                  </p>
                </div>
                <div className="trace-hash">
                  <Fingerprint size={18} aria-hidden="true" />
                  <span>Prompt hash</span>
                  <code>{assessment.trace.prompt_hash}</code>
                </div>
              </div>

              <div className="trace-stages">
                {assessment.trace.stages.map((stage, index) => (
                  <article key={`${stage.layer}-${stage.label}`}>
                    <div className="trace-rail">
                      <span><CheckIcon status={stage.status} /></span>
                      {index < assessment.trace.stages.length - 1 && <i />}
                    </div>
                    <div className="trace-stage-copy">
                      <div>
                        <span>{stage.layer}</span>
                        <em>{stage.status}</em>
                      </div>
                      <h4>{stage.label}</h4>
                      <strong>{stage.method}</strong>
                      <p>{stage.detail}</p>
                    </div>
                  </article>
                ))}
              </div>

              <div className="trace-summary">
                <div>
                  <BrainCircuit size={17} />
                  <span>Reasoning voices<strong>{assessment.trace.reasoning_candidates}</strong></span>
                </div>
                <div>
                  <GitBranch size={17} />
                  <span>Model tokens<strong>
                    {(assessment.trace.input_tokens + assessment.trace.output_tokens).toLocaleString()}
                  </strong></span>
                </div>
                <div>
                  <Workflow size={17} />
                  <span>Gated tool calls<strong>
                    {Object.values(assessment.trace.tool_calls).reduce((sum, count) => sum + count, 0)}
                  </strong></span>
                </div>
              </div>
            </div>
          )}
        </div>

        <footer className="critic-footer">
          <ShieldCheck size={17} aria-hidden="true" />
          <div>
            <strong>Independent critic verdict</strong>
            <span>{assessment.critic_verdict}</span>
          </div>
        </footer>
      </div>
    </section>
  )
}

function CheckIcon({ status }: { status: string }) {
  const passed = status === 'passed' || status === 'complete' || status === 'pass'
  return passed ? <BadgeCheck size={16} /> : <ShieldCheck size={16} />
}

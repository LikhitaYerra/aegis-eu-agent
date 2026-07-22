export type AssessmentSections = {
  evidence: string
  analysis: string
  conclusion: string
  confidence: string
}

export type AssessmentSource = {
  title: string
  source: string
  jurisdiction: string
  score: number
  excerpt: string
}

export type TraceStage = {
  layer: string
  label: string
  method: string
  status: string
  detail: string
}

export type RunTrace = {
  prompt_hash: string
  reasoning_candidates: number
  input_tokens: number
  output_tokens: number
  tool_calls: Record<string, number>
  stages: TraceStage[]
}

export type RagasMetrics = {
  question_count: number
  context_recall: number
  context_precision: number
  faithfulness: number
  answer_relevancy: number
}

export type Assessment = {
  question: string
  answer: string
  sections: AssessmentSections
  critic_verdict: string
  critic_status: 'PASS' | 'REVISE'
  latency_seconds: number
  estimated_cost_usd: number
  reserved_tokens: number
  token_limit: number
  mode: string
  sources: AssessmentSource[]
  trace: RunTrace
  ragas_metrics: RagasMetrics | null
}

type ApiError = {
  detail?: string
}

export async function assess(question: string, signal?: AbortSignal): Promise<Assessment> {
  const response = await fetch('/api/assess', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
    signal,
  })

  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as ApiError
    throw new Error(payload.detail || `Assessment failed with status ${response.status}.`)
  }

  return response.json() as Promise<Assessment>
}

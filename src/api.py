"""FastAPI transport for the Aegis EU governance research agent."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agent import AGENT_VERSION, GovernanceAgent
from guardrails import SecurityError
from reasoning import SYSTEM_PROMPT_HASH


logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"


class AssessRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4_000)


class SourceResponse(BaseModel):
    title: str
    source: str
    jurisdiction: str
    score: float
    excerpt: str


class SectionsResponse(BaseModel):
    evidence: str
    analysis: str
    conclusion: str
    confidence: str


class TraceStageResponse(BaseModel):
    layer: str
    label: str
    method: str
    status: str
    detail: str


class RunTraceResponse(BaseModel):
    prompt_hash: str
    reasoning_candidates: int
    input_tokens: int
    output_tokens: int
    tool_calls: dict[str, int]
    stages: list[TraceStageResponse]


class RagasMetricsResponse(BaseModel):
    question_count: int
    context_recall: float
    context_precision: float
    faithfulness: float
    answer_relevancy: float


class AssessResponse(BaseModel):
    question: str
    answer: str
    sections: SectionsResponse
    critic_verdict: str
    critic_status: str
    latency_seconds: float
    estimated_cost_usd: float
    reserved_tokens: int
    token_limit: int
    mode: str
    sources: list[SourceResponse]
    trace: RunTraceResponse
    ragas_metrics: RagasMetricsResponse | None


class HealthResponse(BaseModel):
    status: str
    version: str
    mode: str


def load_ragas_metrics() -> RagasMetricsResponse | None:
    """Load the saved final evaluation benchmark for transparent UI display."""
    results_path = PROJECT_ROOT / "evaluation_results.json"
    try:
        payload = json.loads(results_path.read_text(encoding="utf-8"))
        final = payload["ragas"]["final"]
        return RagasMetricsResponse(
            question_count=int(payload["question_count"]),
            context_recall=float(final["context_recall"]),
            context_precision=float(final["context_precision"]),
            faithfulness=float(final["faithfulness"]),
            answer_relevancy=float(final["answer_relevancy"]),
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        logger.warning("RAGAS evaluation results are unavailable", exc_info=True)
        return None


def split_answer(answer: str) -> SectionsResponse:
    """Split the required four-heading response into frontend-ready fields."""
    headings = ("EVIDENCE", "ANALYSIS", "CONCLUSION", "CONFIDENCE")
    sections: dict[str, str] = {}
    current: str | None = None
    lines: list[str] = []
    for line in answer.splitlines():
        candidate = line.strip().rstrip(":").upper()
        if candidate in headings:
            if current is not None:
                sections[current] = "\n".join(lines).strip()
            current = candidate
            lines = []
        elif current is not None:
            lines.append(line)
    if current is not None:
        sections[current] = "\n".join(lines).strip()
    return SectionsResponse(
        evidence=sections.get("EVIDENCE", ""),
        analysis=sections.get("ANALYSIS", ""),
        conclusion=sections.get("CONCLUSION", answer),
        confidence=sections.get("CONFIDENCE", "LOW — confidence section was not returned."),
    )


def clean_excerpt(text: str) -> str:
    """Remove corpus front matter before returning evidence to the browser."""
    stripped = text.strip()
    if stripped.startswith("---"):
        closing = stripped.find("\n---", 3)
        if closing != -1:
            stripped = stripped[closing + 4 :].strip()
    return stripped


def serialize_run(
    agent: GovernanceAgent,
    question: str,
    before_cost: float,
) -> AssessResponse:
    result = agent.run(question)
    critic_status = result.critic_verdict.partition(":")[0].strip().upper()
    safe_critic_status = critic_status if critic_status in {"PASS", "REVISE"} else "REVISE"
    source_count = len(agent.last_results)
    return AssessResponse(
        question=question,
        answer=result.answer,
        sections=split_answer(result.answer),
        critic_verdict=result.critic_verdict,
        critic_status=safe_critic_status,
        latency_seconds=agent.last_latency_seconds,
        estimated_cost_usd=max(0.0, agent.estimated_cost_usd - before_cost),
        reserved_tokens=agent.budget.used,
        token_limit=agent.budget.limit,
        mode="deterministic-demo" if agent.demo else agent.model,
        sources=[
            SourceResponse(
                title=item.document.title,
                source=item.document.source,
                jurisdiction=item.document.jurisdiction,
                score=item.score,
                excerpt=clean_excerpt(item.matched_chunk),
            )
            for item in agent.last_results
        ],
        trace=RunTraceResponse(
            prompt_hash=SYSTEM_PROMPT_HASH,
            reasoning_candidates=len(result.candidates),
            input_tokens=agent.input_tokens,
            output_tokens=agent.output_tokens,
            tool_calls=dict(agent.tool_counts),
            stages=[
                TraceStageResponse(
                    layer="Security",
                    label="Security gate",
                    method="L1 input + L2 evidence + L3 output + L4 action",
                    status="passed",
                    detail="Input, retrieved evidence, final output, and tool calls passed policy.",
                ),
                TraceStageResponse(
                    layer="Retrieval",
                    label="Evidence retrieval",
                    method="Parent-child + BM25/dense RRF + cross-encoder",
                    status="complete",
                    detail=f"{source_count} full parent sources survived final reranking.",
                ),
                TraceStageResponse(
                    layer="Reasoning",
                    label="Reasoning ensemble",
                    method="Few-shot CoT + self-consistency",
                    status="complete",
                    detail=f"{len(result.candidates)} independent candidates produced the selected brief.",
                ),
                TraceStageResponse(
                    layer="Operations",
                    label="Production review",
                    method="Prompt versioning + independent critic",
                    status=safe_critic_status.lower(),
                    detail=f"Critic {safe_critic_status}; prompt surface {SYSTEM_PROMPT_HASH}.",
                ),
            ],
        ),
        ragas_metrics=load_ragas_metrics(),
    )


def create_app(
    agent_factory: Callable[[], GovernanceAgent] = GovernanceAgent,
    *,
    serve_frontend: bool = True,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.agent = agent_factory()
        # GovernanceAgent stores per-run output on itself, so serialize access.
        application.state.agent_lock = asyncio.Lock()
        yield

    application = FastAPI(
        title="Aegis EU API",
        version=AGENT_VERSION,
        description="Grounded, guarded EU AI governance research.",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @application.get("/api/health", response_model=HealthResponse)
    async def health(request: Request) -> HealthResponse:
        agent: GovernanceAgent = request.app.state.agent
        return HealthResponse(
            status="ok",
            version=AGENT_VERSION,
            mode="deterministic-demo" if agent.demo else agent.model,
        )

    @application.post("/api/assess", response_model=AssessResponse)
    async def assess(payload: AssessRequest, request: Request) -> AssessResponse:
        question = payload.question.strip()
        if not question:
            raise HTTPException(status_code=422, detail="Question cannot be blank.")
        agent: GovernanceAgent = request.app.state.agent
        lock: asyncio.Lock = request.app.state.agent_lock
        try:
            async with lock:
                before_cost = agent.estimated_cost_usd
                return await run_in_threadpool(serialize_run, agent, question, before_cost)
        except SecurityError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except OSError as error:
            logger.exception("Agent dependency failed")
            raise HTTPException(
                status_code=503,
                detail="A model or retrieval dependency is temporarily unavailable.",
            ) from error
        except Exception as error:
            logger.exception("Unexpected assessment failure")
            raise HTTPException(
                status_code=500,
                detail="The assessment failed safely. Please retry.",
            ) from error

    if serve_frontend and FRONTEND_DIST.is_dir():
        application.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")

    return application


app = create_app()

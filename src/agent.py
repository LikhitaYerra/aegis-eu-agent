"""Command-line AI governance research agent."""

from __future__ import annotations

import argparse
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from dotenv import load_dotenv

from guardrails import SecurityError, TokenBudget, filter_input, gate_action
from reasoning import SynthesisResult, synthesize_with_critic
from retrieval import HybridRetriever, SearchResult, load_documents


AGENT_VERSION = "0.1.0"
DEFAULT_QUESTION = (
    "What EU AI Act obligations should a startup consider before deploying "
    "an AI customer-support chatbot?"
)


class Observation:
    """Small adapter that keeps observability optional and locally runnable."""

    def __init__(self, wrapped: Any = None) -> None:
        self.wrapped = wrapped

    def update(self, **kwargs: Any) -> None:
        if self.wrapped is not None:
            self.wrapped.update(**kwargs)


class Tracer:
    def __init__(self) -> None:
        self.client: Any = None
        if not (
            os.getenv("LANGFUSE_PUBLIC_KEY")
            and os.getenv("LANGFUSE_SECRET_KEY")
        ):
            return
        try:
            from langfuse import Langfuse

            self.client = Langfuse()
        except (ImportError, RuntimeError, ValueError):
            self.client = None

    @contextmanager
    def span(self, name: str, *, kind: str = "span", **metadata: Any) -> Iterator[Observation]:
        if self.client is None:
            yield Observation()
            return
        try:
            with self.client.start_as_current_observation(
                name=name,
                as_type=kind,
                metadata={"agent_version": AGENT_VERSION, **metadata},
            ) as wrapped:
                yield Observation(wrapped)
        except (RuntimeError, ValueError):
            yield Observation()

    def flush(self) -> None:
        if self.client is not None:
            try:
                self.client.flush()
            except RuntimeError:
                pass


class GovernanceAgent:
    """Orchestrate guarded retrieval, self-consistent synthesis, and critique."""

    def __init__(self, *, demo: bool = False) -> None:
        project_root = Path(__file__).resolve().parents[1]
        load_dotenv(project_root / ".env")
        self.demo = demo or not bool(os.getenv("OPENAI_API_KEY"))
        self.model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        self.tracer = Tracer()
        self.retriever = HybridRetriever(load_documents(project_root / "data"))
        self.budget = TokenBudget(limit=int(os.getenv("TOKEN_BUDGET", "12000")))
        self._openai_client: Any = None
        self.input_tokens = 0
        self.output_tokens = 0
        self.tool_counts = {
            "search_regulations": 0,
            "assess_ai_system_risk": 0,
        }
        self.last_latency_seconds = 0.0

    @property
    def estimated_cost_usd(self) -> float:
        """Estimate standard API cost using verified July 2026 model rates."""
        input_rate = float(os.getenv("OPENAI_INPUT_COST_PER_1M", "0.40"))
        output_rate = float(os.getenv("OPENAI_OUTPUT_COST_PER_1M", "1.60"))
        return (
            self.input_tokens * input_rate + self.output_tokens * output_rate
        ) / 1_000_000

    def _model_call(self, system_prompt: str, user_prompt: str, max_tokens: int) -> str:
        with self.tracer.span(
            "llm.call",
            kind="generation",
            model=self.model if not self.demo else "deterministic-demo",
        ) as observation:
            if self.demo:
                if "compact JSON" in system_prompt:
                    output = json.dumps(
                        {
                            "verdict": "PASS",
                            "issues": [],
                            "suggested_fix": "No changes required in demo mode.",
                        }
                    )
                else:
                    output = (
                        "EVIDENCE:\n"
                        "1. People interacting directly with an AI system generally require "
                        "notification unless the AI interaction is obvious [S1].\n"
                        "2. Risk classification depends on the system's intended purpose and "
                        "whether it falls into a prohibited or high-risk use category [S2].\n"
                        "ANALYSIS:\n"
                        "A customer-support chatbot is an interactive AI system. The supplied "
                        "evidence supports a disclosure duty; it does not establish that ordinary "
                        "support use is high-risk. Personal-data processing may create separate "
                        "GDPR duties.\n"
                        "CONCLUSION:\n"
                        "Disclose the AI interaction, document the intended purpose, assess the "
                        "actual features against prohibited/high-risk categories, and obtain legal "
                        "review before deployment. This is preliminary research, not legal advice.\n"
                        "CONFIDENCE:\n"
                        "MEDIUM — the use case lacks details about data, users, and decision effects."
                    )
            else:
                if self._openai_client is None:
                    from openai import OpenAI

                    self._openai_client = OpenAI()
                response = self._openai_client.responses.create(
                    model=self.model,
                    instructions=system_prompt,
                    input=user_prompt,
                    max_output_tokens=max_tokens,
                )
                output = response.output_text
                if response.usage is not None:
                    self.input_tokens += response.usage.input_tokens
                    self.output_tokens += response.usage.output_tokens
            observation.update(output=output)
            return output

    def _retrieve(self, question: str) -> list[SearchResult]:
        arguments = {"query": question, "top_k": 5}
        gate_action("search_regulations", arguments)
        self.tool_counts["search_regulations"] += 1
        with self.tracer.span(
            "tool.search_regulations",
            kind="tool",
            query=question,
        ) as observation:
            results = self.retriever.search(question, top_k=5)
            observation.update(
                output={
                    "result_count": len(results),
                    "sources": [result.document.source for result in results],
                }
            )
            return results

    def _assess_risk_evidence(self, question: str) -> list[SearchResult]:
        arguments = {"system_description": question, "jurisdiction": "EU"}
        gate_action("assess_ai_system_risk", arguments)
        self.tool_counts["assess_ai_system_risk"] += 1
        with self.tracer.span(
            "tool.assess_ai_system_risk",
            kind="tool",
            jurisdiction="EU",
        ) as observation:
            results = self.retriever.search(
                f"EU AI Act prohibited high-risk transparency obligations {question}",
                top_k=3,
            )
            observation.update(
                output={
                    "result_count": len(results),
                    "sources": [result.document.source for result in results],
                }
            )
            return results

    def run(self, question: str) -> SynthesisResult:
        safe_question = filter_input(question)
        self.budget.used = 0
        self.budget.triggered = False
        started = time.perf_counter()
        with self.tracer.span(
            "agent.run",
            kind="agent",
            question=safe_question,
            demo=self.demo,
        ) as observation:
            retrieved = self._retrieve(safe_question) + self._assess_risk_evidence(safe_question)
            results = list({result.document.id: result for result in retrieved}.values())
            result = synthesize_with_critic(
                safe_question,
                results,
                self._model_call,
                self.budget,
                k=3,
            )
            observation.update(
                output={
                    "critic": result.critic_verdict,
                    "latency_seconds": round(time.perf_counter() - started, 3),
                    "reserved_tokens": self.budget.used,
                }
            )
        self.last_latency_seconds = time.perf_counter() - started
        self.tracer.flush()
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description="AI governance compliance research agent")
    parser.add_argument("question", nargs="?", default=DEFAULT_QUESTION)
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Use deterministic local synthesis instead of an external LLM.",
    )
    args = parser.parse_args()
    try:
        agent = GovernanceAgent(demo=args.demo)
        result = agent.run(args.question)
    except (SecurityError, ValueError, OSError) as error:
        print(f"Request blocked or failed safely: {error}")
        return 1
    print("\nAI GOVERNANCE RESEARCH OUTPUT\n")
    print(result.answer)
    print(f"\nCRITIC VERDICT: {result.critic_verdict}")
    print(f"MODE: {'demo' if agent.demo else agent.model}")
    print(f"TOKEN BUDGET RESERVED: {agent.budget.used}/{agent.budget.limit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Few-shot reasoning, self-consistency, and critic prompts."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from typing import Callable, Sequence

from guardrails import TokenBudget
from retrieval import SearchResult


SYNTHESIS_SYSTEM_PROMPT = """You are an EU AI governance research analyst.
Use only the supplied evidence. If evidence is insufficient, say so explicitly.
Produce exactly these sections:
EVIDENCE: numbered source-specific facts with citations such as [S1].
ANALYSIS: concise application of those facts to the question; separate facts from assumptions.
CONCLUSION: the direct answer and concrete next actions.
CONFIDENCE: HIGH, MEDIUM, or LOW, followed by one sentence explaining uncertainty.

Example:
Question: Must a customer-support chatbot disclose that it is AI?
Evidence: [S1] Article 50 says people must be informed when directly interacting with AI unless obvious.
Answer:
EVIDENCE:
1. Direct AI interaction requires disclosure unless obvious [S1].
ANALYSIS:
The chatbot directly interacts with customers; no exception is established by the evidence.
CONCLUSION:
Provide a clear AI disclosure at the start of the conversation.
CONFIDENCE:
HIGH — the supplied rule maps directly to the described use.
"""

CRITIC_SYSTEM_PROMPT = """You are a strict compliance-output critic.
Check whether every material claim is supported by a supplied source, the four required headings
are present, uncertainty is honest, and the conclusion does not present legal information as
legal advice. Return compact JSON with keys verdict (PASS or REVISE), issues (list), and
suggested_fix (string). Do not add facts."""

# Hash the complete prompt surface so behavior changes remain traceable.
SYSTEM_PROMPT_HASH = hashlib.sha256(
    f"{SYNTHESIS_SYSTEM_PROMPT}\n{CRITIC_SYSTEM_PROMPT}".encode("utf-8")
).hexdigest()[:12]


@dataclass(frozen=True)
class SynthesisResult:
    answer: str
    critic_verdict: str
    candidates: tuple[str, ...]


ModelCall = Callable[[str, str, int], str]


def assemble_context(results: Sequence[SearchResult], max_chars: int = 12_000) -> str:
    """Assemble parent documents after reranking while preserving source labels."""
    sections: list[str] = []
    length = 0
    for index, result in enumerate(results, start=1):
        section = (
            f"[S{index}] {result.document.title}\n"
            f"Source: {result.document.source}\n"
            f"{result.document.text.strip()}\n"
        )
        if length + len(section) > max_chars:
            break
        sections.append(section)
        length += len(section)
    return "\n".join(sections)


def _confidence(candidate: str) -> str:
    match = re.search(r"CONFIDENCE:\s*(HIGH|MEDIUM|LOW)", candidate, re.I)
    return match.group(1).upper() if match else "LOW"


def select_consistent_candidate(candidates: Sequence[str]) -> str:
    """Select a representative answer from k candidates using confidence agreement."""
    if not candidates:
        raise ValueError("At least one candidate is required.")
    confidence_counts = Counter(_confidence(candidate) for candidate in candidates)
    majority_confidence = confidence_counts.most_common(1)[0][0]
    eligible = [candidate for candidate in candidates if _confidence(candidate) == majority_confidence]
    # Prefer the median-length answer to avoid both terse and meandering outliers.
    return sorted(eligible, key=len)[len(eligible) // 2]


def parse_critic_response(raw_response: str) -> str:
    """Parse strict or Markdown-wrapped critic JSON and fail closed."""
    candidate = raw_response.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate, flags=re.I)
        candidate = re.sub(r"\s*```$", "", candidate)

    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end <= start:
            return "REVISE: Critic returned invalid JSON."
        try:
            payload = json.loads(candidate[start : end + 1])
        except json.JSONDecodeError:
            return "REVISE: Critic returned invalid JSON."

    if not isinstance(payload, dict):
        return "REVISE: Critic response was not a JSON object."
    verdict = str(payload.get("verdict", "REVISE")).strip().upper()
    if verdict not in {"PASS", "REVISE"}:
        return "REVISE: Critic returned an invalid verdict."
    suggested_fix = str(payload.get("suggested_fix", "")).strip()
    if not suggested_fix:
        suggested_fix = "No changes required." if verdict == "PASS" else "Review critic issues."
    return f"{verdict}: {suggested_fix}"


def synthesize_with_critic(
    question: str,
    results: Sequence[SearchResult],
    model_call: ModelCall,
    budget: TokenBudget,
    *,
    k: int = 3,
) -> SynthesisResult:
    """Run self-consistency k times, select a candidate, and obtain a critic verdict."""
    if k < 3:
        raise ValueError("Self-consistency requires k >= 3.")
    context = assemble_context(results)
    user_prompt = f"Question:\n{question}\n\nEvidence:\n{context}"
    candidates: list[str] = []
    for attempt in range(k):
        budget.reserve(1_500)
        candidates.append(
            model_call(
                SYNTHESIS_SYSTEM_PROMPT,
                f"{user_prompt}\n\nIndependent synthesis attempt: {attempt + 1}",
                900,
            )
        )
    selected = select_consistent_candidate(candidates)
    budget.reserve(700)
    critic_prompt = (
        f"Question:\n{question}\n\nEvidence:\n{context}\n\nCandidate answer:\n{selected}"
    )
    critic_raw = model_call(CRITIC_SYSTEM_PROMPT, critic_prompt, 400)
    verdict = parse_critic_response(critic_raw)
    return SynthesisResult(selected, verdict, tuple(candidates))

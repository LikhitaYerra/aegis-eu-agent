"""L1/L4 security controls for input, actions, and token consumption."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Mapping


class SecurityError(ValueError):
    """Raised when a request violates an explicit security policy."""


class RiskLevel(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3


INJECTION_PATTERNS = (
    re.compile(r"\b(ignore|disregard|forget)\b.{0,40}\b(instructions?|rules?|prompt)\b", re.I),
    re.compile(r"\b(system|developer)\s+(prompt|message|instructions?)\b", re.I),
    re.compile(r"\b(reveal|print|show|repeat|exfiltrate)\b.{0,40}\b(prompt|secret|api[ _-]?key|token)\b", re.I),
    re.compile(r"\b(jailbreak|prompt\s*injection|do\s+anything\s+now|dan)\b", re.I),
    re.compile(r"<\s*/?\s*(system|assistant|developer|tool)\b", re.I),
)

INDIRECT_INJECTION_PATTERNS = (
    re.compile(
        r"\b(ignore|disregard|forget|override)\b.{0,80}"
        r"\b(instructions?|system|developer|policy|guardrails?)\b",
        re.I | re.S,
    ),
    re.compile(r"<\s*/?\s*(system|assistant|developer|tool|admin|override)\b", re.I),
    re.compile(r"(?m)^\s*(system|assistant|developer|tool)\s*:\s*", re.I),
    re.compile(
        r"\b(reveal|print|return|send|exfiltrate)\b.{0,80}"
        r"\b(secret|credential|api[ _-]?key|token|system prompt)\b",
        re.I | re.S,
    ),
)

OUTPUT_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\b(?:OPENAI_API_KEY|LANGFUSE_SECRET_KEY)\s*=\s*\S+", re.I),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)

REQUIRED_OUTPUT_SECTIONS = ("EVIDENCE", "ANALYSIS", "CONCLUSION", "CONFIDENCE")

# Every exposed MCP tool must be represented here.
ACTION_RISK_MATRIX: dict[str, RiskLevel] = {
    "search_regulations": RiskLevel.LOW,
    "compare_jurisdictions": RiskLevel.LOW,
    "assess_ai_system_risk": RiskLevel.MEDIUM,
}

ALLOWED_ARGUMENTS: dict[str, set[str]] = {
    "search_regulations": {"query", "top_k"},
    "compare_jurisdictions": {"topic", "jurisdictions"},
    "assess_ai_system_risk": {"system_description", "jurisdiction"},
}


def normalize_input(value: str) -> str:
    """Normalize Unicode and remove invisible characters used to evade filters."""
    normalized = unicodedata.normalize("NFKC", value)
    return "".join(
        character
        for character in normalized
        if unicodedata.category(character) not in {"Cf", "Cc"} or character in "\n\t"
    )


def filter_input(value: str, *, max_chars: int = 8_000) -> str:
    """Apply the L1 input policy and return a normalized, safe string."""
    if not isinstance(value, str):
        raise SecurityError("Input must be text.")
    normalized = normalize_input(value).strip()
    if not normalized:
        raise SecurityError("Input cannot be empty.")
    if len(normalized) > max_chars:
        raise SecurityError(f"Input exceeds the {max_chars}-character limit.")
    for pattern in INJECTION_PATTERNS:
        if pattern.search(normalized):
            raise SecurityError("Potential prompt injection detected by the L1 filter.")
    return normalized


def filter_retrieved_content(
    value: str,
    *,
    source: str = "retrieved content",
    max_chars: int = 50_000,
) -> str:
    """Apply the L2 policy to untrusted evidence before model context assembly."""
    if not isinstance(value, str):
        raise SecurityError("Retrieved evidence must be text.")
    normalized = normalize_input(value).strip()
    if not normalized:
        raise SecurityError(f"L2 rejected empty evidence from {source}.")
    if len(normalized) > max_chars:
        raise SecurityError(f"L2 evidence from {source} exceeds {max_chars} characters.")
    for pattern in INDIRECT_INJECTION_PATTERNS:
        if pattern.search(normalized):
            raise SecurityError(
                f"Potential indirect prompt injection detected by the L2 evidence filter in {source}."
            )
    return normalized


def validate_output(
    answer: str,
    *,
    source_count: int,
    critic_verdict: str,
    max_chars: int = 40_000,
) -> str:
    """Apply deterministic L3 structure, citation, leakage, and critic checks."""
    if not isinstance(answer, str):
        raise SecurityError("L3 requires a text answer.")
    normalized = normalize_input(answer).strip()
    if not normalized:
        raise SecurityError("L3 rejected an empty model response.")
    if len(normalized) > max_chars:
        raise SecurityError(f"L3 output exceeds the {max_chars}-character limit.")

    missing = [
        section
        for section in REQUIRED_OUTPUT_SECTIONS
        if not re.search(rf"(?m)^\s*{section}\s*:", normalized, re.I)
    ]
    if missing:
        raise SecurityError(f"L3 output is missing required sections: {missing}.")
    if not re.search(r"(?im)^\s*CONFIDENCE\s*:\s*(?:\n\s*)?(HIGH|MEDIUM|LOW)\b", normalized):
        raise SecurityError("L3 output has an invalid confidence label.")

    citations = [int(value) for value in re.findall(r"\[S(\d+)\]", normalized, re.I)]
    if not citations:
        raise SecurityError("L3 output contains no evidence citations.")
    if source_count < 1 or any(index < 1 or index > source_count for index in citations):
        raise SecurityError("L3 output cites a source outside the supplied evidence set.")

    for pattern in OUTPUT_SECRET_PATTERNS:
        if pattern.search(normalized):
            raise SecurityError("L3 blocked potential credential or private-key disclosure.")

    status = critic_verdict.partition(":")[0].strip().upper()
    if status not in {"PASS", "REVISE"}:
        raise SecurityError("L3 received an invalid critic verdict.")
    return normalized


def gate_action(
    tool_name: str,
    arguments: Mapping[str, Any],
    *,
    max_risk: RiskLevel = RiskLevel.MEDIUM,
) -> None:
    """Apply the L4 allowlist, argument, and risk policy before a tool call."""
    if tool_name not in ACTION_RISK_MATRIX:
        raise SecurityError(f"Tool '{tool_name}' is not allowlisted.")
    if ACTION_RISK_MATRIX[tool_name] > max_risk:
        raise SecurityError(f"Tool '{tool_name}' exceeds the permitted action risk.")
    unexpected = set(arguments) - ALLOWED_ARGUMENTS[tool_name]
    if unexpected:
        raise SecurityError(f"Unexpected arguments for '{tool_name}': {sorted(unexpected)}")
    for value in arguments.values():
        if isinstance(value, str):
            filter_input(value, max_chars=4_000)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    filter_input(item, max_chars=200)


@dataclass
class TokenBudget:
    """Track and enforce a per-run token budget across all model calls."""

    limit: int = 12_000
    used: int = 0
    triggered: bool = False

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)

    def reserve(self, tokens: int) -> None:
        if tokens < 0:
            raise ValueError("Token reservation cannot be negative.")
        if self.used + tokens > self.limit:
            self.triggered = True
            raise SecurityError(
                f"Token budget exceeded: requested {tokens}, {self.remaining} remaining."
            )
        self.used += tokens

    def record_usage(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.reserve(prompt_tokens + completion_tokens)

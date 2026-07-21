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

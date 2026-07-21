"""MCP server exposing grounded governance research tools."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from guardrails import SecurityError, filter_input, gate_action
from retrieval import HybridRetriever, load_documents

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as error:  # pragma: no cover - exercised only without installed requirements
    raise SystemExit("Install dependencies with: pip install -r requirements.txt") from error


mcp = FastMCP("AI Governance Research Tools")
_retriever: HybridRetriever | None = None


def get_retriever() -> HybridRetriever:
    global _retriever
    if _retriever is None:
        data_directory = Path(__file__).resolve().parents[1] / "data"
        _retriever = HybridRetriever(load_documents(data_directory))
    return _retriever


def set_retriever(retriever: HybridRetriever) -> None:
    """Share an initialized retriever with an in-process MCP client."""
    global _retriever
    _retriever = retriever


def _error(error: Exception) -> str:
    return json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False)


@mcp.tool()
def search_regulations(query: str, top_k: int = 5) -> str:
    """Search the governance corpus with hybrid retrieval and reranking.

    Use when: locating relevant regulatory provisions, duties, or definitions.
    Do NOT use: for definitive legal advice or questions unrelated to AI governance.
    Returns: JSON containing ranked parent documents, sources, excerpts, and scores.
    Example: search_regulations("Article 50 chatbot disclosure", 3)
    """
    try:
        safe_query = filter_input(query)
        arguments: dict[str, Any] = {"query": safe_query, "top_k": top_k}
        gate_action("search_regulations", arguments)
        results = get_retriever().search(safe_query, top_k=int(top_k))
        return json.dumps(
            {
                "ok": True,
                "results": [
                    {
                        "id": result.document.id,
                        "title": result.document.title,
                        "source": result.document.source,
                        "jurisdiction": result.document.jurisdiction,
                        "text": result.document.text,
                        "excerpt": result.matched_chunk,
                        "score": round(result.score, 4),
                    }
                    for result in results
                ],
            },
            ensure_ascii=False,
        )
    except (SecurityError, ValueError, TypeError, OSError) as error:
        return _error(error)


@mcp.tool()
def compare_jurisdictions(topic: str, jurisdictions: list[str]) -> str:
    """Compare evidence for a governance topic across named jurisdictions.

    Use when: a user needs a source-grounded regulatory comparison.
    Do NOT use: if fewer than two jurisdictions are supplied or as a substitute for counsel.
    Returns: JSON grouping the strongest available evidence by jurisdiction.
    Example: compare_jurisdictions("automated hiring", ["EU", "United States"])
    """
    try:
        safe_topic = filter_input(topic)
        if len(jurisdictions) < 2 or len(jurisdictions) > 5:
            raise ValueError("Provide between two and five jurisdictions.")
        safe_jurisdictions = [filter_input(item, max_chars=100) for item in jurisdictions]
        arguments = {"topic": safe_topic, "jurisdictions": safe_jurisdictions}
        gate_action("compare_jurisdictions", arguments)
        results = get_retriever().search(
            f"{safe_topic} {' '.join(safe_jurisdictions)}",
            top_k=min(10, len(safe_jurisdictions) * 3),
        )
        grouped: dict[str, list[dict[str, str]]] = {
            jurisdiction: [] for jurisdiction in safe_jurisdictions
        }
        for result in results:
            for jurisdiction in safe_jurisdictions:
                if result.document.jurisdiction.casefold() == jurisdiction.casefold():
                    grouped[jurisdiction].append(
                        {
                            "title": result.document.title,
                            "source": result.document.source,
                            "evidence": result.matched_chunk,
                        }
                    )
        return json.dumps(
            {
                "ok": True,
                "comparison": grouped,
                "warning": "No entry means the local corpus lacks evidence; it does not mean no law exists.",
            },
            ensure_ascii=False,
        )
    except (SecurityError, ValueError, TypeError, OSError) as error:
        return _error(error)


@mcp.tool()
def assess_ai_system_risk(system_description: str, jurisdiction: str = "EU") -> str:
    """Retrieve evidence relevant to a preliminary AI-system risk assessment.

    Use when: triaging an AI use case before a qualified legal review.
    Do NOT use: to issue a binding classification, approve deployment, or replace legal advice.
    Returns: JSON with relevant provisions and an explicit preliminary-assessment warning.
    Example: assess_ai_system_risk("CV ranking for job applicants", "EU")
    """
    try:
        safe_description = filter_input(system_description, max_chars=4_000)
        safe_jurisdiction = filter_input(jurisdiction, max_chars=100)
        arguments = {
            "system_description": safe_description,
            "jurisdiction": safe_jurisdiction,
        }
        gate_action("assess_ai_system_risk", arguments)
        results = get_retriever().search(
            f"{safe_jurisdiction} AI Act prohibited high-risk transparency obligations "
            f"{safe_description}",
            top_k=3,
        )
        return json.dumps(
            {
                "ok": True,
                "assessment_type": "preliminary research, not legal advice",
                "evidence": [
                    {
                        "id": result.document.id,
                        "title": result.document.title,
                        "source": result.document.source,
                        "jurisdiction": result.document.jurisdiction,
                        "text": result.document.text,
                        "excerpt": result.matched_chunk,
                        "score": round(result.score, 4),
                    }
                    for result in results
                ],
                "next_step": "Have qualified counsel validate the classification and obligations.",
            },
            ensure_ascii=False,
        )
    except (SecurityError, ValueError, TypeError, OSError) as error:
        return _error(error)


if __name__ == "__main__":
    mcp.run(transport="stdio")

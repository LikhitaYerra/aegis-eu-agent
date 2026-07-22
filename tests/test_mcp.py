"""MCP registration and transport-level contract tests."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import mcp_server


class FakeRetriever:
    def search(self, query: str, top_k: int = 5) -> list[object]:
        return []


class FailingRetriever:
    def search(self, query: str, top_k: int = 5) -> list[object]:
        raise RuntimeError("retrieval unavailable")


def test_registers_three_documented_tools() -> None:
    tools = asyncio.run(mcp_server.mcp.list_tools())
    assert {tool.name for tool in tools} == {
        "search_regulations",
        "compare_jurisdictions",
        "assess_ai_system_risk",
    }
    for tool in tools:
        description = tool.description or ""
        assert "Use when:" in description
        assert "Do NOT use:" in description
        assert "Returns:" in description
        assert "Example:" in description


def test_tools_execute_through_mcp_dispatch(monkeypatch) -> None:
    monkeypatch.setattr(mcp_server, "_retriever", FakeRetriever())

    async def call(name: str, arguments: dict[str, object]) -> dict[str, object]:
        content, _ = await mcp_server.mcp.call_tool(name, arguments)
        return json.loads(content[0].text)

    search = asyncio.run(call("search_regulations", {"query": "Article 50", "top_k": 2}))
    compare = asyncio.run(
        call(
            "compare_jurisdictions",
            {"topic": "automated hiring", "jurisdictions": ["EU", "UK"]},
        )
    )
    risk = asyncio.run(
        call(
            "assess_ai_system_risk",
            {"system_description": "CV ranking", "jurisdiction": "EU"},
        )
    )

    assert search == {"ok": True, "results": []}
    assert compare["ok"] is True
    assert set(compare["comparison"]) == {"EU", "UK"}
    assert risk["assessment_type"] == "preliminary research, not legal advice"


def test_all_tools_return_structured_errors(monkeypatch) -> None:
    monkeypatch.setattr(mcp_server, "_retriever", FailingRetriever())

    async def call(name: str, arguments: dict[str, object]) -> dict[str, object]:
        content, _ = await mcp_server.mcp.call_tool(name, arguments)
        return json.loads(content[0].text)

    payloads = [
        asyncio.run(call("search_regulations", {"query": "Article 50", "top_k": 2})),
        asyncio.run(
            call(
                "compare_jurisdictions",
                {"topic": "automated hiring", "jurisdictions": ["EU", "UK"]},
            )
        ),
        asyncio.run(
            call(
                "assess_ai_system_risk",
                {"system_description": "CV ranking", "jurisdiction": "EU"},
            )
        ),
    ]

    assert all(payload["ok"] is False for payload in payloads)
    assert all("retrieval unavailable" in str(payload["error"]) for payload in payloads)

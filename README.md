# Aegis EU — AI Governance Research Agent

Aegis EU helps startup compliance leads perform a preliminary, source-grounded review of an AI
use case. It retrieves relevant EU AI Act and GDPR material, produces three independent
syntheses, selects a consistent answer, and sends the result to a critic before displaying it.
It is a research aid, not legal advice.

## Quick start

Python 3.11 or 3.12 is recommended.

```bash
git clone <your-repository-url>
cd <your-repository-directory>
cp .env.example .env
pip install -r requirements.txt
python src/agent.py
```

The exact command above works without credentials in deterministic demo mode. Add
`OPENAI_API_KEY` to `.env` for model-backed synthesis. The first retrieval run downloads the
pinned dense embedding and cross-encoder models; if model loading is unavailable, the agent
fails over to deterministic lexical scoring rather than crashing.

Ask a custom question:

```bash
python src/agent.py "Does an AI CV-ranking tool qualify as high-risk in the EU?"
```

Run the security suite:

```bash
python -m pytest tests/test_security.py
```

Run the deterministic 10-question retrieval comparison:

```bash
python src/evaluate.py --retrieval-only
```

After adding `OPENAI_API_KEY`, run genuine RAGAS baseline/final scoring plus 10-run cost, latency,
and tool-distribution measurement:

```bash
python src/evaluate.py
```

Both commands write machine-readable results to `evaluation_results.json`.

Start the MCP server over stdio:

```bash
python src/mcp_server.py
```

The server exposes `search_regulations`, `compare_jurisdictions`, and
`assess_ai_system_risk`. Each tool returns structured JSON and converts validation, security,
and retrieval failures into safe error responses.

## Architecture

1. The L1 guardrail normalizes Unicode, rejects injection patterns, and limits input size.
2. Parent-child retrieval ranks child chunks with BM25 and dense similarity, fuses rankings with
   reciprocal rank fusion, reranks candidates with a cross-encoder, and returns full parents.
3. The L4 gate validates every action against a tool risk matrix and argument allowlist.
4. Three evidence-grounded synthesis calls use the required
   EVIDENCE/ANALYSIS/CONCLUSION/CONFIDENCE format.
5. Self-consistency selects the representative candidate, then a critic returns PASS or REVISE.
6. Langfuse records the agent, two tool calls, three synthesis calls, and critic call as separate
   observations, including agent version metadata.

The detailed diagram and component descriptions are in `docs/architecture.md`.

## Configuration

| Variable | Required | Purpose |
|---|---:|---|
| `OPENAI_API_KEY` | No | Enables model-backed synthesis |
| `OPENAI_MODEL` | No | Responses API model; defaults to `gpt-4.1-mini` |
| `LANGFUSE_PUBLIC_KEY` | No | Langfuse project key |
| `LANGFUSE_SECRET_KEY` | No | Langfuse secret |
| `LANGFUSE_HOST` | No | Langfuse host |
| `TOKEN_BUDGET` | No | Per-run application budget; defaults to 12,000 |

## Security and scope

Outputs are preliminary research and must be validated by qualified counsel. The corpus is not
guaranteed to be complete or current. Tool actions are read-only. Never place real API keys in
source files or commit `.env`.

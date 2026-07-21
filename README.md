# Aegis EU — AI Governance Research Agent

Aegis EU helps startup compliance leads perform a preliminary, source-grounded review of an AI
use case. It retrieves relevant EU AI Act and GDPR material, produces three independent
syntheses, selects a consistent answer, and sends the result to a critic before displaying it.
It is a research aid, not legal advice.

## Quick start

Python 3.11 or 3.12 is recommended.

```bash
git clone https://github.com/LikhitaYerra/aegis-eu-agent.git
cd aegis-eu-agent
cp .env.example .env
pip install -r requirements.txt
python src/agent.py
```

The exact command above works without credentials in deterministic demo mode. Add
`OPENAI_API_KEY` to `.env` for model-backed synthesis. The first retrieval run downloads the
pinned dense embedding and cross-encoder models; if model loading is unavailable, the agent
fails over to deterministic lexical scoring rather than crashing.
On systems where Python is installed as `python3`, use `python3` in the same commands.

Ask a custom question:

```bash
python src/agent.py "Does an AI CV-ranking tool qualify as high-risk in the EU?"
```

Launch the full-stack web interface in two terminals:

```bash
# Terminal 1 — API (from the project root)
uvicorn api:app --app-dir src --reload

# Terminal 2 — React development server
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Vite proxies `/api` requests to FastAPI on port 8000. The
interface provides guided scenarios, structured evidence/analysis/conclusion views, a visible
critic verdict, run cost and latency, and official-source inspection.

For a single-server production-style run, build the frontend and let FastAPI serve it:

```bash
cd frontend && npm install && npm run build && cd ..
uvicorn api:app --app-dir src
```

Then open `http://localhost:8000`. The command-line interface remains available at the unchanged
`python src/agent.py` entry point.

Run the complete security, MCP, and API test suite:

```bash
python -m pytest
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

1. The React/Vite interface sends typed assessment requests to a lifespan-cached FastAPI agent.
2. FastAPI serializes access to mutable agent run state and maps guardrail failures to safe 4xx
   responses.
3. The L1 guardrail normalizes Unicode, rejects injection patterns, and limits input size.
4. Parent-child retrieval ranks child chunks with BM25 and dense similarity, fuses rankings with
   reciprocal rank fusion, reranks candidates with a cross-encoder, and returns full parents.
5. The agent invokes registered FastMCP tools; each action then passes the L4 risk matrix and
   argument allowlist.
6. Three evidence-grounded synthesis calls use the required
   EVIDENCE/ANALYSIS/CONCLUSION/CONFIDENCE format.
7. Self-consistency selects the representative candidate, then a critic returns PASS or REVISE.
8. Langfuse records the agent, two tool calls, three synthesis calls, and critic call as separate
   observations, including agent version metadata.

The detailed diagram and component descriptions are in `docs/architecture.md`.

## Configuration

| Variable | Required | Purpose |
|---|---:|---|
| `OPENAI_API_KEY` | No | Enables model-backed synthesis |
| `OPENAI_MODEL` | No | Responses API model; defaults to `gpt-4.1-mini` |
| `OPENAI_INPUT_COST_PER_1M` | No | Input-token price used for run cost estimates |
| `OPENAI_OUTPUT_COST_PER_1M` | No | Output-token price used for run cost estimates |
| `LANGFUSE_PUBLIC_KEY` | No | Langfuse project key |
| `LANGFUSE_SECRET_KEY` | No | Langfuse secret |
| `LANGFUSE_HOST` | No | Langfuse host |
| `TOKEN_BUDGET` | No | Per-run application budget; defaults to 12,000 |

## Security and scope

Outputs are preliminary research and must be validated by qualified counsel. The corpus is not
guaranteed to be complete or current. Tool actions are read-only. Never place real API keys in
source files or commit `.env`.

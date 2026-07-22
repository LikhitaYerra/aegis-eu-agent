# Architecture

## Complete system schema

```mermaid
flowchart TB
    USER["Compliance researcher"] --> FE["React + Vite web interface"]
    FE -->|"POST /api/assess"| API["FastAPI API"]
    API --> LOCK["Per-agent concurrency lock"]

    subgraph AGENT1["Agent 1 — Governance Research Orchestrator"]
        direction TB
        LOCK --> L1["L1 input guardrail<br/>Unicode normalization · size limit<br/>direct-injection detection"]
        L1 --> BUDGET["TokenBudget<br/>12,000-token run ceiling"]
        BUDGET --> ORCH["Run orchestrator"]
        ORCH --> MCP["FastMCP dispatch"]

        subgraph TOOLS["MCP tool boundary"]
            direction LR
            MCP --> L4["L4 action guardrail<br/>tool allowlist · risk matrix<br/>argument validation"]
            L4 --> T1["search_regulations"]
            L4 --> T2["assess_ai_system_risk"]
            L4 -.->|"Available on demand"| T3["compare_jurisdictions"]
        end

        subgraph RAG["Retrieval-augmented generation"]
            direction TB
            CORPUS[("EU governance corpus<br/>official and curated sources")] --> LOAD["Document loader"]
            LOAD --> PARENTS["Full parent documents"]
            PARENTS --> CHUNKS["Overlapping child chunks"]
            T1 --> QUERY["Search query"]
            T2 --> QUERY
            T3 -.-> QUERY
            QUERY --> BM25["BM25 lexical ranking"]
            QUERY --> DENSE["Dense semantic ranking"]
            CHUNKS --> BM25
            CHUNKS --> DENSE
            BM25 --> RRF["Reciprocal Rank Fusion"]
            DENSE --> RRF
            RRF --> RERANK["Cross-encoder reranking"]
            RERANK --> RESTORE["Restore full parent context"]
            PARENTS --> RESTORE
            RESTORE --> L2["L2 evidence guardrail<br/>indirect-injection detection<br/>role-tag and exfiltration blocking"]
            L2 --> CONTEXT["Bounded trusted evidence context"]
        end

        CONTEXT --> PROMPT["Few-shot structured reasoning prompt"]
        PROMPT --> S1["Synthesis candidate 1"]
        PROMPT --> S2["Synthesis candidate 2"]
        PROMPT --> S3["Synthesis candidate 3"]
        S1 --> SELECT["Self-consistency selector<br/>confidence majority + median length"]
        S2 --> SELECT
        S3 --> SELECT
    end

    subgraph AGENT2["Agent 2 — Independent Critic"]
        direction TB
        SELECT --> CRITIC["Critic review<br/>grounding · completeness<br/>uncertainty · scope"]
        CRITIC --> VERDICT{"PASS or REVISE"}
    end

    VERDICT --> L3["L3 output guardrail<br/>required sections · citation bounds<br/>confidence enum · secret-leak detection"]
    L3 --> RESULT["Structured compliance brief<br/>Evidence · Analysis · Conclusion<br/>Confidence · Sources · Critic verdict"]
    RESULT --> TRACE["API response<br/>answer + sources + trace<br/>latency + tokens + estimated cost"]
    TRACE --> API
    API --> FE

    subgraph OBS["Observability and evaluation"]
        direction LR
        LF["Langfuse traces<br/>agent version + prompt hash"]
        METRICS["Runtime metrics<br/>latency · cost · tokens · tool calls"]
        EVAL["RAGAS evaluation<br/>context recall · precision<br/>faithfulness · relevance"]
        TESTS["Regression suite<br/>security · MCP · API contracts"]
    end

    ORCH -.->|"agent.run span"| LF
    T1 -.->|"tool span"| LF
    T2 -.->|"tool span"| LF
    S1 -.->|"generation span"| LF
    S2 -.->|"generation span"| LF
    S3 -.->|"generation span"| LF
    CRITIC -.->|"critic.review span"| LF
    TRACE -.-> METRICS
    RESULT -.-> EVAL
    L1 -.-> TESTS
    L2 -.-> TESTS
    L3 -.-> TESTS
    L4 -.-> TESTS

    classDef actor fill:#e8f1ff,stroke:#2563eb,color:#172033;
    classDef agent fill:#f3ecff,stroke:#7c3aed,color:#241638;
    classDef guard fill:#fff2d8,stroke:#d97706,color:#3b2405;
    classDef tool fill:#e9f8ef,stroke:#15803d,color:#11351d;
    classDef data fill:#edf7f7,stroke:#0f766e,color:#123838;
    classDef output fill:#e8f1ff,stroke:#2563eb,color:#172033;

    class USER,FE,API,LOCK actor;
    class ORCH,PROMPT,S1,S2,S3,SELECT,CRITIC,VERDICT agent;
    class L1,L2,L3,L4,BUDGET guard;
    class MCP,T1,T2,T3 tool;
    class CORPUS,LOAD,PARENTS,CHUNKS,QUERY,BM25,DENSE,RRF,RERANK,RESTORE,CONTEXT data;
    class RESULT,TRACE output;
```

## Components

- `frontend/` provides the typed React/Vite interface, guided scenarios, progressive run state,
  responsive result workspace, critic verdict, run measurements, and official-source inspection.
- `src/api.py` exposes `GET /api/health` and `POST /api/assess`. Its lifespan initializes one
  agent, and an async lock serializes runs because token, cost, and retrieval measurements are
  mutable per-agent state. Guardrail and validation errors become safe client responses. When
  `frontend/dist` exists, the same process serves the production frontend.
- `src/agent.py` owns the command-line entry point and run lifecycle. It creates a top-level
  observation, invokes two registered MCP tools, performs synthesis, and prints the critic
  verdict and AI-use disclosure.
- `src/retrieval.py` splits source documents into overlapping child chunks. BM25 and dense
  rankings are fused with RRF. A cross-encoder reranks the fused shortlist, after which the full
  parent document is supplied as context.
- `src/guardrails.py` implements the L1 input filter, L2 evidence filter, L3 deterministic output
  validator, L4 action gate, shared risk matrix, argument allowlists, and hard `TokenBudget`.
- `src/reasoning.py` contains the few-shot structured prompt, context assembly,
  self-consistency (`k=3`), and independent critic.
- `src/mcp_server.py` exposes three read-only tools over MCP stdio with complete usage contracts
  and safe JSON error handling.

## Web deployment

During development, Vite runs on port 5173 and proxies `/api` to Uvicorn on port 8000. For a
single-process deployment, `npm run build` writes static assets to `frontend/dist`; FastAPI
mounts that directory after registering API routes. The transport does not replace or change
the required `python src/agent.py` grading entry point.

## Non-obvious design decision

The retriever ranks small child chunks but sends their full parent documents to synthesis. Small
chunks improve matching precision, especially for article numbers and narrow obligations, while
parents preserve the surrounding qualifications and exceptions needed for legal research. The
trade-off is higher context use. `assemble_context` therefore imposes a character ceiling, and
`TokenBudget` independently limits total model-call allocation.

## Observability

When Langfuse is configured, every run emits an `agent.run` span, two tool spans, three synthesis
generations, and one critic generation. Each observation includes agent version `0.1.0` and the
system-prompt hash. A production alert should trigger when the critic REVISE rate exceeds 20%
over 30 minutes or when p95 run latency exceeds 30 seconds; either condition indicates source
drift, model degradation, or retrieval/model-service failure requiring review.

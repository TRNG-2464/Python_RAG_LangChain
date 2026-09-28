# DevMate

**DevMate** is an internal engineering assistant for **Northbeam**, a
fictional software company. Engineers can browse and search
Northbeam's runbooks, wikis, postmortems, and onboarding guides;
track operational tickets; pull team-workload and document-ownership
analytics; and — the core of the project — ask plain-language
questions and get answers grounded in Northbeam's own documents, with
citations back to the source material and memory of the conversation
so far.

This is a training project built incrementally, one day at a time, as
part of a Python / FastAPI / LangChain course. Everything below
describes the project in its final, complete state — no more new code
is planned for it; later course material is taught as discussion
against this app exactly as it stands.

## Features

- **A plain-Python OOP domain model** — `Document`, `Ticket`,
  `Comment`, and `User` classes with no framework dependency of their
  own.
- **File-based ingestion** — documents loaded from a folder of Markdown
  and text files, tickets loaded from a CSV, both with per-record error
  handling so one bad file or row doesn't take down the whole batch.
- **A REST API** (FastAPI + Pydantic v2) — routers, dependency
  injection, request logging middleware, and an `X-API-Key` header
  required on every protected route.
- **pandas/numpy analytics** — team workload distribution and document
  ownership/staleness reports computed directly from the in-memory
  data, no database involved.
- **Retrieval-augmented Q&A** (LangChain + Ollama + Chroma) — the
  document corpus is chunked, embedded, and persisted to a local
  vector store; three retrieval strategies (similarity, MMR,
  confidence-threshold) sit behind a common retriever interface.
- **Grounded generation with citations** — questions are answered
  using only retrieved context, paired with a citation list pointing
  back to the specific documents an answer drew from, with a
  confidence-gated path that refuses to answer honestly rather than
  guess when nothing relevant was found.
- **A formal LCEL retrieval chain and summarizing conversation
  memory** — retrieval, formatting, and generation composed into one
  `Runnable`, with a hand-built memory pattern so a follow-up question
  can build on earlier turns without re-sending the entire
  conversation history verbatim.
- **A `pytest` suite** — unit tests for the ingestion layer and
  `TestClient`-based integration tests for the API routes.

## Tech Stack

| Layer | Technology |
|---|---|
| Language / runtime | Python 3.10+ |
| Web framework | FastAPI, Pydantic v2 |
| Testing | pytest, `fastapi.testclient.TestClient` |
| Analytics | pandas, numpy |
| LLM orchestration | LangChain (LCEL) |
| Chat model | Ollama, running `llama3.2` locally |
| Embeddings | Ollama, running `nomic-embed-text` locally |
| Vector store | Chroma (`langchain-chroma`), embedded/self-hosted mode |

Everything runs on localhost with no paid API keys, no cloud
deployment, and no external accounts — Ollama serves both the chat
model and the embedding model on your own machine.

## Project Structure

```
backend/
├── app/
│   ├── ai/
│   │   └── chains.py            # ticket/document summarization, triage,
│   │                             # tool-calling follow-up chains
│   ├── analytics/
│   │   ├── ownership.py         # document ownership / staleness report
│   │   └── workload.py          # team workload distribution report
│   ├── api/
│   │   ├── deps.py              # KnowledgeBaseService + DI provider
│   │   ├── main.py              # FastAPI app, middleware, router registration
│   │   ├── schemas.py           # Pydantic request/response models
│   │   ├── security.py          # X-API-Key auth dependency
│   │   └── routers/
│   │       ├── analytics.py     # /analytics
│   │       ├── ask.py           # /ask
│   │       ├── documents.py     # /documents
│   │       └── tickets.py       # /tickets
│   ├── core/
│   │   └── exceptions.py
│   ├── ingestion/
│   │   ├── document_loader.py   # loads Document rows from docs/
│   │   └── ticket_loader.py     # loads Ticket rows from tickets.csv
│   ├── models/
│   │   ├── comment.py
│   │   ├── document.py
│   │   ├── enums.py
│   │   ├── ticket.py
│   │   └── user.py
│   └── rag/
│       ├── vector_store.py      # chunk, embed, persist/load the vector store
│       ├── retriever.py         # similarity / MMR / threshold retrievers
│       └── qa_chain.py          # grounded Q&A, citations, retrieval_chain, memory
├── chroma_db/                    # persisted vector store (created on first run)
├── docs/                         # sample knowledge base: runbooks, wikis, postmortems
├── scripts/                      # one demo/challenge script per teaching day
├── tests/                        # pytest suite
├── tickets.csv                   # sample ticket data
└── requirements.txt
```

## Getting Started

### Prerequisites

- Python 3.10 or later (this project uses the `X | None` union-type
  syntax from PEP 604).
- [Ollama](https://ollama.com) installed separately — a native
  application, not a Python package.

### 1. Set up the virtual environment

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

### 2. Install dependencies

```powershell
pip install "fastapi[standard]" pytest pandas numpy `
    langchain langchain-ollama langchain-text-splitters langchain-chroma
```

(`fastapi[standard]` bundles `uvicorn` and `httpx`, so no separate
install is needed to run the API or use `TestClient` in tests.)

### 3. Pull the local models

With Ollama running:

```powershell
ollama pull llama3.2
ollama pull nomic-embed-text
ollama list        # confirm both models are present
```

### 4. Build the vector store (first run only)

The RAG endpoints need a populated `chroma_db\` directory. From
`backend\`:

```powershell
python -m scripts.day8_demo
```

This chunks and embeds every document in `docs\` and persists the
result to `chroma_db\`. It only needs to be run once — later runs of
the API reopen the same persisted store.

### 5. Run the API

```powershell
fastapi dev app/api/main.py
```

The API is now available at `http://127.0.0.1:8000`, with interactive
docs at `http://127.0.0.1:8000/docs`.

### Authentication

Every route except the root health check requires an `X-API-Key`
header set to `devmate-local-key`. In Swagger UI, click **Authorize**
and enter the key once; from a script or `Invoke-RestMethod`, pass it
as a header on every request.

## API Reference

| Method | Path | Description |
|---|---|---|
| GET | `/` | Health check — no API key required |
| GET | `/documents` | Paginated list of documents |
| GET | `/documents/stale` | Non-postmortem documents overdue for review |
| GET | `/documents/{document_id}` | A single document by id |
| GET | `/tickets` | Paginated list of tickets |
| GET | `/tickets/mismatches` | Tickets assigned outside the team that owns the related document |
| GET | `/tickets/{ticket_id}` | A single ticket by id |
| GET | `/analytics/workload` | Team workload distribution report |
| GET | `/analytics/document-ownership` | Document ownership / staleness report by team |
| POST | `/ask` | Grounded Q&A with citations |
| POST | `/ask/strict` | Grounded Q&A that refuses to answer below a confidence threshold |
| POST | `/ask/conversation` | Grounded Q&A with conversation memory, keyed by `conversation_id` |

## Running Tests

```powershell
pytest
```

Covers the ingestion layer directly (no API involved) and the
`/documents` and `/tickets` routes end-to-end through `TestClient`,
including the API-key requirement itself.

## Demo & Challenge Scripts

`scripts\` holds one script per teaching day this project was built
across — small, standalone entry points (`python -m scripts.<name>`)
used to demonstrate or exercise a single day's addition in isolation,
separate from the API. `scripts\day8_demo.py` is the one script every
later RAG feature depends on, since it's what actually builds
`chroma_db\` the first time.

## Data

- `docs\` — a small sample knowledge base (runbooks, a wiki page, a
  postmortem, an onboarding guide) used as the corpus for retrieval.
- `tickets.csv` — sample operational tickets referencing the documents
  in `docs\`.

Both are intentionally small, hand-authored datasets sized for
demonstrating the concepts clearly, not a realistic production corpus.

## Project Status

This project was built incrementally as a teaching capstone and is
now feature-complete: retrieval, grounded generation with citations, a
formal LCEL retrieval chain, and summarizing conversation memory are
all in place and working end-to-end against a real local model. No
further code is planned — remaining course material (agentic
reasoning, LangGraph, MCP) is taught as concept discussion against
this exact codebase, not as further changes to it.

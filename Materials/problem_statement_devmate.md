# Problem Statement: "DevMate" Engineering Assistant

---

## 1. Business Context

**Northbeam** is a mid-size software company whose engineering
knowledge — runbooks, wiki pages, postmortems, onboarding guides — is
scattered across a wiki nobody fully trusts, alongside a ticket
backlog nobody has time to triage by hand. New engineers can't find
the right runbook during an incident; on-call engineers re-discover
the same fixes repeatedly; documentation quietly goes stale while
tickets pile up against outdated guidance.

This project builds **DevMate**, an internal engineering assistant
that starts as a plain REST service over Northbeam's documents and
tickets, then grows into a retrieval-augmented assistant that can
answer engineering questions grounded in Northbeam's own documents —
and, ultimately, reason about taking action on a team's behalf.

---

## 2. Key Business Questions

The build must let an engineer eventually ask DevMate — in code, and
later in plain language — the following:

* **Stale Documentation:** *Which non-Postmortem documents haven't
  been reviewed recently enough to still be trusted?*
* **Team Ownership Mismatch:** *Which open tickets are assigned to an
  engineer outside the team that owns the document the ticket relates
  to?*
* **Team Workload Distribution:** *How is open ticket volume
  distributed across teams and priority levels — and which teams are
  carrying disproportionate load?*
* **Grounded Q&A:** *Given a plain-language engineering question,
  what's the best answer DevMate can give, backed by citations to the
  actual internal documents it came from?*
* **Proactive Triage:** *Can DevMate autonomously find and summarize
  the highest-priority open tickets, without an engineer manually
  searching for them?*
* **Safe Automation:** *Before DevMate takes any action that changes
  real data — drafting a ticket, escalating an incident — how does a
  human stay in control?*

---

## 3. Data Architecture & Core Entities

```
                        +----------------+
                        |      User      |
                        +----------------+
                        | id             |
                        | name           |
                        | team           |
                        +----------------+
                          |      |      |
                    owner |      |      | author
                          |      | assignee
                          *      |      *
              +----------------+ | +----------------+
              |    Document    | | |    Comment     |
              +----------------+ | +----------------+
              | id             | | | id             |
              | title          | | | ticket_id      |---+
              | category       | | | author_id      |   |
              | body           | | | body           |   |
              | owner_id       | | | created_at     |   |
              | last_reviewed_at| +----------------+   |
              +----------------+                        |
                       ^                                 |
                       | (related_document_id, optional)  |
                       |                          *       |
                       |              +----------------+  |
                       +--------------|     Ticket     |<-+
                                      +----------------+
                                      | id             |
                                      | title          |
                                      | priority       |
                                      | status         |
                                      | assignee_id    |
                                      | related_document_id
                                      | created_at     |
                                      +----------------+
```

### Entity Specifications

1. **Users:** Northbeam engineers (`id`, `name`, `team`). Not part of
   the initial build, deliberately — the way a foreign key can imply
   an entity before that entity gets modeled explicitly.
2. **Documents:** Runbooks, wiki pages, postmortems, and onboarding
   guides (`id`, `title`, `category`: *Runbook* | *Wiki* | *Postmortem*
   | *Onboarding*, `body`, `owner_id`, `last_reviewed_at`). Once
   retrieval is introduced, these same rows become the source material
   that gets chunked and embedded — not a separate copy of the data.
3. **Tickets:** Engineering work items (`id`, `title`, `priority`:
   *Low* | *Medium* | *High* | *Critical*, `status`: *Open* |
   *In-Progress* | *Resolved* | *Closed*, `assignee_id`,
   `related_document_id`, `created_at`).
4. **Comments:** Notes attached to a ticket (`id`, `ticket_id`,
   `author_id`, `body`, `created_at`) — the same one-attaches-to-one
   shape any later log-style entity in this codebase follows.

There is no separate "KnowledgeBase" table — a knowledge base, here,
is just the `Document` rows themselves, plus the embeddings and chunks
derived from them once retrieval is introduced.

---

## 4. Technical Requirements & System Features

Deliberately bounded: no RBAC, no frontend, no cloud deployment. This
is a backend and AI-engineering project — everything runs on
localhost.

### A. REST API Layer (FastAPI + Pydantic v2)

* Clean REST endpoints over `Document`, `Ticket`, and (later)
  `/ask`, using routers, dependency injection, and middleware.
* All request/response bodies validated with Pydantic v2 models.
* Interactive API documentation via the auto-generated Swagger/OpenAPI
  UI, and a `pytest` suite (unit + `TestClient` integration tests)
  covering every route.

### B. Analytics Layer (pandas + numpy)

* A `/analytics` endpoint that answers the Team Workload Distribution
  question directly from the in-memory `Ticket`/`Document` data — no
  database required for this project.

### C. Retrieval-Augmented Q&A (LangChain + embeddings + a vector store)

* Chunk and embed the `Document` corpus; store the vectors locally.
* A retriever answering the Grounded Q&A question: given a natural-
  language question, return an answer with citations back to the
  specific documents it drew from.
* Conversation memory so a follow-up question doesn't need to repeat
  context already given.

### D. Agentic Automation (LCEL, agents, LangGraph, MCP)

* Formalize the retrieval chain using LCEL for composability and
  reuse.
* Extend DevMate from answering questions to planning and executing
  multi-step tasks — answering the Proactive Triage question — with a
  human-in-the-loop approval step before any action that changes real
  data, answering the Safe Automation question.
* Model the agent's reasoning explicitly as a state graph (LangGraph)
  rather than an implicit loop, so its decisions are inspectable.
* Expose DevMate's tools via the Model Context Protocol (MCP) so other
  MCP-compatible clients can use them, and consume external MCP tools
  in turn.

---

## 5. Technology Stack & Deployment Architecture

| Tier | Technology | Runs on |
|---|---|---|
| **Backend / API** | Python 3.11, FastAPI, Pydantic v2 | Localhost |
| **Testing** | pytest | Localhost |
| **Analytics** | pandas, numpy | Localhost |
| **LLM orchestration** | LangChain (LCEL), LangGraph | Localhost |
| **LLM** | Ollama, running Llama 3.2 (3B) or Mistral 7B locally | Localhost (no API key, no rate limit) |
| **Embeddings** | Ollama's `nomic-embed-text` | Localhost |
| **Vector store** | Chroma, self-hosted embedded mode | Localhost (in-process) |
| **Tool integration** | MCP SDK | Localhost |
| **AI-assisted coding** | GitHub Copilot Free | Local editor |

No cloud tier — this project is designed to run entirely on free and
self-hosted tooling. If a machine can't run local models comfortably,
a hosted free tier (Google Gemini or Groq) is a drop-in substitute for
Ollama; just give each developer their own API key rather than sharing
one.

---
*DevMate — Northbeam Engineering Assistant — Problem Statement (reference document)*

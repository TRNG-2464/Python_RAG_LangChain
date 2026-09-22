# Problem Statement: "LineMate" Kitchen Operations Assistant

## 1. Business Context

**Hearthline** is a mid-size restaurant group whose kitchen knowledge —
recipes, prep guides, food-safety SOPs, post-incident reviews — is
scattered across binders, laminated sheets, and group chats nobody
fully trusts, alongside a backlog of kitchen issues nobody has time to
triage by hand. A new line cook can't find the right prep guide during
a dinner rush; a sous chef re-discovers the same equipment fix
repeatedly; a food-safety SOP quietly goes stale while tickets pile up
against outdated guidance.

This project builds **LineMate**, an internal kitchen operations
assistant that starts as a plain REST service over Hearthline's
documents and tickets, then grows into a retrieval-augmented assistant
that can answer kitchen operations questions grounded in Hearthline's
own documents.

> **A naming note worth stating explicitly:** in a real kitchen, the
> word "ticket" already means something specific — the slip of paper
> (or screen order) listing what a table ordered. That is **not** what
> `Ticket` means in this system. Here, a `Ticket` is an *operational*
> issue — a broken piece of equipment, a supply shortage, a food-safety
> concern — not a customer order. Keep the two meanings separate when
> discussing this project with anyone who's actually worked a line.

---

## 2. Key Business Questions

The build must let a staff member eventually ask LineMate — in code,
and later in plain language — the following:

* **Stale Documentation:** *Which non-Incident-Report documents
  haven't been reviewed recently enough to still be trusted?*
* **Station Ownership Mismatch:** *Which open tickets are assigned to
  a staff member outside the station that owns the document the
  ticket relates to?*
* **Station Workload Distribution:** *How is open ticket volume
  distributed across stations and priority levels — and which
  stations are carrying disproportionate load?*
* **Grounded Q&A:** *Given a plain-language kitchen operations
  question, what's the best answer LineMate can give, backed by
  citations to the actual internal documents it came from?*

---

## 3. Data Architecture & Core Entities

```
                        +----------------+
                        |   CrewMember   |
                        +----------------+
                        | id             |
                        | name           |
                        | station        |
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

1. **CrewMembers:** Hearthline kitchen staff (`id`, `name`, `station`:
   e.g. *Grill* | *Pastry* | *Prep* | *Front of House*). Not part of
   the initial build, deliberately — the way a foreign key can imply
   an entity before that entity gets modeled explicitly.
2. **Documents:** Recipes, prep guides, food-safety SOPs, and incident
   reports (`id`, `title`, `category`: *Recipe* | *SOP* | *Incident
   Report* | *Onboarding*, `body`, `owner_id`, `last_reviewed_at`).
   Once retrieval is introduced, these same rows become the source
   material that gets chunked and embedded — not a separate copy of
   the data.
3. **Tickets:** Kitchen operational issues (`id`, `title`, `priority`:
   *Low* | *Medium* | *High* | *Critical*, `status`: *Open* |
   *In-Progress* | *Resolved* | *Closed*, `assignee_id`,
   `related_document_id`, `created_at`) — equipment failures, supply
   shortages, food-safety concerns, and similar operational items.
   **Not** a customer's food order (see the naming note above).
4. **Comments:** Notes attached to a ticket (`id`, `ticket_id`,
   `author_id`, `body`, `created_at`) — the same one-attaches-to-one
   shape any later log-style entity in this system should follow.

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

* An `/analytics` endpoint that answers the Station Workload
  Distribution question directly from the in-memory `Ticket`/
  `Document` data — no database required for this project.

### C. Retrieval-Augmented Q&A (LangChain + embeddings + a vector store)

* Chunk and embed the `Document` corpus; store the vectors locally.
* A retriever answering the Grounded Q&A question: given a natural-
  language question, return an answer with citations back to the
  specific documents it drew from.
* Conversation memory so a follow-up question doesn't need to repeat
  context already given.
* Formalize the retrieval chain using LCEL for composability and
  reuse.

---

## 5. Technology Stack & Deployment Architecture

| Tier | Technology | Runs on |
|---|---|---|
| **Backend / API** | Python 3.11, FastAPI, Pydantic v2 | Localhost |
| **Testing** | pytest | Localhost |
| **Analytics** | pandas, numpy | Localhost |
| **LLM orchestration** | LangChain (LCEL) | Localhost |
| **LLM** | Ollama, running Llama 3.2 (3B) or Mistral 7B locally | Localhost (no API key, no rate limit) |
| **Embeddings** | Ollama's `nomic-embed-text` | Localhost |
| **Vector store** | Chroma, self-hosted embedded mode | Localhost (in-process) |
| **AI-assisted coding** | GitHub Copilot Free | Local editor |

No cloud tier — this project is designed to run entirely on free and
self-hosted tooling. If a machine can't run local models comfortably,
a hosted free tier (Google Gemini or Groq) is a drop-in substitute for
Ollama; use a personal API key rather than a shared one.

---
*LineMate — Hearthline Restaurant Group — Problem Statement (reference document)*

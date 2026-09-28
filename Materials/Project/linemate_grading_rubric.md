# LineMate Project — Grading Rubric (50 points)

**Format:** Live demonstration, 10 minutes max, no slideshow required.
Students should show each item running against their own LineMate
codebase rather than just describing it.

## Technical Requirements — 47 points

| # | Requirement (demonstrate live) | Points |
|---|---|---|
| 1 | **Core REST API** — `Document` and `Ticket` endpoints built with routers, dependency injection, and middleware; request/response bodies validated with Pydantic v2 | 6 |
| 2 | **API documentation & tests** — interactive Swagger/OpenAPI UI shown live, and a `pytest` suite (unit + `TestClient` integration tests) run showing routes passing | 5 |
| 3 | **Analytics endpoint** — `/analytics` answers the Station Workload Distribution question (open ticket volume by station/priority) using pandas/numpy | 5 |
| 4 | **Business logic queries** — code that answers the Stale Documentation question (non-Incident-Report documents overdue for review) and the Station Ownership Mismatch question (tickets assigned outside the station that owns the related document) | 6 |
| 5 | **Document ingestion pipeline** — the `Document` corpus is chunked, embedded, and stored in a persisted local vector store | 6 |
| 6 | **Retriever** — a working retriever that returns relevant chunks for a natural-language query | 5 |
| 7 | **Grounded Q&A endpoint** — `/ask` returns an answer to a kitchen-operations question with citations back to the specific source documents | 8 |
| 8 | **Conversation memory & LCEL chain** — a formal, composed LCEL `retrieval_chain`, and conversation memory so a follow-up question builds on a prior one without repeating context | 6 |
| | **Technical subtotal** | **47** |

## Soft Skills / Presentation — 3 points

| # | Criterion | Points |
|---|---|---|
| 1 | **Time management** — covers the required material within the 10-minute limit without rushing or running over | 1 |
| 2 | **Clarity of communication** — explains technical decisions in plain language a non-presenter could follow, with a clear structure | 2 |
| | **Soft skills subtotal** | **3** |

## Total: 50 points

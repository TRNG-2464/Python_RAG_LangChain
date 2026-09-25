# DevMate Notes
## Topic: Grounded Generation, Citations, and Closing the RAG Loop

---

## Executive Summary

Every prior step in this arc stopped at "return documents." A vector
store that could be searched, a retriever that standardized *how* it
got searched, a way to filter out weak matches entirely — none of it
ever actually answered a question. Today closes that loop: retrieved
chunks get formatted into a citation-ready string, handed to a chat
model alongside a strict grounding instruction, and the model's answer
comes back paired with a citation list pointing at exactly which
documents it drew from — all of it behind a real `POST /ask` endpoint
an engineer could actually call.

Today also adds a second, stricter path: one that refuses to answer at
all, honestly, rather than risk generating a confident-sounding guess
from weak or nonexistent context. Both paths reuse everything built
this week — nothing about today introduced a new retrieval mechanism
or a new vector store operation. Today is entirely about composition:
taking pieces that already worked in isolation and wiring them
together into something a real client can call over HTTP.

---

## Deep Dive: The Generation Half of RAG

- **This is the second half of the two-phase pattern established when
  RAG was first introduced.** Indexing — chunk, embed, persist — was
  finished days ago. Retrieval — embed a question, search, optionally
  filter or re-rank — was finished yesterday. **Generation** is the
  final phase: hand whatever was retrieved to a language model
  alongside the original question, and let it produce an answer
  *grounded in that retrieved text specifically*, not in whatever the
  model happened to learn during training. A RAG system without this
  phase is just a search engine; a RAG system without the retrieval
  phase behind it is just an ungrounded chatbot. Today is the first
  point in this project where both halves exist together, connected.
- **The generation chain itself is nothing new in shape — the exact
  same `prompt | llm | output_parser` pattern already used repeatedly
  earlier this week**, just pointed at a different prompt and fed a
  freshly retrieved context on every call instead of a fixed set of
  ticket or document fields. That consistency is deliberate: once a
  composition pattern is established and proven, reusing it rather
  than inventing a new shape for a superficially different use case
  keeps a codebase predictable. The prompt's *content* is what changes
  from one chain to the next — the *shape* of how a prompt, a model,
  and an output parser snap together does not need to.
- **A second, dedicated chat-model instance, deliberately not a reuse
  of an existing one.** A separate `ChatOllama` instance, configured
  with its own `temperature`, was constructed specifically for
  grounded generation rather than reaching for whatever instance
  already existed in a different module for a different purpose.
  `temperature` controls how much randomness gets sampled into a
  model's token choices — a low value (at the extreme, `0.0`) pushes
  the model toward its single most probable continuation at every
  step, minimizing creative variation; a higher value allows more
  variety, appropriate for a more conversational or creative use case.
  Grounded Q&A specifically wants the low end of that range: the goal
  is the model faithfully reflecting what the retrieved context
  actually says, not adding conversational flourish on top of it. A
  different chain built for a different purpose — summarizing a
  ticket in a friendly tone, say — reasonably wants a different value.
  Reusing one shared instance across genuinely different use cases
  means one setting has to compromise for every use case at once;
  separate instances mean each one can be tuned for what it's actually
  for.

---

## Deep Dive: Grounding, and Why "Use ONLY the Context" Matters

- **The core risk generation introduces that retrieval alone never
  had.** A retriever can return a weak or irrelevant result, but it
  can never *invent* one — every document it returns genuinely exists
  in the corpus. A language model has no such constraint: left
  unguided, it will happily produce a fluent, confident-sounding answer
  drawn from whatever it learned during training, whether or not that
  answer has anything to do with the specific documents actually
  retrieved for this specific question. This failure mode has a name —
  **hallucination** — and it's the single biggest reason RAG exists at
  all instead of just asking a model a question directly: retrieval
  gives generation something real to be grounded *in*, but only if the
  generation step is actually instructed to stay inside it.
- **An explicit grounding instruction in the system prompt is the
  primary defense, and it needs to say two different things, not just
  one.** "Answer using ONLY the context below" addresses the more
  obvious failure — reaching outside the provided material entirely.
  "If the context doesn't contain enough information to answer, say so
  plainly instead of guessing" addresses a subtler, easy-to-miss
  failure: a model that *does* stay grounded in a technical sense, but
  papers over a genuine gap in the retrieved context with a vague,
  hedge-y, still-confident-sounding non-answer rather than admitting
  the gap outright. Both instructions matter; an prompt with only the
  first can still produce a misleadingly confident answer when the
  retrieved context simply doesn't cover what was asked.
- **A prompt instruction is a strong nudge, not an ironclad
  guarantee.** Nothing about a system message *mechanically* prevents
  a model from drifting outside the provided context — it's steering
  the model's behavior through instruction, not enforcing a hard
  constraint the way a type system or a validation check would. This
  is worth understanding honestly rather than treating "the prompt
  says not to hallucinate" as equivalent to "the code cannot
  hallucinate." It's precisely this gap — a strong-but-not-absolute
  defense — that motivates the second layer of protection covered
  below.

---

## Deep Dive: From Retrieved Chunks to a Citation List

- **Why citations matter for something an engineer will actually
  trust.** An answer with no way to trace it back to a source asks for
  blind faith — "the model said so" is the entire justification. An
  answer paired with the specific document titles it was built from
  gives an engineer something concretely checkable: they can go read
  the runbook themselves and confirm the answer actually reflects it,
  rather than having to either trust or distrust a black box.
  Citations are what turn "an AI generated some text" into "a
  system produced a checkable claim."
- **Citations are derived from the same retrieved documents the
  formatted context was already built from — not a second, separate
  lookup.** The documents a retriever returns already carry their
  source title in `metadata["title"]`, the exact same field
  `format_retrieved_context` already reads to build the `[Source:
  ...]` labels inside the context string handed to the model. Building
  a citation list is just reading that same field a second time, off
  the same list of documents, for a different purpose — labeling
  content for the model versus labeling content for the person
  reading the model's answer.
- **Deduplicating citations, in first-seen order, is a small but real
  correctness detail.** A retriever configured to return several
  chunks can, on a larger corpus than this project's own, plausibly
  return more than one chunk from the *same* source document. Listing
  that document's title three times in a citation list is technically
  accurate but genuinely less useful to read than listing it once —
  and preserving the order chunks were actually retrieved in (rather
  than, say, alphabetizing) keeps the most relevant source listed
  first, matching the order an engineer would naturally want to check
  sources in.
- **The citation-bearing return value is deliberately a plain
  container, not itself an API response type.** Keeping "what a
  grounded-answer function returns" separate from "what an HTTP
  response looks like" means the exact same underlying function works
  identically whether it's called from a script, a test, or a real
  endpoint — the API layer's only job is translating one shape into
  the other at the boundary, not owning any of the actual logic.

---

## Deep Dive: Refusing to Answer — A Second Defense Against Hallucination

- **A prompt instruction alone is a strong defense with a specific,
  known weak point: a genuinely empty or near-empty context.** If
  nothing relevant was retrieved at all, a plain similarity-based
  retriever still hands back *something* — the least-bad matches
  available, however weak — and a model instructed to "use only the
  context" can still, in practice, drift toward filling a real gap
  with plausible-sounding outside knowledge, especially when the
  provided context gives it almost nothing to work with. The
  instruction is doing real work, but it's being asked to do that work
  under exactly the conditions where it's hardest to trust.
- **The more reliable fix doesn't ask the model to behave better under
  those conditions — it removes the conditions.** Rather than handing
  a model weak-to-nonexistent context and trusting a prompt to keep it
  honest, a confidence-threshold retriever can be checked *before* any
  model call happens at all: if nothing in the corpus clears a
  minimum relevance bar, skip the model call entirely and return a
  fixed, honest admission of the gap instead. This is a fundamentally
  different, stronger kind of guarantee than a prompt instruction —
  it's not "the model was told not to guess here," it's "the model was
  never given the opportunity to guess here in the first place,"
  enforced by ordinary Python control flow, not by trusting a
  language model's compliance.
- **The two defenses are complementary, not redundant.** The
  confidence threshold only ever catches the *complete-refusal* case —
  zero documents clearing the bar. It says nothing about the case
  where a few chunks *do* clear the threshold but are still,
  individually, a mediocre match for the actual question — the prompt
  instruction is still the only defense operating in that murkier,
  more common middle ground. Neither defense makes the other
  unnecessary.
- **The fixed refusal text is deliberately not built from the
  question, and deliberately not generated.** A canned, honest
  admission of a gap — the same wording every time a threshold isn't
  cleared — reads unambiguously as "the system knows it doesn't know,"
  rather than something dressed up to look like it drew from real
  content it never actually had access to. Interpolating the specific
  question into that fixed text, or otherwise dressing it up to look
  more tailored, would blur exactly the distinction this whole
  mechanism exists to preserve.

---

## Worth Knowing: Why Today Isn't a Single Formal LCEL Chain

- **Retrieval, formatting, and generation are called as three separate
  statements in a plain Python function today — not composed together
  with `|` into one `Runnable`.** This is worth understanding as a
  deliberate sequencing decision, not a missed opportunity to "do it
  properly." `format_retrieved_context` takes a plain
  `list[LCDocument]` and returns a plain `str` — LCEL's `|` operator
  composes `Runnable` objects together, and turning an ordinary
  function into something `|` can compose against needs an explicit
  wrapping step (a `RunnableLambda`) that hasn't been introduced yet.
  Reaching for that wrapping today, before there's an actual reason to
  need it, would be solving a problem this project doesn't have yet.
- **The real reason to eventually formalize this into one chain is
  conversation memory, not tidiness.** A single, unified
  `Runnable` composed from retrieval through generation becomes
  genuinely valuable once a follow-up question needs to reuse context
  from earlier turns — threading conversation history through three
  separately-called plain Python statements gets unwieldy fast, in a
  way that a properly composed chain, with memory wired through it
  once, does not. That formalization is real, planned future work, not
  a hypothetical improvement — it's just sequenced to happen once
  memory is actually the problem being solved, rather than ahead of
  time.
- **What "formalizing into a chain" will concretely change when it
  does happen, worth previewing conceptually:** the same three
  operations happening today — retrieve, format, generate — would
  become stages of one composed `Runnable`, callable as a single
  `.invoke(...)`, with conversation history flowing through as part of
  the input rather than being manually threaded between separate
  function calls the way `ask_ticket_followup` and
  `ask_document_followup` already do it by hand, earlier this week.
  Today's plain-function version and that future chain-based version
  will produce the same *answers* — what changes is how the pieces are
  wired together internally, not what a caller gets back.

---

## Architectural Analysis: One Question's Path From HTTP Request to Cited Answer

Tracing a single request all the way through today's stack:

1. A client sends `POST /ask` with a JSON body containing `question`.
   FastAPI validates that body against the request schema before any
   application code runs at all — a request missing `question`, or
   sending the wrong type for it, is rejected automatically with a
   `422` response, never reaching the route function.
2. The router-level `X-API-Key` dependency runs next, exactly the same
   authorization check every other route in this API already goes
   through — a request without a valid key never reaches the route
   function either, regardless of what its body contains.
3. The route function itself does almost nothing — it takes the
   validated `question`, hands it to the plain Python function that
   does the actual work, and translates that function's return value
   into the response schema. All of the real logic lives below the API
   layer entirely, reachable and testable independent of FastAPI ever
   being involved.
4. Inside that function: a retriever — built fresh on every call via
   the same `load_vector_store()`-based persistence discipline every
   function in this package has followed since the vector store was
   first built — embeds the question and searches for the closest
   matching chunks.
5. Those retrieved chunks get formatted into one citation-labeled
   string, and, separately, their titles get collected into a
   deduplicated citation list — the same list of documents feeding two
   different downstream needs.
6. The formatted string and the original question are handed to the
   generation chain — a prompt template carrying the grounding
   instruction, a chat model configured for low-variance, faithful
   output, and an output parser extracting the plain answer text.
7. The answer text and the citation list are packaged together and
   handed back up through the API layer, which translates them into
   the response schema a client actually receives.
8. For the stricter path: step 4 uses a confidence-threshold retriever
   instead of a plain similarity one, and if that retriever returns
   nothing, steps 5 and 6 never execute at all — a fixed refusal and an
   empty citation list are returned immediately, with the language
   model never having been called for that request.

A question worth sitting with: at which of these eight steps would a
retrieval-side bug (say, a corrupted or never-rebuilt vector store)
actually surface to the person asking the question? Not as a crash, or
an obviously-wrong-looking response — the honest answer is that it
would surface as a *plausible-sounding but ungrounded or outdated
answer*, indistinguishable at a glance from a correct one, unless the
citation list is actually checked against what the retrieved documents
should have been. This is exactly why the citation list isn't a
cosmetic addition — it's the one part of the response that gives
someone a real way to catch that kind of failure instead of just
trusting fluent-sounding output.

---

## Closing the Arc: Chunking to a Cited Answer, Start to Finish

Worth stepping back and tracing the whole shape of what this stretch
of work actually built, now that every piece of it exists:

1. **Ingestion** turned raw document rows into embeddable chunks —
   splitting where a document was long enough to need it, leaving it
   untouched where it wasn't.
2. **Embedding** turned each chunk into a vector capturing its
   meaning, using a model dedicated to that one job and nothing else.
3. **A persisted vector store** made those vectors searchable by
   nearest-neighbor distance, reopenable by a completely different
   process without ever needing to redo the first two steps.
4. **A retriever abstraction** standardized *how* that store got
   searched, decoupling calling code from Chroma's own specific method
   names — and, layered on top of that same abstraction, offered a
   choice of search strategy: plain closeness, diversity-aware
   re-ranking, or a confidence floor that can honestly return nothing.
5. **Generation**, built today, is what finally turns "the closest
   matching text" into "an answer to the actual question" — grounded
   by an explicit instruction, and backed by a second, structural
   defense against the exact failure that instruction alone can't
   fully prevent.
6. **Citations**, also built today, are what make the result of all of
   that checkable rather than merely plausible — the difference
   between an engineer trusting an answer because it sounds right and
   trusting it because they can go verify it themselves.
7. **The `/ask` endpoint** is what makes all six of the above reachable
   by an actual client, over HTTP, the same way every other piece of
   this project's functionality has been exposed since the REST layer
   was first built.

Every one of these seven pieces was built, tested (to whatever extent
this sandbox allowed), and understood as its own independently
inspectable unit — never as one opaque "ask the documents a question"
black box. That's not an incidental detail of how this arc happened to
unfold; it's the entire reason a bug anywhere in this pipeline is
something that can actually be isolated and fixed, rather than a
mystery buried inside a single monolithic function. What's still
ahead — formalizing this sequence into one composed chain, and adding
conversation memory so a follow-up question doesn't need to repeat
context already given — builds directly on top of every piece traced
above, without needing to revisit how any of them individually work.

---

## Quiz-Prep Quick Reference

| Term | One-line definition |
|---|---|
| Generation (RAG's second phase) | Handing retrieved context and a question to an LLM to produce a grounded answer — indexing and retrieval alone never answer anything |
| Hallucination | A model producing a fluent, confident answer not actually supported by the provided context — the core risk generation introduces |
| Grounding instruction | An explicit prompt directive to answer only from provided context, and to admit a gap rather than guess when the context doesn't cover it |
| `temperature` | Controls sampling randomness; low values (e.g. `0.0`) favor faithful, low-variance output — appropriate for grounded Q&A specifically |
| Citations | A deduplicated list of source titles, built from the same retrieved documents' metadata already used to format the model's context |
| Confidence-gated generation | Checking a threshold retriever's result *before* calling the LLM at all, so a "nothing confident enough" case never reaches the model |
| `RunnableLambda` | The wrapping needed to compose a plain Python function into an LCEL `\|` chain — not yet used in today's plain-function composition |
| Why not one formal chain yet | Real future value comes from threading conversation memory through it — sequenced to happen once memory is the actual problem, not ahead of time |
| `AskResult` | A plain dataclass return type, independent of FastAPI/Pydantic — keeps the RAG logic callable identically from a script, a test, or a route |
| Router-level dependency reuse | A new route added to an existing `APIRouter` inherits that router's `dependencies=[...]`, rather than redeclaring them per-route |

---

## Common Pitfalls & Anti-Patterns

- **Trusting a grounding instruction alone as a complete defense
  against hallucination.** It's a strong, real defense, not an
  absolute guarantee — a model can still drift, especially against
  weak or near-empty context. A structural defense (checking
  confidence *before* generating) covers exactly the gap a prompt
  instruction alone can't fully close.
- **Building citations from a separate lookup instead of the same
  retrieved documents already in hand.** The titles used to label
  context for the model and the titles shown to the person reading the
  answer should come from the exact same list of retrieved documents —
  a second, independent lookup risks the two silently drifting out of
  sync.
- **Listing the same source document multiple times in a citation
  list** when more than one retrieved chunk happens to come from it —
  technically accurate, but meaningfully less useful than a
  deduplicated, first-seen-order list.
- **Reaching for a `RunnableLambda`-wrapped, fully composed LCEL chain
  before there's an actual reason to need one.** Three separate,
  clearly-named function calls in a plain Python function are not a
  worse design than a composed chain — they're the right design for
  right now, with the formalization deliberately sequenced to happen
  once conversation memory actually requires it.
- **Interpolating the user's specific question into a fixed refusal
  message**, or otherwise dressing it up to look tailored — undermines
  the entire point of a fixed, honest "I don't know" response, which
  is to read unambiguously as an admission of a gap rather than as
  generated-sounding text.
- **Wrapping a confidence-gated function's LLM call in a
  `try`/`except`** on the theory that it makes the code more robust —
  nothing about a successful retrieval and generation should raise
  here, and suppressing an error that wasn't supposed to happen hides
  a real, different kind of failure behind handling meant for a
  perfectly normal "not confident enough" outcome.
- **Declaring a brand-new `APIRouter` for a closely related new
  route** instead of adding it to an existing router that already has
  the right `prefix` and `dependencies=[...]` — works, but duplicates
  configuration that was already correctly declared once.

---

## Troubleshooting Guide

| Symptom | Likely Cause | Fix |
|---|---|---|
| An answer sounds fluent and confident but doesn't match any of the listed sources | The model drifted outside the provided context despite the grounding instruction | Check the citation list against the actual answer content; consider tightening the prompt or reaching for confidence-gated generation for this use case |
| A grounded-Q&A response cites the same document title more than once | Citations weren't deduplicated before being returned | Build the citation list with a seen-set, in first-seen order, off the same retrieved documents used for context |
| The "strict" endpoint sometimes still seems to call the model even when nothing should have cleared the threshold | The zero-result check happens after, rather than before, the formatting/generation calls, or checks a proxy condition instead of the actual document list | Check `if not documents:` immediately after retrieval, before any formatting or generation call, and return early |
| A fixed refusal message reads like it was generated from context that doesn't exist | The refusal text was built dynamically (e.g. interpolating the question) instead of using one constant string | Use a single, fixed, honest constant for the "not confident enough" response, not something built per-request |
| `422 Unprocessable Entity` on a request to a grounded-Q&A endpoint | The request body is missing a required field, or a field has the wrong type, per the Pydantic request schema | Check the schema's required fields and types match what the client is actually sending |
| Two closely related routes duplicate the same authorization dependency declaration | A new `APIRouter` was declared for the new route instead of adding it to the existing one | Add the new route to the existing router so it inherits the router-level `dependencies=[...]` automatically |
| A follow-up question doesn't build on an earlier answer in the same conversation | Conversation memory isn't part of this arc yet — today's generation is single-turn only | Expected at this stage; threading memory through a formalized chain is planned, later work |

---
*DevMate — Northbeam Engineering Assistant — Notes: Grounded Generation, Citations, and Closing the RAG Loop*

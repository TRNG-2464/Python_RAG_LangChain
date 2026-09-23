# DevMate Notes
## Topic: Chunking, Embeddings, Vector Databases, and Retrieval-Augmented Generation

---

## Deep Dive: Vector Databases, Chroma, and How They Differ From a Relational Database

- **What makes something a "vector database" rather than just "a
  database that happens to store vectors."** A conventional database's
  fundamental query is an exact or range match — `WHERE id = 42` or
  `WHERE created_at > X` — with a deterministic yes/no answer for every
  row. A vector database's fundamental query is entirely different in
  kind: "given this vector, return the *k* stored vectors closest to
  it," ranked by a distance or similarity score. There is no notion of
  a row "matching" or "not matching" — only closer or farther, and the
  actual numbers depend entirely on which embedding model produced the
  vectors being compared.
- **Why this needs specialized indexing, not just a bigger B-tree.**
  Finding the *true* nearest neighbors among millions of
  high-dimensional vectors by brute force means comparing the query
  against every single stored vector — computationally expensive, and,
  per a well-established result in the nearest-neighbor search
  literature, this cost degrades toward no-better-than-a-full-scan as
  dimensionality grows (often called the "curse of dimensionality").
  Vector databases instead use **approximate nearest neighbor (ANN)**
  index structures, which deliberately trade a small, tunable amount
  of recall accuracy for large gains in query speed — this is a
  well-established, uncontroversial trade-off in the field, not a
  shortcut specific to any one product.
- **Chroma specifically uses HNSW (Hierarchical Navigable Small World
  graphs) for the kind of single-node, local deployment this project
  uses** — implemented via `chroma-hnswlib`, Chroma's own maintained
  fork of the widely-used `hnswlib` library. (Chroma's distributed,
  cloud-hosted deployment mode uses a different index, called SPANN —
  worth knowing the name exists, but irrelevant to the local,
  `persist_directory`-based usage in this project.)
- **Chroma is a library, not a server, in the mode used here.** This
  is the detail that explains why there was never an "install and
  start Chroma" step the way there was for Ollama: `langchain-chroma`
  (which pulls in the `chromadb` package) is a pure Python dependency
  that runs *embedded*, inside the same process as the rest of the
  code. Passing a `persist_directory` to `Chroma.from_documents(...)`
  writes straight to a folder on disk — no separate host, port,
  username, or password, because there's no separate server process to
  connect to at all. (Chroma also supports a client-server deployment
  mode for production use at larger scale; this project deliberately
  stays in the simpler embedded mode throughout.)
- **A specific, well-documented gotcha worth knowing by name: Chroma's
  default distance metric is L2 (squared Euclidean), not cosine.**
  This surprises people constantly — cosine similarity is the more
  commonly discussed metric in embedding-search tutorials generally,
  which leads to a natural but incorrect assumption that it's also the
  default here. A collection created without an explicit
  `collection_metadata={"hnsw:space": "cosine"}` override uses L2
  distance, full stop. This matters directly for interpreting
  `.similarity_search_with_score(...)`'s output correctly, covered
  below.
- **How Chroma's core operations map onto this project's own function
  names**, as a quick mental model: `Chroma.from_documents(...)`
  (inside `build_vector_store`) chunks are already prepared, so this
  call embeds them and writes both the vectors and their metadata to
  disk. `Chroma(persist_directory=..., embedding_function=...)`
  (inside `load_vector_store`) reopens that same on-disk collection
  without touching the data at all. `.similarity_search(query, k=...,
  filter=...)` (inside `search_documents`) is the only one of the
  three that actually talks to the ANN index — everything before it is
  setup, and everything after it is a plain Python list of results.

### How a Vector Database Differs From a Relational Database (Postgres)

| | Relational database (Postgres) | Vector database (Chroma) |
|---|---|---|
| **Fundamental query** | Exact or range match — deterministic: a row satisfies `WHERE ...` or it doesn't | Nearest-neighbor — approximate: return the *k* closest vectors, ranked by distance |
| **Index structure** | B-tree / hash indexes, built for exact lookups and ordered ranges | ANN structures (HNSW for Chroma's single-node mode), built for fast approximate similarity search |
| **Query language** | Full relational query language — joins across tables, aggregations, subqueries, constraints | A narrow API: store a vector plus metadata, return top-*k* nearest, optionally filtered on metadata — no joins |
| **Metadata values** | Any SQL column type, including `NULL` | Chroma's underlying store accepts only `str`, `int`, `float`, or `bool` — no `None`, no nested structures |
| **Transactions & integrity** | ACID transactions, foreign keys, constraints are core features | No cross-table joins or foreign-key enforcement to speak of — a much simpler consistency model, matching a much narrower job |
| **Deployment (as used here)** | A separate server process — host, port, credentials, a connection to manage | An embedded Python library writing straight to a local folder — no server, no connection string |
| **What it's for** | Structured, interrelated business data that needs joins, transactions, and exact answers | "Find things that mean something similar," at speed, across a large collection |

- **The two worlds are starting to blend, and that's worth knowing as
  a footnote rather than a contradiction.** `pgvector` is a real,
  actively maintained PostgreSQL extension that adds a native vector
  data type and nearest-neighbor search (via HNSW or IVFFlat indexes)
  directly into Postgres — meaning ordinary relational queries and
  vector similarity search can run against the very same table. This
  project deliberately keeps the two stores separate — Chroma for
  vectors, the project's own in-memory registries for structured data
  — partly for conceptual clarity while these ideas are still new, and
  partly because a separate, purpose-built vector store is still the
  far more common pattern in production RAG systems generally. Neither
  choice is "wrong;" they're different, valid trade-offs on the same
  underlying question of how much to unify.

---

## Executive Summary

Every chain built up to this point answered questions using either
what the model already knew from training, or a small, specific piece
of text handed to it directly by the calling code — a single ticket's
title, a single document's category. Neither of those approaches
scales to "answer a question grounded in the real internal document
corpus," because the model was never trained on those documents, and
the corpus is both too large to paste into a single prompt and, for
any one question, mostly irrelevant anyway.

**Retrieval-Augmented Generation (RAG)** is the pattern that solves
this, and everything covered today is the first half of it:
**chunking** breaks a document collection into retrievable pieces,
**embeddings** turn each piece into a vector that captures meaning
rather than exact wording, and a **vector database** (Chroma, in this
project) stores those vectors so the closest ones to a new question
can be found quickly, later. None of this answers a question by
itself yet — that's the second half of RAG, still ahead. Today's
output is a searchable, persisted store and nothing more.

---

## Deep Dive: Retrieval-Augmented Generation (RAG)

This is worth understanding thoroughly, because everything else in
these notes is really just the mechanics underneath one idea.

- **The problem RAG exists to solve.** A language model's knowledge is
  *parametric* — baked into its weights during training, fixed at
  whatever point training stopped, and completely blind to anything
  private, internal, or created afterward. Northbeam's runbooks,
  postmortems, and onboarding docs were never part of any model's
  training data, and pasting an entire growing document corpus into
  every prompt doesn't scale: eventually it stops fitting in the
  model's context window, and even before that point, most of the
  corpus is irrelevant to any single question, just adding noise and
  cost. RAG's answer to both problems at once: don't ask the model to
  know everything, and don't paste everything into the prompt — instead,
  find the *specific* pieces of text relevant to *this* question, and
  hand the model only those.
- **Two phases, happening at two different times.** This is the single
  most important structural fact about RAG, and it maps directly onto
  this project's own code and schedule:
  1. **Indexing** — done once up front, and again whenever the source
     documents change. Chunk the corpus, embed each chunk, store the
     chunks and their embeddings in a vector database. This is
     entirely what `documents_to_chunks` and `build_vector_store` do,
     and it's the entire scope of what got built today.
  2. **Retrieval + Generation** — done fresh for every question, using
     whatever was indexed. Embed the incoming question the same way
     the chunks were embedded, search the vector database for the
     chunks whose embeddings land closest to the question's embedding
     (`search_documents`, added in the challenge, does exactly this),
     and hand those retrieved chunks to the LLM alongside the question,
     instructing it to answer using what it was just given. This half
     of RAG — actually building a retriever and wiring it into a
     prompt and a live `/ask` endpoint — is still ahead; today only
     builds the foundation it will stand on.
  A useful gut check for "is this RAG:" if the answer changes when the
  underlying documents change, without retraining anything, it's RAG.
  If getting new knowledge into the system requires retraining or
  fine-tuning the model itself, it's a different pattern entirely.
- **RAG is not fine-tuning, and conflating the two is a common,
  costly mistake.** Fine-tuning changes the model's *weights* — an
  expensive, slow, offline process that teaches the model new patterns
  of behavior or style, but doesn't reliably teach it new *facts*, and
  provides no way to trace an answer back to a specific source. RAG
  changes what's in the *prompt* at request time — cheap, fast, and
  exactly as current as the last time the vector store was re-indexed.
  A team wanting a model to "know about" a constantly-changing internal
  document corpus wants RAG, not fine-tuning; a team wanting a model to
  reliably adopt a certain tone or output format might reach for
  fine-tuning instead. The two aren't mutually exclusive in a mature
  system, but for "answer questions grounded in Northbeam's own
  documents," RAG is the correct tool, and fine-tuning would be both
  more expensive and less effective at the actual goal.
- **The payoff, stated plainly.** A RAG-backed assistant can answer
  questions about documents it was never trained on, stays current as
  those documents change (re-index, don't retrain), and — critically
  for something engineers will actually trust — can cite exactly which
  documents an answer came from, because the specific chunks it drew
  from are known at generation time. An answer with no retrieval step
  behind it has no way to back up its claims beyond "the model said
  so;" a RAG answer can point at the retrieved text directly.
- **What can go wrong with RAG, conceptually, independent of any one
  library's API.** Three distinct failure modes are worth knowing by
  name, because they produce very different symptoms and call for
  different fixes:
  - **Retrieval miss** — the right chunk exists in the store, but
    wasn't among the top-*k* results returned for a given question,
    usually because the question's wording is semantically distant
    from the chunk's wording, or *k* was set too low. The generation
    step never even sees the right information, no matter how good the
    prompt is.
  - **Retrieval noise** — irrelevant or only-tangentially-related
    chunks get retrieved alongside (or instead of) the useful one,
    diluting the context the model has to work with and sometimes
    actively distracting it into a wrong or hedged answer.
  - **A stale index** — the source documents changed, but the vector
    store was never rebuilt against the new versions, so retrieval
    keeps confidently returning chunks from the *old* text. This is a
    RAG-specific version of a very old bug shape: the code runs
    without error and produces a plausible-looking answer that is
    simply wrong, because what it's reading from is out of date.
  Recognizing which of these three is happening is most of the work of
  debugging a RAG system that gives a bad answer — and it's exactly why
  today's chunking/embedding/storage layer and tomorrow's retrieval
  layer are worth understanding as separate, individually-inspectable
  pieces, rather than one opaque "ask the documents a question" black
  box.

---

## Deep Dive: Chunking

- **Why chunk at all, instead of embedding whole documents.** A vector
  embedding compresses a piece of text into a single fixed-length
  vector — the more text goes in, the more that vector has to
  represent, and the less precisely it can represent any one part of
  it. A whole multi-page document embedded as one vector produces a
  blurry average of everything the document covers; a focused
  paragraph-sized chunk embedded on its own produces a vector that
  actually represents *that specific idea*. Chunking is what makes
  retrieval precise enough to be useful.
- **`RecursiveCharacterTextSplitter` (from the separate
  `langchain-text-splitters` package, not `langchain_core`) is the
  standard tool for this.** `chunk_size` is a *maximum*, not a target
  — the splitter never hands back a chunk longer than this many
  characters by default (a different `length_function`, like a token
  counter, can be swapped in, but character count is the default).
  `chunk_overlap` means adjacent chunks share a number of
  trailing/leading characters, so a sentence that happens to land
  right at a chunk boundary doesn't lose all of its surrounding
  context in either resulting chunk.
- **The separator priority list is what makes the splitting "smart"
  rather than purely mechanical.** By default,
  `RecursiveCharacterTextSplitter` tries `["\n\n", "\n", " ", ""]`, in
  that order — splitting on paragraph breaks first, then line breaks,
  then spaces, only falling back to splitting in the middle of a word
  as an absolute last resort. This is why a paragraph that fits under
  `chunk_size` on its own tends to survive as one clean chunk rather
  than getting sliced at an arbitrary character count.
- **Chunk size and overlap are real trade-offs, not settings with one
  obviously correct value.** Too small, and a chunk loses the
  surrounding context needed to make sense of it on its own — a
  sentence fragment about "the second step" means nothing without the
  first step, which may have landed in a different chunk. Too large,
  and each chunk's embedding gets diluted across multiple unrelated
  ideas, making retrieval less precise, while also spending more of
  the model's context window on text that might not be relevant to the
  question at hand. Overlap set too high wastes storage and search
  time on near-duplicate content; overlap set to zero risks losing
  continuity exactly at chunk boundaries.
- **Worth knowing directly, because it's genuinely counterintuitive
  the first time it happens: chunking can appear to do nothing, and
  that can be entirely correct.** Verified directly against this
  project's real document corpus: every document body is under 150
  characters, comfortably under a `chunk_size` of 500 — so
  `documents_to_chunks` produces exactly one chunk per document, a
  clean one-to-one mapping, with no actual splitting taking place
  anywhere. Someone expecting to see chunking "in action" by watching
  document count change could easily read this as a bug. It isn't —
  chunking only does visible work once a document body is longer than
  `chunk_size`, and a small starter corpus simply hasn't hit that point
  yet. The same code will start visibly splitting the moment a real
  document grows past a few hundred words, with no changes needed.

---

## Deep Dive: Embeddings

- **What an embedding actually is.** A fixed-length list of floating
  point numbers (a vector) that represents a piece of text's
  *meaning*, positioned in a high-dimensional space such that texts
  with similar meaning end up numerically close together — even when
  they share almost no exact words. "How do I roll back a bad deploy"
  and "steps for reverting a failed release" should land close
  together in embedding space despite having very little vocabulary
  overlap; this is precisely the capability plain keyword search
  lacks, and precisely why RAG typically pairs with embeddings rather
  than a simpler text-matching approach.
- **`OllamaEmbeddings` (from `langchain_ollama`) mirrors `ChatOllama`'s
  own constructor shape** — `model=` and an optional `base_url=` — but
  serves a completely different purpose: it turns text into vectors,
  it does not generate conversational responses. `.embed_query(text)`
  returns a single vector for one piece of text; `.embed_documents(texts)`
  returns one vector per string in a list, for embedding many chunks
  at once. Nothing about either method is specific to any one
  project's data — this is exactly the same shape of call
  `Chroma.from_documents(...)` makes internally on every chunk it's
  handed.
- **An embedding model and a chat model are not interchangeable, even
  when they come from the same provider.** `nomic-embed-text` is
  documented as producing 768-dimensional vectors and is
  embedding-only — it cannot be used as a `ChatOllama` model, the same
  way a chat model like Llama 3.2 cannot be used for embeddings. Each
  has to be pulled separately (`ollama pull nomic-embed-text`,
  distinct from whatever chat model is already in use), and `ollama
  list` should show both, as two different model sizes, once both are
  present.
- **A quieter but important constraint: embeddings from two different
  models are not comparable to each other.** A vector's numbers only
  mean something relative to the specific model that produced them —
  swapping `EMBEDDING_MODEL` to a different embedding model changes
  the coordinate system those numbers live in entirely. A vector store
  built with one embedding model cannot be meaningfully searched using
  a different embedding model's query vector; doing so doesn't
  necessarily error, but the resulting "closeness" is meaningless. In
  practice, this means changing an embedding model requires fully
  re-embedding and rebuilding the entire vector store from scratch —
  there's no way to "upgrade" half a store's worth of vectors to a new
  model while leaving the rest as-is.
- **The numbers themselves are not meant to be read.** Printing the
  first few values of a 768-dimensional vector produces output that
  looks arbitrary because, read one number at a time, it is — the
  useful signal only emerges from comparing whole vectors to each
  other (via distance or similarity calculations), never from
  inspecting individual components.

---

## Deep Dive: Persisting and Reopening a Chroma Collection

- **There is no `.persist()` method anymore, and this is a real
  "the library moved" gotcha, not a hypothetical one.** Older
  tutorials — and older versions of this same library — called
  `vector_store.persist()` explicitly after building a Chroma store,
  as a separate, required step. That method has been removed entirely
  from the current `langchain-chroma` package: once a
  `persist_directory` is passed to `Chroma.from_documents(...)`, every
  write goes to disk automatically, immediately, with nothing further
  to call. Code copied from an older example that still calls
  `.persist()` will fail with an `AttributeError` — not because
  persistence itself stopped working, but because the method that used
  to make it explicit simply isn't there to call anymore. This is the
  same shape as `LLMChain`'s removal from earlier this week, showing up
  in a different corner of the same fast-moving library.
- **`embedding=` vs. `embedding_function=` is a real, easy-to-miss
  naming mismatch between Chroma's two entry points.**
  `Chroma.from_documents(...)` takes `embedding=`; the plain
  `Chroma(...)` constructor used to reopen an existing store takes
  `embedding_function=`. Mixing the two up produces a `TypeError`
  naming the wrong keyword — worth reading the actual error message
  carefully rather than assuming the whole call is broken.
- **Two classes named `Document`, deliberately kept apart by an
  import alias.** LangChain's own representation of a piece of
  retrievable text is a class called `Document`
  (`langchain_core.documents.Document`), with `page_content` and
  `metadata` fields — a genuine, coincidental naming collision with
  this project's own, completely unrelated `Document` domain model.
  Importing LangChain's version as `LCDocument` is what keeps a file
  readable: every `LCDocument` reference is unambiguously LangChain's
  container, and every plain `Document` reference is this project's
  own row. Skipping the alias and letting an un-aliased `from
  langchain_core.documents import Document` shadow the domain import is
  a realistic, easy mistake — one that fails loudly and confusingly the
  moment code elsewhere expects `document.title` and gets an
  `AttributeError`, because `Document` silently started meaning
  something else partway through the file.
- **Chroma's metadata constraint is a real limitation, not defensive
  styling.** The underlying client only accepts `str`, `int`, `float`,
  or `bool` metadata values — no `None`, no nested dicts or lists. A
  Python `date` object (exactly what a `last_reviewed_at` field is on
  this project's own `Document` model) is none of those, and passing
  one through unconverted raises a `ValueError` at the point the
  vector store is actually written to — several layers removed from
  where the `date` object was originally created, which makes it a
  confusing error to debug blind. `.isoformat()` sidesteps the problem
  entirely by converting it to a plain string up front. LangChain does
  ship an "official" fix for this exact situation —
  `langchain_community.vectorstores.utils.filter_complex_metadata` —
  but it lives in the same unmaintained, archived `langchain_community`
  package this project has avoided throughout, and hasn't been
  migrated anywhere current. For a small, known set of non-primitive
  fields, hand-converting the one problematic value is more honest than
  depending on an unmaintained package's utility function.

---

## Deep Dive: Querying With Filters and Understanding Similarity Scores

- **Omitting the `filter` argument, versus passing a `None` value
  inside one, are not the same thing — and only one of them works.**
  Chroma's metadata store never actually contains a `None` value
  (nothing in this project's metadata-building code produces one), so
  a filter like `{"category": None}` doesn't mean "no filter" the way
  it might in some other API — it either errors outright or silently
  matches nothing, depending on the version. The correct way to run an
  unfiltered search is to not pass the `filter` argument at all,
  which is exactly why `search_documents` branches on `category is
  None` rather than always constructing a filter dict.
- **Chroma's `filter` (the `where` filter) supports real operators
  beyond simple equality**, documented directly in Chroma's own
  reference: scalar comparisons (`$eq`, `$ne`, `$gt`, `$gte`, `$lt`,
  `$lte`), set membership (`$in`, `$nin`), logical combinators (`$and`,
  `$or`), and, for metadata fields that are themselves lists,
  `$contains`/`$not_contains`. A separate, similarly-named
  `where_document` filter (not the same as the metadata `filter`) also
  supports `$contains`/`$not_contains`/`$regex`, but there it means a
  substring or pattern match against the document's actual text, not
  metadata membership — the same operator names meaning genuinely
  different things depending on which filter they're used in is worth
  reading carefully rather than assuming by name alone.
- **A `.similarity_search_with_score(...)` result's score is a raw
  distance, and lower always means more similar — regardless of which
  distance metric the collection is actually configured to use.** This
  is a specific, well-documented source of real confusion (it has
  caused genuine bugs in the wild, including a threshold-filtering bug
  in LangChain's own history from exactly this mix-up): people
  naturally expect a "similarity score" to work like cosine similarity,
  where *higher* is better, but `similarity_search_with_score` always
  returns Chroma's raw distance value, where *lower* is better — a
  completely different, separate method,
  `similarity_search_with_relevance_scores`, is the one that converts
  that raw distance into a normalized 0–1 scale where higher does mean
  more similar. Combined with the L2-default gotcha above: the raw
  number coming back from `similarity_search_with_score` on this
  project's default-configured collection is a squared Euclidean
  distance, not a cosine similarity — treating it as "closer to 1.0 is
  better" would be actively backwards.

---

## Worth Knowing: What Happens When Ingestion Runs Twice

A fair question to ask before this ever becomes a production concern:
what happens if `build_vector_store` gets called a second time against
a `persist_directory` that already has data in it from a previous run?

- **Short answer: the collection grows, with duplicate content stored
  under new IDs — it does not deduplicate, and it does not raise an
  error.** This follows from two separately well-documented facts,
  combined: first, `Chroma.from_documents(...)` mints a fresh random ID
  for every document unless explicit `ids=` are supplied; second,
  Chroma's own "add" operation only skips a record when its *ID*
  already exists in the collection. Put together, a second ingestion
  run — with no explicit IDs — never triggers that dedup check at all,
  because every ID it generates is brand new, even for chunks whose
  *content* is identical to something already stored.
- **Why this matters for a real ingestion pipeline, not just as
  trivia.** A production system that re-runs ingestion on a schedule
  (nightly, on every document update, and so on) without addressing
  this would slowly accumulate duplicate vectors for unchanged
  documents, degrading both storage efficiency and retrieval quality —
  duplicate near-identical chunks crowding out genuinely different
  results in a top-*k* search. The fix is to pass deterministic `ids=`
  when calling `from_documents(...)` — commonly a hash of the chunk's
  content, or a stable identifier derived from the source document's
  own ID and chunk position — so that re-running ingestion against
  unchanged content reuses the same IDs and lets Chroma's own
  dedup-on-add behavior actually do its job. This project's own
  `build_vector_store` doesn't do this yet — worth flagging as a real,
  known gap rather than a hidden one, and a natural next improvement
  once ingestion needs to run more than once against a growing corpus.

---

## Architectural Analysis: One Document's Path From Row to Retrievable Vector

Tracing a single `Document` row all the way through today's pipeline:

1. `load_documents_from_folder("docs")` populates `Document.registry`
   with real rows — `title`, `category`, `body`, `owner_id`,
   `last_reviewed_at` — exactly as it did the first time this loader
   was introduced.
2. `documents_to_chunks` converts each `Document` into LangChain's own
   `LCDocument` representation, building a metadata dictionary
   alongside it (`_document_to_metadata`) that converts the one
   non-primitive field (`last_reviewed_at`, a `date`) into a plain
   string up front, avoiding a `ValueError` several steps later.
3. `_splitter.split_documents(...)` runs `RecursiveCharacterTextSplitter`
   against each `LCDocument`'s `page_content`. For this project's
   current, short document bodies, this step is a no-op in terms of
   actual splitting — one document in, one chunk out — but the same
   call will start dividing documents into multiple chunks the moment
   any body grows past `CHUNK_SIZE`, with no code changes required.
4. `build_vector_store` hands the resulting chunks to
   `Chroma.from_documents(...)`, which calls `_embeddings.embed_documents(...)`
   internally to turn each chunk's text into a 768-dimensional vector,
   then writes both the vectors and their metadata dictionaries to disk
   at `persist_directory`.
5. Later — potentially in a completely different process, hours or
   days afterward — `load_vector_store()` reopens that same on-disk
   collection without touching any of the data, and `search_documents`
   embeds an incoming query with the same embedding model, asks
   Chroma's HNSW index for the nearest stored vectors, optionally
   narrowed by a metadata `filter`, and returns them as a plain
   `list[LCDocument]` — unmodified, ready for whatever calls it to
   decide how to use them.
6. What comes after step 5 — assembling those retrieved chunks into a
   prompt, calling the LLM, and returning an answer with citations
   back to the specific documents it drew from — is the second half of
   RAG, and is still ahead. Everything traced above is entirely the
   indexing half: get the data into a state where step 5 is even
   possible.

A question worth sitting with: at which of these six steps would a
*stale index* problem (documents changed on disk, but the vector store
was never rebuilt) actually become visible? The honest answer: nowhere
in this trace — every one of these steps would complete without error,
using the last set of documents that were ever ingested. The problem
only becomes visible downstream, as a wrong-sounding answer in step 6,
which is exactly why "when was this vector store last rebuilt, and
against what documents" is one of the first questions worth asking
when a RAG-backed answer looks outdated or wrong, rather than assuming
the retrieval or generation logic itself is broken.

---

## Quiz-Prep Quick Reference

| Term | One-line definition |
|---|---|
| Retrieval-Augmented Generation (RAG) | A two-phase pattern: index a document corpus once (chunk, embed, store), then retrieve the most relevant pieces and hand them to an LLM fresh for every question |
| Indexing | The offline half of RAG — chunk, embed, and persist a corpus into a searchable store |
| Retrieval + Generation | The online half of RAG — embed a question, search the store, hand retrieved chunks plus the question to the LLM |
| `RecursiveCharacterTextSplitter` | Splits text using a separator priority list (`\n\n`, `\n`, ` `, then character-level), respecting `chunk_size` as a maximum and `chunk_overlap` for shared context at boundaries |
| `OllamaEmbeddings` | Turns text into vectors (`.embed_query` for one string, `.embed_documents` for many); a different kind of model from a chat model, not interchangeable with one |
| Vector database | A database whose core query is "return the *k* stored vectors nearest to this one," not exact/range matching |
| HNSW | Hierarchical Navigable Small World graphs — the ANN index structure Chroma's single-node mode uses, trading a small amount of recall for large speed gains |
| Chroma (as used in this project) | An embedded vector database — a Python library writing straight to a local folder, no separate server process |
| `build_vector_store` / `load_vector_store` | Build-and-persist vs. reopen-without-rebuilding — the second is what a real query-only process should always use |
| `search_documents` | Queries an already-persisted store via `load_vector_store()`; omits the `filter` argument entirely when no category is given, rather than passing a `None` value |
| Chroma's default distance metric | L2 (squared Euclidean) — not cosine, despite cosine being the more commonly assumed default |
| `similarity_search_with_score` | Returns raw distance; **lower is always more similar**, regardless of the collection's configured metric |
| `similarity_search_with_relevance_scores` | A separate method that normalizes distance into a 0–1 scale where higher means more similar |
| Chroma metadata constraint | Only `str`/`int`/`float`/`bool` values allowed — no `None`, no nested structures; a `date` needs `.isoformat()` first |
| pgvector | A real PostgreSQL extension adding native vector search (HNSW/IVFFlat) directly into Postgres tables |

---

## Common Pitfalls & Anti-Patterns

- **Assuming chunking is broken because a small corpus produces a
  clean one-to-one mapping of documents to chunks.** Chunking only
  does visible work once a document body exceeds `chunk_size` — a
  1-to-1 result on short documents is correct, not a sign of failure.
- **Treating an embedding vector from one model as comparable to a
  vector from a different embedding model.** The numbers only mean
  something relative to the model that produced them; switching
  `EMBEDDING_MODEL` requires a full re-embed and rebuild, not a partial
  update.
- **Assuming Chroma's default distance metric is cosine similarity.**
  It's L2 by default — a real, commonly-made wrong assumption that
  changes how a raw similarity-search score should be interpreted.
- **Reading `similarity_search_with_score`'s output as "higher is
  better."** It returns a raw distance; lower is always more similar,
  regardless of which distance metric the collection actually uses.
  `similarity_search_with_relevance_scores` is the method that flips
  this to a higher-is-better scale.
- **Passing `filter={"category": None}` instead of omitting the
  `filter` argument** when no category filter is wanted — Chroma's
  metadata never actually contains `None`, so this doesn't mean "no
  filter" the way it might elsewhere.
- **Calling `build_vector_store(...)` from a process that only needs
  to search** — even if it "works," it needlessly re-ingests and
  re-embeds the entire corpus on every call, and, without deterministic
  IDs, actively duplicates data in the store on every re-run.
- **Assuming an old tutorial's `vector_store.persist()` call still
  exists.** It's been removed entirely; passing `persist_directory` up
  front is already enough.
- **Mixing up `embedding=` (used by `from_documents`) and
  `embedding_function=` (used by the plain `Chroma(...)` constructor).**
  A `TypeError` naming the wrong keyword is the signal this happened.
- **Letting an un-aliased `from langchain_core.documents import Document`
  shadow this project's own domain `Document` import.** Fails loudly
  the moment code expects `document.title` and instead gets an
  `AttributeError`, because `Document` silently started meaning
  something else.

---

## Troubleshooting Guide

| Symptom | Likely Cause | Fix |
|---|---|---|
| A vector store build produces the same number of chunks as documents, with no splitting visible | Every document body is shorter than `chunk_size` | Expected behavior for a small corpus — not a bug; splitting will appear once a document body exceeds `chunk_size` |
| `AttributeError` on `.persist()` | Copied code from an older tutorial or library version | Remove the call entirely — passing `persist_directory` to `from_documents(...)` already persists automatically |
| `TypeError` about an unexpected keyword argument involving `embedding` | Used `embedding=` where `embedding_function=` was needed, or vice versa | `from_documents(...)` takes `embedding=`; the plain `Chroma(...)` reopen constructor takes `embedding_function=` |
| `ValueError` when building the vector store, mentioning metadata | A non-primitive value (commonly a `date`) is in the metadata dict passed to `LCDocument` | Convert it to `str`/`int`/`float`/`bool` first — `.isoformat()` for dates |
| A filtered search raises an error or returns nothing when no filter was intended | Passed `filter={"category": None}` instead of omitting the `filter` argument | Branch on `category is None` and omit the `filter` keyword entirely in that case |
| A similarity search seems to rank the "wrong" result as most similar | Interpreting a raw distance score as if higher meant more similar | Remember `similarity_search_with_score` returns distance (lower = more similar); use `similarity_search_with_relevance_scores` for a higher-is-better scale |
| A vector store's answers seem to reference outdated document content | The vector store was never rebuilt after the source documents changed — a stale index | Re-run the ingestion/build step against the current documents; consider deterministic chunk IDs so re-ingestion updates rather than duplicates |
| Repeated ingestion runs seem to bloat the vector store over time | `build_vector_store` was called again without deterministic `ids=`, so every run adds new vectors instead of updating existing ones | Pass a stable `ids=` (e.g., a hash of chunk content) so Chroma's own dedup-on-add behavior can take effect |
| `AttributeError` on `document.title` partway through a file that imports both `Document` types | An un-aliased `from langchain_core.documents import Document` shadowed the domain model's own `Document` import | Import LangChain's version under an alias (`as LCDocument`) and keep the domain `Document` import unaliased |

---
*DevMate — Northbeam Engineering Assistant — Notes: Chunking, Embeddings, Vector Databases, and Retrieval-Augmented Generation*

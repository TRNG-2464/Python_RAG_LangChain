# Vector Databases

Embedding a handful of sentences into a Python list works fine for a demo. It stops working the moment we have real data: the vectors vanish when the process exits, every search compares against all of them, and there's nowhere to record which file a chunk came from.

A **vector database** solves those three problems. It stores vectors alongside their original text and metadata, persists them, and indexes them so search stays fast as the collection grows.

---

## What Actually Gets Stored

Each record in a vector store has four parts:

| Part | Example | Purpose |
|---|---|---|
| **id** | `"handbook-pdf-chunk-12"` | Unique key — enables update and delete |
| **embedding** | `[0.021, -0.147, ...]` | What gets searched |
| **document** | `"Employees accrue 15 days..."` | The original text, returned on a hit |
| **metadata** | `{"source": "handbook.pdf", "page": 4}` | Filtering, and citation in the answer |

The embedding is what we search *by*; the document is what we get *back*. That distinction is the whole design. Nobody wants a list of floats returned from a search — they want the text those floats represent, plus enough context to say where it came from.

Metadata is the part most often under-used. It's what makes "search only the 2025 documents" or "only this user's files" possible, and it's what lets a RAG answer cite a page number.

---

## Chroma Through LangChain

Chroma is an open-source vector database that runs embedded in the Python process — no server to start. LangChain wraps it so it looks like any other vector store.

```python
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings

embeddings = OllamaEmbeddings(model="nomic-embed-text")

store = Chroma(
    collection_name="handbook",
    embedding_function=embeddings,
    persist_directory="./chroma_db",
)
```

*Opens (or creates) a persistent Chroma collection backed by a local directory.*

Three arguments, each doing real work:

- **`collection_name`** — a named partition inside the database. Separate collections are fully isolated; use them to keep unrelated corpora apart, and remember that a collection is tied to the embedding model that built it.
- **`embedding_function`** — the model Chroma calls to embed anything added or searched. We hand it the model, not vectors, and Chroma handles the embedding.
- **`persist_directory`** — where it writes to disk. Omit it and the store is in-memory only, gone when the process exits. Recent versions of `langchain-chroma` persist automatically; there's no separate `.persist()` call to remember.

---

## Adding Documents

Given a list of `Document` objects — which is what loaders and splitters produce — adding them is one call:

```python
from langchain_core.documents import Document

docs = [
    Document(page_content="Employees accrue 15 days of PTO annually.",
             metadata={"source": "handbook.pdf", "page": 4, "year": 2025}),
    Document(page_content="Expense reports are due by the 5th of each month.",
             metadata={"source": "handbook.pdf", "page": 9, "year": 2025}),
]

store.add_documents(docs)
```

*Embeds each document's text and stores it with its metadata in the collection.*

Chroma embeds the `page_content` and keeps the `metadata` alongside, unmodified. There's also a one-shot constructor that creates the collection and loads it in a single step:

```python
store = Chroma.from_documents(
    documents=docs,
    embedding=embeddings,
    collection_name="handbook",
    persist_directory="./chroma_db",
)
```

*Builds a new collection directly from a list of documents.*

Convenient for a first ingestion, but note it's additive — running it twice adds everything twice.

### Controlling IDs

By default every `add_documents` call generates fresh random ids, so re-running an ingestion script duplicates the whole corpus. Supplying stable ids makes ingestion **idempotent**:

```python
ids = [f"{d.metadata['source']}-p{d.metadata['page']}" for d in docs]
store.add_documents(docs, ids=ids)      # re-running updates in place, no duplicates
```

*Assigns deterministic ids so repeated ingestion overwrites instead of duplicating.*

This is worth doing from the start. Duplicate chunks are unpleasant to detect after the fact — search returns the same passage three times, which looks like a retrieval bug rather than an ingestion one.

Metadata values must be simple scalars: strings, numbers, or booleans. Nested dicts and lists aren't supported, so flatten before storing (`"tags": "python,web"` rather than a list).

---

## Searching

The basic search embeds the query and returns the closest documents:

```python
results = store.similarity_search("How much vacation do I get?", k=3)
for doc in results:
    print(doc.metadata["source"], "p.", doc.metadata["page"])
    print(doc.page_content[:80])
```

*Returns the three closest documents, each with its original text and metadata.*

To see how good the matches are, ask for scores:

```python
for doc, score in store.similarity_search_with_score(query, k=3):
    print(f"{score:.3f}  {doc.page_content[:60]}")
```

*Returns each match with its distance score — in Chroma, lower is closer.*

And when we already have a vector (from a cache, or from an earlier search), we can skip re-embedding with `similarity_search_by_vector`.

---

## Metadata Filtering

Filtering is where metadata earns its place. The `filter` argument restricts search to matching records *before* similarity is applied:

```python
results = store.similarity_search(
    "vacation policy",
    k=3,
    filter={"year": 2025},
)
```

*Searches only records whose `year` metadata equals 2025.*

Chroma uses a MongoDB-style operator syntax for anything beyond equality:

```python
# One of several values
filter={"source": {"$in": ["handbook.pdf", "policies.pdf"]}}

# Numeric comparison
filter={"page": {"$gte": 10}}

# Multiple conditions
filter={"$and": [{"year": 2025}, {"source": "handbook.pdf"}]}
```

*Restricts search using set membership, numeric comparison, and combined conditions.*

The available operators are `$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte`, `$in`, `$nin`, `$and`, and `$or`. There's also a separate `where_document` argument for substring matching on the text itself, which is occasionally useful for exact identifiers that embeddings handle poorly.

One behavior to expect: a filter narrows the candidate pool, so an aggressive filter can return fewer than `k` results, or none at all. That's usually correct — but it means filtered searches need the same "did we get anything?" check as any other.

---

## Updating and Deleting

Stable ids make maintenance possible:

```python
store.update_document(document_id="handbook.pdf-p4", document=revised_doc)
store.delete(ids=["handbook.pdf-p9"])
```

*Replaces one record and removes another by id.*

Re-ingesting a changed source file is the common case, and it needs care: if the new version splits into fewer chunks than the old one, the leftover chunks from the previous run stay behind and keep surfacing in search. The reliable pattern is delete-then-insert by source:

```python
store.delete(where={"source": "handbook.pdf"})   # clear the old chunks first
store.add_documents(new_chunks, ids=new_ids)
```

*Removes every chunk from a source before re-adding it, avoiding stale leftovers.*

---

## Chroma in Context

Chroma is one of several options, and the choice is mostly about deployment:

| Store | Runs as | Good for |
|---|---|---|
| **Chroma** | Embedded library or local server | Development, small-to-mid corpora, teaching |
| **FAISS** | In-process library | Fast local experiments; no metadata filtering or persistence built in |
| **pgvector** | Postgres extension | Teams already on Postgres who want one database |
| **Pinecone / Weaviate / Qdrant** | Managed or self-hosted service | Production scale, high concurrency |

They all expose the same LangChain `VectorStore` interface, so swapping one for another is usually a constructor change. That portability is a real benefit of going through LangChain rather than Chroma's client directly.

---

## Key Takeaways

- A vector store keeps four things per record: an id, the embedding, the original text, and metadata.
- We search by the embedding but get back the text and metadata — that's what makes results usable and citable.
- `Chroma(collection_name=..., embedding_function=..., persist_directory=...)` opens a persistent local collection; without a directory it's in-memory only.
- `add_documents` embeds and stores; `from_documents` creates and loads in one step, but is additive.
- Supply stable ids so re-running ingestion updates in place instead of duplicating.
- Metadata values must be scalars; they power filtering and source citation.
- `filter` uses MongoDB-style operators and applies before similarity, so it can return fewer than `k` results.
- Re-ingesting a changed file should delete the old chunks by source first, or stale chunks linger in search.
- A collection is bound to the embedding model that built it — changing models means rebuilding.

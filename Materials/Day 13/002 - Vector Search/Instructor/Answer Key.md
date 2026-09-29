# Vector Search — Answer Key

Mirrors `Review/Reading Questions.md` exactly: same sections, same order, same numbering.

---

## Embeddings

**Q1. What does an embedding let us do that keyword search structurally cannot?**

**A:** Match on **meaning** rather than characters.

- Keywords miss: "python programming" vs "coding in python" — nearly the same meaning, one shared word. Embeddings score these close.
- Keywords falsely match: "python programming" vs "python snake" — one shared word, unrelated meaning. Embeddings score these far apart.

*Discussion:* Both directions matter. Associates usually grasp the first and miss the second, but disambiguation-by-context is what makes semantic search usable on real corpora.

---

**Q2. Three words vs three hundred — what comes back, and why does that matter?**

**A:** The same fixed length both times (768 with `nomic-embed-text`). Length is set by the **model**, not the text.

That uniformity is what makes every piece of text a point in the *same* space, which is the precondition for comparing any two of them. Without it there'd be nothing to measure.

---

**Q3. Can we interpret dimension 400? What follows?**

**A:** No. No single dimension corresponds to a readable attribute — meaning is distributed across all of them at once. Consequently the **only** useful operation is comparing one whole vector against another. Inspecting, slicing, or thresholding individual components is meaningless.

---

**Q4. Why does LangChain separate `embed_query` and `embed_documents`?**

**A:** Two reasons. (1) `embed_documents` takes a list and **batches**, which is substantially faster — use it for ingestion. (2) Some models are **asymmetric**: trained to encode a short question differently from a long passage, with different internal prefixes applied by each method.

```python
doc_vectors = embeddings.embed_documents(docs)   # ingestion
query_vector = embeddings.embed_query(question)  # search
```

Calling the wrong one usually still works, just slightly worse.

---

**Q5. The one rule that poisons a whole system when broken?**

**A:** **Documents and queries must be embedded by the same model.** Vectors from different models live in unrelated coordinate systems.

It presents as a **silent** failure — no error, no exception, just results that are quietly wrong. Search still returns its `k` results with plausible-looking scores. The only fix is **re-embedding the entire collection**.

*Discussion:* Practical consequences worth stating: pin the model name in config next to the DB path; switching models means a full rebuild; two collections built with different models can never be merged or searched together. "Did the embedding model change?" is the first question when a working RAG system suddenly degrades.

---

**Q6. What does determinism enable, and what does `namespace` protect against?**

**A:** **Caching.** Same text + same model always yields the same vector, so cached embeddings never go stale and re-embedding unchanged text on every run is pure waste.

```python
cached = CacheBackedEmbeddings.from_bytes_store(
    embeddings, LocalFileStore("./embedding_cache"), namespace=embeddings.model
)
```

`namespace` keys the cache **by model**, so switching models doesn't serve stale vectors from the previous one — which would be exactly the silent failure in Q5, self-inflicted.

*Note:* `CacheBackedEmbeddings` and `LocalFileStore` are in `langchain-classic` as of LangChain 1.x.

---

**Q7. Three things embeddings are bad at, and what to do instead.**

**A:** Any three of:

| Weakness | Why | Do instead |
|---|---|---|
| **Negation** | "is running" and "is not running" embed close; similarity is topical, not logical | Don't rely on retrieval to distinguish; handle in generation or with structured data |
| **Exact identifiers** | Order `A-4471` isn't semantically distinctive | Metadata filter, `where_document` substring match, or a regular database |
| **Long undivided text** | A whole document averages to a vector matching nothing specific | Chunk it (the core argument for the next unit) |
| **Ranking truth** | Nearest = most *similar*, not most correct or most recent | Metadata filters on date/version |

---

## Similarity Search

**Q8. Cosine vs Euclidean — what each measures, and which direction is "similar"?**

**A:** **Cosine similarity** measures the *angle* between vectors, ignoring magnitude — it compares direction, i.e. what the text is about. Range −1 to 1, **higher is more similar**.

**Euclidean (L2) distance** measures straight-line distance, accounting for magnitude. Range 0 upward, **lower is more similar**, 0 = identical.

*Discussion:* That inversion is where most misread scores come from. Also worth noting: for **normalized** vectors, dot product and cosine rank identically, which is why many models normalize — the cheaper dot product becomes a free substitute.

---

**Q9. Is 0.45 cosine "moderately relevant"?**

**A:** No — it usually means **not relevant at all**. Text embeddings rarely drop below about 0.2 because nearly any two English sentences share some structure. The usable band is compressed near the top.

Rough guide: `1.0` identical, `~0.8` strongly related, `~0.5` loosely related at best, `0.0` unrelated.

*Discussion:* Associates consistently over-read mid-range scores. The embeddings lab has them score an obviously-unrelated pair and see it land around 0.3–0.5, which fixes the intuition fast.

---

**Q10. Steps from query to results?**

**A:** (1) Embed the query. (2) Compare that vector against stored vectors. (3) Sort by score. (4) Return the top `k`.

A vector database does exactly this, plus indexing so step 2 doesn't touch every vector.

---

**Q11. Cooking corpus, Kubernetes query — what comes back?**

**A:** The `k` recipes with the highest scores. **Top-k always returns `k` results.** There is no "no match" state.

Therefore: **a non-empty result list proves nothing about relevance.** Any code branching on `if results:` is checking the wrong thing — it needs a score threshold.

---

**Q12. Too-small vs too-large `k`, and why more isn't better?**

**A:** Too small (1–3): high precision, but if the relevant chunk isn't in those, the answer is unrecoverable. Too large (10+): high recall, but fills the context window and buries the good chunk among mediocre ones.

More context isn't better because models attend **less reliably to the middle of a long prompt** — ten mediocre chunks often produce a worse answer than three good ones. 4–6 is the usual RAG default.

---

**Q13. What kind of number does `similarity_search_with_score` return?**

**A:** A **distance** — **lower is closer**. Not a similarity.

It's easy to get backwards because the sibling concept (cosine) runs the other way, so a threshold written in the wrong direction **silently filters out the good results and keeps the bad ones** — no error, just quietly inverted behavior.

*Discussion:* `similarity_search_with_relevance_scores` normalizes to 0–1 where higher is better, if that's easier to reason about. The chunking lab surfaces real distances (~2.1) so associates see these aren't 0–1 similarities.

---

**Q14. Why can't we look up a good threshold?**

**A:** The useful cutoff varies by **embedding model** and by **corpus**. There's no portable number.

The method: run known-good and known-bad queries against the actual store, print the scores, and set the cutoff between the two clusters. Do this before writing any threshold into code.

---

**Q15. Approximate (HNSW) search — tradeoff and when it explains a surprise?**

**A:** Exact search compares against every vector — correct but linear, fine for thousands, too slow for millions. **ANN** (HNSW in Chroma) builds a navigable graph so a query touches a small fraction of vectors.

Tradeoff: it's *approximate* — a true nearest neighbor is occasionally missed, in exchange for speed that holds as the collection grows.

It's a candidate explanation for "why didn't this obviously-relevant chunk come back?" beyond embedding quality. At training-corpus scale it's invisible and defaults are correct.

---

**Q16. Four near-duplicate results — name, cost, fix?**

**A:** **Redundancy.** We've spent the entire context budget on one fact and retrieved nothing else — the prompt is full but the information is thin.

Fix is **Maximal Marginal Relevance (MMR)**: take the best match, then pick each subsequent result for being relevant *and* different from what's already selected.

```python
store.max_marginal_relevance_search(query, k=4, fetch_k=20, lambda_mult=0.5)
```

Covered properly in Retriever Design; introduced here because it's the first real limitation of plain top-k.

---

## Vector Databases

**Q17. Four parts of a record; search by vs get back?**

**A:** **id**, **embedding**, **document** (original text), **metadata**.

We search **by** the embedding; we get **back** the document plus metadata. That split is the whole design — nobody wants floats returned from a search, they want the text those floats represent plus enough context to cite it.

---

**Q18. Three problems a vector DB solves over a Python list?**

**A:** (1) **Persistence** — vectors survive process exit. (2) **Indexing** — search doesn't compare against every vector, so it stays fast at scale. (3) **Associated data** — somewhere to keep the original text and metadata alongside each vector.

---

**Q19. The three constructor arguments, and omitting `persist_directory`?**

**A:**

```python
store = Chroma(
    collection_name="handbook",
    embedding_function=embeddings,
    persist_directory="./chroma_db",
)
```

- `collection_name` — a named, fully isolated partition; also implicitly bound to the embedding model that built it.
- `embedding_function` — the model Chroma calls to embed anything added or searched. We hand it the model, not vectors.
- `persist_directory` — where it writes to disk.

Omit `persist_directory` and the store is **in-memory only**, gone at process exit. (That's deliberate and useful while experimenting — the retrieval lab does exactly this so every run starts clean.) Recent `langchain-chroma` persists automatically; there's no separate `.persist()` call.

---

**Q20. Ran ingestion twice, now duplicates. What happened?**

**A:** Without explicit `ids`, every `add_documents` call generates **fresh random ids**, so the second run added the whole corpus again rather than overwriting.

```python
ids = [f"{d.metadata['source']}-p{d.metadata['page']}" for d in docs]
store.add_documents(docs, ids=ids)      # idempotent
```

*Discussion:* Do this from the start. Duplicates are nasty to detect after the fact — search returning the same passage three times looks like a retrieval bug, not an ingestion one. `Chroma.from_documents` is also additive; convenient for a first load, duplicating on a second.

---

**Q21. Metadata constraints, and why inconsistency breaks filtering?**

**A:** Values must be **simple scalars** — strings, numbers, booleans. Nested dicts and lists are rejected, so flatten (`"tags": "python,web"` rather than a list).

Keys must be **consistent** across the corpus. A filter on `{"year": 2025}` silently skips every document where the field was spelled `date`, or omitted. Silently — the search succeeds and just returns less.

---

**Q22. Two consequences of filters applying before similarity?**

**A:** (1) An aggressive filter can return **fewer than `k` results, or none** — so filtered searches need the same "did we get anything?" check as any other. (2) A filter on a key some documents lack **excludes those documents entirely**, which is why Q21's consistency requirement has teeth.

```python
filter={"$and": [{"year": 2025}, {"source": "handbook.pdf"}]}
```

Operators: `$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte`, `$in`, `$nin`, `$and`, `$or`.

---

**Q23. Re-ingesting a changed document — why isn't `add_documents` enough?**

**A:** If the new version splits into **fewer chunks** than the old one, the surplus chunks from the previous run stay behind and keep surfacing in search — stale content presented as current.

```python
store.delete(where={"source": "handbook.pdf"})   # clear old chunks first
store.add_documents(new_chunks, ids=new_ids)
```

Delete-by-source, then insert. Stable ids alone don't cover this case.

---

**Q24. Same interface across stores — benefit and what drives the choice?**

**A:** Benefit: **portability**. Swapping stores is usually a constructor change, since they all implement LangChain's `VectorStore` interface. That's a real argument for going through LangChain rather than Chroma's client directly.

The choice is driven mostly by **deployment**: Chroma (embedded, dev and small-to-mid corpora), FAISS (in-process, fast, no metadata filtering or built-in persistence), pgvector (teams already on Postgres), Pinecone/Weaviate/Qdrant (managed, production scale and concurrency).

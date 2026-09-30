# Retriever Design

A **retriever** is the component that takes a question and returns relevant documents. It sits between the vector store and the prompt, and its configuration decides what the model gets to see.

This is where most RAG tuning happens. A store can hold exactly the right chunk and still fail to surface it, and when that happens the answer cannot be correct no matter how good the prompt is.

---

## The Retriever Interface

A retriever is a runnable with one job — question in, documents out:

```python
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings

store = Chroma(persist_directory="./chroma_db",
               embedding_function=OllamaEmbeddings(model="nomic-embed-text"))

retriever = store.as_retriever(search_kwargs={"k": 4})

docs = retriever.invoke("How much PTO do employees accrue?")
```

*Creates a retriever over the store and fetches the four closest chunks for a question.*

The value of this being a standard interface is substitutability. A vector store retriever, a keyword retriever, a web search retriever, and a hybrid of several all look identical from the outside, so swapping strategies doesn't disturb the chain around them.

`as_retriever()` takes two arguments worth knowing: `search_type`, which picks the algorithm, and `search_kwargs`, a dict of options for it.

---

## Search Types

### `similarity` — the default

Plain top-k by vector distance. Fast, predictable, and always returns exactly `k` results:

```python
retriever = store.as_retriever(search_kwargs={"k": 4})
```

*Returns the four nearest chunks, regardless of how relevant they are.*

### `mmr` — relevance with diversity

**Maximal Marginal Relevance** fixes the redundancy problem. Plain similarity search on a corpus that repeats a point in four places returns all four near-identical chunks, spending the whole context budget on one fact.

MMR fetches a wider candidate pool, then selects results that are relevant *and* different from what's already picked:

```python
retriever = store.as_retriever(
    search_type="mmr",
    search_kwargs={"k": 4, "fetch_k": 20, "lambda_mult": 0.5},
)
```

*Considers 20 candidates and selects 4 that are relevant but distinct from each other.*

Three parameters:

- **`k`** — how many to return.
- **`fetch_k`** — how many candidates to consider before diversifying. Larger means more room to find variety; 4–5× `k` is a reasonable starting point.
- **`lambda_mult`** — the balance, from `1.0` (pure relevance, identical to similarity search) to `0.0` (pure diversity). `0.5` is a balanced default; `0.7` leans toward relevance.

MMR is usually the better default for RAG over any corpus with repetition — which is most real corpora.

### `similarity_score_threshold` — allowing "nothing"

Both search types above always return `k` results, however bad. When "we have nothing relevant" needs to be a possible outcome, use a threshold:

```python
retriever = store.as_retriever(
    search_type="similarity_score_threshold",
    search_kwargs={"k": 4, "score_threshold": 0.5},
)
docs = retriever.invoke("What is the airspeed velocity of a swallow?")
# [] — nothing cleared the bar
```

*Returns only chunks above a relevance score, possibly none at all.*

This returns an empty list when nothing qualifies, which lets the application say "I don't have information about that" instead of asking the model to answer from four irrelevant chunks.

The threshold value has to be calibrated against the actual corpus and embedding model — there's no portable number. Run a handful of known-good and known-bad queries, print the scores, and set the cutoff between the two clusters. Note also that this search type uses a normalized relevance score where **higher is better**, which is the opposite direction from the raw distance that `similarity_search_with_score` returns.

---

## Metadata Filtering

Filters narrow the candidate pool before similarity is applied — the retrieval equivalent of a `WHERE` clause:

```python
retriever = store.as_retriever(
    search_kwargs={"k": 4, "filter": {"department": "HR"}}
)
```

*Searches only chunks whose `department` metadata is "HR".*

Chroma supports MongoDB-style operators for anything beyond equality:

```python
search_kwargs={"k": 4, "filter": {"year": {"$gte": 2024}}}

search_kwargs={"k": 4, "filter": {
    "$and": [{"doc_type": "policy"}, {"department": {"$in": ["HR", "Legal"]}}]
}}
```

*Filters by numeric comparison, and by combining multiple metadata conditions.*

Filtering is frequently the highest-leverage fix available. Semantic similarity alone has no notion of recency or ownership — it will happily return a superseded 2019 policy that reads almost identically to the current one. A filter makes that structurally impossible, where prompt instructions only make it less likely.

Two behaviors to expect. An aggressive filter can return fewer than `k` results or none, so the empty case needs handling. And a filter on a key some documents lack excludes those documents entirely, which is why consistent metadata at load time matters.

### Filters Chosen at Query Time

Filters often depend on the user, so building the retriever per request is normal:

```python
def make_retriever(user_id: str, year: int | None = None):
    conditions = [{"owner": user_id}]
    if year:
        conditions.append({"year": year})
    flt = conditions[0] if len(conditions) == 1 else {"$and": conditions}
    return store.as_retriever(search_kwargs={"k": 4, "filter": flt})
```

*Builds a retriever whose filter is assembled from the current request's context.*

For multi-tenant data this is a security boundary, not a convenience. The filter is what stops one user's question from retrieving another user's documents — it belongs in code, derived from the authenticated session, never in anything the model or the user can influence.

---

## Diagnosing Retrieval

When RAG answers are wrong, inspect retrieval before touching anything else:

```python
docs = retriever.invoke(question)
for d in docs:
    print(f"[{d.metadata.get('source')} p.{d.metadata.get('page')}]")
    print(d.page_content[:200], "\n")
```

*Prints what the retriever actually returned, with sources, before it reaches the prompt.*

If the answer isn't in that output, the problem is upstream and no prompt change will fix it. Common patterns:

| Symptom | Likely cause | Fix |
|---|---|---|
| Right topic, wrong detail | Chunks too large — signal diluted | Smaller chunks |
| Chunks cut mid-thought | Chunk size or overlap too small | More overlap; pull neighbors by `chunk_index` |
| Same passage repeated | Redundant corpus | Switch to MMR |
| Outdated or wrong-scope results | No filtering | Add a metadata filter |
| Nothing relevant at all | Vocabulary mismatch, or it isn't in the corpus | Check the corpus; consider hybrid search |
| Right chunk retrieved, answer still wrong | Generation problem | Now look at the prompt |

That last row is the one to remember — it's the only case where prompt engineering is the right response.

---

## Beyond the Basics

Three techniques worth knowing by name, for when tuning `k`, `search_type`, and filters isn't enough.

**Multi-query retrieval** asks the model to rewrite the question several ways, retrieves for each, and unions the results. It handles the case where the user's phrasing doesn't match the corpus's vocabulary:

```python
from langchain_classic.retrievers.multi_query import MultiQueryRetriever

retriever = MultiQueryRetriever.from_llm(
    retriever=store.as_retriever(search_kwargs={"k": 3}), llm=llm
)
```

*Generates several phrasings of the question and merges what each one retrieves.*

As of LangChain 1.x this lives in the separate `langchain-classic` package (`pip install langchain-classic`).

**Contextual compression** retrieves generously, then uses a model to strip the irrelevant parts from each chunk before they reach the prompt. It buys precision at the cost of extra model calls.

**Hybrid search** combines vector similarity with keyword (BM25) matching. It's the standard answer for corpora full of exact identifiers — product codes, error numbers, names — which embeddings handle poorly.

All three cost extra latency or model calls. Reach for them after the basics are tuned, not instead of tuning them.

---

## Key Takeaways

- A retriever turns a question into documents; `store.as_retriever(search_type=..., search_kwargs=...)` configures it.
- `similarity` is plain top-k and always returns `k` results, relevant or not.
- `mmr` balances relevance against diversity via `fetch_k` and `lambda_mult` — usually the better RAG default.
- `similarity_score_threshold` can return nothing, which is what lets an app say "I don't know"; calibrate the threshold against the real corpus.
- Metadata filters apply before similarity and are often the highest-leverage fix; for multi-tenant data they're a security boundary set in code.
- Print retrieved chunks before debugging prompts — most wrong answers are retrieval failures.
- Multi-query, contextual compression, and hybrid search are the next steps once `k`, search type, and filters are tuned.

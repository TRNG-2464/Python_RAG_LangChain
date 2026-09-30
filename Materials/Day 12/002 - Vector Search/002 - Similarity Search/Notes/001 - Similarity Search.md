# Similarity Search

Embeddings give us points in space. **Similarity search** is what we do with them: measure how close a query's vector is to every stored vector, then return the closest ones.

The mechanics are simple arithmetic. What takes practice is reading the scores correctly and knowing why the search returned what it did.

---

## Measuring Distance

Three metrics cover essentially all vector search. The one a database uses is a configuration choice, and it changes what the numbers mean.

### Cosine Similarity

**Cosine similarity** measures the angle between two vectors, ignoring their length. It's the default for text because it compares *direction* — what the text is about — rather than magnitude, which is influenced by things like text length.

```python
import numpy as np

def cosine_similarity(a, b):
    a, b = np.array(a), np.array(b)
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
```

*Computes the cosine of the angle between two vectors.*

The range is −1 to 1, and **higher is more similar**:

| Value | Meaning |
|---|---|
| `1.0` | Identical direction — same meaning |
| `~0.8` | Strongly related |
| `~0.5` | Loosely related, same general topic |
| `0.0` | Unrelated |
| `< 0` | Opposing direction (rare with text embeddings) |

In practice, text embeddings rarely go below about 0.2 — nearly any two English sentences share some structure. This is the single most common surprise: a score of 0.45 does not mean "moderately relevant," it usually means "not relevant at all."

### Euclidean Distance (L2)

**Euclidean distance** is straight-line distance between the two points. It accounts for magnitude as well as direction.

```python
def euclidean_distance(a, b):
    return np.linalg.norm(np.array(a) - np.array(b))
```

*Computes straight-line distance between two vectors.*

Range is 0 upward, and **lower is more similar** — 0 means identical. That inversion relative to cosine is where most misread scores come from.

### Dot Product

The **dot product** multiplies corresponding elements and sums them, factoring in both direction and magnitude. Higher is more similar. For **normalized** vectors (length 1), the dot product and cosine similarity are the same number — which is why many embedding models normalize their output, making the cheaper dot product a free substitute for cosine.

### Which to Use

For text embeddings, cosine is the right default and what most vector databases use unless told otherwise. If a model emits normalized vectors, cosine and dot product rank results identically, so the choice only affects the numbers you read, not the order you get back.

---

## Top-k Retrieval

Search doesn't return everything above some threshold. It returns the **top k** — the k closest vectors, ranked. The algorithm is:

```
1. Embed the query
2. Compare the query vector to every stored vector
3. Sort by score
4. Return the top k
```

Written out directly, to make the mechanism concrete:

```python
from langchain_ollama import OllamaEmbeddings
import numpy as np

embeddings = OllamaEmbeddings(model="nomic-embed-text")

corpus = [
    "Python is a high-level programming language.",
    "Snakes are legless reptiles found on every continent except Antarctica.",
    "Django is a web framework written in Python.",
    "The recipe calls for two cups of flour.",
]
corpus_vectors = embeddings.embed_documents(corpus)
query_vector = embeddings.embed_query("web development tools")

scores = [cosine_similarity(query_vector, v) for v in corpus_vectors]
ranked = sorted(zip(scores, corpus), reverse=True)

for score, text in ranked[:2]:
    print(f"{score:.3f}  {text}")
```

*Embeds a small corpus and a query, scores every document, and prints the two closest.*

This is exactly what a vector database does — just with indexing so it doesn't have to compare against every vector.

**Top-k always returns k results.** There's no notion of "no match." Query a cooking corpus for "Kubernetes networking" and it will cheerfully return the three recipes with the highest scores. Those scores will be low, but something always comes back. Any code that assumes a result exists because the list isn't empty is wrong.

### Choosing k

`k` is a precision/recall dial:

- **Small k (1–3):** high precision, risk of missing the relevant chunk entirely.
- **Medium k (4–6):** the usual default for RAG — enough coverage without flooding the prompt.
- **Large k (10+):** high recall, but fills the context window and can bury the right answer among mediocre ones.

More context is not automatically better. Models attend less reliably to the middle of a long prompt, so ten mediocre chunks often produce a worse answer than three good ones.

---

## Filtering by Score

When "nothing relevant" needs to be a possible outcome, we apply a score threshold ourselves:

```python
from langchain_chroma import Chroma

store = Chroma(persist_directory="./chroma_db", embedding_function=embeddings)

results = store.similarity_search_with_score("web development tools", k=4)
for doc, score in results:
    print(f"{score:.3f}  {doc.page_content[:60]}")
```

*Returns each match alongside its score so we can decide what's good enough.*

The critical detail: **`similarity_search_with_score` in Chroma returns a distance, where lower is better** — not a similarity where higher is better. A threshold written the wrong way round silently filters out the good results and keeps the bad ones.

The safe habit is to print scores for known-good and known-bad queries against the actual store before writing any threshold. Two reasons: the direction is easy to get backwards, and the useful cutoff varies by embedding model and corpus. There is no universal magic number. Chroma also exposes `similarity_search_with_relevance_scores`, which normalizes to a 0–1 scale where higher is better, if that's easier to reason about.

---

## Exact vs. Approximate Search

Comparing a query against every vector is **exact search**. It's correct and it's linear — fine for thousands of vectors, too slow for millions.

Production vector databases use **approximate nearest neighbor (ANN)** search instead. Chroma uses **HNSW**, which builds a navigable graph so a query only touches a small fraction of the vectors. The tradeoff is in the name: approximate. A true nearest neighbor is occasionally missed, in exchange for search that stays fast as the collection grows.

At training-corpus scale this is invisible, and the default settings are the right settings. It's worth knowing the tradeoff exists so that "why didn't this obviously-relevant chunk come back?" has a candidate explanation beyond embedding quality.

---

## When Similar Isn't Useful

Pure top-k has a failure mode that shows up constantly in RAG: **redundancy**. If a document repeats a point in four places, a query about that point returns all four near-duplicate chunks. We've spent our entire context budget on one fact and retrieved nothing else.

**Maximal Marginal Relevance (MMR)** addresses this by balancing relevance against diversity. It takes the best match, then picks each subsequent result for being relevant *and* different from what's already selected:

```python
results = store.max_marginal_relevance_search(
    "web development tools",
    k=4,             # results to return
    fetch_k=20,      # candidates to consider before diversifying
    lambda_mult=0.5, # 1.0 = pure relevance, 0.0 = pure diversity
)
```

*Retrieves a diverse set by considering 20 candidates and selecting 4 that are relevant but distinct.*

MMR is covered properly in the Retriever Design notes. The reason to meet it here is that it's the direct answer to the first real limitation of plain similarity search.

---

## Key Takeaways

- Similarity search embeds the query, scores it against stored vectors, and returns the closest k.
- Cosine similarity compares direction and is the default for text — higher is more similar, and realistic scores rarely fall below ~0.2.
- Euclidean distance inverts that: lower is more similar. Always confirm which direction a given API returns.
- For normalized vectors, dot product and cosine rank identically.
- Top-k always returns k results regardless of quality — "no relevant match" requires an explicit score threshold.
- Chroma's `similarity_search_with_score` returns a distance (lower is better); calibrate thresholds against real queries rather than guessing.
- Production stores use approximate (HNSW) search, trading occasional missed neighbors for speed at scale.
- Plain top-k returns redundant near-duplicates; MMR trades some relevance for diversity.

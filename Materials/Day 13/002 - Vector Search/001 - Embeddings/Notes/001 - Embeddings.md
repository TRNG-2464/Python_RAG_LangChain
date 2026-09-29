# Embeddings

Keyword search matches characters. Ask it for "car" and it will miss every document that says "automobile," "vehicle," or "sedan." That's the gap **embeddings** close: they convert text into a list of numbers positioned so that text with similar *meaning* ends up close together in space.

Once meaning is a position, "find related text" becomes "find nearby points" — an ordinary geometry problem that computers are very good at. Embeddings are the foundation of everything in the rest of this subject.

---

## Text In, Vector Out

An **embedding model** takes a piece of text and returns a fixed-length list of floats, called a **vector** or **embedding**:

```python
from langchain_ollama import OllamaEmbeddings

embeddings = OllamaEmbeddings(model="nomic-embed-text")

vector = embeddings.embed_query("The cat sat on the mat.")
print(len(vector))     # 768 — the model's dimensionality
print(vector[:5])      # [0.021, -0.147, 0.066, 0.009, -0.052]
```

*Converts a single string into its vector representation using a local Ollama embedding model.*

The length is fixed by the model, not the text. A three-word sentence and a three-hundred-word paragraph both come out as 768 numbers with `nomic-embed-text`. That's what makes them comparable — every piece of text becomes a point in the same space.

The individual numbers mean nothing we can read. No single dimension is "formality" or "topic." Meaning is encoded across all 768 of them at once, and the only useful operation is comparing one vector to another.

---

## Why Nearby Means Similar

Embedding models are trained on enormous amounts of text with an objective that pulls related passages together and pushes unrelated ones apart. The result is a space with a useful property:

```
   "python programming"  ●
   "coding in python"     ● ← very close, nearly the same meaning
   "software development" ●  ← close, related field

   "python snake"            ● ← far from the above, despite sharing a word
   "banana bread recipe"           ● ← far from everything here
```

Two things are worth noticing in that sketch. "Python programming" and "coding in python" land near each other despite sharing only one word — that's semantic matching doing its job. And "python snake" lands far away despite sharing a word with the top cluster, because the model reads the word in context.

This is what keyword search cannot do, in either direction.

---

## Embedding Documents vs. Queries

LangChain's embedding interface has two methods, and the distinction matters:

```python
docs = [
    "LangChain is a framework for building LLM applications.",
    "Chroma is an open-source vector database.",
    "Ollama runs language models locally.",
]

doc_vectors = embeddings.embed_documents(docs)    # list[list[float]] — one per doc
query_vector = embeddings.embed_query("How do I run a model on my laptop?")
```

*Embeds a batch of documents for storage and a single query for searching.*

`embed_documents` takes a list and batches the work, which is substantially faster than looping over `embed_query`. Use it for ingestion.

Some embedding models are **asymmetric** — they're trained to encode a short question differently from a long passage, and the two methods apply different internal prefixes. That's why LangChain separates them even though both return vectors. Calling the wrong one usually still works, just slightly worse.

---

## The Rule That Breaks Everything When Broken

**Documents and queries must be embedded by the same model.** Vectors from different models live in unrelated coordinate systems — comparing them produces numbers that look plausible and mean nothing.

This fails silently, which is what makes it dangerous. Search doesn't error; it just returns bad results. If a working RAG pipeline suddenly starts returning nonsense, "did the embedding model change?" is the first question to ask. Re-embedding the entire collection is the only fix.

Practical consequences:

- Pin the embedding model name in configuration, next to the database path.
- Switching models means rebuilding the store from scratch.
- Two collections built with different models cannot be merged or searched together.

---

## Choosing a Model

Embedding models trade off quality, speed, and size. A few running locally under Ollama:

| Model | Dimensions | Notes |
|---|---|---|
| `nomic-embed-text` | 768 | Strong general-purpose default; handles long inputs well |
| `mxbai-embed-large` | 1024 | Higher quality, slower, larger index |
| `all-minilm` | 384 | Small and fast; good when volume matters more than precision |

Higher dimensionality generally means more nuance captured, at the cost of more storage and slower comparison. For a training-scale corpus, any of these is fine — `nomic-embed-text` is a reasonable default.

Two properties worth knowing about the models themselves. They have an **input limit** (a maximum number of tokens); text beyond it is silently truncated, which is one of the reasons we chunk documents before embedding. And they're **deterministic** — the same text through the same model always produces the same vector, which is why caching embeddings is safe and worthwhile.

---

## Cost, Latency, and Batching

Embedding is not free. Each call runs a neural network, and ingesting a thousand chunks means a thousand forward passes. Locally, that's CPU or GPU time; hosted, it's a per-token bill.

Two habits keep this manageable:

```python
# Slow — one model call per chunk
vectors = [embeddings.embed_query(c) for c in chunks]

# Fast — batched in a single pass
vectors = embeddings.embed_documents(chunks)
```

*Contrasts per-item embedding with batched embedding of the same chunks.*

And because embeddings are deterministic, caching avoids re-embedding unchanged text on every run:

```python
from langchain_classic.embeddings import CacheBackedEmbeddings
from langchain_classic.storage import LocalFileStore

cached = CacheBackedEmbeddings.from_bytes_store(
    embeddings, LocalFileStore("./embedding_cache"), namespace=embeddings.model
)
```

*Wraps the embedding model with a disk cache keyed by text and model name.*

As of LangChain 1.x both of these live in the separate `langchain-classic` package (`pip install langchain-classic`) rather than the main `langchain` package.

The `namespace` argument is doing quiet but important work — it keys the cache by model, so switching models doesn't serve stale vectors from the previous one.

---

## What Embeddings Don't Do

Being clear about the limits prevents a lot of confusion later:

- **They don't understand negation well.** "The server is running" and "the server is not running" often embed close together. Similarity is topical, not logical.
- **They're weak on exact identifiers.** Order number `A-4471` is not semantically distinctive. Exact-match lookups belong in metadata filters or a regular database, not vector search.
- **They lose detail in long text.** Embedding a whole ten-page document produces an average of everything in it, matching nothing specific. This is the core argument for chunking.
- **They're not a ranking of truth.** The nearest vector is the most *similar* text, not the most correct or most recent.

---

## Key Takeaways

- An embedding model converts text into a fixed-length vector; similar meanings land near each other in that space.
- Vector length is set by the model, not the text — that uniformity is what makes comparison possible.
- Individual dimensions aren't interpretable; only the relationship between vectors is useful.
- Use `embed_documents` for batches during ingestion and `embed_query` for searches.
- Documents and queries must use the same embedding model — mismatches fail silently, and the only fix is re-embedding everything.
- Embeddings are deterministic, so caching is safe; batch during ingestion to keep it fast.
- They capture topical similarity, not logic — negation, exact identifiers, and long undivided documents are all weak spots.

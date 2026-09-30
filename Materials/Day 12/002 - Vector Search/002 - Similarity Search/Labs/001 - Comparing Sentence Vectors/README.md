# Comparing Sentence Vectors

We'll turn sentences into vectors and measure how close they are, with no database involved. We'll cover `embed_query`, `embed_documents`, cosine similarity, and ranking a small corpus against a query.

## Prerequisites

| Software | Required Version |
|---|---|
| Python | >=3.10 |
| langchain-ollama | 1.1.0 |
| numpy | >=2.1 |
| Ollama | any current release, running locally |
| Ollama model | `nomic-embed-text` |

Setup, from this lab's directory:

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
ollama pull nomic-embed-text
```

Run it with `python src/main.py`.

---

## Guided walkthrough

Open `src/main.py`. The embedding model is set up and the parts are marked out.

### 1. Look at a vector

Add this under `# --- Part 1 ---`:

```python
v = embeddings.embed_query("The cat sat on the mat.")
print(type(v), len(v))
print(v[:5])
```

*Embeds one sentence and prints its length and first few values.*

Run it. We get 768 floats. The numbers don't mean anything individually — no single one is "topic" or "tone." Only the relationship between whole vectors is useful.

Try embedding a much longer sentence and check `len(v)` again. Still 768. Length is fixed by the model, not the text, and that's what makes any two pieces of text comparable.

### 2. Measure closeness

Cosine similarity compares the angle between two vectors. Add under `# --- Part 2 ---`:

```python
def cosine(a, b):
    a, b = np.array(a), np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
```

*Computes cosine similarity — 1.0 is identical direction, 0.0 is unrelated.*

### 3. Compare some pairs

Add under `# --- Part 3 ---`:

```python
pairs = [
    ("I love programming in Python", "Python coding is my favorite"),
    ("I love programming in Python", "Pythons are large snakes"),
    ("I love programming in Python", "The recipe calls for two eggs"),
]

for a, b in pairs:
    score = cosine(embeddings.embed_query(a), embeddings.embed_query(b))
    print(f"{score:.3f}  {a!r} vs {b!r}")
```

*Scores three sentence pairs against the same first sentence.*

Run it. The first pair scores high despite sharing almost no words — that's meaning being matched, not characters. The second scores lower despite sharing the word "Python," because the model reads it in context. The third is lowest.

Notice the third pair probably still scores somewhere around 0.3–0.5, not 0. Almost any two English sentences share some structure, so a middling score means "unrelated," not "somewhat related." Calibrating that expectation is the point of this part.

### 4. Embed a batch

For several texts at once, `embed_documents` is much faster than looping. Add under `# --- Part 4 ---`:

```python
corpus = [
    "Python is a high-level programming language.",
    "Django is a web framework written in Python.",
    "Snakes are legless reptiles.",
    "The recipe calls for two cups of flour.",
    "JavaScript runs in the browser.",
]

corpus_vectors = embeddings.embed_documents(corpus)
print(len(corpus_vectors), "vectors of length", len(corpus_vectors[0]))
```

*Embeds the whole corpus in one batched call.*

### 5. Rank against a query

This is similarity search, written out by hand. Add under `# --- Part 5 ---`:

```python
query = "web development tools"
query_vector = embeddings.embed_query(query)

scored = [(cosine(query_vector, v), text) for v, text in zip(corpus_vectors, corpus)]
scored.sort(reverse=True)

print(f"\nquery: {query!r}")
for score, text in scored:
    print(f"  {score:.3f}  {text}")
```

*Scores every document against the query and prints them ranked.*

Run it. Embed, compare, sort, take the top — that's everything a vector database does, minus the indexing that keeps it fast at scale.

### 6. Top-k always returns something

Add under `# --- Part 6 ---`:

```python
query_vector = embeddings.embed_query("How do I fix a bicycle tire?")
scored = [(cosine(query_vector, v), text) for v, text in zip(corpus_vectors, corpus)]
scored.sort(reverse=True)

print("\ntop 2 for a question the corpus can't answer:")
for score, text in scored[:2]:
    print(f"  {score:.3f}  {text}")
```

*Queries the corpus for something it has no answer to and takes the top two anyway.*

Run it. We still get two results. There's no such thing as "no match" — something is always closest. The scores are low, and that's the only signal we have. Any code that assumes a result exists because the list isn't empty is wrong.

---

## Exercises

1. **Find the threshold.** Using the corpus from Part 4, try several queries — some answerable, some not — and record the top score for each. Where would you draw a cutoff between "relevant" and "not"?

2. **Negation.** Score `"The server is running"` against `"The server is not running"`. Explain the result and what it implies for search.

3. **Identifiers.** Add `"Order A-4471 shipped on Tuesday."` to the corpus and query for `"A-4471"`. Does it rank first? Why is this a weak spot for embeddings?

4. **A different metric.** Write a `euclidean(a, b)` function using `np.linalg.norm(a - b)` and re-rank Part 5 with it. Does the order change? Remember lower is better for this one.

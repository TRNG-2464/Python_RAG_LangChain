# Vector Search — Reading Questions

Use these while reading this unit's notes. They follow the order of the material, so an answer you're hunting for is in the section you're currently reading. Each one points at something worth understanding well enough to explain to a teammate.

---

## Embeddings

1. Keyword search matches characters. What does an embedding let us do that keyword search structurally cannot — and give an example in each direction (a match keywords miss, and a false match keywords make).

2. We embed a three-word sentence and a three-hundred-word paragraph. What do we get back in each case, and why is that property the thing that makes comparison possible at all?

3. Can we look at dimension 400 of a vector and say what it represents? What does that tell us about the only useful operation on an embedding?

4. `embed_query` and `embed_documents` both return vectors. Why does LangChain separate them, and which should we use during ingestion?

5. What is the one rule about embedding models that, when broken, poisons an entire search system? Describe how that failure presents itself and what it costs to fix.

6. Embeddings are deterministic. What practical optimization does that enable, and what does the `namespace` argument protect us from when we use it?

7. Name three things embeddings are genuinely bad at. For each, say what we should do instead.

---

## Similarity Search

8. Cosine similarity and Euclidean distance both measure closeness. What does each actually measure, and — critically — which direction means "more similar" for each?

9. A search returns a result scoring 0.45 cosine similarity. Is that "moderately relevant"? Explain what realistic scores look like for text embeddings.

10. Walk through what happens between a user typing a query and getting results back. What are the steps?

11. We query a cooking corpus for "Kubernetes networking." What comes back? What does that tell us about any code that checks whether a result list is empty?

12. `k` is a precision/recall dial. What goes wrong at a too-small `k`, and what goes wrong at a too-large one? Why isn't more context automatically better?

13. Chroma's `similarity_search_with_score` returns a number. What kind of number is it, which direction is better, and why is this the single easiest thing to get backwards?

14. Why can't we just look up a "good" score threshold online and use it?

15. Production stores use approximate (HNSW) search rather than comparing against every vector. What's the tradeoff, and when might it explain a result we didn't expect?

16. A document repeats the same point in four places and our search returns all four. What's the name of this problem, what has it cost us, and what's the fix?

---

## Vector Databases

17. A vector store record has four parts. What are they, and which one do we search *by* versus which one we get *back*?

18. What three problems does a vector database solve that a Python list of vectors doesn't?

19. What does each of `collection_name`, `embedding_function`, and `persist_directory` do — and what happens if we omit the last one?

20. We run our ingestion script twice and search starts returning the same passage three times. What happened, and what's the fix?

21. What are the constraints on metadata values in Chroma, and why does inconsistent metadata across a corpus quietly break filtering later?

22. A filter narrows results *before* similarity is applied. What are two consequences of that ordering that our code needs to handle?

23. We edit a source document and re-ingest it. Why isn't re-running `add_documents` enough, and what's the reliable pattern?

24. Chroma, FAISS, pgvector, and Pinecone all expose the same LangChain interface. What practical benefit does that give us, and what mainly drives the choice between them?

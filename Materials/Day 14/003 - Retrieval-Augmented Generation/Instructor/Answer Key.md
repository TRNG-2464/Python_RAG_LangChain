# Retrieval-Augmented Generation — Answer Key

Mirrors `Review/Reading Questions.md` exactly: same sections, same order, same numbering.

---

## What Is RAG?

**Q1. RAG in one sentence, without "retrieval." What's the open-book analogy getting at?**

**A:** We search our own data for passages relevant to the question and paste them into the prompt, so the model answers *from that text* rather than from memory.

The analogy: we're handing the model the open book and asking it to read. **Nothing is taught and no weights change.** That reframing is what makes the rest of the unit make sense — every problem from here is about getting the right pages in front of it.

---

**Q2. RAG vs fine-tuning — the dividing line?**

**A:** **Knowledge versus behavior.** RAG is for what the model should *know*; fine-tuning is for how it should *behave* — tone, format, an output convention.

| | RAG | Fine-tuning |
|---|---|---|
| Adds new facts | Yes | Unreliably |
| Updating | Re-ingest the changed file | Retrain |
| Cost | Embedding + storage | GPU training runs |
| Citations | Natural | Impossible |
| Changes style/format | No | Yes |

Documents the model has never seen → **RAG, essentially every time.**

---

**Q3. The third option?**

**A:** Put **all** the data in the prompt. If the relevant corpus fits in the context window, no retrieval machinery is needed. RAG exists because most corpora don't.

*Discussion:* Worth raising — associates sometimes build a full RAG stack over a 4-page document. Context windows have grown enough that this is a genuine option more often than it used to be.

---

**Q4. The two pipelines?**

**A:** **Ingestion** (offline, reruns only when source data changes): load → split → embed → store. Slow, batch work.

**Query** (online, per question, must be fast): embed → retrieve → augment → generate.

They meet at the vector store. Keeping them mentally separate matters because they run at different times and fail in different ways.

---

**Q5. Two benefits, two new failure modes?**

**A:** Benefits (any two): current and private knowledge; citable sources; cheap updates; reduced hallucination.

Failure modes (any two):
- **Retrieval misses** — if the right chunk doesn't come back, the model cannot answer correctly. Most "the model got it wrong" reports are this.
- **Bad chunking** — a chunk splitting a table in half is retrieved and used anyway.
- **Multi-hop questions** — "which policy changed most between 2023 and 2025" needs reasoning across sources, not top-k similarity.
- **Aggregate questions** — "how many tickets last quarter" is a database query; RAG retrieves a few tickets and the model guesses.

*Discussion:* Stress that RAG *reduces* hallucination, doesn't eliminate it. A model can still misread a chunk or blend it with training knowledge.

---

**Q6. Wrong answer — what do we look at first?**

**A:** **The retrieved chunks.** Print them.

If the answer isn't in them, no amount of prompt engineering helps — the model never had the information. The problem is upstream, in chunking or retrieval.

*Discussion:* This is the single most valuable debugging habit in the unit and it recurs in Q25 and Q31. Worth stating three times.

---

## Document Loading

**Q7. Two attributes, and why the uniform shape matters?**

**A:** `page_content` (the text that gets embedded and shown to the model) and `metadata` (a flat dict of scalars that travels with it).

Every loader returns `list[Document]`, and every splitter and vector store consumes them. So a PDF, a web page, and a database row all become the same thing — **the rest of the pipeline doesn't care where the text came from.**

---

**Q8. Why explicit `encoding="utf-8"`?**

**A:** Without it Python uses the platform default, which on Windows is **not** UTF-8. Any file containing a smart quote, em dash, or accented character raises `UnicodeDecodeError`.

```python
docs = TextLoader("./notes/architecture.md", encoding="utf-8").load()
```

*Discussion:* Guaranteed to bite this cohort — it's a Windows shop and real documents are full of smart quotes. Called out in the chunking lab too.

---

**Q9. Why are PDFs the worst, and what do we do first?**

**A:** Extraction problems (any two): multi-column layouts get mangled; tables come out as scrambled runs of numbers; a **scanned PDF contains no extractable text at all** — it's an image and needs OCR.

**Always print a few loaded pages before building anything further.** Garbage extracted here is garbage embedded, retrieved, and answered from — and it's invisible three steps downstream.

`PyPDFLoader` does give one page per `Document` with page numbers in metadata, which is exactly what a citation needs.

---

**Q10. When `.lazy_load()`, and the second benefit?**

**A:** For large corpora — it yields documents one at a time instead of loading everything into memory.

Second benefit: **incremental progress.** If ingestion fails at file 900 of 1000, the first 899 are already stored rather than lost.

```python
for doc in loader.lazy_load():
    store.add_documents(splitter.split_documents([doc]))
```

---

**Q11. What depends on metadata, and why can't it be added later?**

**A:** **Citation** ("according to handbook.pdf, page 4" requires the page number to have survived the pipeline) and **filtering** ("only 2025 HR documents" requires `year` and `department` to be stored).

It can't be added later because **if it isn't attached at load time, it isn't in the store.** The chunks are already embedded and written; the provenance is gone.

Constraints: scalar values only, consistent keys across the corpus.

---

**Q12. Why clean, and what about near-empty documents?**

**A:** Loaded text carries noise — repeated page headers, scraped nav menus, form feeds, runs of blank lines. All of it gets embedded and **dilutes the vector**.

Near-empty documents (a scanned page, a failed parse) should be **dropped**:

```python
docs = [d for d in docs if len(d.page_content.strip()) > 50]
```

Because embedding them adds a meaningless vector that can still surface in search — a result that looks like a hit and contains nothing.

---

## Chunking Strategies

**Q13. Three reasons not to embed whole documents, plus the counter-pressure?**

**A:** (1) **Embeddings dilute** — a fixed-length vector averages everything in a 40-page document, sitting in the middle of "general HR topics" and close to nothing specific. (2) **Context windows are finite** — four whole documents won't fit in a prompt; four paragraphs will. (3) **Precision** — we want the paragraph that answers the question, not the document containing it.

Counter-pressure: chunks too small lose the context that makes them interpretable. *"It must be submitted within 30 days."* — what must be, and to whom? This is why it's a tradeoff, not "smaller is better."

---

**Q14. What does overlap solve, how much, and the cost of too much?**

**A:** Split points are arbitrary and sometimes land mid-thought. Overlap repeats the tail of the previous chunk so a boundary-spanning idea stays retrievable in at least one chunk.

**10–20% of chunk size** — ~100 characters for 800-character chunks.

Too much inflates the store and returns **near-duplicate chunks that waste the prompt** — the redundancy problem from the last unit, self-inflicted.

---

**Q15. The separator ladder and its effect?**

**A:** `"\n\n"` (paragraphs) → `"\n"` (lines) → `" "` (words) → `""` (raw characters).

It falls back only when a chunk is still too large, so it **prefers to break at a paragraph** and only cuts mid-word if a single word somehow exceeds the chunk size. That's what keeps chunks readable rather than guillotined at an arbitrary character count.

---

**Q16. `split_documents` vs `split_text`?**

**A:** `split_documents` takes and returns `Document` objects, **carrying metadata through**. `split_text` takes and returns raw strings and **loses metadata entirely**.

Consequence of the wrong choice: a store full of chunks that can't be cited or filtered — which, per Q11, can't be repaired without re-ingesting.

*Discussion:* Common enough mistake to be worth calling out explicitly. The chunking lab has associates verify metadata survived.

---

**Q17. When to split along structure, with an example?**

**A:** Whenever the source has structure worth preserving — character splitting is structure-blind and will cut a markdown doc mid-section or a Python file mid-function.

```python
md_splitter = MarkdownHeaderTextSplitter(
    headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3")])
```

Extra benefit: **the header hierarchy lands in each chunk's metadata** (`{'h1': 'Employee Handbook', 'h2': 'Time Off'}`), usable for both citation and filtering.

Standard pattern is header-split first, then recursive on the results, since one section can still be too long. For code, `from_language(Language.PYTHON, ...)` swaps in syntax-aware separators.

---

**Q18. What does `chunk_index` enable?**

**A:** Fetching **neighboring chunks** after retrieval. When a retrieved chunk is clearly cut off mid-thought, pull `chunk_index ± 1` and include them.

```python
for i, chunk in enumerate(chunks):
    chunk.metadata["chunk_index"] = i
```

It recovers context on demand without having to store larger chunks everywhere — precision in the index, context at read time.

---

**Q19. How do we actually decide size and overlap?**

**A:** **Empirically.** Print real chunks and look at them; there's no table to read the answer off.

Three things to check: (1) Are chunks cut mid-sentence in a way that destroys meaning? (2) Does each chunk make sense read on its own, without its neighbors? (3) Are there tiny orphan chunks — a heading with nothing under it — that should be merged?

Then test retrieval: ask a question with a known answer and print what comes back. If the right chunk isn't retrieved, **adjust chunking before the retriever, and long before the prompt.**

---

## Retriever Design

**Q20. Three search types and what each solves?**

**A:**
- `similarity` — plain top-k by distance. Fast, predictable, always returns exactly `k`.
- `mmr` — balances relevance against **diversity**; solves redundant near-duplicate results.
- `similarity_score_threshold` — can return **nothing**; solves the inability to say "no relevant match."

---

**Q21. MMR's three parameters; what does `lambda_mult=1.0` mean?**

**A:** `k` = how many to return. `fetch_k` = candidates considered before diversifying (4–5× `k` is a reasonable start). `lambda_mult` = the balance, `1.0` pure relevance → `0.0` pure diversity.

`lambda_mult=1.0` makes MMR **identical to plain similarity search**.

```python
store.as_retriever(search_type="mmr",
                   search_kwargs={"k": 4, "fetch_k": 20, "lambda_mult": 0.5})
```

MMR is usually the better RAG default, since most real corpora repeat themselves.

---

**Q22. Which type returns empty, and why does that matter?**

**A:** `similarity_score_threshold`. The other two always return `k` results however bad.

It matters because it lets the application say **"I don't have information about that"** instead of handing the model four irrelevant chunks and asking it to answer. It short-circuits to an honest response before generation.

The threshold must be calibrated against the real corpus and model. Note this type uses a **normalized relevance score where higher is better** — opposite direction from raw distance.

---

**Q23. Why is a filter structurally stronger than a prompt instruction?**

**A:** Semantic similarity has **no notion of recency, ownership, or version**. A superseded 2019 policy reads almost identically to the current one, so it scores just as well.

A filter makes retrieving it **structurally impossible**. A prompt instruction only makes the model *less likely* to use it — and the wrong chunk is still in the context, competing for attention.

Structure beats instruction wherever the constraint is expressible as data.

---

**Q24. Multi-tenant — where does the filter come from?**

**A:** From **code**, derived from the **authenticated session**. Never from anything the model or the user can influence.

It's a **security boundary**, not a convenience — it's what stops one user's question from retrieving another user's documents.

```python
return store.as_retriever(search_kwargs={"k": 4, "filter": {"owner": user_id}})
```

*Discussion:* Parallels the tool-integration lesson from day one — the model proposes, our code decides what's permitted.

---

**Q25. Retrieval failure vs generation failure?**

**A:** Print the retrieved chunks next to the answer.

- **Answer not in the chunks** → retrieval failure. Fix chunking or retrieval; the prompt is irrelevant.
- **Answer in the chunks, response still wrong** → generation failure, and *now* the prompt is the right place to work.

That second case is **the one symptom** that makes prompt engineering the correct response.

---

**Q26. Symptom → fix.**

**A:**

| Symptom | Cause | Fix |
|---|---|---|
| (a) Right topic, wrong detail | Chunks too large, signal diluted | Smaller chunks |
| (b) Same passage repeated | Redundant corpus | Switch to MMR |
| (c) Outdated results | No filtering | Metadata filter |
| (d) Chunks cut mid-thought | Size or overlap too small | More overlap; pull neighbors via `chunk_index` |

*Also worth knowing by name:* multi-query retrieval (rewrites the question several ways, unions results — handles vocabulary mismatch), contextual compression (retrieve generously, strip irrelevant parts), hybrid search (vector + BM25 keyword, the standard answer for exact identifiers). All cost extra latency or calls — reach for them after the basics are tuned.

---

## Augmented Generation

**Q27. Why source labels and a delimiter?**

**A:** The **label** is what makes citation possible at all — the model can only cite what it can see. Naive `"\n\n".join(d.page_content ...)` throws the metadata away and with it any hope of a sourced answer.

The **delimiter** (`---`) gives an unambiguous boundary so the model doesn't read two unrelated passages as one continuous argument.

```python
def format_docs(docs):
    return "\n\n---\n\n".join(
        f"[Source: {d.metadata['source']}]\n{d.page_content}" for d in docs)
```

---

**Q28. Three jobs of the grounding prompt; which instruction matters most?**

**A:** (1) Supply the context. (2) Restrict the model to it. (3) Give it a way out when the context doesn't contain the answer.

**The escape hatch matters most.** Without an explicitly permitted response for "not in the context," the model does what it was trained to do — produce a plausible answer — and that answer is invented. Giving it a sanctioned alternative is what makes "I don't know" an available output rather than a failure.

*Discussion:* The retrieval lab has associates delete this line and watch the model invent a parental leave policy in the same confident tone as a real answer. It lands hard.

---

**Q29. Why "quote figures and dates exactly"?**

**A:** Models **paraphrase**, and a paraphrased number is a wrong number. "About two weeks" is not "15 days." In a policy, benefits, or pricing answer that difference is the whole answer.

It's a subtler failure than outright hallucination because the response looks correct and well-grounded.

---

**Q30. What does `RunnablePassthrough()` do, and the dict at the front?**

**A:** The dict is a `RunnableParallel` — both keys are computed from the **same input**. `retriever | format_docs` runs retrieval and flattens it into `context`; `RunnablePassthrough()` forwards the raw question unchanged into `question`.

```python
rag_chain = (
    {"context": retriever | format_docs, "question": RunnablePassthrough()}
    | prompt | llm | StrOutputParser()
)
```

Composing this way gets streaming, batching, and async for free.

---

**Q31. What do we lose returning just a string?**

**A:** The application has **no idea what was retrieved**. That kills verification (users can't check the answer) and debugging (a wrong answer can't be classified per Q25).

Returning sources enables: showing them in the UI so users verify rather than trust, and **logging them** so a wrong answer reported later is diagnosable after the fact.

```python
RunnableParallel({"docs": retriever, "question": RunnablePassthrough()}).assign(
    answer=(... | prompt | llm | StrOutputParser()))
```

`.assign()` adds a key to a dict already flowing through the chain, leaving existing keys intact — which is how `docs` and `answer` both come out.

---

**Q32. What is "stuff," and why are the alternatives rarely right?**

**A:** **Stuff** every retrieved document into one prompt and make a single call. It's the right default.

Alternatives — **map-reduce** and **refine** — make one model call *per document* to handle corpora exceeding the context window. They're rarely right now because context windows are large enough that the latency cost isn't justified.

*Note:* `create_stuff_documents_chain` / `create_retrieval_chain` are legacy as of LangChain 1.x and live in `langchain-classic`. Recognize them in existing code and tutorials; build new work with LCEL.

---

**Q33. Three things real systems add, and why `temperature=0`?**

**A:** Any three:
- **Return the sources** so users verify rather than trust.
- **Log the retrieved chunks** with every answer so failures are diagnosable later.
- **Use a threshold retriever** so empty retrieval short-circuits to "I don't have that information" before the model is asked.
- **Verify high-stakes answers** with a second call checking the answer against the context — expensive, appropriate when a wrong answer is costly.

`temperature=0` because **RAG generation is reading, not composing.** We want the model transcribing and synthesizing supplied text, not producing creative variation.

*Discussion:* Close the unit on this: a prompt instruction is a request, not enforcement. Smaller local models blend in training knowledge more often than hosted ones. Designing as though grounding is guaranteed is the most common mistake made with RAG.

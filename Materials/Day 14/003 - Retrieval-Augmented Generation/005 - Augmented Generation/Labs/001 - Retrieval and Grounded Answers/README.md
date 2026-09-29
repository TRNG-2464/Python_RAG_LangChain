# Retrieval and Grounded Answers

We'll tune what comes back from a vector store, then turn those chunks into an answer the model can't wander away from. We'll cover `as_retriever` with `k`, MMR, and metadata filters, then formatting chunks with sources and writing a grounding prompt.

## Prerequisites

| Software | Required Version |
|---|---|
| Python | >=3.10 |
| langchain-core | 1.6.4 |
| langchain-text-splitters | 1.1.2 |
| langchain-chroma | 1.1.0 |
| langchain-ollama | 1.1.0 |
| Ollama | any current release, running locally |
| Ollama models | `nomic-embed-text` and `llama3.1` |

Setup, from this lab's directory:

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
ollama pull nomic-embed-text
ollama pull llama3.1
```

Run it with `python src/main.py`.

This lab builds its own small store, so it doesn't depend on the previous lab having been run.

---

## Guided walkthrough

Open `src/main.py`. Both models are set up, a short corpus is already defined at the top, and the parts are marked out.

### 1. Build a store

Add this under `# --- Part 1 ---`:

```python
splitter = RecursiveCharacterTextSplitter(chunk_size=200, chunk_overlap=30)
chunks = splitter.split_documents(CORPUS)

store = Chroma.from_documents(
    documents=chunks,
    embedding=embeddings,
    collection_name="policies",
)

print("stored", len(chunks), "chunks")
```

*Splits the built-in corpus and loads it into an in-memory Chroma collection.*

No `persist_directory` here, so the store lives only for the run. That's what we want while experimenting — every run starts clean instead of stacking duplicates.

### 2. Vary k

Add under `# --- Part 2 ---`:

```python
question = "How many vacation days do I get?"

for k in [1, 2, 4]:
    retriever = store.as_retriever(search_kwargs={"k": k})
    docs = retriever.invoke(question)
    print(f"\nk={k} -> {len(docs)} chunks")
    for d in docs:
        print(f"   [{d.metadata['topic']}] {d.page_content[:60]}")
```

*Retrieves the same question at three different `k` values.*

Run it. `k=1` is precise but fragile — miss, and there's nothing to answer from. `k=4` covers more but starts dragging in chunks about unrelated policies.

Notice every value of `k` returns exactly `k` chunks. There's no "nothing relevant" outcome here.

### 3. Add diversity with MMR

Plain similarity search happily returns four near-identical chunks. MMR picks results that are relevant *and* different from each other. Add under `# --- Part 3 ---`:

```python
mmr = store.as_retriever(
    search_type="mmr",
    search_kwargs={"k": 3, "fetch_k": 10, "lambda_mult": 0.5},
)

print("\nMMR results:")
for d in mmr.invoke("time off"):
    print(f"   [{d.metadata['topic']}] {d.page_content[:60]}")
```

*Considers 10 candidates and selects 3 that are relevant but distinct.*

Compare that against plain `k=3` for the same query. `fetch_k` is the candidate pool, and `lambda_mult` is the dial: `1.0` is pure relevance (identical to similarity search), `0.0` is pure diversity. Try `lambda_mult=0.1` and `lambda_mult=0.9` and watch the results shift.

### 4. Filter by metadata

Add under `# --- Part 4 ---`:

```python
filtered = store.as_retriever(
    search_kwargs={"k": 2, "filter": {"topic": "expenses"}}
)

print("\nfiltered to expenses:")
for d in filtered.invoke("How many vacation days do I get?"):
    print(f"   [{d.metadata['topic']}] {d.page_content[:60]}")
```

*Restricts the search to chunks tagged with the expenses topic.*

Run it. We asked about vacation and got expense policy, because the filter ran first and the vector search only ever saw expense chunks. Filters apply *before* similarity — they narrow the pool, they don't re-rank it.

This is also the point where a filter can return fewer than `k` results, or none. Try `filter={"topic": "parking"}` and see.

### 5. Format the chunks with their sources

Now we move to generation. The model needs the chunks as text, and it can only cite what it can see. Add under `# --- Part 5 ---`:

```python
def format_docs(docs):
    return "\n\n---\n\n".join(
        f"[Source: {d.metadata['source']}]\n{d.page_content}" for d in docs
    )


retriever = store.as_retriever(search_kwargs={"k": 3})
print(format_docs(retriever.invoke("How many vacation days do I get?")))
```

*Joins the retrieved chunks into one string, labelling each with its source.*

Two things this does. The `---` separator stops the model reading two unrelated chunks as one continuous passage, and the `[Source: ...]` label is what makes a citation possible at all.

### 6. Write the grounding prompt

Add under `# --- Part 6 ---`:

```python
prompt = ChatPromptTemplate.from_messages([
    ("system",
     "Answer using only the context provided.\n"
     "If the context does not contain the answer, say "
     "\"I don't have that information.\"\n"
     "Cite the source for each fact, like [pto.txt].\n"
     "Quote figures and dates exactly as they appear."),
    ("human", "Context:\n{context}\n\nQuestion: {question}"),
])


def answer(question):
    docs = retriever.invoke(question)
    chain = prompt | llm | StrOutputParser()
    return chain.invoke({"context": format_docs(docs), "question": question})


print(answer("How many vacation days do I get?"))
```

*Retrieves, formats, and generates an answer restricted to the retrieved context.*

Run it. We should get the number with a citation.

The "I don't have that information" line is the most important instruction in that prompt. Without a sanctioned way to decline, a model will do what it was trained to do and invent something plausible.

### 7. Ask something the corpus can't answer

Add under `# --- Part 7 ---`:

```python
print(answer("What is the company's parental leave policy?"))
```

*Asks a question the corpus has no answer to.*

Run it. It should decline. Now delete the "If the context does not contain the answer" line from the prompt and run again — most models will invent a parental leave policy, in the same confident tone as the real answer. Put the line back.

### 8. Return the sources too

A bare string gives the app no way to verify or debug. Add under `# --- Part 8 ---`:

```python
def answer_with_sources(question):
    docs = retriever.invoke(question)
    chain = prompt | llm | StrOutputParser()
    text = chain.invoke({"context": format_docs(docs), "question": question})
    return {"answer": text, "sources": [d.metadata["source"] for d in docs]}


result = answer_with_sources("When are expense reports due?")
print(result["answer"])
print("sources:", set(result["sources"]))
```

*Returns the retrieved sources alongside the generated answer.*

This is what makes a wrong answer diagnosable. Print the chunks next to the answer: if the answer isn't in them, it's a retrieval failure and the prompt is irrelevant. If it is in them and the answer is still wrong, now the prompt is the place to work.

---

## Exercises

1. **Force a retrieval failure.** Find a question whose answer is in the corpus but which `k=1` fails to retrieve. Show the retrieved chunk to prove the answer isn't in it, then fix it by raising `k`.

2. **Make it paraphrase a number.** Remove the "Quote figures and dates exactly" line and ask about the hotel cap or the receipt threshold several times. Does the model ever round or soften a figure?

3. **Filter inside the answer function.** Add a `topic` argument to `answer()` that passes a metadata filter into the retriever. Ask an expenses question restricted to `topic="time-off"` and explain the result.

4. **Compare MMR end to end.** Run the same question through `answer()` with a plain `k=4` retriever and with an MMR retriever at `k=4`. Do the answers differ? Print the chunks each one used to explain why.

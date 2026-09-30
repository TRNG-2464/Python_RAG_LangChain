# From Files to a Vector Store

We'll run the whole ingestion pipeline: load text files into `Document` objects, attach metadata, split them into chunks, embed them, and store them in Chroma. We'll cover `TextLoader`, `RecursiveCharacterTextSplitter`, chunk size and overlap, and `Chroma.add_documents`.

## Prerequisites

| Software | Required Version |
|---|---|
| Python | >=3.10 |
| langchain-core | 1.6.4 |
| langchain-community | 0.4.2 |
| langchain-text-splitters | 1.1.2 |
| langchain-chroma | 1.1.0 |
| langchain-ollama | 1.1.0 |
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

The `data/` folder already has two small text files to ingest.

---

## Guided walkthrough

Open `src/main.py`. The embedding model is set up and the parts are marked out.

### 1. Load a file

Add this under `# --- Part 1 ---`:

```python
docs = TextLoader("data/pto.txt", encoding="utf-8").load()

print(len(docs), "document(s)")
print(docs[0].metadata)
print(docs[0].page_content[:120])
```

*Loads one text file into a list of `Document` objects.*

Run it. One `Document`, with `page_content` holding the whole file and `metadata` holding just `{'source': 'data/pto.txt'}`.

That `encoding="utf-8"` is not optional on Windows. Without it Python uses the platform default and any smart quote or dash in a file will raise a `UnicodeDecodeError`.

### 2. Load both files and add metadata

Loaders give us a bare `source`. Anything else is on us, and it has to happen now — metadata can't be added after the chunks are in the store. Add under `# --- Part 2 ---`:

```python
docs = []
for name, topic in [("pto.txt", "time-off"), ("expenses.txt", "expenses")]:
    for doc in TextLoader(f"data/{name}", encoding="utf-8").load():
        doc.metadata["topic"] = topic
        doc.metadata["year"] = 2025
        docs.append(doc)

for d in docs:
    print(d.metadata, len(d.page_content), "chars")
```

*Loads both files and tags each with a topic and year.*

Metadata values have to be scalars — strings, numbers, booleans. Chroma rejects lists and nested dicts.

### 3. Split into chunks

Whole documents embed badly: one vector averaging everything in the file, matching nothing specific. Add under `# --- Part 3 ---`:

```python
splitter = RecursiveCharacterTextSplitter(chunk_size=300, chunk_overlap=50)
chunks = splitter.split_documents(docs)

print(f"{len(docs)} documents -> {len(chunks)} chunks\n")
for c in chunks[:4]:
    print(f"--- {len(c.page_content)} chars | {c.metadata} ---")
    print(c.page_content)
    print()
```

*Splits the documents into overlapping chunks and prints the first few.*

Run it and actually read the output. Are the chunks cut at sensible places? Does each one make sense on its own? This is the check that matters most, and it's the one people skip.

Notice the metadata survived onto every chunk. That's because we used `split_documents`, which takes and returns `Document` objects. Its sibling `split_text` takes and returns plain strings and loses metadata entirely — a common way to end up with a store full of chunks that can't be traced back anywhere.

### 4. Watch the parameters

Add under `# --- Part 4 ---`:

```python
for size in [100, 300, 1000]:
    n = len(RecursiveCharacterTextSplitter(
        chunk_size=size, chunk_overlap=0).split_documents(docs))
    print(f"chunk_size={size:5}  ->  {n} chunks")
```

*Splits the same documents at three different sizes to compare.*

Small chunks give precise matches but can strand a sentence from the context that makes it meaningful. Large chunks keep context but dilute the embedding. 500–1000 characters is the usual starting range; we used 300 here so the effect is visible on short files.

Now look at what overlap does:

```python
no_overlap = RecursiveCharacterTextSplitter(
    chunk_size=300, chunk_overlap=0).split_documents(docs)
print(repr(no_overlap[0].page_content[-60:]))
print(repr(no_overlap[1].page_content[:60]))
```

*Prints the boundary between two chunks split with no overlap.*

The break is clean and abrupt. With `chunk_overlap=50`, the second chunk repeats the last 50 characters of the first, so an idea that straddles the boundary is still retrievable.

### 5. Embed and store

Add under `# --- Part 5 ---`:

```python
store = Chroma(
    collection_name="handbook",
    embedding_function=embeddings,
    persist_directory="./chroma_db",
)

ids = [f"{c.metadata['source']}-{i}" for i, c in enumerate(chunks)]
store.add_documents(chunks, ids=ids)

print("stored", len(chunks), "chunks")
```

*Creates a persistent Chroma collection and adds every chunk with a stable id.*

Chroma embeds each chunk's `page_content` and keeps the metadata alongside it.

The `ids` matter. Without them, every run generates fresh random ids and re-running this script duplicates the entire corpus. With stable ids, a second run overwrites in place. Run the script twice and then check:

```python
print(len(store.get()["ids"]), "records in collection")
```

*Prints how many records the collection actually holds.*

The count should stay the same across runs. Delete the `ids=ids` argument, run twice more, and watch it double.

### 6. Search it

Add under `# --- Part 6 ---`:

```python
for query in ["how many vacation days", "when are receipts required"]:
    print(f"\nquery: {query!r}")
    for doc, score in store.similarity_search_with_score(query, k=2):
        print(f"  {score:.3f}  [{doc.metadata['topic']}] {doc.page_content[:70]}")
```

*Searches the store and prints each hit with its distance score and metadata.*

Run it. We get back the chunk text and its metadata, which is what makes a result usable — nobody wants a list of floats.

One thing to watch: in Chroma, this score is a **distance**, so **lower is closer**. That's the opposite direction from the cosine similarity we computed by hand in the embeddings lab, and getting it backwards is an easy way to write a filter that keeps exactly the wrong results.

---

## Exercises

1. **A third file.** Write `data/parking.txt` with a few short paragraphs, load it with `topic="facilities"`, and confirm it shows up in a search for something it covers.

2. **Tune the split.** Re-run the pipeline with `chunk_size=1000, chunk_overlap=0`, then query `"how many sick days"`. Compare the retrieved chunk against the `chunk_size=300` version. Which gives a tighter answer, and why?

3. **Filter the search.** Pass `filter={"topic": "expenses"}` to `similarity_search` and query for vacation days. Explain what comes back and why.

4. **Re-ingest cleanly.** Edit `data/pto.txt` to be much shorter, then re-run. Are there leftover chunks from the old version still in the store? Use `store.delete(where={"source": "data/pto.txt"})` before re-adding and check the count again.

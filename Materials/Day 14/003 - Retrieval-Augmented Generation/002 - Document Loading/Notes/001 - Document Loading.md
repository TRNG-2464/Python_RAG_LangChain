# Document Loading

Ingestion starts by getting source material — PDFs, markdown files, web pages, CSV rows — into a single uniform shape that the rest of the pipeline can work with. That shape is LangChain's `Document`.

It's the least glamorous step in RAG and the one that quietly determines how good the final answers are, because the metadata we attach here is the only thing that makes citation and filtering possible later.

---

## The `Document` Object

A `Document` has exactly two attributes:

```python
from langchain_core.documents import Document

doc = Document(
    page_content="Employees accrue 15 days of PTO annually.",
    metadata={"source": "handbook.pdf", "page": 4, "department": "HR"},
)
```

*Constructs a document by hand — text in `page_content`, everything else in `metadata`.*

`page_content` is the text that gets embedded and eventually shown to the model. `metadata` is a flat dict of scalars that travels with the text through splitting, embedding, and storage, and comes back attached to every search result.

Every loader in LangChain returns `list[Document]`, and every splitter and vector store consumes them. That uniformity is the point — a PDF, a web page, and a database row all become the same thing, so the rest of the pipeline doesn't care where the text came from.

---

## Loaders

A **document loader** knows how to read one kind of source and produce `Document` objects from it.

### Text and Markdown

```python
from langchain_community.document_loaders import TextLoader

docs = TextLoader("./notes/architecture.md", encoding="utf-8").load()
print(docs[0].metadata)    # {'source': './notes/architecture.md'}
```

*Reads a plain text file into a single document.*

Always pass `encoding="utf-8"` explicitly. Without it the loader uses the platform default, which on Windows is not UTF-8 — the result is a `UnicodeDecodeError` on any file containing a smart quote or an em dash.

### PDFs

```python
from langchain_community.document_loaders import PyPDFLoader

docs = PyPDFLoader("./handbook.pdf").load()
print(len(docs))           # one Document per page
print(docs[3].metadata)    # {'source': './handbook.pdf', 'page': 3}
```

*Loads a PDF, producing one document per page with page numbers in metadata.*

`PyPDFLoader` gives us page numbers for free, which is exactly what a citation needs. Requires `pypdf` installed.

PDFs are the most common source and the most troublesome. Text extraction often mangles multi-column layouts, tables come out as scrambled runs of numbers, and a scanned PDF contains no extractable text at all — it's an image, and needs OCR. **Always print a few loaded pages before building the rest of the pipeline.** Garbage extracted here is garbage embedded, retrieved, and answered from.

### Directories

```python
from langchain_community.document_loaders import DirectoryLoader, TextLoader

docs = DirectoryLoader(
    "./docs",
    glob="**/*.md",
    loader_cls=TextLoader,
    loader_kwargs={"encoding": "utf-8"},
    show_progress=True,
).load()
```

*Walks a directory tree, loading every matching file with the given loader.*

The `glob` pattern controls which files are picked up, and `loader_cls` says how to read each one. For a mixed corpus, run several `DirectoryLoader`s with different globs and concatenate the lists.

### Web Pages and CSVs

```python
from langchain_community.document_loaders import WebBaseLoader, CSVLoader

web_docs = WebBaseLoader("https://example.com/policy").load()
csv_docs = CSVLoader("./tickets.csv", source_column="ticket_id").load()
```

*Loads a web page into one document and a CSV into one document per row.*

`CSVLoader` produces one `Document` per row, with the columns rendered as `key: value` lines. That works well for records that stand alone — support tickets, product entries — and poorly for numeric tables, which belong in a real database queried by a tool rather than in a vector store.

There are well over a hundred loaders in `langchain_community` (Notion, Slack, S3, Confluence, SQL, and so on). They all expose the same `.load()` interface, so the pattern generalizes.

---

## `load()` vs. `lazy_load()`

`.load()` reads everything into memory and returns a list. For a few hundred files that's fine. For a large corpus it isn't, and `.lazy_load()` yields documents one at a time:

```python
loader = DirectoryLoader("./big_corpus", glob="**/*.txt", loader_cls=TextLoader)

for doc in loader.lazy_load():
    chunks = splitter.split_documents([doc])
    store.add_documents(chunks)
```

*Streams documents one at a time so the whole corpus is never in memory at once.*

This also gives incremental progress — if ingestion fails at file 900 of 1000, the first 899 are already stored rather than lost.

---

## Metadata Is the Part That Matters

Loaders set a minimal `source`, and sometimes `page`. Everything else is on us, and it's worth the effort, because metadata is the only thing that makes two important features possible:

- **Citation** — "according to handbook.pdf, page 4" requires that page number to have survived the whole pipeline.
- **Filtering** — "search only 2025 HR documents" requires `year` and `department` to be stored.

Neither can be added later. If it isn't attached at load time, it isn't in the store.

```python
from pathlib import Path

docs = []
for path in Path("./policies").glob("*.pdf"):
    for doc in PyPDFLoader(str(path)).load():
        doc.metadata.update({
            "title": path.stem,
            "department": path.parent.name,
            "year": 2025,
            "doc_type": "policy",
        })
        docs.append(doc)
```

*Enriches each loaded page with metadata derived from the file path before it moves down the pipeline.*

Two constraints to respect. Metadata values must be **scalars** — strings, numbers, booleans. Chroma rejects nested dicts and lists, so flatten (`"tags": "hr,pto"` rather than a list). And keys must be **consistent** across the corpus; a filter on `{"year": 2025}` silently skips every document where the field was spelled `date` instead.

---

## Cleaning Before Splitting

Loaded text usually carries noise: page headers repeated on every page, navigation menus from scraped HTML, form-feed characters, runs of blank lines. All of it gets embedded and dilutes the vector.

A cleaning pass between loading and splitting is cheap and pays off:

```python
import re

def clean(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text)          # collapse blank-line runs
    text = re.sub(r"Page \d+ of \d+", "", text)     # strip repeated footers
    return text.strip()

for doc in docs:
    doc.page_content = clean(doc.page_content)
```

*Normalizes whitespace and removes repeated boilerplate from each document's text.*

It's also the right moment to drop documents that extracted to nothing — a scanned page or a failed parse becomes an empty or near-empty `page_content`, and embedding it just adds a meaningless vector that can still surface in search:

```python
docs = [d for d in docs if len(d.page_content.strip()) > 50]
```

*Discards documents with too little extracted text to be useful.*

---

## Key Takeaways

- A `Document` is `page_content` plus a flat `metadata` dict; every loader produces them and every downstream step consumes them.
- `TextLoader`, `PyPDFLoader`, `DirectoryLoader`, `WebBaseLoader`, and `CSVLoader` cover most sources, and all share the same `.load()` interface.
- Pass `encoding="utf-8"` explicitly on text loaders — the Windows default will fail on common punctuation.
- Inspect extracted text before building further, especially from PDFs; scanned pages yield nothing without OCR.
- Use `.lazy_load()` for large corpora to stream documents and get incremental progress.
- Metadata must be added at load time — it's what enables citation and filtering, and it cannot be recovered later.
- Keep metadata values scalar and keys consistent, or filters will silently skip documents.
- Clean boilerplate and drop near-empty documents before splitting, so noise never reaches the embeddings.

# Chunking Strategies

A loaded document is usually far too big to be useful as a unit of retrieval. **Chunking** — splitting documents into smaller pieces before embedding — is the step that decides what a search can actually return.

It gets less attention than prompting and matters more. Chunk badly and no retriever configuration or prompt rewrite will save the answers, because the right information was never stored in a retrievable form.

---

## Why Not Embed Whole Documents?

Three independent reasons, each sufficient on its own.

**Embeddings dilute.** A vector is a fixed length regardless of input size. Embedding a forty-page handbook produces an average of everything in it — a vector that sits in the middle of "general HR topics" and is close to nothing specific. The PTO policy is in there, but its signal has been averaged away.

**Context windows are finite.** Retrieved text goes into the prompt. Four whole documents won't fit; four paragraphs will.

**Precision.** We want the paragraph that answers the question, not the document that contains it. Retrieval quality is bounded by chunk granularity.

The counter-pressure matters too, which is why this is a tradeoff rather than "smaller is better." Chunks that are too small lose the context that makes them interpretable. A chunk reading *"It must be submitted within 30 days."* is useless — what must be, and to whom?

---

## Size and Overlap

Two parameters govern every splitter.

**Chunk size** is the target length of each piece, measured in characters (or tokens, depending on the splitter). It's the precision/context dial:

| Size | Effect |
|---|---|
| 200–400 | Very precise matches; high risk of orphaned fragments |
| 500–1000 | The usual default — roughly a paragraph or two |
| 1500–2000 | Preserves argument and context; dilutes the embedding, fills the prompt fast |

**Chunk overlap** is how much text each chunk repeats from the end of the previous one. It exists because split points are arbitrary and will sometimes land mid-thought:

```
Without overlap:
  chunk 1: "...requests must be approved by a manager."
  chunk 2: "Approval must be obtained 30 days in advance..."
                ↑ retrieved alone, "approval" of what is unclear

With 100-char overlap:
  chunk 1: "...requests must be approved by a manager."
  chunk 2: "...must be approved by a manager. Approval must be obtained 30 days..."
                ↑ carries enough context to stand on its own
```

A sensible overlap is **10–20% of chunk size** — 100 characters for 800-character chunks. Too little and boundary-spanning ideas get lost; too much inflates the store and returns near-duplicate chunks that waste the prompt.

---

## `RecursiveCharacterTextSplitter`

This is the default for prose, and the one to reach for unless there's a specific reason not to. It tries a ladder of separators in order, falling back only when a chunk is still too large:

```
1. "\n\n"  paragraph breaks
2. "\n"    line breaks
3. " "     word breaks
4. ""      raw characters (last resort)
```

The effect is that it prefers to break at a paragraph, and only cuts mid-word if a single word somehow exceeds the chunk size.

```python
from langchain_text_splitters import RecursiveCharacterTextSplitter

splitter = RecursiveCharacterTextSplitter(
    chunk_size=800,
    chunk_overlap=100,
    length_function=len,
    separators=["\n\n", "\n", " ", ""],
)

chunks = splitter.split_documents(docs)
print(f"{len(docs)} documents → {len(chunks)} chunks")
```

*Splits documents at natural boundaries, preferring paragraph breaks over mid-sentence cuts.*

Use `split_documents` (which takes and returns `Document` objects, carrying metadata through) rather than `split_text` (which takes and returns raw strings, losing metadata). Getting this backwards is a common way to end up with a store full of chunks that can't be cited.

---

## Splitting by Tokens

Characters aren't what the model counts — tokens are, and the ratio varies by language and content. Roughly four characters per token for English prose, but code and non-English text differ enough to matter.

When chunks need to fit a precise token budget, count tokens directly:

```python
splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
    chunk_size=250,          # now measured in tokens
    chunk_overlap=30,
)
```

*Measures chunk size in tokens rather than characters, for exact context-window budgeting.*

This matters most when retrieved chunks are close to filling the prompt. For a training-scale corpus with `k=4` and 800-character chunks, character counting is fine.

---

## Splitting Along Structure

Character-based splitting is structure-blind: it will happily cut a markdown document in the middle of a section, or a Python file in the middle of a function. When the source has structure, respecting it produces better chunks.

### Markdown by Headers

```python
from langchain_text_splitters import MarkdownHeaderTextSplitter

md_splitter = MarkdownHeaderTextSplitter(
    headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3")],
)
chunks = md_splitter.split_text(markdown_string)
print(chunks[0].metadata)    # {'h1': 'Employee Handbook', 'h2': 'Time Off'}
```

*Splits at markdown headers and records the header hierarchy in each chunk's metadata.*

The metadata is the real win here. Every chunk now knows which section it came from, which is usable both for citation and as a filter.

The standard pattern is to run this first and then the recursive splitter on the results, since a single section can still be too long:

```python
sections = md_splitter.split_text(markdown_string)
chunks = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100) \
    .split_documents(sections)
```

*Splits by section first, then splits any oversized section by character, preserving header metadata throughout.*

### Code by Syntax

```python
from langchain_text_splitters import RecursiveCharacterTextSplitter, Language

py_splitter = RecursiveCharacterTextSplitter.from_language(
    language=Language.PYTHON, chunk_size=1000, chunk_overlap=100
)
```

*Uses Python-aware separators so splits fall at class and function boundaries.*

This swaps the separator ladder for language-appropriate ones (`\nclass `, `\ndef `, and so on), so a function is far more likely to survive intact. `Language` covers most common languages.

---

## Keeping Chunks Traceable

Metadata carries through `split_documents` automatically, but adding position information is worth the two extra lines:

```python
for i, chunk in enumerate(chunks):
    chunk.metadata["chunk_index"] = i
    chunk.metadata["chunk_total"] = len(chunks)
```

*Records each chunk's position so neighbors can be located after retrieval.*

This enables a genuinely useful trick: when a retrieved chunk is clearly cut off mid-thought, fetch `chunk_index ± 1` and include the neighbors. It recovers context without having to store larger chunks everywhere.

---

## Choosing a Strategy

| Content | Approach |
|---|---|
| Prose, articles, reports | `RecursiveCharacterTextSplitter`, 800/100 |
| Markdown docs | Header splitter, then recursive on the sections |
| Source code | `from_language` with the matching `Language` |
| FAQs, Q&A pairs | Split on the record boundary — one chunk per pair |
| CSV rows, tickets | One chunk per row; don't split at all |
| Legal, dense reference | Larger chunks (1200–1500), higher overlap |

The general rule: **split along whatever boundary the content already has.** Documents come with structure — sections, records, functions — and reusing it beats imposing an arbitrary character count.

---

## Testing the Split

Chunking is empirical. The only reliable way to set these parameters is to look at the output:

```python
for c in chunks[:5]:
    print(f"--- {len(c.page_content)} chars | {c.metadata.get('source')} ---")
    print(c.page_content)
```

*Prints the first few chunks with their sizes and sources to check boundaries by eye.*

Three things to look for. Are chunks being cut mid-sentence in a way that destroys meaning? Does each chunk make sense read on its own, without the ones around it? And are there tiny orphan chunks — a heading with nothing under it — that should be merged?

Then test retrieval directly. Ask a question with a known answer and print what comes back. If the right chunk isn't retrieved, chunking is the first thing to adjust, before the retriever and long before the prompt.

---

## Key Takeaways

- Chunking determines what retrieval can return; it constrains answer quality more than prompting does.
- Whole documents embed poorly because a fixed-length vector averages everything in them.
- Chunk size trades precision against context — 500–1000 characters is the usual starting range.
- Overlap of 10–20% keeps ideas that straddle a split point retrievable.
- `RecursiveCharacterTextSplitter` is the prose default; it prefers paragraph breaks and falls back only as needed.
- Use `split_documents`, not `split_text`, so metadata survives.
- Split along existing structure when it exists — markdown headers, code syntax, record boundaries.
- Add `chunk_index` so neighboring chunks can be pulled in when a result is cut off.
- Inspect real chunks and test real queries; these parameters are tuned empirically, not chosen from a table.

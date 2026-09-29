# What Is RAG?

A language model knows what was in its training data. It does not know our company handbook, last week's incident reports, or the contents of a customer's account. Ask it anyway and we get one of two bad outcomes: an admission that it doesn't know, or a confident, fluent, invented answer.

**Retrieval-Augmented Generation (RAG)** is the standard fix. Before asking the model anything, we search our own data for the passages most relevant to the question and paste them into the prompt. The model then answers *from* that text rather than from memory.

The reframing that makes it click: we're not teaching the model anything. We're handing it the open book and asking it to read.

---

## Why Not Just Fine-Tune?

Fine-tuning — continuing a model's training on our own data — is the obvious alternative, and it's usually the wrong tool for this job.

| | RAG | Fine-tuning |
|---|---|---|
| Adds new facts | Yes | Unreliably |
| Updating data | Re-ingest the changed file | Retrain the model |
| Cost | Embedding + storage | GPU training runs |
| Citations | Natural — we know which chunk was used | Impossible |
| Changes *style* or format | No | Yes |

The dividing line is **knowledge versus behavior**. RAG is for what the model should *know*. Fine-tuning is for how it should *behave* — tone, format, a specialized output convention. When someone asks a model to answer questions about documents it has never seen, the answer is RAG essentially every time.

There's also a third option worth naming: if the relevant data is small enough to fit entirely in the context window, just put all of it in the prompt. RAG exists because most corpora aren't.

---

## Two Pipelines

Every RAG system is two separate pipelines that meet at the vector store. Keeping them mentally distinct prevents a lot of confusion, because they run at different times and fail in different ways.

```
INGESTION  (offline — run when data changes)

  Source files
      ↓  load          → Document objects (text + metadata)
      ↓  split         → chunks small enough to embed precisely
      ↓  embed         → vectors
      ↓  store         → Chroma collection
                              │
                              │
QUERY  (online — runs per question)                │
                              │
  User question               │
      ↓  embed                ↓
      ↓  retrieve  ←──────────┘   → top-k relevant chunks
      ↓  augment                  → chunks pasted into the prompt
      ↓  generate                 → grounded answer + citations
```

**Ingestion** happens ahead of time. We load documents, split them into chunks, embed those chunks, and store them. It's slow, it's batch work, and it only reruns when the source data changes.

**Query** happens per question and needs to be fast. We embed the question, retrieve the closest chunks, build a prompt containing them, and call the model.

The remaining topics in this unit walk these steps in order: Document Loading and Chunking Strategies cover ingestion, Retriever Design covers retrieval, and Augmented Generation covers turning retrieved chunks into an answer.

---

## The Smallest Complete Example

Before breaking it apart, it's worth seeing the whole thing in one piece:

```python
from langchain_chroma import Chroma
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

embeddings = OllamaEmbeddings(model="nomic-embed-text")
llm = ChatOllama(model="llama3.1", temperature=0)

store = Chroma(persist_directory="./chroma_db", embedding_function=embeddings)
retriever = store.as_retriever(search_kwargs={"k": 4})

prompt = ChatPromptTemplate.from_template(
    "Answer the question using only the context below. "
    "If the context doesn't contain the answer, say you don't know.\n\n"
    "Context:\n{context}\n\nQuestion: {question}"
)

def rag(question: str) -> str:
    docs = retriever.invoke(question)
    context = "\n\n".join(d.page_content for d in docs)
    chain = prompt | llm | StrOutputParser()
    return chain.invoke({"context": context, "question": question})

print(rag("How much PTO do employees accrue?"))
```

*Retrieves the four closest chunks, pastes them into a grounded prompt, and generates an answer.*

That's the entire query pipeline: retrieve, format, prompt, generate. Everything else in this unit is about doing each of those four steps well enough that the answers are trustworthy.

---

## What RAG Fixes, and What It Doesn't

RAG buys us four things:

- **Current and private knowledge** the model was never trained on.
- **Citations** — we know exactly which chunks were used, so the answer can point at its sources.
- **Cheap updates** — changed a document? Re-ingest that file.
- **Fewer hallucinations**, because the model is told to answer from supplied text rather than memory.

That last one deserves a qualification. RAG *reduces* hallucination; it doesn't eliminate it. A model can still misread a retrieved chunk, blend it with its own training knowledge, or answer confidently from context that doesn't actually address the question.

And RAG introduces failure modes of its own:

- **Retrieval misses.** If the right chunk doesn't come back, the model cannot answer correctly — it has never seen the information. Most "the model got it wrong" reports turn out to be retrieval problems.
- **Bad chunking.** A chunk that splits a table in half, or cuts a sentence mid-clause, is retrieved and used anyway.
- **Multi-hop questions.** "Which policy changed most between 2023 and 2025?" requires comparing across documents. Top-k retrieval of similar passages doesn't do reasoning across sources.
- **Aggregate questions.** "How many tickets were filed last quarter?" is a database query, not a similarity search. RAG will retrieve a few tickets and the model will guess.

The debugging instinct this should build: **when a RAG answer is wrong, look at the retrieved chunks before touching the prompt.** Print them. If the answer isn't in there, no amount of prompt engineering will help — the problem is upstream, in chunking or retrieval.

---

## Key Takeaways

- RAG grounds a model's answers in our own data by retrieving relevant text and adding it to the prompt.
- It's an open-book exam, not additional training — the model's weights never change.
- Use RAG for knowledge the model lacks; use fine-tuning for behavior, tone, or format.
- Every RAG system is two pipelines: offline ingestion (load, split, embed, store) and online query (embed, retrieve, augment, generate).
- The payoff is current knowledge, citable sources, cheap updates, and reduced hallucination.
- The main new failure mode is retrieval — if the right chunk isn't retrieved, the answer cannot be right.
- Debug by inspecting the retrieved chunks first; prompt fixes can't recover missing context.

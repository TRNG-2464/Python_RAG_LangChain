# Augmented Generation

Retrieval gives us a list of `Document` objects. The last step is turning them into an answer: formatting them into the prompt, instructing the model to use only that text, and returning the result with its sources attached.

This step is short on code and long on consequences. The difference between a RAG system that's trustworthy and one that quietly invents things is mostly in the prompt written here.

---

## Formatting Retrieved Documents

The model receives text, so documents have to be flattened into a string. The naive version:

```python
def format_docs(docs) -> str:
    return "\n\n".join(doc.page_content for doc in docs)
```

*Joins the retrieved chunks into one block of text.*

That works, but it throws away the metadata — and with it, any possibility of citation. The better version keeps the source attached to each chunk so the model can point at it:

```python
def format_docs(docs) -> str:
    return "\n\n---\n\n".join(
        f"[Source: {d.metadata.get('source', 'unknown')}"
        f", page {d.metadata.get('page', 'n/a')}]\n{d.page_content}"
        for d in docs
    )
```

*Labels each chunk with its source and page, separated by a clear delimiter.*

Two things this gets right. The `---` delimiter gives the model an unambiguous boundary between chunks, so it doesn't read two unrelated passages as one continuous argument. And the inline `[Source: ...]` label is what makes "cite your sources" a request the model can actually satisfy — it can only cite what it can see.

---

## The Grounding Prompt

This prompt is the control surface for hallucination. It needs to do three things: supply the context, restrict the model to it, and give it a way out when the context doesn't contain the answer.

```python
from langchain_core.prompts import ChatPromptTemplate

prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You answer questions using only the context provided.\n"
     "Rules:\n"
     "- If the context does not contain the answer, say "
     "\"I don't have that information in the provided documents.\"\n"
     "- Do not use knowledge from outside the context.\n"
     "- Cite the source for each fact, like [handbook.pdf, page 4].\n"
     "- Quote exact figures, dates, and names from the context; do not paraphrase them."),
    ("human", "Context:\n{context}\n\nQuestion: {question}"),
])
```

*Instructs the model to answer strictly from supplied context, with an explicit escape hatch and a citation format.*

The escape hatch is the single most important line. Without an explicit permitted response for "not in the context," a model will do what it was trained to do — produce a plausible answer — and that answer will be invented. Giving it a sanctioned alternative is what makes "I don't know" an available output rather than a failure.

The instruction about exact figures addresses a subtler failure: models paraphrase, and a paraphrased number is a wrong number. "About two weeks" is not "15 days," and in a policy answer that difference matters.

---

## Wiring It Together

The manual version, written out so each step is visible:

```python
from langchain_core.output_parsers import StrOutputParser

def answer(question: str) -> str:
    docs = retriever.invoke(question)
    chain = prompt | llm | StrOutputParser()
    return chain.invoke({"context": format_docs(docs), "question": question})
```

*Retrieves, formats, prompts, and generates in four explicit steps.*

The same thing as a single LCEL chain, which is what we'd use in practice:

```python
from langchain_core.runnables import RunnablePassthrough

rag_chain = (
    {"context": retriever | format_docs, "question": RunnablePassthrough()}
    | prompt
    | llm
    | StrOutputParser()
)

print(rag_chain.invoke("How much PTO do employees accrue?"))
```

*Builds the prompt inputs in parallel — retrieving and formatting for `context`, passing the question straight through — then generates.*

The dict at the front is a `RunnableParallel`: both keys are computed from the same input. `retriever | format_docs` runs retrieval and flattens the result into `context`, while `RunnablePassthrough()` forwards the raw question to `question`. Composing this way gets streaming, batching, and async support for free.

---

## Returning the Sources

The chain above returns a string, which means the application has no idea what was retrieved. That's a problem: the sources are half the value, and without them there's no way to verify an answer or debug a bad one.

The fix is to branch the chain so the documents survive alongside the generated text:

```python
from langchain_core.runnables import RunnableParallel

rag_with_sources = RunnableParallel(
    {"docs": retriever, "question": RunnablePassthrough()}
).assign(
    answer=(
        {"context": lambda x: format_docs(x["docs"]), "question": lambda x: x["question"]}
        | prompt | llm | StrOutputParser()
    )
)

result = rag_with_sources.invoke("How much PTO do employees accrue?")
print(result["answer"])
for d in result["docs"]:
    print("-", d.metadata.get("source"), d.metadata.get("page"))
```

*Keeps the retrieved documents in the output while generating the answer from them.*

`.assign()` adds a key to a dict that's already flowing through the chain, leaving the existing keys intact. That's what lets `docs` and `answer` both come out the other end.

This matters beyond display. Showing sources in the UI is how users verify an answer, and logging them is how we debug — when a wrong answer comes in, the stored `docs` tell us immediately whether it was a retrieval failure or a generation failure.

---

## The Prebuilt Chains

LangChain also ships helpers that assemble this pattern. As of LangChain 1.x they're considered legacy and live in the separate `langchain-classic` package (`pip install langchain-classic`) — the LCEL version above is the current way to build this. They're worth recognizing, because a great deal of existing code and tutorial material uses them:

```python
from langchain_classic.chains import create_retrieval_chain
from langchain_classic.chains.combine_documents import create_stuff_documents_chain

combine = create_stuff_documents_chain(llm, prompt)
chain = create_retrieval_chain(retriever, combine)

result = chain.invoke({"input": "How much PTO do employees accrue?"})
print(result["answer"])
print(result["context"])     # the retrieved documents
```

*Uses the prebuilt retrieval chain, which returns both the answer and the documents it used.*

"Stuff" refers to the strategy — stuff every retrieved document into one prompt. It's the right default. The alternatives (map-reduce, refine) make one model call per document to handle corpora that don't fit in a context window, at a large cost in latency; they're rarely the right answer now that context windows are large.

These helpers expect specific keys: the prompt must use `{context}`, and the chain takes `{"input": ...}`. Recognize this form when we meet it in older code, but build new work with LCEL.

---

## Diagnosing a Bad Answer

Every RAG failure is one of two kinds, and telling them apart takes one step:

```python
result = rag_with_sources.invoke(question)
print(result["answer"])
for d in result["docs"]:
    print("---", d.page_content[:200])
```

*Prints the answer next to the exact chunks it was generated from.*

**If the answer is not in those chunks**, it's a retrieval failure. Go back to chunking and retriever design — the prompt is irrelevant, because the model never had the information.

**If the answer is in those chunks but the response is still wrong**, it's a generation failure, and now the prompt is the right place to work:

| Symptom | Fix |
|---|---|
| Invents facts not in the context | Strengthen the grounding rules; lower `temperature` to 0 |
| Answers from training data instead of context | Add "do not use outside knowledge" explicitly |
| Refuses despite having the answer | The escape hatch is too aggressive — soften it |
| Won't cite sources | Labels missing from `format_docs`, or no format specified |
| Numbers slightly wrong | Add the "quote figures exactly" rule |
| Ignores the later chunks | Too many retrieved — lower `k`; models attend poorly to long middles |

`temperature=0` is the right setting for RAG generally. We want the model reading, not composing.

---

## Grounding Is a Request, Not a Guarantee

Worth stating plainly: a prompt instruction is not enforcement. A model told to use only the supplied context will still, occasionally, blend in something from training — more often with smaller local models than with large hosted ones.

Real systems add checks on top:

- **Return the sources** so users can verify rather than trust.
- **Log the retrieved chunks** with every answer, so failures are diagnosable after the fact.
- **Use a threshold retriever** so an empty retrieval short-circuits to "I don't have that information" before the model is ever asked.
- **Verify high-stakes answers** with a second call that checks the answer against the context — expensive, but appropriate when a wrong answer is costly.

RAG substantially reduces hallucination. It doesn't make a system that can be trusted without verification, and designing as though it does is the most common mistake made with it.

---

## Key Takeaways

- Format retrieved documents with their source metadata inline — the model can only cite what it can see.
- Use a clear delimiter between chunks so unrelated passages aren't read as one.
- The grounding prompt must restrict the model to the context, forbid outside knowledge, and give an explicit "I don't know" option.
- Instruct the model to quote figures, dates, and names exactly; paraphrased numbers are wrong numbers.
- The LCEL pattern is `{"context": retriever | format_docs, "question": RunnablePassthrough()} | prompt | llm | parser`.
- Use `RunnableParallel` with `.assign()`, or `create_retrieval_chain`, to return sources alongside the answer.
- Diagnose by printing the answer next to its chunks: answer missing from the chunks means a retrieval failure, not a prompt problem.
- Set `temperature=0` — RAG generation is reading, not composing.
- Grounding instructions reduce hallucination but don't enforce it; return sources, log chunks, and verify what matters.

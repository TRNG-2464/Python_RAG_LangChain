# Retrieval-Augmented Generation — Reading Questions

Use these while reading this unit's notes. They follow the order of the material, so an answer you're hunting for is in the section you're currently reading. This unit covers five topics and builds one pipeline end to end — the questions track that build.

---

## What Is RAG?

1. Describe RAG in one sentence, without using the word "retrieval." What's the open-book analogy getting at, and what does it tell us about whether the model has *learned* anything?

2. RAG and fine-tuning both adapt a model to our situation. What's the dividing line between them, and which do we reach for when someone wants a model to answer questions about documents it's never seen?

3. There's a third option that isn't RAG at all. When is it the right answer?

4. RAG is two separate pipelines. Name them, say when each runs, and list their steps.

5. Name two things RAG genuinely buys us and two failure modes it introduces.

6. A RAG answer comes back wrong. What's the first thing we look at, and why is rewriting the prompt usually the wrong first move?

---

## Document Loading

7. A `Document` has exactly two attributes. What are they, and why does every loader in LangChain returning this same shape matter for the rest of the pipeline?

8. Why must `encoding="utf-8"` be passed explicitly to a text loader, and what specifically breaks without it on Windows?

9. Why are PDFs the most troublesome source? Name at least two ways extraction goes wrong, and say what we should do before building anything on top of a loaded PDF.

10. When would we use `.lazy_load()` instead of `.load()`? Name the second benefit beyond memory.

11. Metadata has to be attached at load time. What two capabilities depend on it, and why can't we add it later?

12. Why bother cleaning text between loading and splitting? What should we do with a document that extracted to almost nothing, and why?

---

## Chunking Strategies

13. Give three independent reasons not to embed a whole document. Then give the counter-pressure — what goes wrong if chunks are too small?

14. What does chunk overlap exist to solve? Roughly how much, and what's the cost of too much?

15. `RecursiveCharacterTextSplitter` tries a ladder of separators. What's the ladder, and what's the practical effect of trying them in that order?

16. `split_documents` and `split_text` sound interchangeable. What's the difference, and what's the consequence of picking the wrong one?

17. When is it worth splitting along a document's structure instead of by character count? Give an example and say what extra benefit we get.

18. What does recording `chunk_index` on each chunk enable after retrieval?

19. How do we actually decide on chunk size and overlap for a given corpus? What are the three things to look for when inspecting real chunks?

---

## Retriever Design

20. What are the three search types available from `as_retriever`, and what problem does each one solve?

21. MMR takes `k`, `fetch_k`, and `lambda_mult`. What does each control, and what does `lambda_mult=1.0` make MMR equivalent to?

22. Which search type can return an empty list, and why does that capability matter for what our application is able to say?

23. Metadata filtering is described as often the highest-leverage fix available. Why is a filter structurally stronger than a prompt instruction for something like "only use current policies"?

24. In a multi-tenant app, where does the filter come from and where must it never come from? What kind of boundary is it?

25. Our RAG answers are wrong. Walk through how we tell a retrieval failure apart from a generation failure, and name the one symptom that means the prompt really is the right place to work.

26. Match each symptom to its likely fix: (a) right topic but wrong detail, (b) the same passage returned repeatedly, (c) outdated results, (d) chunks that read as cut off mid-thought.

---

## Augmented Generation

27. Why do we label each retrieved chunk with its source when formatting, and why put a delimiter between chunks?

28. The grounding prompt has to do three jobs. What are they, and which single instruction matters most for keeping the model from inventing things?

29. Why explicitly tell the model to quote figures and dates exactly? What's the failure this prevents?

30. What does `RunnablePassthrough()` do in the standard RAG chain, and what is the dict at the front of that chain accomplishing?

31. Returning just a string from a RAG chain is a problem. What do we lose, and what does returning the sources alongside the answer enable?

32. "Stuff" is one strategy for combining retrieved documents. What does it mean, what are the alternatives, and why are they rarely the right answer now?

33. Grounding instructions reduce hallucination but don't enforce it. Given that, name three things a real system adds on top — and say why `temperature=0` is the right setting for RAG generation.

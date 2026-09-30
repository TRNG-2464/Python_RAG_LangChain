# LangGraph — Reading Questions

## LangGraph Overview

1. `create_agent` plus middleware already handles limits, retries, and approval gates. What kind of requirement is the signal to drop down to LangGraph directly?
2. Why does an agent built with `create_agent` already support checkpointers, recursion limits, and resumable interrupts?
3. What does making a step a fixed node in the graph, such as loading the customer record, guarantee that a system-prompt instruction to "always look up the customer first" can't?
4. For a two-step RAG pipeline, LCEL works as well as a graph. What does a graph let us express that a linear chain can't?

## State Management

1. A node returns only the keys it changed. What decides how each returned value combines with what's already in the state?
2. Why does LangGraph raise an error when two parallel nodes write the same key without a reducer, instead of just keeping one of the values?
3. Why does a message-list field need a purpose-built reducer rather than plain list concatenation?
4. On the second call to a checkpointed graph we send only the new user message, yet the model knows what was said in the first. Where did the earlier conversation come from?
5. Why can a run that fails partway through be resumed without redoing the steps that already succeeded?
6. Why should state hold plain data rather than objects like database clients or open connections?

## Graph-Based Agent Workflows

1. When we rebuild the tool-calling loop as a graph, the `for` loop disappears from our code. What in the graph's structure makes the agent repeat, and what makes it stop?
2. Why does the model node add the system message on every call instead of storing it in the state?
3. The write-review cycle keeps its own attempts counter even though the graph already has a recursion limit. Why have both?
4. Why should a node that calls `interrupt()` avoid side effects before the interrupt?
5. Why does the review node return a `Command` rather than relying on a conditional edge to choose the next node?

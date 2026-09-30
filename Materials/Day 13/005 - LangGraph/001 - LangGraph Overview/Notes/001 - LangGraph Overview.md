# LangGraph Overview

**LangGraph** is a lower-level framework for building stateful LLM applications as graphs. We describe the work as **nodes** (Python functions) joined by **edges** (which node runs next), all reading from and writing to one shared **state** object. The runtime handles executing the graph, saving state between steps, pausing for input, and streaming progress.

We've been using it already without seeing it: `create_agent` builds and returns a LangGraph graph. That's why it accepts a checkpointer and a `recursion_limit`, and why `HumanInTheLoopMiddleware` resumes with a `Command` from `langgraph.types`. Installing `langchain` installs `langgraph` alongside it.

---

## Why Drop Down from create_agent

`create_agent` gives us one fixed shape: a model node and a tools node in a loop, with middleware hooks around each call. Middleware covers a lot — limits, retries, summarization, approval gates. We reach for LangGraph directly when the *shape* itself needs to change:

- **Fixed steps mixed with model-driven ones.** Always retrieve first, always validate the output last, and let the model loop only in between.
- **Branching our code controls.** Route to different sub-flows based on a classification, a confidence score, or a business rule.
- **State beyond a message list.** Track an order id, a retry counter, a draft, a list of findings — typed fields that nodes read and update.
- **Several agents or loops in one application,** with explicit handoffs between them.
- **Pauses for review at any point,** not only before a tool call.

The trade is more code for more control. If `create_agent` plus middleware does the job, it's the better choice. LangGraph is for when we find ourselves fighting the prebuilt loop's shape.

---

## The Core Pieces

| Piece | What it is |
|---|---|
| **State** | A schema (usually a `TypedDict`) for the data shared by every node |
| **Node** | A function that takes the current state and returns an *update* to it |
| **Edge** | A connection saying which node runs after another |
| **Conditional edge** | A function that looks at the state and returns the name of the next node |
| **`START` / `END`** | Special markers for where the graph begins and finishes |
| **`StateGraph`** | The builder we add nodes and edges to |
| **Compile** | Validates the graph and turns it into a runnable object with `invoke`, `stream`, and the rest |

A compiled graph is a LangChain runnable, so it's invoked the same way as a chain.

---

## A First Graph

RAG from the previous unit is a natural first graph: two fixed steps, one after the other.

```python
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END

# retriever, prompt, llm, and format_docs as built in the RAG notes

class RAGState(TypedDict):
    question: str
    context: str
    answer: str

def retrieve(state: RAGState) -> dict:
    docs = retriever.invoke(state["question"])
    return {"context": format_docs(docs)}

def generate(state: RAGState) -> dict:
    reply = (prompt | llm).invoke({"context": state["context"], "question": state["question"]})
    return {"answer": reply.content}

builder = StateGraph(RAGState)
builder.add_node("retrieve", retrieve)
builder.add_node("generate", generate)
builder.add_edge(START, "retrieve")
builder.add_edge("retrieve", "generate")
builder.add_edge("generate", END)

graph = builder.compile()

result = graph.invoke({"question": "How much PTO do employees accrue?"})
print(result["answer"])
```

*Builds a two-node graph that retrieves context and then generates an answer from it.*

Three things to notice:

- **Nodes return partial updates.** `retrieve` returns only `{"context": ...}`; LangGraph merges that into the state. A node never has to copy the fields it didn't touch.
- **The input is a partial state too.** We passed only `question`; the other fields fill in as nodes run.
- **The result is the final state** — every field, not just the answer. `result["context"]` is right there for citing or debugging.

For a pipeline this simple, LCEL is just as good. The graph form pays off once we need something LCEL can't express: a loop, a branch based on state, or a pause.

---

## Mixing Fixed and Model-Driven Steps

What sets LangGraph apart is putting fixed and model-driven steps in one flow. A support assistant might always load the customer record (fixed), then run a tool-calling loop (model-driven), then always check the reply against policy (fixed):

```
START ─► load_customer ─► agent ◄──► tools
                            │
                            ▼
                      policy_check ─► END
```

*A graph where the model controls only the middle loop; our code guarantees the first and last steps.*

The model decides how many times to go around the `agent ⇄ tools` loop, but it can't skip the customer lookup or the policy check. Those are edges in code. That's the core appeal: autonomy exactly where we want it, guarantees everywhere else.

---

## How a Graph Runs

LangGraph executes in **super-steps**. In each one, every node that's ready runs; nodes that run in parallel share a super-step, and nodes that run in sequence take separate ones. After each super-step, the nodes' updates are merged into the state, and the edges determine which nodes run next. Execution ends when there are no more nodes to run — typically on reaching `END`.

This is also what `recursion_limit` counts. A graph that cycles (as every agent loop does) will hit the limit and raise `GraphRecursionError` rather than run forever.

We can print the structure of any compiled graph as a Mermaid diagram — handy for checking that the edges are what we meant:

```python
print(graph.get_graph().draw_mermaid())
```

*Prints the compiled graph's nodes and edges as Mermaid diagram source.*

---

## LangChain vs LangGraph

| | LangChain (`create_agent`, LCEL) | LangGraph |
|---|---|---|
| Level | High — prebuilt agent and chain patterns | Low — we define every node and edge |
| Control flow | Fixed loop, customized with middleware | Anything: branches, cycles, parallel steps, sub-graphs |
| State | A message list (extendable) | Any schema we define |
| Best for | Standard agents and linear pipelines | Custom flows, multi-agent systems, long-running and resumable work |

They aren't competitors. LangChain's agent runs on LangGraph, and a LangGraph node can call any LangChain model, chain, retriever, or even a whole `create_agent` agent.

---

## Key Takeaways

- LangGraph models an application as nodes (functions) joined by edges, sharing one state object.
- `create_agent` is itself a LangGraph graph — the reason it supports checkpointers, recursion limits, and interrupts.
- Drop down to LangGraph when the flow's shape needs to change: fixed steps around a model loop, custom branching, richer state, or multiple agents.
- Build with `StateGraph(State)`, `add_node`, `add_edge`, `START`/`END`, then `compile()`.
- Nodes return partial updates, which are merged into the shared state.
- A graph runs in super-steps; `recursion_limit` caps how many can run.

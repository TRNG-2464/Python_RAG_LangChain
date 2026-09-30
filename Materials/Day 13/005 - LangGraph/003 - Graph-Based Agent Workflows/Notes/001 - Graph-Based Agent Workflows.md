# Graph-Based Agent Workflows

With nodes, edges, and state in hand, we can build the agent loop ourselves: a node that calls the model, a node that runs tools, a **conditional edge** that decides whether to keep going, and a **cycle** back from tools to model. Everything `create_agent` does is here in plain view — and once it's ours, we can put review points, fixed steps, and extra loops wherever the task needs them.

---

## The Agent Loop as a Graph

Compare this with the manual loop from the Tool Integration notes. The pieces are identical; they've just been rearranged into nodes and edges:

```python
from langchain_core.messages import SystemMessage, ToolMessage
from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, MessagesState, START, END

# get_order and track_package: the order tools from the What Are AI Agents notes
tools = [get_order, track_package]
tools_by_name = {t.name: t for t in tools}
llm_with_tools = ChatOllama(model="llama3.1", temperature=0).bind_tools(tools)

SYSTEM = SystemMessage("You help customers track orders. Use the tools; never guess.")

def call_model(state: MessagesState) -> dict:
    reply = llm_with_tools.invoke([SYSTEM] + state["messages"])
    return {"messages": [reply]}

def call_tools(state: MessagesState) -> dict:
    results = []
    for call in state["messages"][-1].tool_calls:
        try:
            output = tools_by_name[call["name"]].invoke(call["args"])
        except Exception as e:
            output = f"Error: {e}"
        results.append(ToolMessage(content=str(output), tool_call_id=call["id"]))
    return {"messages": results}

def should_continue(state: MessagesState) -> str:
    return "tools" if state["messages"][-1].tool_calls else END

builder = StateGraph(MessagesState)
builder.add_node("agent", call_model)
builder.add_node("tools", call_tools)
builder.add_edge(START, "agent")
builder.add_conditional_edges("agent", should_continue, ["tools", END])
builder.add_edge("tools", "agent")

graph = builder.compile()
```

*Builds the tool-calling agent loop by hand: a model node, a tools node, a conditional exit, and a cycle back.*

Mapping it back to the manual loop:

| Manual loop | Graph |
|---|---|
| `messages` list we append to | `MessagesState`, merged by `add_messages` |
| `llm_with_tools.invoke(messages)` | the `agent` node |
| `for call in reply.tool_calls: ...` | the `tools` node |
| `if not reply.tool_calls: break` | `should_continue` returning `END` |
| the `for` loop itself | the edge from `tools` back to `agent` |
| `range(5)` iteration cap | `recursion_limit` |

`add_conditional_edges` takes the source node, a routing function that returns the next node's name, and the list of possible destinations. The list isn't required for execution, but it lets LangGraph validate the graph and draw it correctly.

Notice the system message is added inside `call_model` rather than stored in state. The instructions are re-applied on every call but never pile up in the saved history.

Running it looks like running `create_agent`:

```python
result = graph.invoke(
    {"messages": [("user", "Where is order A1001 right now?")]},
    {"recursion_limit": 12},
)
print(result["messages"][-1].content)
```

*Runs the hand-built agent with a step cap and prints the final reply.*

---

## Prebuilt Pieces

The tools node and routing function are standard enough that LangGraph ships them:

```python
from langgraph.prebuilt import ToolNode, tools_condition

builder = StateGraph(MessagesState)
builder.add_node("agent", call_model)
builder.add_node("tools", ToolNode(tools))
builder.add_edge(START, "agent")
builder.add_conditional_edges("agent", tools_condition)
builder.add_edge("tools", "agent")
```

*Replaces the hand-written tools node and router with LangGraph's prebuilt equivalents.*

`ToolNode` runs every tool call in the last `AIMessage` and returns the matching `ToolMessage`s. `tools_condition` routes to the node named `"tools"` when there are tool calls and to `END` otherwise. Having written both by hand, we know exactly what they do.

---

## Watching It Run

`stream` with `stream_mode="updates"` yields each node's update as the node finishes — the clearest view of the loop in motion:

```python
for update in graph.stream(
    {"messages": [("user", "Where is order A1001 right now?")]},
    stream_mode="updates",
):
    for node, change in update.items():
        last = change["messages"][-1]
        print(f"[{node}]", getattr(last, "tool_calls", None) or last.content)
```

*Prints which node ran at each step and what it added: tool requests from `agent`, results from `tools`.*

---

## Fixed Steps Around the Loop

Because the loop is just edges, adding guaranteed steps before or after it is a matter of wiring. Here a fixed node loads the customer's record before the model ever runs:

```python
class SupportState(MessagesState):
    customer_id: str
    customer_profile: str

def load_customer(state: SupportState) -> dict:
    return {"customer_profile": crm_lookup(state["customer_id"])}   # plain code, no model

def call_model(state: SupportState) -> dict:
    system = SystemMessage(f"Customer profile:\n{state['customer_profile']}")
    return {"messages": [llm_with_tools.invoke([system] + state["messages"])]}

builder = StateGraph(SupportState)
builder.add_node("load_customer", load_customer)
builder.add_node("agent", call_model)
builder.add_node("tools", ToolNode(tools))
builder.add_edge(START, "load_customer")
builder.add_edge("load_customer", "agent")
builder.add_conditional_edges("agent", tools_condition)
builder.add_edge("tools", "agent")
```

*Puts a fixed, code-only step in front of the model-driven loop, so it always runs exactly once.*

The model can't skip the lookup, and it doesn't spend a tool call on it. A guardrail node after the loop — checking the final reply against a policy before it reaches the user — is wired the same way.

---

## Cycles for Repeat Work

Cycles aren't only for tool calls. Any "try, check, try again" process is a cycle with a condition. Here a draft is reviewed and revised until it passes or runs out of attempts:

```python
from typing_extensions import TypedDict

# llm: a plain ChatOllama model
# reviewer: llm.with_structured_output(...) on a schema with passed: bool and feedback: str

class DraftState(TypedDict):
    request: str
    draft: str
    feedback: str
    attempts: int

def write(state: DraftState) -> dict:
    prompt = f"Write a reply to: {state['request']}"
    if state.get("feedback"):
        prompt += f"\n\nRevise this draft:\n{state['draft']}\n\nReviewer feedback: {state['feedback']}"
    return {"draft": llm.invoke(prompt).content, "attempts": state.get("attempts", 0) + 1}

def review(state: DraftState) -> dict:
    verdict = reviewer.invoke(state["draft"])
    return {"feedback": "" if verdict.passed else verdict.feedback}

def after_review(state: DraftState) -> str:
    if not state["feedback"] or state["attempts"] >= 3:
        return END
    return "write"

builder = StateGraph(DraftState)
builder.add_node("write", write)
builder.add_node("review", review)
builder.add_edge(START, "write")
builder.add_edge("write", "review")
builder.add_conditional_edges("review", after_review, ["write", END])
```

*A write-review cycle that revises until the reviewer passes the draft or three attempts are used.*

The `attempts` counter lives in state, and the exit condition checks it. That's a cap specific to this loop, independent of the graph-wide `recursion_limit` — every cycle should have one.

---

## Interrupting for Review

`interrupt()` pauses a graph from inside a node. The run stops, its state is checkpointed, and whatever we pass to `interrupt()` is surfaced to the caller. When the caller resumes with `Command(resume=value)`, that value becomes the return value of `interrupt()`.

Here a review node sits between the model and the tools, gating sensitive calls:

```python
from typing import Literal
from langgraph.types import interrupt, Command
from langgraph.checkpoint.memory import InMemorySaver

# issue_refund: a @tool that refunds an order
# call_model: the MessagesState version from the first example
all_tools = tools + [issue_refund]
llm_with_tools = ChatOllama(model="llama3.1", temperature=0).bind_tools(all_tools)

SENSITIVE = {"issue_refund"}

def route_after_agent(state: MessagesState) -> str:
    calls = state["messages"][-1].tool_calls
    if not calls:
        return END
    return "review" if any(c["name"] in SENSITIVE for c in calls) else "tools"

def review(state: MessagesState) -> Command[Literal["tools", "agent"]]:
    calls = state["messages"][-1].tool_calls
    decision = interrupt({"pending": [{"name": c["name"], "args": c["args"]} for c in calls]})

    if decision == "approve":
        return Command(goto="tools")

    rejected = [ToolMessage(content=f"Rejected by reviewer: {decision}", tool_call_id=c["id"]) for c in calls]
    return Command(goto="agent", update={"messages": rejected})

builder = StateGraph(MessagesState)
builder.add_node("agent", call_model)
builder.add_node("review", review)
builder.add_node("tools", ToolNode(all_tools))
builder.add_edge(START, "agent")
builder.add_conditional_edges("agent", route_after_agent, ["review", "tools", END])
builder.add_edge("tools", "agent")

graph = builder.compile(checkpointer=InMemorySaver())
```

*Routes sensitive tool calls through a review node that pauses for a decision, then continues to the tools or back to the model.*

The review node returns a **`Command`**, which combines a state update with a routing decision. Two rules come with it: the return type must be annotated with the possible destinations (`Command[Literal["tools", "agent"]]`), and a node that routes with `Command` shouldn't also have normal outgoing edges. Pick one routing mechanism per node.

Driving it:

```python
config = {"configurable": {"thread_id": "ticket-812"}}

result = graph.invoke({"messages": [("user", "Refund order A1001 in full.")]}, config, version="v2")
print(result.interrupts[0].value)     # {'pending': [{'name': 'issue_refund', 'args': {...}}]}

result = graph.invoke(Command(resume="approve"), config, version="v2")
# or: graph.invoke(Command(resume="amount exceeds policy limit"), config, version="v2")
```

*Runs until the review pause, shows the pending call, then resumes with the reviewer's decision.*

With `version="v2"`, `invoke` returns an object with `.value` (the state) and `.interrupts`. Without it, the same information arrives as a plain dict with the interrupts under `result["__interrupt__"]`. For UIs that drive interruptible graphs, the LangGraph docs recommend event streaming with `graph.stream_events(..., version="v3")`, which exposes the same interrupts alongside streamed output.

Interrupts have rules worth knowing before they cause a bug:

- **A checkpointer and a thread id are required.** The pause *is* a saved checkpoint.
- **On resume, the node restarts from the top,** not from the `interrupt()` line. Anything before the `interrupt()` runs again — keep side effects (writes, emails, charges) after it, or in a later node. That's why the review node above does nothing but read state before pausing.
- **Don't wrap `interrupt()` in a bare `try/except`.** It works by raising a special exception, and catching it prevents the pause.
- **Keep multiple interrupts in a node in a fixed order.** On resume they're matched to resume values by position.

Compiling with `interrupt_before=["tools"]` pauses before a node without any code in the node. It's handy for stepping through a graph while debugging, but `interrupt()` is the tool for real approval flows, since it can carry a payload and route on the answer.

---

## Key Takeaways

- The agent loop is two nodes (model, tools), a conditional edge that exits when there are no tool calls, and an edge back from tools to model.
- `ToolNode` and `tools_condition` are the prebuilt versions of the tools node and router.
- `stream(..., stream_mode="updates")` shows each node's update as the graph runs.
- Fixed steps are ordinary edges before or after the loop — the model can't skip them.
- Any try-check-retry process is a cycle; give each one its own counter-based exit.
- `interrupt(payload)` pauses inside a node; `Command(resume=value)` continues it, and that value becomes `interrupt()`'s return.
- A node returning `Command(goto=..., update=...)` routes and updates at once; annotate its destinations and don't mix it with normal edges.
- On resume the interrupted node re-runs from the top, so keep side effects after the `interrupt()` call.

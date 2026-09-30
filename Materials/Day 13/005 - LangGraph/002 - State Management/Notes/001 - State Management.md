# State Management

Every LangGraph node reads from and writes to one shared **state** object. Getting the state right is most of the work of building a graph: its **schema** says what data exists, its **reducers** say how each node's updates are merged in, and a **checkpointer** saves it after every step so a run can be inspected, paused, and resumed.

---

## The State Schema

State is usually a `TypedDict`. Each key is an independent field — LangGraph calls them **channels** — that nodes can read and update:

```python
from typing_extensions import TypedDict

class TicketState(TypedDict):
    ticket_text: str
    category: str
    priority: int
    reply: str
```

*Declares the fields a support-ticket graph shares between its nodes.*

A node receives the whole current state and returns a dict containing only the keys it wants to change. Keys it leaves out are untouched:

```python
def classify(state: TicketState) -> dict:
    route = router.invoke(state["ticket_text"])     # a structured-output model call
    return {"category": route.category, "priority": route.priority}
```

*Reads one field and returns updates for two others; everything else in the state is left as-is.*

Pydantic models and dataclasses also work as schemas. `TypedDict` is the common default. It's lightweight and doesn't validate at runtime, so a node that returns the wrong type isn't caught at the point of the write.

---

## Reducers: How Updates Merge

When a node returns `{"priority": 2}`, what happens to the old value? That's decided per key by a **reducer**. With no reducer declared, the default is **overwrite**: the new value replaces the old one.

For fields that should accumulate, we attach a reducer with `Annotated`. Its second argument is a function that takes the current value and the update and returns the merged result:

```python
import operator
from typing import Annotated
from typing_extensions import TypedDict

class ResearchState(TypedDict):
    question: str                                  # overwrite
    findings: Annotated[list[str], operator.add]   # append

def search_docs(state: ResearchState) -> dict:
    return {"findings": [f"docs: {lookup_docs(state['question'])}"]}

def search_tickets(state: ResearchState) -> dict:
    return {"findings": [f"tickets: {lookup_tickets(state['question'])}"]}
```

*Declares `findings` with `operator.add` as its reducer, so each node's list is concatenated onto it rather than replacing it.*

`operator.add` on two lists concatenates them, so each node adds its items to `findings` without erasing anyone else's. Note that nodes still return a *list* — the reducer combines list with list.

Reducers matter most when nodes run in parallel. If both search nodes run in the same super-step:

```python
builder.add_edge(START, "search_docs")
builder.add_edge(START, "search_tickets")      # both start at once
```

*Fans out from `START` so the two search nodes run in the same super-step.*

...then both write `findings` in one step. With the `operator.add` reducer, both results are kept. Without it, LangGraph can't know which value should win, and it raises `InvalidUpdateError` instead of silently picking one. Any key that more than one parallel node writes needs a reducer.

A reducer can be any two-argument function. This one keeps a bounded history:

```python
def keep_last_5(current: list, update: list) -> list:
    return (current + update)[-5:]

class State(TypedDict):
    recent_errors: Annotated[list[str], keep_last_5]
```

*A custom reducer that appends new items but keeps only the five most recent.*

---

## Messages and add_messages

A message list is the most common state field, and it gets a purpose-built reducer, `add_messages`:

```python
from typing import Annotated
from typing_extensions import TypedDict
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

class ChatState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
```

*Declares a message-list field whose updates are merged by `add_messages`.*

`add_messages` does more than append:

- **Appends** new messages to the end, so a node returns `{"messages": [reply]}`, not the whole history.
- **Replaces by id.** If an incoming message has the same `id` as one already in the list, it replaces that one. That's how a node can edit an earlier message in place.
- **Converts shorthand** like `{"role": "user", "content": "..."}` or `("user", "...")` into proper message objects.
- **Deletes** messages when given `RemoveMessage(id=...)` — useful for trimming history from inside a graph.

Because this pattern is so common, LangGraph ships it prebuilt as `MessagesState`. Subclass it to add fields:

```python
from langgraph.graph import MessagesState

class SupportState(MessagesState):
    customer_id: str
    escalated: bool
```

*Extends the prebuilt `messages` field with two extra fields of our own.*

---

## Persistence with Checkpointers

Compile a graph with a **checkpointer** and LangGraph saves a snapshot of the state after every super-step. Snapshots are grouped by a **thread id** that we pass in the config:

```python
from langgraph.checkpoint.memory import InMemorySaver

graph = builder.compile(checkpointer=InMemorySaver())

config = {"configurable": {"thread_id": "customer-42"}}

graph.invoke({"messages": [("user", "Hi, my name is Dana.")]}, config)
result = graph.invoke({"messages": [("user", "What's my name?")]}, config)
```

*Runs two turns on the same thread; the second turn starts from the state the first one saved.*

The second call didn't resend the first message — the checkpointer restored the thread's state, and `add_messages` appended the new turn to it. This is the conversation memory from the Memory Concepts notes, with the dict-of-lists replaced by a checkpointer keyed on thread id. A different `thread_id` starts from empty state.

A thread's saved state can be inspected at any time:

```python
snapshot = graph.get_state(config)
print(snapshot.values["messages"][-1].content)   # the current state
print(snapshot.next)                             # nodes due to run next; empty if finished

for past in graph.get_state_history(config):     # every checkpoint, newest first
    print(past.config["configurable"]["checkpoint_id"], past.next)
```

*Reads a thread's current state and walks its checkpoint history.*

`snapshot.next` tells us where a run stopped: empty if it finished, or the name of the node it's waiting on if it was paused or failed partway through. `graph.update_state(config, {...})` writes into a thread's state directly, applying the same reducers a node's return value would. It's how an operator or a review step corrects a run from outside.

---

## Resuming Where a Run Stopped

Because a checkpoint is saved after each super-step, a run that fails partway through hasn't lost the steps that succeeded. Invoking the same thread with `None` as the input resumes from the last checkpoint instead of starting over:

```python
try:
    graph.invoke({"question": "Summarize open tickets for ACME"}, config)
except TimeoutError:
    pass                          # e.g. a tool timed out in step 3

graph.invoke(None, config)        # retries from the failed step; steps 1-2 are not re-run
```

*Resumes a failed run from its last successful checkpoint rather than repeating the completed steps.*

This is the same mechanism that makes human-in-the-loop pauses possible. A pause is just a run that stopped on purpose, waiting to be resumed.

---

## Durable Checkpointers

`InMemorySaver` loses everything when the process exits. For state that must survive a restart, use a database-backed checkpointer. These live in separate packages:

| Checkpointer | Package | Import |
|---|---|---|
| `SqliteSaver` | `langgraph-checkpoint-sqlite` | `from langgraph.checkpoint.sqlite import SqliteSaver` |
| `PostgresSaver` | `langgraph-checkpoint-postgres` | `from langgraph.checkpoint.postgres import PostgresSaver` |

```python
from langgraph.checkpoint.sqlite import SqliteSaver

with SqliteSaver.from_conn_string("checkpoints.db") as checkpointer:
    graph = builder.compile(checkpointer=checkpointer)
    graph.invoke({"messages": [("user", "Hello")]}, {"configurable": {"thread_id": "t-1"}})
```

*Opens a SQLite-backed checkpointer, so thread state persists in a local file across restarts.*

`from_conn_string` is a context manager that owns the database connection, so the graph must be used inside the `with` block. Database checkpointers like `PostgresSaver` also need their tables created once, with `checkpointer.setup()`, typically as a deployment step.

Checkpointers serialize the state, so keep it to data: strings, numbers, lists, dicts, messages, Pydantic models. Clients, connections, and open files belong in module scope or node closures, not in the state.

---

## Key Takeaways

- State is a schema (usually a `TypedDict`) shared by every node; nodes return partial updates.
- Each key's reducer decides how updates merge; the default is overwrite.
- `Annotated[list, operator.add]` accumulates; any key written by parallel nodes needs a reducer or LangGraph raises `InvalidUpdateError`.
- `add_messages` appends, replaces by id, converts shorthand, and supports `RemoveMessage`; `MessagesState` packages it.
- A checkpointer saves state after every super-step, keyed by `thread_id` — conversation memory comes for free.
- `get_state`, `get_state_history`, and `update_state` inspect and correct a thread; `invoke(None, config)` resumes a stopped run.
- Use `SqliteSaver` or `PostgresSaver` for state that must survive a restart, and keep the state serializable.

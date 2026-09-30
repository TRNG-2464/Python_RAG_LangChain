# Interrupting for Approval

We'll take a working agent graph that changes things without asking and put a person in front of it. We'll cover compiling with a checkpointer (`InMemorySaver`), running with a `thread_id`, pausing inside a node with `interrupt()`, inspecting a paused run with `get_state()`, and resuming it with `Command(resume=...)` to approve or reject.

## Prerequisites

| Software | Required Version |
|---|---|
| Python | >=3.10 |
| langgraph | 1.2.12 |
| langchain-core | 1.6.6 |
| langchain-ollama | 1.1.0 |
| Ollama | any current release, running locally |
| Ollama model | `llama3.1` (must be tool-capable) |

Setup, from this lab's directory:

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
ollama pull llama3.1
```

Run it with `python src/main.py`.

---

## Guided walkthrough

Open `src/main.py`. It has a pretend IT support queue (`TICKETS`) and two tools. `list_tickets` only reads the queue, but `close_ticket` really changes it. Below those is a complete agent graph: a model node, a `ToolNode`, the prebuilt `tools_condition` router, and the cycle back. `statuses()` prints every ticket's status so we can see what changed.

Parts 2 and 3 edit the graph section. Every other part adds code below its banner. Each run starts fresh from the top, with all tickets open again.

### 1. Watch it act

Let's see the problem first. Add under Part 1:

```python
print("before:", statuses())
result = graph.invoke({"messages": [("user", "Close ticket T-102.")]})
print("reply:", result["messages"][-1].content)
print("after: ", statuses())
```

*Asks the agent to close a ticket and prints the queue before and after.*

Run it. T-102 goes from `open` to `closed`, and nobody was asked. The model decided, the tool ran, and the change is done. For closing a ticket that's an annoyance. For a refund, a deletion, or an email to a customer, it's the reason we don't ship the agent.

### 2. Add a checkpointer and a thread id

To pause a run and pick it up later, the run's state has to be saved somewhere outside the running `invoke` call. That's what a **checkpointer** does. In the graph section, change the compile line to:

```python
graph = builder.compile(checkpointer=InMemorySaver())
```

*Compiles the graph so it saves a snapshot of its state after every step.*

Run it. Part 1 now fails:

```
ValueError: Checkpointer requires one or more of the following 'configurable' keys: thread_id, checkpoint_ns, checkpoint_id
```

Saved state has to be filed under something. A **thread id** names the conversation the snapshots belong to. Update Part 1 so it passes one:

```python
config = {"configurable": {"thread_id": "desk-1"}}

print("before:", statuses())
result = graph.invoke({"messages": [("user", "Close ticket T-102.")]}, config)
print("reply:", result["messages"][-1].content)
print("after: ", statuses())
```

*Runs the same request, with its state saved under the thread id `desk-1`.*

Run it again. It behaves exactly like before, and the ticket still closes without asking. The difference is invisible for now: every step of that run was saved under `desk-1`.

### 3. Pause before the tools run

Now for the gate. We'll add a `review` node between the model and the tools. It calls `interrupt()`, which stops the run, saves it, and hands a payload back to whoever called `invoke`.

In the graph section, add these two functions above `builder = StateGraph(...)`:

```python
def route_after_agent(state: MessagesState) -> str:
    return "review" if state["messages"][-1].tool_calls else END


def review(state: MessagesState) -> Command[Literal["tools", "agent"]]:
    calls = state["messages"][-1].tool_calls
    decision = interrupt({"pending": [{"name": c["name"], "args": c["args"]} for c in calls]})

    if decision == "approve":
        return Command(goto="tools")

    rejected = [
        ToolMessage(content=f"Rejected by reviewer: {decision}", tool_call_id=c["id"])
        for c in calls
    ]
    return Command(goto="agent", update={"messages": rejected})
```

*A router that sends any tool request to `review`, and a review node that pauses for a decision, then either continues to the tools or sends a rejection back to the model.*

Then register the node and replace the `tools_condition` line so the model's tool requests go to `review` instead of straight to `tools`:

```python
builder.add_node("review", review)
builder.add_conditional_edges("agent", route_after_agent, ["review", END])
```

*Adds the review node and routes every tool request through it.*

A few things are going on in `review`:

- `interrupt(payload)` stops the run right there. When the run is resumed later, whatever value we resume with becomes the return value of `interrupt()`, so it lands in `decision`.
- The node returns a `Command`, which does two things at once: it picks the next node (`goto`) and, optionally, updates the state. The `Command[Literal["tools", "agent"]]` annotation tells LangGraph where it might go, since `review` has no ordinary edges.
- On a rejection we don't run the tool, but the model still asked for it and expects a result. So we answer each call with a `ToolMessage` that says it was refused, and send the run back to the model.

Finally, add one line to the end of Part 1 so we can see the pause:

```python
print("interrupt:", result.get("__interrupt__"))
```

*Prints the interrupt payload, if the run paused.*

Run it. This time `reply` is empty, `after` still shows T-102 as `open`, and `interrupt` shows the pending call:

```
interrupt: [Interrupt(value={'pending': [{'name': 'close_ticket', 'args': {'ticket_id': 'T-102'}}]}, id='...', response_schema=None)]
```

`invoke` returned, but the run isn't over. It's parked in the checkpointer under `desk-1`, waiting.

### 4. Inspect the paused state

A paused run can be read like any saved thread. Add under Part 4:

```python
snapshot = graph.get_state(config)
print("next:", snapshot.next)
print("pending:", snapshot.values["messages"][-1].tool_calls)
print("payload:", snapshot.interrupts[0].value)
```

*Reads `desk-1`'s saved state: which node it's waiting on, the tool call the model wants, and the interrupt payload.*

Run it. `next` is `('review',)`, which means the run stopped inside `review` and will continue from there. `pending` is the full tool call the model made, including its `id`. That's exactly what a reviewer needs to see: which tool, with which arguments. Nothing has happened to the queue yet.

### 5. Approve

To continue a paused run, we invoke the same thread with a `Command` that carries the decision. Add under Part 5:

```python
result = graph.invoke(Command(resume="approve"), config)
print("reply:", result["messages"][-1].content)
print("after:", statuses())
print("next:", graph.get_state(config).next)
```

*Resumes `desk-1` with an approval and prints the outcome.*

Run it. T-102 closes, the model confirms it, and `next` is now `()`, so the run is finished.

There's a detail here that matters: on resume, `review` runs again **from the top**, not from the `interrupt()` line. The second time, `interrupt()` returns `"approve"` instead of pausing. That's fine here because everything before the `interrupt()` only reads state. A node that sent an email *before* its `interrupt()` would send it twice. Keep side effects after the pause, or in a later node.

### 6. Reject

Now the other answer. Add under Part 6:

```python
result = graph.invoke({"messages": [("user", "Close ticket T-101.")]}, config)
print("pending:", result["__interrupt__"][0].value)

result = graph.invoke(Command(resume="the printer vendor hasn't confirmed the fix"), config)
print("reply:", result["messages"][-1].content)
print("after:", statuses())
```

*Asks to close another ticket on the same thread, then resumes with a rejection reason instead of an approval.*

Run it. T-101 stays `open`, and the model explains that the reviewer rejected it, usually repeating our reason. Any value other than `"approve"` goes down the rejection branch, so the reason we give becomes the tool result the model reads.

Since this is the same thread, the model also has the whole earlier exchange about T-102 in its history. The checkpointer restored it, and `add_messages` appended the new turn.

### 7. A second thread

The thread id is the only thing tying a run to its saved state. Add under Part 7:

```python
other = {"configurable": {"thread_id": "desk-2"}}
print("desk-2 before:", graph.get_state(other).values)

result = graph.invoke({"messages": [("user", "Close ticket T-103.")]}, other)
print("desk-2 pending:", result["__interrupt__"][0].value)

for name, cfg in [("desk-1", config), ("desk-2", other)]:
    snap = graph.get_state(cfg)
    print(f"{name}: next={snap.next}, messages={len(snap.values['messages'])}")
```

*Starts a new thread, pauses it, and compares where each thread stands.*

Run it. `desk-2` starts completely empty, with `{}` for values. After the request it's paused at `review` with 2 messages, while `desk-1` is finished with 8. Each thread is its own conversation with its own pause.

The tickets, on the other hand, are shared. `TICKETS` is ordinary data outside the graph, so a change approved on either thread affects both. The checkpointer saves the *conversation*, not the world the tools act on.

---

## Exercises

1. **Only gate what's risky.** `list_tickets` only reads, but right now it also stops for review. Change `route_after_agent` so calls go straight to `tools` unless one of them is in a `SENSITIVE = {"close_ticket"}` set. Ask "Which tickets are open?" and confirm it answers without pausing, then confirm closing a ticket still pauses.

2. **Edit instead of approve or reject.** Let a reviewer fix the arguments. Resume with a dict like `{"action": "edit", "ticket_id": "T-103"}`, and in `review`, build a replacement `AIMessage` with the corrected tool call and the **same message `id`** as the original, so `add_messages` replaces it instead of appending. Then route to `tools`. Ask to close T-102 and have the reviewer change it to T-103.

3. **A reviewer at the keyboard.** Write a small driver loop that sends a request, and while the result has an `__interrupt__`, prints the pending calls and reads `approve` or a reason from `input()`, then resumes with it. Run several requests through it on one thread.

4. **Survive a restart.** Swap `InMemorySaver` for `SqliteSaver` (`pip install langgraph-checkpoint-sqlite`, then `from langgraph.checkpoint.sqlite import SqliteSaver`, used as a context manager with `SqliteSaver.from_conn_string("checkpoints.db")`). Write one script that makes a request and exits while paused, and a second that resumes the same thread id with an approval.

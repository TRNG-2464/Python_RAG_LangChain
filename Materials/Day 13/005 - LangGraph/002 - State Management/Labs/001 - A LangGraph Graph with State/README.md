# A LangGraph Graph with State

We'll rebuild the tool-calling agent as a LangGraph graph, one piece at a time. We'll cover a `TypedDict` state schema with the `add_messages` reducer, nodes that return partial updates, a conditional edge with `add_conditional_edges`, and the cycle from the tools back to the model. Then we'll swap the reducer for plain overwrite and watch the conversation history disappear.

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

Open `src/main.py`. The model is ready, and two tools are already defined, `get_weather` and `convert_currency`, backed by small hardcoded dicts. `llm_with_tools` is the model with both tools bound. Parts 2 through 5 each have a `banner(...)` call. Add each part's code below its banner.

Each run executes the whole file from the top, so earlier parts re-run every time.

### 1. The state schema

In LangGraph, every node reads from one shared state object and returns updates to it. The schema says what's in that state. Add under Part 1:

```python
class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
```

*Declares a state with one field, a list of messages, whose updates are merged by the `add_messages` reducer.*

The `Annotated[..., add_messages]` part is the **reducer**. It tells LangGraph what to do when a node returns `{"messages": [...]}`. Without it, the new list would replace the old one. With it, the new messages are appended. Keep this line in mind, because Part 6 is all about it.

There's nothing to run yet.

### 2. A one-node graph

A node is just a function that takes the state and returns a dict of updates. Add under Part 2:

```python
def call_model(state: AgentState) -> dict:
    print(f"  [agent] sees {len(state['messages'])} message(s)")
    reply = llm_with_tools.invoke(state["messages"])
    return {"messages": [reply]}


builder = StateGraph(AgentState)
builder.add_node("agent", call_model)
builder.add_edge(START, "agent")
builder.add_edge("agent", END)
graph = builder.compile()

result = graph.invoke({"messages": [HumanMessage("What's the weather in Oslo?")]})

print("state keys:", list(result.keys()))
for message in result["messages"]:
    message.pretty_print()
```

*Wraps the model call in a node, wires it from `START` to `END`, runs it, and prints the final state.*

Run it. `invoke` returns the whole final state, not just the reply. Look at what's in `messages`: our `HumanMessage` and the model's `AIMessage`, both there. The `AIMessage` has no text, only a request to call `get_weather` for Oslo. The graph has nowhere to send that request yet, so the run just ends. We'll fix that over the next three parts.

`call_model` returned a list with *only* the reply in it. It didn't copy the history into its return value. The reducer appended the reply to the existing list for us. That's the habit to build: a node returns just what it changed.

### 3. A tool node

Next, a node that runs tools. It reads the tool calls off the last message and returns the results. Add under Part 3:

```python
def call_tools(state: AgentState) -> dict:
    results = []
    for call in state["messages"][-1].tool_calls:
        output = tools_by_name[call["name"]].invoke(call["args"])
        print(f"  [tools] {call['name']}({call['args']}) -> {output}")
        results.append(ToolMessage(content=output, tool_call_id=call["id"]))
    return {"messages": results}


update = call_tools(result)
print(update)
```

*Defines a tools node, then tests it by calling it directly on the state Part 2 left in `result`.*

Run it. The one-node graph in Part 2 stopped with the model's `get_weather` request as the last message, and we handed that state to `call_tools` ourselves. It returned `{'messages': [ToolMessage(...)]}`, which is a partial update just like `call_model`'s.

A node is an ordinary function. We can call it, test it, and print what it returns, without a graph around it.

### 4. A conditional edge

Now we'll put both nodes in one graph and let the graph decide which way to go after the model runs. Add under Part 4:

```python
def should_continue(state: AgentState) -> str:
    return "tools" if state["messages"][-1].tool_calls else END


builder = StateGraph(AgentState)
builder.add_node("agent", call_model)
builder.add_node("tools", call_tools)
builder.add_edge(START, "agent")
builder.add_conditional_edges("agent", should_continue, ["tools", END])
graph = builder.compile()

result = graph.invoke({"messages": [HumanMessage("What's the weather in Oslo?")]})
print([type(m).__name__ for m in result["messages"]])
```

*Adds a routing function that sends the run to `tools` when the model requested a call, and to `END` otherwise.*

`add_conditional_edges` takes the source node, a function that returns the name of the next node, and the list of places it's allowed to go.

Run it. The output ends with `ToolMessage`. The router saw a tool call and sent the run to `tools`, and the weather was fetched. But nobody told the model, so there's no final answer. `tools` has no outgoing edge, so the run simply stops after it. The `END` branch is used when the model replies without a tool call, which is what its final answer will look like once it can see the results.

### 5. Close the cycle

The missing piece is an edge from `tools` back to `agent`, so the model gets to read the results. Add under Part 5:

```python
builder = StateGraph(AgentState)
builder.add_node("agent", call_model)
builder.add_node("tools", call_tools)
builder.add_edge(START, "agent")
builder.add_conditional_edges("agent", should_continue, ["tools", END])
builder.add_edge("tools", "agent")
graph = builder.compile()

result = graph.invoke(
    {"messages": [HumanMessage("What's the weather in Lisbon right now, and how much is 100 USD in EUR?")]},
    {"recursion_limit": 10},
)
for message in result["messages"]:
    message.pretty_print()
```

*Builds the full agent loop, with an edge from `tools` back to `agent` that forms the cycle, and runs a question that needs both tools.*

Run it and watch the `[agent]` and `[tools]` lines:

```
  [agent] sees 1 message(s)
  [tools] get_weather({'city': 'Lisbon'}) -> 22C and sunny
  [tools] convert_currency({'amount': '100', 'from_currency': 'USD', 'to_currency': 'EUR'}) -> 100.0 USD = 92.0 EUR
  [agent] sees 4 message(s)
```

The second time through, the model sees four messages: the question, its own request for two tools, and both results. That growing list is what lets it write an answer that uses both. The cycle plus the conditional edge *is* the agent loop. `recursion_limit` is the step cap, the same job `max_steps` did in a hand-written loop.

### 6. Swap the reducer

Now we'll see what the reducer was doing for us. Go back to Part 1 and remove the reducer, so `messages` falls back to the default, which is overwrite:

```python
class AgentState(TypedDict):
    messages: list[AnyMessage]
```

*Declares the same field with no reducer, so each update replaces the list instead of adding to it.*

Change nothing else, and run the whole file again. Compare with the previous run:

- **Part 2** prints only the `AIMessage` with its tool request. The question we asked is gone from the state.
- **Part 4** ends with just one `ToolMessage` in the list.
- **Part 5**'s second `[agent]` line says it sees **2** messages instead of 4. Those are the two tool results, with no question and no request in front of them. The answer no longer fits the question. In our run it was just *"The current exchange rate is 1 USD = 0.92 EUR."*, with no mention of Lisbon or its weather, because the model no longer knows what we asked.

Every node still returned exactly what it did before. The only difference is how those returns were merged into the state. That's why the reducer earns a place in the schema: updates merge, and the reducer decides how.

Put the `add_messages` reducer back when you're done.

---

## Exercises

1. **Count the steps.** Add a `steps: Annotated[int, operator.add]` field to the state (import `operator`). Have both nodes return `{"steps": 1}` alongside their messages, pass `"steps": 0` in the input, and print the total after the Part 5 run. Then remove the reducer from `steps` and see what the count turns into.

2. **A bounded log.** Write a custom reducer `keep_last_3(current, update)` that appends and keeps only the three most recent items. Use it on a new `tool_log: Annotated[list[str], keep_last_3]` field, where the tools node adds one line per call like `"get_weather(Oslo)"`. Ask for the weather in four cities at once and print `tool_log` at the end.

3. **Two writers at once.** Build a separate small graph with a `TypedDict` that has a `notes: list[str]` field (no reducer) and two nodes that each return `{"notes": [...]}`. Wire *both* from `START`, so they run in the same step, and invoke it. Read the error, then fix the schema so both notes survive.

4. **The prebuilt pieces.** Replace `call_tools` and `should_continue` with LangGraph's `ToolNode(tools)` and `tools_condition` (both from `langgraph.prebuilt`). Run the Part 5 question again and confirm the message list is the same shape.

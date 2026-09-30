# The Agent Loop

We'll build an agent loop by hand. We bind a tool, read the model's `tool_calls`, run the function ourselves, append a `ToolMessage` with the matching `tool_call_id`, and repeat until the model stops asking. Then we'll replace the whole loop with `create_agent` and confirm it produces the same message list.

## Prerequisites

| Software | Required Version |
|---|---|
| Python | >=3.10 |
| langchain | 1.4.3 |
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

Open `src/main.py`. The model is set up, and there's a small pretend order system (`ORDERS` and `PACKAGES`) that the model has never seen. Every part has a `banner(...)` call that prints a header. Add each part's code below its banner.

Each run executes the whole file from the top, so earlier parts re-run every time. That's expected.

### 1. Ask without tools

Let's start with what the model can do on its own. Add under Part 1:

```python
reply = llm.invoke([HumanMessage("What is the status of order A1001?")])
print(reply.content)
```

*Asks a question about data the model has no access to.*

Run it. The model asks which company we mean, or says it can't look orders up. It has no way to reach `ORDERS`. Everything it knows is in its weights and in the messages we send it.

### 2. Define a tool and bind it

We'll give the model a way to ask for that data. Add under Part 2:

```python
@tool
def get_order(order_id: str) -> str:
    """Look up an order by its id (e.g. 'A1001'). Returns its status and tracking number."""
    order = ORDERS.get(order_id)
    if order is None:
        return f"No order found with id {order_id}"
    return f"status={order['status']}, tracking={order['tracking']}"


llm_with_tools = llm.bind_tools([get_order])

messages = [HumanMessage("What is the status of order A1001?")]
reply = llm_with_tools.invoke(messages)

print("content:", repr(reply.content))
print("tool_calls:", reply.tool_calls)
```

*Defines an order-lookup tool, tells the model about it, and asks the same question again.*

Run it. This time `content` is empty and `tool_calls` holds something like:

```
[{'name': 'get_order', 'args': {'order_id': 'A1001'}, 'id': '3b60e2c0-...', 'type': 'tool_call'}]
```

That's a request, not a result. `get_order` hasn't run. The model has only described the call it wants. The tool call is plain data sitting on the reply, and it's up to us to act on it.

### 3. Run the tool and append the result

Now we act on it. Add under Part 3:

```python
available = {"get_order": get_order}

messages.append(reply)

for call in reply.tool_calls:
    result = available[call["name"]].invoke(call["args"])
    print(f"running {call['name']}({call['args']}) -> {result}")
    messages.append(ToolMessage(content=result, tool_call_id=call["id"]))
```

*Looks up each requested tool by name, runs it, and appends the model's request followed by our result.*

Run it and look at the order we appended in. The model's own message (the one carrying the request) goes in first, then the `ToolMessage`. The `tool_call_id` on the result must match the `id` on the request, because that's how the model pairs each result with the call that asked for it.

The `available` dict is the whole dispatch mechanism. The model sends a name, and our code decides what function that name maps to.

### 4. Ask again with the history

The model still hasn't answered. We need to send it the history with the result in it. Add under Part 4:

```python
final = llm_with_tools.invoke(messages)
print("answer:", final.content)
print("tool_calls:", final.tool_calls)
```

*Sends the question, the tool request, and the tool result back to the model.*

Run it. Now `content` has a real answer built from our data, and `tool_calls` is empty. That empty list is how the model signals it's done.

### 5. Make it a loop

Parts 2 through 4 were one round: ask, run the tools, ask again. Some questions need more than one round, and we can't know in advance how many. So we'll repeat until the model stops asking. Add under Part 5:

```python
def run_loop(question, tools, max_steps=5):
    bound = llm.bind_tools(tools)
    by_name = {t.name: t for t in tools}
    messages = [HumanMessage(question)]

    for step in range(max_steps):
        reply = bound.invoke(messages)
        messages.append(reply)

        if not reply.tool_calls:
            print("done:", reply.content)
            return messages

        for call in reply.tool_calls:
            result = by_name[call["name"]].invoke(call["args"])
            print(f"  step {step}: {call['name']}({call['args']}) -> {result}")
            messages.append(ToolMessage(content=result, tool_call_id=call["id"]))

    print(f"gave up after {max_steps} steps")
    return messages


run_loop("What is the status of order A1002?", [get_order])
```

*Wraps the request-run-append cycle in a loop that ends when a reply has no tool calls, or when the step cap is hit.*

Run it. One tool step, then `done:`. It's the same logic as Parts 2 through 4, and the only new pieces are the loop and the exit check.

`max_steps` isn't optional. A model that misreads a result can keep asking forever, so every agent loop needs a hard ceiling.

### 6. A second tool

Now we'll give the model a choice of tools. We'll add a second one and ask a question that needs both. Add under Part 6:

```python
@tool
def track_package(tracking_number: str) -> str:
    """Get the current location of a package from its carrier tracking number."""
    return PACKAGES.get(tracking_number, f"No tracking info for {tracking_number}")


loop_messages = run_loop(
    "What is the status of order A1002, and where is the package with tracking number 1Z999AA10123456784 right now?",
    [get_order, track_package],
)
```

*Adds a package-tracking tool and asks a question that needs both tools.*

Run it:

```
  step 0: get_order({'order_id': 'A1002'}) -> status=processing, tracking=None
  step 0: track_package({'tracking_number': '1Z999AA10123456784'}) -> Out for delivery in Austin, TX
done: The status of order A1002 is "processing" and the package with tracking number 1Z999AA10123456784 is currently "out for delivery" in Austin, TX.
```

Both calls are labeled `step 0`. The model saw two independent questions and requested both tools in a single reply, so `reply.tool_calls` held two entries and our inner `for` ran each one. The loop then went around a second time, sent the model both results, and got the answer. Nothing in our code decided which tools to use or how many. The model chose from the names and docstrings, and the loop kept going until it stopped asking.

Local models like `llama3.1` tend to request everything they can in one step like this. A question where the second call needs a value from the first call's result is where small models get unreliable. They sometimes skip the second call or invent its argument instead of waiting for the result. Printing the calls, as `run_loop` does, is how we catch that.

### 7. Replace the loop with create_agent

LangChain ships this loop prebuilt. Add under Part 7:

```python
agent = create_agent(model=llm, tools=[get_order, track_package])

result = agent.invoke(
    {"messages": [{"role": "user", "content": "What is the status of order A1002, and where is the package with tracking number 1Z999AA10123456784 right now?"}]}
)

for message in result["messages"]:
    message.pretty_print()

print("\nour loop:    ", [type(m).__name__ for m in loop_messages])
print("create_agent:", [type(m).__name__ for m in result["messages"]])
```

*Runs the same question through the prebuilt agent, prints its full message list, and compares its shape with ours.*

Run it. The two lines at the bottom should match:

```
our loop:     ['HumanMessage', 'AIMessage', 'ToolMessage', 'ToolMessage', 'AIMessage']
create_agent: ['HumanMessage', 'AIMessage', 'ToolMessage', 'ToolMessage', 'AIMessage']
```

It's one AI message carrying both tool calls, then a result for each call, then the answer. That's the same structure our loop built by hand.

`create_agent` takes a dict with a `messages` list and returns the full state at the end of the run, not just the answer. The final answer alone is `result["messages"][-1].content`. It also handles what our loop doesn't, like a step limit that raises an error and hooks for middleware. But the mechanism underneath is the one we just wrote. When an agent misbehaves, printing its message list and reading it the way we read ours is how we find out why.

---

## Exercises

1. **A tool that changes something.** Add a `cancel_order(order_id: str) -> str` tool that sets an order's status to `"cancelled"`, but only if it's still `"processing"`. Otherwise it returns a message saying why it can't. Ask the model to cancel both A1001 and A1002 in one question, then print `ORDERS`. Check how many calls it requested in one step, and whether its answer matches what actually happened to each order.

2. **Hit the ceiling.** Run the Part 6 question through `run_loop` with `max_steps=1` and see what comes back. Then make the same thing happen with `create_agent` by passing `{"recursion_limit": 2}` as the second argument to `invoke`. Catch the `GraphRecursionError` it raises (from `langgraph.errors`) and print a friendly message.

3. **Survive a bad call.** Ask for an order that doesn't exist, then change `get_order` to raise a `KeyError` instead of returning a message. Your loop crashes; `create_agent` doesn't. Make `run_loop` handle both an exception inside a tool and a tool name that isn't in `by_name`, by sending the error back to the model as the `ToolMessage` content instead of crashing.

4. **Where do instructions live?** Give `run_loop` a `system` parameter that puts a `SystemMessage` at the front of the history, and pass `create_agent` the same text through `system_prompt=`. Try `"Answer in one sentence and always include the tracking number."` Compare the two message lists. Does the system message show up in both?

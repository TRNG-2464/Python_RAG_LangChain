# What Are AI Agents?

An **AI agent** is a model running in a loop that chooses its own next step. It reads the task, decides whether to call a tool, reads the result, and decides again — until it judges the task done. The tool-calling loop we wrote by hand in the Tool Integration notes is already an agent. This topic is about what makes that loop different from everything we built before it, and when that difference is worth paying for.

---

## Who Decides the Next Step

Every LLM application we've written so far falls into one of three shapes. What separates them is who controls the flow:

| Shape | Who decides what happens next | Example |
|---|---|---|
| **Single call** | Nobody — one request, one reply | Summarize this email |
| **Chain / pipeline** | Our code, fixed in advance | RAG: retrieve → format → generate |
| **Agent** | The model, at runtime | "Where is order A1001?" — the model picks which lookups to run, and how many |

A RAG chain always retrieves once and generates once, no matter the question. An agent might call zero tools, or one, or six, depending on what each result tells it. That runtime choice of control flow is the defining property. Tools alone don't make an agent — a chain can call a tool at a fixed step. The loop, with the model deciding when to leave it, does.

---

## Anatomy of the Loop

An agent is built from five pieces, all of which we've already met:

- **Model** — a tool-capable chat model that decides the next action.
- **Tools** — the actions available to it, described by name, docstring, and schema.
- **Instructions** — the system prompt: the goal, the rules, when to stop.
- **State** — the growing message list: the task, every tool request, every result.
- **Stop condition** — the model replies without requesting a tool, or we hit a limit.

Each pass through the loop is the same cycle: the model reads the full state, emits either tool calls or a final answer, and if it asked for tools, our code runs them and appends the results. The model never remembers anything between passes — it re-reads the whole message list every time. The "agent" is really the loop plus that list.

---

## A Task That Needs More Than One Step

A task only needs an agent when the next step depends on a result the model hasn't seen yet. Here the second lookup can't be made until the first one returns a tracking number:

```python
from langchain_core.tools import tool

ORDERS = {"A1001": {"status": "shipped", "tracking": "1Z999AA10123456784"}}
PACKAGES = {"1Z999AA10123456784": "Out for delivery in Austin, TX"}

@tool
def get_order(order_id: str) -> str:
    """Look up an order by its id (e.g. 'A1001'). Returns status and tracking number."""
    order = ORDERS.get(order_id)
    if order is None:
        return f"No order found with id {order_id}"
    return f"status={order['status']}, tracking={order['tracking']}"

@tool
def track_package(tracking_number: str) -> str:
    """Get the current location of a package from its carrier tracking number."""
    return PACKAGES.get(tracking_number, f"No tracking info for {tracking_number}")
```

*Defines two tools where the second needs an input that only the first can supply.*

We could write that loop by hand again. LangChain ships it prebuilt as `create_agent`:

```python
from langchain.agents import create_agent
from langchain_ollama import ChatOllama

llm = ChatOllama(model="llama3.1", temperature=0)

agent = create_agent(
    model=llm,
    tools=[get_order, track_package],
    system_prompt="You help customers track orders. Use the tools; never guess a status or location.",
)

result = agent.invoke({"messages": [{"role": "user", "content": "Where is order A1001 right now?"}]})

for message in result["messages"]:
    message.pretty_print()
```

*Builds the prebuilt agent loop, runs one task, and prints every message the run produced.*

The input is a dict with a `messages` list, and the output is the same shape: the full state at the end of the run, not just the answer. Printing every message is the most useful debugging habit with agents. For this task, the sequence we're looking for is:

```
Human   Where is order A1001 right now?
AI      tool_calls: get_order(order_id='A1001')
Tool    status=shipped, tracking=1Z999AA10123456784
AI      tool_calls: track_package(tracking_number='1Z999AA10123456784')
Tool    Out for delivery in Austin, TX
AI      (final answer, no tool_calls)
```

*The shape of a two-step run: each tool round adds an AI request and a Tool result before the final reply.*

That trace is exactly the message list our manual loop built. `create_agent` adds the loop control, and hooks for **middleware** — reusable pieces that run around each model or tool call — but no new mechanism. A local model will occasionally deviate from this sequence (skip a step, or answer early); reading the trace is how we see it.

The final answer alone is `result["messages"][-1].content`.

---

## Stopping: The Model Decides, We Enforce

The model ends the run by replying without tool calls. We can't rely on that alone. A model that misreads a result can request the same tool forever, so every agent needs a hard ceiling.

`create_agent` returns a LangGraph graph, which carries a **recursion limit**: each model call and each round of tool execution counts as a step, and exceeding the limit raises `GraphRecursionError`:

```python
from langgraph.errors import GraphRecursionError

try:
    result = agent.invoke(
        {"messages": [{"role": "user", "content": "Where is order A1001 right now?"}]},
        {"recursion_limit": 10},
    )
except GraphRecursionError:
    print("Agent did not finish within 10 steps.")
```

*Caps the run at ten graph steps and handles the case where the model never stops.*

For a softer stop, the built-in `ModelCallLimitMiddleware` counts model calls and can end the run gracefully instead of raising:

```python
from langchain.agents.middleware import ModelCallLimitMiddleware

agent = create_agent(
    model=llm,
    tools=[get_order, track_package],
    middleware=[ModelCallLimitMiddleware(run_limit=5, exit_behavior="end")],
)
```

*Limits a single run to five model calls, ending the run rather than raising when the limit is hit.*

---

## The Cost of Autonomy

Letting the model choose the path buys flexibility, and we pay for it in three ways:

- **Cost and latency.** Every step is a model call that re-sends the entire history. A four-step run costs far more than four times a single call.
- **Predictability.** The same input can take different paths on different runs. Testing an agent means testing distributions of behavior, not one output.
- **Compounding error.** If each step is right 95% of the time, a ten-step run is fully right only about 60% of the time (0.95¹⁰ ≈ 0.60). Longer loops are less reliable, not just slower.

This is why the right question is never "can we make this an agent?" but "does this task require the model to choose the path?" If we can write the steps down in advance, a chain is cheaper, faster, and easier to test. Agents earn their keep when the number or order of steps genuinely depends on intermediate results — open-ended lookups, multi-system troubleshooting, research across sources.

---

## Running Agents Locally

Two practical notes for Ollama:

- **The model must be tool-capable** (`llama3.1`, `qwen2.5`, `qwen3`, `mistral-nemo`, and similar). A model without tool training ignores the tools or describes calls in prose.
- **Small models drift on long loops.** They lose track of the goal, repeat calls, or stop early. Keep the toolset small, the tool descriptions sharp, and the step limit tight.

---

## Key Takeaways

- An agent is a model in a loop that decides its own next step; the defining property is model-controlled flow, not the presence of tools.
- Its pieces are a model, tools, instructions, a message-list state, and a stop condition.
- `create_agent(model, tools, system_prompt=...)` is the prebuilt loop; it takes and returns a `{"messages": [...]}` state.
- Print every message in `result["messages"]` to see what the agent actually did.
- The model ends the run by not calling a tool; we enforce a ceiling with `recursion_limit` or `ModelCallLimitMiddleware`.
- Agents cost more, vary more, and compound errors across steps — use one only when the path genuinely can't be fixed in advance.

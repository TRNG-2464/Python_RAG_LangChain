# Tool Integration

A model can't look up today's weather, query our database, or send an email. It can only produce text. **Tool integration** is the pattern that gets around this: we describe some Python functions to the model, and when it decides one would help, it replies with a *request* to call it. Our code runs the function and hands the result back.

The critical point, and the one that's easiest to misread: **the model never executes anything.** It emits a structured request. We execute. That boundary is where all the control — and all the security — lives.

---

## The Call-and-Return Loop

Every tool interaction follows the same four steps:

```
1. We send:     messages + tool definitions
2. Model sends: "call get_weather(city='Paris')"     ← a request, not a result
3. We run:      get_weather("Paris") → "18°C, clear"
4. We send:     messages + the tool result → model writes the final answer
```

Steps 2–4 can repeat. The model might call one tool, look at the result, and decide it needs another. A loop that keeps going until the model stops asking for tools is, essentially, an **agent**.

---

## Defining a Tool

The `@tool` decorator turns a Python function into something a model can be told about:

```python
from langchain_core.tools import tool

@tool
def get_weather(city: str) -> str:
    """Get the current weather for a city.

    Args:
        city: The name of the city, e.g. 'Paris' or 'Austin'.
    """
    return f"18°C and clear in {city}"

@tool
def add_to_cart(product_id: str, quantity: int = 1) -> str:
    """Add a product to the user's shopping cart."""
    return f"Added {quantity} x {product_id}"
```

*Decorates plain functions so LangChain can generate a schema the model understands.*

The decorator reads three things and sends them to the model: the **function name**, the **type hints**, and the **docstring**.

That docstring is not documentation for us — it's the prompt the model uses to decide whether this tool is the right one. A vague docstring produces a model that calls the wrong tool or doesn't call any. Type hints matter just as much: `quantity: int` is what makes the model send `2` rather than `"two"`, and a parameter with a default becomes optional in the schema.

We can inspect what the model will actually see:

```python
print(get_weather.name)          # 'get_weather'
print(get_weather.description)   # the docstring
print(get_weather.args)          # {'city': {'title': 'City', 'type': 'string'}}
```

*Shows the generated schema — useful for debugging why a model isn't picking a tool.*

For anything beyond a couple of scalar arguments, define the input as a Pydantic model and attach it, so each field gets its own description:

```python
from pydantic import BaseModel, Field

class SearchInput(BaseModel):
    query: str = Field(description="search terms")
    limit: int = Field(default=5, description="max results, 1-50")

@tool(args_schema=SearchInput)
def search_products(query: str, limit: int = 5) -> str:
    """Search the product catalog."""
    ...
```

*Attaches an explicit schema so every argument carries its own description and constraints.*

---

## Binding Tools to a Model

`bind_tools()` attaches the definitions to a model. It returns a new model — the original is untouched:

```python
from langchain_ollama import ChatOllama

llm = ChatOllama(model="llama3.1", temperature=0)
llm_with_tools = llm.bind_tools([get_weather, add_to_cart])
```

*Produces a model that knows about both tools and may request them.*

Now when we invoke it, the reply may contain tool calls instead of (or alongside) content:

```python
from langchain_core.messages import HumanMessage

messages = [HumanMessage("What's the weather in Paris?")]
reply = llm_with_tools.invoke(messages)

print(reply.content)      # often '' — the model has nothing to say yet
print(reply.tool_calls)
# [{'name': 'get_weather', 'args': {'city': 'Paris'}, 'id': 'call_abc123', 'type': 'tool_call'}]
```

*Invokes the tool-aware model and inspects the structured call request it returned.*

An empty `.content` with a populated `.tool_calls` is normal and expected — the model is waiting on us. If the question doesn't need a tool ("What's 2+2?"), `.tool_calls` comes back empty and `.content` has the answer.

---

## Executing and Returning the Result

We run the requested function and send the result back as a `ToolMessage`. The `tool_call_id` is what pairs a result with its request:

```python
from langchain_core.messages import ToolMessage

messages.append(reply)                      # the AIMessage carrying the tool_calls

available = {"get_weather": get_weather, "add_to_cart": add_to_cart}

for call in reply.tool_calls:
    selected = available[call["name"]]
    result = selected.invoke(call["args"])
    messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))

final = llm_with_tools.invoke(messages)
print(final.content)     # 'It's currently 18°C and clear in Paris.'
```

*Runs each requested tool and appends its result as a `ToolMessage`, then calls the model again for the final answer.*

Three details that cause real bugs:

- **The `AIMessage` must be appended too.** Sending a `ToolMessage` without the request that produced it is a protocol error on most providers.
- **The `tool_call_id` must match.** When the model requests three tools at once, these ids are the only thing connecting each result to its request.
- **We invoke the tool, not the raw function.** `get_weather.invoke({"city": "Paris"})` takes the args dict directly; the decorated object isn't a plain callable any more.

---

## Making It a Loop

One round is rarely enough. Wrapping the exchange in a loop that continues while the model keeps asking for tools is the whole idea behind an agent:

```python
messages = [HumanMessage("What's the weather in Paris, and add product A17 to my cart?")]

for _ in range(5):                                  # a hard cap, always
    reply = llm_with_tools.invoke(messages)
    messages.append(reply)

    if not reply.tool_calls:
        break                                       # model is done

    for call in reply.tool_calls:
        try:
            result = available[call["name"]].invoke(call["args"])
        except Exception as e:
            result = f"Error: {e}"                  # let the model see and recover
        messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))

print(messages[-1].content)
```

*Repeats the call-and-return cycle until the model stops requesting tools, with an iteration cap and per-tool error handling.*

The iteration cap is not optional. A model that misreads a tool result can loop indefinitely, and on a local Ollama model that means a pegged CPU until we kill it.

Feeding errors back as tool results rather than raising is usually the better behavior — the model often recovers by fixing its arguments and trying again. Returning `"Error: city not found"` gives it something to work with; crashing gives it nothing.

That loop is standard enough that LangChain ships it prebuilt as `create_agent` (in `langchain.agents`), wrapping this same cycle with state handling, streaming, and step limits already wired in. We're staying with the manual version here, and that's the right order to learn it in: when an agent misbehaves, debugging means reasoning about exactly the messages we assembled by hand above.

---

## The Ollama Caveat

Tool calling requires a model trained for it. With Ollama, that means `llama3.1`, `qwen2.5`, `mistral-nemo`, or another tool-capable model. Calling `bind_tools()` on a model without that training produces one of two failure modes: tool calls are silently ignored, or the model describes the call in prose instead of emitting a structured request.

If `.tool_calls` is consistently empty when it obviously shouldn't be, the model is the first thing to check, not the prompt. Local models are also measurably weaker than hosted ones at picking the right tool once there are more than a handful available — keep the toolset small.

---

## Designing Tools That Work

Most tool-calling problems are tool-design problems:

- **Few tools, clearly distinct.** Three tools with overlapping purposes confuse a model more than ten unrelated ones. If two tools could plausibly answer the same question, merge them.
- **Descriptive names and docstrings.** `search_customer_orders` beats `query`. Say when to use it, not just what it does.
- **Return text the model can read.** A tool returning a 4,000-row dump wastes the context window. Return a summary, or the top few rows.
- **Validate inside the tool.** The model's arguments are untrusted input — it will occasionally invent a plausible-looking id.
- **Never expose a destructive operation directly.** A tool that runs arbitrary SQL, deletes records, or spends money should sit behind an allowlist and a human confirmation step. The model decides *what* to ask for; our code decides what's permitted.

---

## Key Takeaways

- The model requests tool calls; our code executes them. That boundary is where control and safety live.
- `@tool` builds the schema from the function name, type hints, and docstring — the docstring is the model's instruction for when to use it.
- `bind_tools()` returns a tool-aware model whose replies may carry `.tool_calls` instead of content.
- Append the `AIMessage`, then a `ToolMessage` per call with a matching `tool_call_id`, then invoke again for the final answer.
- Looping that exchange until no tools are requested is what makes an agent — always with a hard iteration cap.
- Return errors to the model as tool results so it can recover instead of crashing the run.
- Ollama needs a tool-capable model; empty `.tool_calls` usually means the wrong model, not a bad prompt.

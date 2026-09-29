# Watching a Model Call Tools

We'll define Python functions as tools, watch the model request them, run them ourselves, and feed the results back. We'll cover `@tool`, `bind_tools()`, inspecting `.tool_calls`, returning a `ToolMessage`, and looping until the model is done.

## Prerequisites

| Software | Required Version |
|---|---|
| Python | >=3.10 |
| langchain-core | 1.6.4 |
| langchain-ollama | 1.1.0 |
| Ollama | any current release, running locally |
| Ollama model | `llama3.1` — must be tool-capable |

The model matters here. Tool calling only works on a model trained for it — `llama3.1`, `qwen2.5`, and `mistral-nemo` all work. A model without that training will silently ignore the tools.

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

Open `src/main.py`. The model is ready and the parts are marked out. Parts 2 through 5 already have a `banner(...)` call that prints a header, so we can tell which output came from which part. Add each part's code below its banner. Parts 1 and 6 don't get one — Part 1 prints nothing, and Part 6 edits earlier code rather than adding new code.

### 1. Define two tools

The `@tool` decorator turns a function into something the model can be told about. Add this under `# --- Part 1 ---`:

```python
@tool
def add(a: int, b: int) -> int:
    """Add two numbers together."""
    return a + b


@tool
def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    return f"18C and raining in {city}"
```

*Defines two tools; the docstrings and type hints are what the model reads.*

`get_weather` returns a hardcoded string on purpose — the point is watching the call happen, not fetching real weather.

### 2. See what the model sees

Add under `# --- Part 2 ---`:

```python
print(add.name)
print(add.description)
print(add.args)
```

*Prints the schema generated from the function's name, docstring, and type hints.*

Run it. That's the entire basis on which the model decides whether to use this tool. A vague docstring is a tool that never gets picked.

### 3. Bind and watch

Now attach the tools and ask something that needs one. Add under `# --- Part 3 ---`:

```python
llm_with_tools = llm.bind_tools([add, get_weather])

messages = [HumanMessage("What is 12 plus 30?")]
reply = llm_with_tools.invoke(messages)

print("content:", repr(reply.content))
print("tool_calls:", reply.tool_calls)
```

*Binds both tools and prints what came back for a question that needs one.*

Run it. `content` is probably empty and `tool_calls` has an entry like `{'name': 'add', 'args': {'a': 12, 'b': 30}, 'id': 'call_...'}`.

Nothing has been executed. The model asked us to run `add(12, 30)`. That's the whole idea — the model requests, we decide.

Try swapping the question for `"What is the capital of France?"` and run again. `tool_calls` is empty and `content` has the answer — the model only asks when a tool helps.

### 4. Run it and hand back the result

Add under `# --- Part 4 ---`:

```python
available = {"add": add, "get_weather": get_weather}

messages.append(reply)

for call in reply.tool_calls:
    result = available[call["name"]].invoke(call["args"])
    print(f"running {call['name']}({call['args']}) -> {result}")
    messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))

final = llm_with_tools.invoke(messages)
print("answer:", final.content)
```

*Runs each requested tool and appends its result, then calls the model again for the final answer.*

Run it. We execute the function, hand back the result, and the model writes the sentence.

Two details worth pausing on. We append `reply` — the message carrying the request — before appending the result; sending a result without its request is an error. And `tool_call_id` is what pairs each result with the call that asked for it.

### 5. Make it a loop

One round isn't always enough. Add under `# --- Part 5 ---`:

```python
messages = [HumanMessage("What is 5 plus 7, and what's the weather in Paris?")]

for step in range(5):
    reply = llm_with_tools.invoke(messages)
    messages.append(reply)

    if not reply.tool_calls:
        print("done:", reply.content)
        break

    for call in reply.tool_calls:
        result = available[call["name"]].invoke(call["args"])
        print(f"  step {step}: {call['name']}({call['args']}) -> {result}")
        messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))
```

*Repeats the request-and-return cycle until the model stops asking for tools.*

Run it and watch the steps print. That loop is what an agent is — there's nothing else to it.

`range(5)` is a hard cap, and it's not optional. A model that misreads a result can keep asking forever, and locally that means a pegged CPU until we kill it.

### 6. Break a tool

Let's see what happens when a tool fails. Change `add` to raise:

```python
@tool
def add(a: int, b: int) -> int:
    """Add two numbers together."""
    raise ValueError("calculator is offline")
```

*Makes the tool fail so we can see how the loop handles it.*

Run Part 5 — it crashes. Now catch it and hand the error back instead:

```python
        try:
            result = available[call["name"]].invoke(call["args"])
        except Exception as e:
            result = f"Error: {e}"
```

*Returns the error to the model as a tool result rather than crashing the run.*

Run it again. The model sees the error and usually responds sensibly rather than the program dying. Put `add` back to normal afterward.

---

## Exercises

1. **A third tool.** Write a `multiply` tool and add it to the bind list. Ask a question needing both `add` and `multiply` and watch the loop handle two steps.

2. **Sabotage a docstring.** Change `get_weather`'s docstring to just `"Does a thing."` and ask about the weather. Does the model still pick it? Change the name to `do_thing` too and try again.

3. **Default arguments.** Give `get_weather` a second parameter `units: str = "celsius"` and ask for the weather in Fahrenheit. Check `.tool_calls` to see what the model passed.

4. **Count the calls.** Add a counter that prints how many times the model called a tool before answering. Ask a question needing three tool calls and confirm the count.

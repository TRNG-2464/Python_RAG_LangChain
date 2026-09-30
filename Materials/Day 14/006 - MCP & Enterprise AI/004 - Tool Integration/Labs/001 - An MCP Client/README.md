# An MCP Client

We'll connect to a running MCP server from Python, discover its tools at runtime, and hand them to an agent. We'll cover `MCPAdapter` from `langchain.mcp`, reading tool names and schemas published by the server, calling an MCP tool directly with `ainvoke`, running `create_agent` with MCP tools, and mixing those tools with a local `@tool` function in one agent.

## Prerequisites

| Software | Required Version |
|---|---|
| Python | >=3.10 |
| langchain (with the `mcp` extra) | 1.4.3 |
| fastmcp | 4.0.10 (installed by `langchain[mcp]`) |
| langchain-ollama | 1.1.0 |
| Ollama | any current release, running locally |
| Ollama model | `llama3.1` (must be tool-capable) |

`langchain.mcp` is in beta, and importing it prints a `LangChainBetaWarning`. That's expected.

Setup, from this lab's directory:

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
ollama pull llama3.1
```

Run it with `python src/main.py`. We never start the server ourselves; the client launches it.

---

## Guided walkthrough

Two files matter here:

- `src/warehouse_server.py` is a finished MCP server with two tools, `shipping_cost` and `check_stock`, backed by `data/inventory.json`. We won't change it. Treat it as a server someone else wrote.
- `src/main.py` is our client, and it's where we'll work. It already opens a connection with `async with MCPAdapter(SERVER) as adapter:`. Because `SERVER` is a `Path` to a script, the adapter launches that script as a subprocess and talks to it over stdio.

All of our code goes **inside the `async with` block**, indented to match the banners. MCP tools are async-only, so this whole client is an `async def main()` run by `asyncio.run`.

Each run executes the whole file from the top.

### 1. List the server's tools

Let's find out what the server offers. Nothing in `main.py` knows yet. Add under Part 1:

```python
        tools = await adapter.list_tools()

        for t in tools:
            print(f"{t.name}: {t.description}")
            print(f"  args: {t.args}")
```

*Asks the server for its tools and prints each one's name, description, and argument schema.*

Run it:

```
shipping_cost: Calculate the shipping cost in US dollars for a parcel.
  args: {'weight_kg': {'type': 'number', 'description': "The parcel's weight in kilograms."}, 'express': {'default': False, 'type': 'boolean', 'description': 'Whether to use next-day express shipping.'}}
check_stock: Look up a product's stock level and storage bin by its SKU.
  args: {'sku': {'type': 'string', 'description': "The product's SKU, e.g. 'WID-100'."}}
```

Above them there's a `Starting MCP server 'warehouse' with transport 'stdio'` line. That's the server process the adapter just launched, logging to its stderr, which shares our terminal.

These tools arrived at runtime, over the protocol. The adapter sent a `tools/list` request and turned each entry into a LangChain tool. The `args` came from the server's published JSON Schema, not from any type hints in our code. That schema is exactly what a model will see when we hand it these tools.

### 2. Call a tool directly

Before a model gets involved, let's check the tools work by calling one ourselves. Add under Part 2:

```python
        by_name = {t.name: t for t in tools}

        result = await by_name["check_stock"].ainvoke({"sku": "WID-100"})
        print(result)
```

*Calls the server's `check_stock` tool through the adapter, with no model involved.*

Run it:

```
[{'type': 'text', 'text': 'Widget: 42 on hand in bin A-03', 'id': 'lc_...'}]
```

The result is a list of content blocks, not a plain string. That's the MCP `content` list from the server's response, carried over as-is. The function ran in the server process, and the adapter sent a `tools/call` and handed back what came back.

Now add one more line and run it again:

```python
        by_name["check_stock"].invoke({"sku": "WID-100"})
```

*Tries to call the same tool synchronously.*

It fails with `NotImplementedError: StructuredTool does not support sync invocation.` MCP tools are async-only, so it's `ainvoke` for the tool and, next, `ainvoke` for the agent. Delete that line before moving on.

### 3. Hand the tools to an agent

From here it's ordinary agent code. The tools list goes to `create_agent` like any other. Add under Part 3:

```python
        agent = create_agent(model=llm, tools=tools, system_prompt=SYSTEM_PROMPT)

        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": "How many Widgets (SKU WID-100) are in stock, and which bin are they in?"}]}
        )
        print(result["messages"][-1].content)
```

*Builds an agent from the server's tools and asks a question that needs one.*

Run it. The answer is 42 units in bin A-03, which the model could only get from the server.

We're calling the agent inside the `async with` block, so every tool call in this run reuses the one server process the adapter started. MCP tools can also work after the block exits, but then each call reconnects, which for a stdio server means launching it again.

### 4. Find the tool call in the messages

Let's look at how that answer was reached. Add under Part 4:

```python
        for message in result["messages"]:
            message.pretty_print()
```

*Prints every message from the Part 3 run.*

Run it and read down the list. We should see the question, then an AI message with a `check_stock` tool call and `sku: WID-100`, then a tool message holding the server's result, then the final answer.

It's the same shape as an agent with local tools. Nothing in the message list says "MCP". Between the tool call and the tool result, the adapter sent a `tools/call` to another process and turned its content blocks into the `ToolMessage` we're looking at, but the model never sees that hop.

### 5. Add a local tool

Now we'll mix an ordinary `@tool` function in with the server's tools. Add under Part 5:

```python
        @tool
        def convert_currency(amount_usd: float, to_currency: str) -> str:
            """Convert an amount in US dollars to another currency, given its three-letter code (e.g. 'EUR')."""
            rates = {"EUR": 0.92, "GBP": 0.79}
            rate = rates.get(to_currency.upper())
            if rate is None:
                return f"No rate for {to_currency}"
            return f"{round(amount_usd * rate, 2)} {to_currency.upper()}"

        mixed_agent = create_agent(
            model=llm, tools=[convert_currency, *tools], system_prompt=SYSTEM_PROMPT
        )

        for question in [
            "How much does it cost to ship a 3 kg parcel by express?",
            "What is 20 US dollars in British pounds?",
        ]:
            result = await mixed_agent.ainvoke({"messages": [{"role": "user", "content": question}]})
            calls = [c["name"] for m in result["messages"] for c in getattr(m, "tool_calls", [])]
            print(f"Q: {question}")
            print(f"   tools used: {calls}")
            print(f"   A: {result['messages'][-1].content}")
```

*Defines a local currency tool, builds one agent with it and the server's tools, and asks one question for each kind.*

Run it. The shipping question goes to `shipping_cost`, which runs in the server process. The currency question goes to `convert_currency`, which runs right here in our process. The agent picked each one from its name, description, and schema, and nothing else. By the time the list reached `create_agent`, a tool from another program and a function from this file were the same kind of object.

That's what MCP buys us. The warehouse tools could have been written by another team, in another language, and deployed somewhere we never touch. As long as the server speaks the protocol, our agent gets them at startup the same way it did here.

---

## Exercises

1. **Allowlist the tools.** Pretend the warehouse team adds a tool you haven't reviewed. Change the agent setup so it only gets tools whose names are in an `ALLOWED` set you control, and confirm by printing the names the agent received. Then ask a shipping question with `shipping_cost` left out of the set and see how the model responds.

2. **Server tools as strings.** Write an async helper `call_text(tool, args)` that calls an MCP tool directly and joins the `text` of every content block into one plain string. Use it to check stock for every SKU in `data/inventory.json` and print which ones are out of stock.

3. **Two servers, one agent.** Copy `warehouse_server.py` to a second server file with one new tool of your choice, such as a `supplier_lead_time(sku)` lookup. Connect to both through one adapter using an `mcpServers` config (`{"mcpServers": {"warehouse": {"command": "python", "args": [...]}, "suppliers": {...}}}`), print the tool names, and notice the prefixes. Ask a question that needs a tool from each server.

4. **Watch the protocol hop.** Add a `print(..., file=sys.stderr)` line inside `check_stock` in the server that logs the SKU it was asked about. Run the Part 3 question again and find that line in your terminal output among the client's prints. Then move the Part 3 agent call outside the `async with` block (keeping `tools` from inside it) and see whether it still works.

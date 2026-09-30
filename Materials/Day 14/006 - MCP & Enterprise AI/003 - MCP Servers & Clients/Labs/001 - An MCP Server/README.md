# An MCP Server

We'll build a small MCP server with FastMCP that exposes two tools over stdio, then talk to it by hand, with no client library and no model. We'll cover `@mcp.tool` and how type hints and docstrings become a published schema, running a stdio server, and sending raw JSON-RPC `tools/list` and `tools/call` requests with the per-request `_meta` block that protocol version `2026-07-28` requires.

## Prerequisites

| Software | Required Version |
|---|---|
| Python | >=3.10 |
| fastmcp | 4.0.10 |
| MCP protocol version | 2026-07-28 |

No model is involved in this lab, so Ollama isn't needed.

Setup, from this lab's directory:

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Run the server with `python src/server.py`. Stop it with `Ctrl+C`.

---

## Guided walkthrough

Open `src/server.py`. It creates a `FastMCP` server named `warehouse` and runs it when the file is executed. `DATA_FILE` points at `data/inventory.json`, a small stock list we'll use in Part 5. Add each part's code under its comment.

### 1. A tool with typed parameters

A tool is a plain Python function with a decorator on it. Add under Part 1:

```python
@mcp.tool
def shipping_cost(weight_kg: float, express: bool = False) -> float:
    """Calculate the shipping cost in US dollars for a parcel.

    Args:
        weight_kg: The parcel's weight in kilograms.
        express: Whether to use next-day express shipping.
    """
    rate = 3.0 if express else 1.5
    return round(5 + rate * weight_kg, 2)
```

*Registers a shipping-cost calculator as an MCP tool.*

Everything a client will learn about this tool comes from what we just wrote. The function name becomes the tool name, and the docstring becomes its description. The type hints become a JSON Schema, and so do the `Args:` lines and the default on `express`. Any program that connects to this server, whatever language it's written in, will read the tool from that schema.

### 2. Run it and watch it wait

In the terminal, from this lab's directory, run:

```bash
python src/server.py
```

A FastMCP banner box appears, followed by a line like `Starting MCP server 'warehouse' with transport 'stdio'`. Then nothing happens. The server is sitting on its standard input, waiting for a message.

That banner was written to **stderr**, not stdout. With the stdio transport, stdout is reserved for protocol messages, and anything else printed there would corrupt the stream the client is reading. That's why a stray `print()` in a stdio server breaks it, and why server logging goes to stderr.

Leave it running. For the next two parts, we're the client.

### 3. Send tools/list by hand

Every MCP message is one line of JSON-RPC 2.0. Let's ask the server what tools it has. Paste this into the running server's terminal as a single line, and press Enter:

```json
{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{"_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28","io.modelcontextprotocol/clientCapabilities":{}}}}
```

*A `tools/list` request, carrying the per-request metadata the current protocol requires.*

The `method` says what we want, and the `id` is how we'll recognize the reply. The `_meta` block is there because in protocol version `2026-07-28` every request is **stateless**. There's no handshake beforehand, so each request carries the protocol version and the client's capabilities itself.

The server answers with the tool list. It arrives as one long line, because the stdio transport frames each message as a single line. Formatted, the important part looks like this:

```json
{
  "name": "shipping_cost",
  "title": "Shipping Cost",
  "description": "Calculate the shipping cost in US dollars for a parcel.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "weight_kg": { "type": "number", "description": "The parcel's weight in kilograms." },
      "express": { "default": false, "type": "boolean", "description": "Whether to use next-day express shipping." }
    },
    "required": ["weight_kg"]
  },
  "outputSchema": { ... }
}
```

Match it up against the Python. `float` became `"number"`, and `express` isn't in `required` because it has a default. Each `Args:` line became a property `description`. When an agent eventually uses this server, this JSON is all its model will ever see of our tool.

Now let's see why `_meta` is there. Send the same request without it:

```json
{"jsonrpc":"2.0","id":2,"method":"tools/list"}
```

*A bare JSON-RPC request, with no protocol metadata.*

The server refuses it:

```json
{"jsonrpc":"2.0","id":2,"error":{"code":-32602,"message":"params._meta must be an object carrying the required 'io.modelcontextprotocol/protocolVersion' and 'io.modelcontextprotocol/clientCapabilities' envelope keys"}}
```

The reply carries `id` 2, matching the request it answers, which is how a client pairs replies with requests. Without the version, the server can't tell which rules the request follows.

The order we sent these in matters. The first request on a stdio connection tells the server which protocol era the client speaks. If a server's first message has no `_meta`, it assumes an older client that opens with an `initialize` handshake, and from then on it rejects `2026-07-28` requests on that connection with *"this connection serves the handshake protocol era"*. If you see that message, stop the server with `Ctrl+C`, start it again, and send a request with `_meta` first.

### 4. Send tools/call by hand

Now let's call it. Paste this as a single line:

```json
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"shipping_cost","arguments":{"weight_kg":2.5},"_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28","io.modelcontextprotocol/clientCapabilities":{}}}}
```

*Calls `shipping_cost` with a 2.5 kg parcel.*

The response carries the result two ways:

```json
"content": [{"text": "8.75", "type": "text"}],
"isError": false,
"structuredContent": {"result": 8.75}
```

`content` is a list of typed blocks, which is the form every MCP client understands and the form a model ends up reading. `structuredContent` is the same value as typed JSON, because our function declared a return type. Try sending the call again with `"express":true` added to `arguments`, and give it a new `id`.

That's the whole protocol for tools: list them, call one by name with arguments that match the schema. When you're done, stop the server with `Ctrl+C`.

### 5. A tool that reads the data file

Let's add a second tool, this one backed by data on disk. Add under Part 5:

```python
@mcp.tool
def check_stock(sku: str) -> str:
    """Look up a product's stock level and storage bin by its SKU.

    Args:
        sku: The product's SKU, e.g. 'WID-100'.
    """
    inventory = json.loads(DATA_FILE.read_text())
    item = inventory.get(sku.upper())
    if item is None:
        return f"Unknown SKU {sku}"
    return f"{item['name']}: {item['on_hand']} on hand in bin {item['bin']}"
```

*Registers a tool that reads `data/inventory.json` and reports on one product.*

Start the server again. It only reads its tools at startup, so a running server won't see the new one. Send the first `tools/list` line from Part 3, the one with `_meta`, and `check_stock` appears alongside `shipping_cost`. Then call it:

```json
{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"check_stock","arguments":{"sku":"WID-100"},"_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28","io.modelcontextprotocol/clientCapabilities":{}}}}
```

*Calls `check_stock` for the Widget SKU.*

The text comes back as `Widget: 42 on hand in bin A-03`. Try `GAD-200` and a SKU that doesn't exist.

`DATA_FILE` is built from `Path(__file__)`, not a bare `"data/inventory.json"`. When a host application launches a stdio server, it picks the working directory, and it usually isn't our project folder. Anchoring the path to the file keeps the server working no matter where it's launched from.

### 6. Change the interface and watch the schema follow

The schema isn't written anywhere by hand. It's generated from the function every time the server starts. Stop the server and change `shipping_cost` to take pounds:

```python
@mcp.tool
def shipping_cost(weight_lb: float, express: bool = False) -> float:
    """Calculate the shipping cost in US dollars for a parcel, from its weight in pounds.

    Args:
        weight_lb: The parcel's weight in pounds.
        express: Whether to use next-day express shipping.
    """
    rate = 3.0 if express else 1.5
    return round(5 + rate * weight_lb * 0.4536, 2)
```

*Renames the weight parameter, rewords the description, and converts pounds to kilograms internally.*

Start the server and send `tools/list` again. The property is now `weight_lb`, and the description and the per-argument text have both changed. Now send the Part 4 `tools/call` line unchanged, the one still using `weight_kg`. This time `isError` is `true`, and the text explains that `weight_lb` is missing and `weight_kg` was unexpected.

The failing call is the point. Anything that talks to this server depends on that schema: a script, a desktop app, an agent. A renamed parameter breaks every one of them, even though our Python still looks fine. Once a tool is published, its name, parameters, and description are an interface other people rely on.

---

## Exercises

1. **A tool with a list argument.** Add a `restock_report(skus: list[str]) -> str` tool that reports on several SKUs at once and flags any with zero on hand. Check how a `list[str]` shows up in `inputSchema`, then call it by hand with three SKUs.

2. **Validate what comes in.** Tool arguments come from whoever calls the server, so they can't be trusted. Make `shipping_cost` reject a weight that's zero, negative, or over 70 kg by raising a `ValueError` with a clear message. Call it by hand with a bad weight and look at what comes back. Then call it with a string like `"heavy"` for the weight and compare the two errors.

3. **Log without breaking the stream.** Add a line to `check_stock` that logs every lookup. First try `print(...)`, call the tool a couple of times, and look for lines on stdout that aren't JSON-RPC messages. A real client reads every stdout line as a protocol message. Then switch to `print(..., file=sys.stderr)` (import `sys`) and confirm that only JSON comes back on stdout.

4. **A structured result.** Write a `find_bin(bin: str) -> dict` tool that returns every product stored in a given bin as a dict. Call it and compare `content` with `structuredContent` for a dict return versus the string returns we've used so far.

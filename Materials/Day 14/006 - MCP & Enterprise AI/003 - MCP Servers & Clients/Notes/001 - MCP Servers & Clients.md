# MCP Servers & Clients

We'll build both ends: a server that exposes our Chroma-backed handbook as MCP tools, a resource, and a prompt, and a client that connects to it, discovers what it offers, and calls it. Both use **FastMCP**, a Python framework for MCP that handles the protocol, transports, and schema generation. It's also the library LangChain's MCP support is built on.

```bash
pip install fastmcp
```

*Installs FastMCP, which provides both the server framework and the client.*

The official MCP SDK for Python (the `mcp` package) is the other common choice. An early version of FastMCP was folded into it, which is why older examples import `from mcp.server.fastmcp import FastMCP`. The concepts are identical. We use the standalone `fastmcp` package here because it's what LangChain uses.

---

## Writing a Server

A FastMCP server is a `FastMCP` instance plus decorated functions. This one wraps the handbook vector store from the RAG unit:

```python
# handbook_server.py
import os
from pathlib import Path

from fastmcp import FastMCP
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings

DB_DIR = Path(__file__).parent / "chroma_db"

mcp = FastMCP("handbook")

store = Chroma(
    collection_name=os.environ.get("HANDBOOK_COLLECTION", "handbook"),
    embedding_function=OllamaEmbeddings(model="nomic-embed-text"),
    persist_directory=str(DB_DIR),
)

@mcp.tool
def search_handbook(query: str, k: int = 4) -> str:
    """Search the employee handbook and return the most relevant passages with their sources.

    Args:
        query: What to search for, e.g. 'parental leave eligibility'.
        k: How many passages to return, 1-10.
    """
    k = max(1, min(k, 10))
    docs = store.similarity_search(query, k=k)
    return "\n\n---\n\n".join(
        f"[Source: {d.metadata.get('source', 'unknown')}]\n{d.page_content}" for d in docs
    )

@mcp.resource("handbook://sources")
def list_sources() -> str:
    """The source files indexed in the handbook collection, one per line."""
    metadatas = store.get(include=["metadatas"])["metadatas"]
    return "\n".join(sorted({m.get("source", "unknown") for m in metadatas}))

@mcp.prompt
def policy_question(topic: str) -> str:
    """Ask a grounded question about a handbook policy."""
    return (
        f"Using only the search_handbook tool, explain our policy on {topic}. "
        "Cite the source file for each fact. If the handbook doesn't cover it, say so."
    )

if __name__ == "__main__":
    mcp.run()
```

*An MCP server exposing a search tool, a resource listing indexed files, and a reusable prompt, all over stdio by default.*

What the decorators do:

- **`@mcp.tool`** reads the function's name, type hints, and docstring and publishes them as a tool with a JSON Schema — the same job `@tool` does in LangChain. `k: int = 4` becomes an optional integer with a default. The docstring is the description the model will read, so it gets the same care.
- **`@mcp.resource("handbook://sources")`** registers read-only data under a URI. Clients read it by URI; it isn't offered to the model as something to call.
- **`@mcp.prompt`** publishes a template. Its arguments become the prompt's parameters, and the returned string becomes a user message.
- **`mcp.run()`** with no arguments serves over **stdio**.

Two server habits are already built into this example:

- **Paths are anchored to the file.** When a host launches a stdio server, the working directory is whatever the host chose, not our project folder. `Path(__file__).parent` makes `chroma_db` resolve the same way every time. A bare `"./chroma_db"` would silently create a new, empty store somewhere else.
- **Inputs are validated inside the tool.** `k` is clamped regardless of what the model sends. Tool arguments come from a model and are untrusted.

And one rule to never break on stdio: **no `print()`**. `stdout` is the protocol channel. Log to `stderr` (`print(..., file=sys.stderr)` or the `logging` module, which writes to `stderr` by default).

---

## Serving over HTTP

The same server becomes a network service by changing only the run call:

```python
if __name__ == "__main__":
    mcp.run(transport="http", host="127.0.0.1", port=8000)
```

*Serves the same tools, resource, and prompt over Streamable HTTP at `http://127.0.0.1:8000/mcp`.*

Now it runs on its own, and clients connect to `http://127.0.0.1:8000/mcp` rather than launching it. Binding to `127.0.0.1` keeps it reachable only from this machine. Exposing it more widely is a deployment decision that comes with authentication.

---

## Connecting as a Client

FastMCP's `Client` picks a transport from what we pass it: a `Path` to a script launches it as a stdio subprocess, a URL string connects over HTTP, and a `FastMCP` instance connects in memory (useful in tests). The client is an async context manager; the connection lives for the `async with` block.

```python
import asyncio
from pathlib import Path

from fastmcp import Client

async def main():
    async with Client(Path("handbook_server.py")) as client:
        print("protocol:", client.protocol_version)
        print("capabilities:", client.server_capabilities)

        for tool in await client.list_tools():
            print(tool.name, "-", tool.description)
            print(tool.input_schema)

        result = await client.call_tool("search_handbook", {"query": "parental leave", "k": 2})
        print(result.content[0].text)

        for resource in await client.list_resources():
            print(resource.uri, "-", resource.name)
        contents = await client.read_resource("handbook://sources")
        print(contents[0].text)

        prompt = await client.get_prompt("policy_question", {"topic": "remote work"})
        for message in prompt.messages:
            print(message.role, message.content.text)

asyncio.run(main())
```

*Launches the server as a subprocess, discovers its capabilities, then calls the tool, reads the resource, and renders the prompt.*

This is discovery in practice. Nothing in the client knew about `search_handbook` in advance. It listed the tools, read each one's schema from the server, and called by name. `server_capabilities` reports which primitives the server supports at all, so a client can skip asking a tools-only server for prompts.

The pieces of a tool result:

- **`result.content`** — the MCP content blocks exactly as sent; here, one text block.
- **`result.data`** — FastMCP's deserialized Python value, when the tool declares a return type.
- **`result.is_error`** — whether the tool reported failure. By default, a failed call raises `ToolError` in the client. Pass `raise_on_error=False` to inspect the failure instead.

For interactive exploration, the **MCP Inspector** (`npx @modelcontextprotocol/inspector`, which needs Node.js) is a browser UI that connects to a server and lets us list and call everything by hand. It's the most direct way to check a server before involving a model.

---

## Several Servers at Once

A client can also take a configuration dict in the `mcpServers` format that Claude Desktop, IDEs, and LangChain all share. Each entry is either a command to launch (stdio) or a URL (HTTP):

```python
config = {
    "mcpServers": {
        "handbook": {
            "command": "python",
            "args": ["handbook_server.py"],
            "env": {"HANDBOOK_COLLECTION": "handbook"},
        },
        "tickets": {"url": "http://127.0.0.1:8001/mcp"},
    }
}

async with Client(config) as client:
    tools = await client.list_tools()
```

*Connects to one stdio server and one HTTP server through a single client configuration.*

The `env` entry is how a stdio server receives its settings and secrets: the client sets those variables on the subprocess it launches. When one config holds several servers, their tools are presented with a prefix per server, so two servers can each have a `search` tool without colliding.

---

## Authenticating to a Remote Server

Auth depends on the transport.

**stdio servers** run locally as the user's own process, so the specification says they shouldn't use the MCP auth flow at all. They read credentials from the environment, passed in through `env` as above.

**HTTP servers** use standard HTTP authentication. The simplest case is a token the server's operators issued to us:

```python
import os
from fastmcp import Client

async with Client("https://mcp.internal.example.com/mcp", auth=os.environ["TICKETS_TOKEN"]) as client:
    tools = await client.list_tools()
```

*Connects to a remote server with a pre-issued bearer token read from the environment.*

FastMCP sends it as an `Authorization: Bearer ...` header on every request. Pass the bare token — FastMCP adds the `Bearer` prefix itself.

For servers that follow the MCP authorization spec, `auth="oauth"` runs the full **OAuth 2.1** flow instead. What happens underneath:

1. The client calls the server without a token and gets `401 Unauthorized`. The `WWW-Authenticate` header points to the server's **protected resource metadata**.
2. That metadata names the **authorization server** — often the company's existing identity provider — and the client fetches its metadata to find the login and token endpoints.
3. The client identifies itself to the authorization server, by a pre-registered client id or a published client metadata document.
4. The user logs in and consents in a browser. The client uses PKCE and names the MCP server as the token's intended audience.
5. The client receives an access token and sends it as a bearer token on every request.

Two rules from the specification make this safe in an enterprise setting. Tokens are **audience-bound**: a server must reject tokens that weren't issued for it. And a server must never pass the client's token through to other APIs it calls — it gets its own credentials for those. A compromised or malicious server therefore can't reuse a user's token elsewhere.

On the server side, FastMCP can verify bearer tokens or act as an OAuth resource server through its auth providers. The exact configuration depends on the identity provider, so it's covered in FastMCP's authentication documentation rather than reproduced here.

---

## Key Takeaways

- FastMCP builds servers from decorated functions: `@mcp.tool`, `@mcp.resource(uri)`, and `@mcp.prompt`, with schemas generated from type hints and docstrings.
- `mcp.run()` serves over stdio; `mcp.run(transport="http", ...)` serves over Streamable HTTP at `/mcp`.
- In stdio servers, never print to `stdout`, and anchor file paths to `__file__` because the host sets the working directory.
- `Client` infers the transport: a `Path` launches a subprocess, a URL connects over HTTP, a `FastMCP` instance connects in memory.
- Discovery is `list_tools`, `list_resources`, and `list_prompts`; use is `call_tool`, `read_resource`, and `get_prompt`.
- stdio servers take credentials from `env`; HTTP servers take a bearer token (`auth=token`) or run OAuth 2.1 (`auth="oauth"`).
- MCP tokens are audience-bound to one server and must never be passed through to other services.

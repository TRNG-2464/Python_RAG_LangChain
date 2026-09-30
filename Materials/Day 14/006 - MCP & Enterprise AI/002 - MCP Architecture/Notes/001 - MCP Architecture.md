# MCP Architecture

MCP has three roles, two layers, and a small set of message types. Once those are clear, every MCP interaction — in Claude Desktop, an IDE, or our own agent — reads the same way. The details below follow the current specification, protocol version `2026-07-28`.

---

## Host, Client, Server

- The **host** is the AI application: Claude Desktop, VS Code, or our LangChain agent. It owns the model, the conversation, and the user's consent, and it decides which servers to connect to.
- A **client** is a component inside the host that holds the connection to *one* server. A host connected to three servers runs three clients.
- A **server** is the program that provides tools, resources, and prompts. It may run locally as a subprocess or remotely as a web service.

```
┌──────────── Host (AI application) ────────────┐
│   model · conversation · user consent         │
│                                               │
│   Client 1 ──────┼──── stdio ────► Server A (local: filesystem)
│   Client 2 ──────┼──── stdio ────► Server B (local: database)
│   Client 3 ──────┼──── HTTP ─────► Server C (remote: ticketing)
└───────────────────────────────────────────────┘
```

*The host runs one client per server; each client talks to exactly one server.*

The host sits in the middle of everything. It gathers the tools from all its clients into one list for the model, routes each tool call the model makes to the right client, and decides what the user must approve. Servers never see each other, and they never see the model directly.

---

## Two Layers

MCP separates *what* is said from *how* it's delivered:

- The **data layer** defines the messages: discovery, the primitives (tools, resources, prompts), and notifications. It's built on JSON-RPC 2.0.
- The **transport layer** moves those messages: framing, delivery, cancellation, and authorization. MCP defines two standard transports, stdio and Streamable HTTP.

The same JSON-RPC messages travel over either transport unchanged. A server written for stdio can be offered over HTTP without touching its tools.

---

## The Message Layer: JSON-RPC 2.0

Every MCP message is a JSON-RPC 2.0 object, and there are three kinds:

- A **request** has an `id`, a `method`, and `params`, and expects a reply.
- A **response** carries the same `id` and either a `result` or an `error`.
- A **notification** has a `method` but no `id`, and gets no reply.

In the current protocol, clients send requests and servers answer them. Servers don't initiate requests of their own.

The exchange that matters most for agents is calling a tool. The request:

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "search_handbook",
    "arguments": { "query": "parental leave" },
    "_meta": {
      "io.modelcontextprotocol/protocolVersion": "2026-07-28",
      "io.modelcontextprotocol/clientInfo": { "name": "support-agent", "version": "1.0.0" },
      "io.modelcontextprotocol/clientCapabilities": {}
    }
  }
}
```

*A `tools/call` request: the tool name, its arguments, and the per-request metadata every request carries.*

And the response:

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "resultType": "complete",
    "content": [
      { "type": "text", "text": "[Source: benefits.md]\nEmployees receive 12 weeks of paid parental leave..." }
    ]
  }
}
```

*The matching response: the same `id`, and the tool's output as a list of typed content blocks.*

The result is a list of **content blocks**, each with a `type` — text here, but images and embedded resources are possible. The client hands this to the host, which turns it into a tool result for the model.

---

## Stateless Requests and Discovery

In the current protocol, every request stands on its own. The `_meta` block carries the protocol version and the client's capabilities, and normally the client's identity, on every request, so the server needs no memory of earlier ones. That's what lets a remote server sit behind an ordinary load balancer.

To learn what a server supports, a client can send a `server/discover` request. The response lists the protocol versions the server accepts, its **capabilities** (which primitives it offers, and whether it can report changes), and its identity. Discovery is optional; a client can simply send a request and handle a version error if one comes back.

Earlier protocol versions, up to `2025-11-25`, worked differently. The client opened a session with an `initialize` handshake before anything else, and the session carried the negotiated version and capabilities. Many servers in the wild still speak those versions. Clients that support both detect which kind of server they've reached and fall back to the handshake when needed. SDKs handle this for us, but it explains why older MCP material leads with `initialize`.

---

## What a Server Exposes

Servers offer three **primitives**, each with a method to list them and a method to use them:

| Primitive | What it is | Typically controlled by | Methods |
|---|---|---|---|
| **Tools** | Actions with side effects or computation | The model — it decides when to call one | `tools/list`, `tools/call` |
| **Resources** | Read-only data identified by URI (`file:///...`, `handbook://sources`) | The application — it decides what to load as context | `resources/list`, `resources/read` |
| **Prompts** | Parameterized prompt templates | The user — they pick one, like a slash command | `prompts/list`, `prompts/get` |

A tool's listing is what eventually reaches the model. Each entry from `tools/list` has a `name`, a `description`, and an `inputSchema` in JSON Schema:

```json
{
  "name": "search_handbook",
  "description": "Search the employee handbook and return the most relevant passages with their sources.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query": { "type": "string" },
      "k": { "type": "integer", "default": 4 }
    },
    "required": ["query"]
  }
}
```

*One tool from a `tools/list` response: its name, description, and argument schema.*

That's the same information `@tool` extracted from a Python function: a name, a docstring, and typed parameters. The difference is that the server published it, and our side reads it from the wire.

Clients can offer a primitive to servers too. **Elicitation** lets a server ask for user input partway through a request — to confirm an action, or to fill in a missing detail. In the current protocol, the server does this by returning an "input required" result instead of a final one. The client collects the input and retries the original request with the answers attached. Two older client features, **sampling** (a server asking the host's model for a completion) and protocol-level **logging**, are deprecated as of `2026-07-28`.

**Notifications** carry updates. Progress on a long-running request arrives as notifications tied to that request. Changes like "the tool list changed" are opt-in: a client that wants them opens a long-lived `subscriptions/listen` request, and the server sends matching notifications on it. A client that gets `notifications/tools/list_changed` re-runs `tools/list`.

---

## Transports

### stdio

The client launches the server as a **subprocess** and the two talk over its standard streams:

- The client writes requests to the server's `stdin`, one JSON message per line.
- The server writes responses and notifications to `stdout`, one per line.
- The server may write logs to `stderr`. It must never write anything to `stdout` that isn't an MCP message.
- The client shuts the server down by closing its `stdin`.

That `stdout` rule catches almost everyone once: a stray `print()` in a stdio server corrupts the message stream, and the client sees garbage or hangs. Log to `stderr` instead.

stdio servers are local, run with the user's own permissions, and typically serve a single client. Credentials come from the environment the client launches them with, not from an auth protocol.

### Streamable HTTP

The server runs as an independent web service with a single **MCP endpoint** (conventionally `/mcp`):

- Every client message is its own HTTP `POST` to that endpoint.
- The server answers each request with either a single JSON response or a **Server-Sent Events** stream scoped to that request. The stream is used when the server has progress notifications to send before the final result.
- Selected fields are mirrored into HTTP headers (`MCP-Protocol-Version`, `Mcp-Method`, and `Mcp-Name` for the tool, prompt, or resource) so gateways and load balancers can route and log without parsing the body.
- There are no protocol-level sessions and no standing `GET` stream in the current version. Both existed in earlier versions of this transport and were removed.

Remote servers serve many clients, so security is part of the transport. Servers must validate the `Origin` header to block DNS-rebinding attacks. When running locally for development, they should bind to `127.0.0.1` rather than `0.0.0.0`. Authentication uses standard HTTP. The specification's recommended approach is OAuth 2.1, with the client sending `Authorization: Bearer <token>` on every request.

An older HTTP transport, **HTTP+SSE** (separate endpoints for sending and receiving), is deprecated. We'll still see it referenced in older servers and tutorials.

| | stdio | Streamable HTTP |
|---|---|---|
| **Where the server runs** | Local subprocess, launched by the client | Independent service, local or remote |
| **Clients per server** | Typically one | Many |
| **Framing** | Newline-delimited JSON on stdin/stdout | One HTTP POST per message; JSON or SSE response |
| **Credentials** | Environment variables | OAuth 2.1 bearer tokens (or other HTTP auth) |
| **Good for** | Local tools: files, local databases, dev utilities | Shared, centrally managed services |

---

## Key Takeaways

- The host is the AI application; it runs one client per server and is the only party that talks to the model.
- The data layer is JSON-RPC 2.0: requests with an `id`, responses with the same `id`, and notifications with none.
- In protocol `2026-07-28`, every request carries its version and capabilities in `_meta`, and `server/discover` reports what a server supports. Older versions used an `initialize` handshake instead.
- Servers expose tools (`tools/list`, `tools/call`), resources (`resources/list`, `resources/read`), and prompts (`prompts/list`, `prompts/get`).
- A tool listing's name, description, and `inputSchema` are what the model ultimately sees.
- stdio launches the server as a subprocess and uses newline-delimited JSON; never print to `stdout` in a stdio server.
- Streamable HTTP uses one POST per message to a single endpoint, with JSON or SSE replies, `Origin` validation, and OAuth-based auth.

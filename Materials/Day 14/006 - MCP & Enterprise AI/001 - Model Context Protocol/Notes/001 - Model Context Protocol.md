# Model Context Protocol

Every tool we've written so far lives inside one application. A `@tool` function in our LangChain agent is available to that agent and nothing else. If a second team wants the same capability in their app, or we want it in an IDE assistant or a desktop chat client, it gets written again, in whatever shape each of those expects.

The **Model Context Protocol (MCP)** is an open standard that removes that duplication. An integration is written once as an **MCP server**, and any application that speaks MCP can discover and use it. MCP was introduced by Anthropic and is developed openly with a public specification. Clients now include Claude Desktop, Claude Code, VS Code, many other editors and assistants, and our own Python code through LangChain.

---

## The Problem It Solves

Without a shared protocol, connecting M AI applications to N external systems takes M × N custom integrations. Each app has its own tool format, its own way of describing parameters, its own auth handling, and each integration is written against one of them:

```
Without MCP                         With MCP

App A ──┬── GitHub                  App A ─┐          ┌─ GitHub server
        ├── Jira                    App B ─┼── MCP ───┼─ Jira server
        └── Database                App C ─┘          └─ Database server
App B ──┬── GitHub
        ├── Jira                    3 clients + 3 servers,
        └── Database                any client works with any server
App C ── ...  (9 integrations)
```

*Per-app integrations grow as M × N; a shared protocol reduces it to M + N.*

With MCP, each application implements the client side of the protocol once, and each system is wrapped as a server once. The design echoes the Language Server Protocol, which did the same thing for editors and programming languages: one language server works in every editor that speaks LSP.

---

## What MCP Standardizes — and What It Doesn't

MCP defines how an application and a server talk: how the application discovers what a server offers, how it invokes those capabilities, and what comes back. A server can expose three kinds of things:

- **Tools** — actions the model can ask to run (search tickets, create an issue, query a table).
- **Resources** — read-only data the application can pull in as context (a file, a schema, a record).
- **Prompts** — reusable prompt templates a user can pick from.

MCP deliberately does *not* standardize the model, the agent loop, or how the application uses what it gets. The model never speaks MCP. From its point of view, nothing has changed: it still sees tool names, descriptions, and schemas, and still emits tool-call requests. MCP sits between the *application* and the tool provider, replacing "a Python function in our codebase" with "a capability offered by a server we connect to."

---

## MCP Tools vs In-App Tools

| | LangChain `@tool` | MCP server tool |
|---|---|---|
| **Where the code lives** | In our application | In a separate server process, local or remote |
| **Who can use it** | This application only | Any MCP client |
| **Language** | Python, same as the app | Any language with an MCP SDK |
| **Schema comes from** | Our type hints and docstring | The server's published JSON Schema |
| **Runs** | In-process, a function call | Out-of-process, over a transport |
| **Owned by** | The app's developers | Whoever owns the server — possibly another team or vendor |

That last row is the one that changes how organizations work. An MCP server can be owned by the team that owns the underlying system.

---

## MCP in the Enterprise

The value of MCP grows with the number of AI applications and internal systems an organization has.

- **Build once, reuse everywhere.** The team that owns the ticketing system publishes one MCP server. Every internal assistant, IDE, and agent uses it, and they all get fixes and new capabilities at the same time.
- **Ownership stays with system owners.** The ticketing team decides what's exposed, how inputs are validated, and what's off-limits, instead of every consuming app re-implementing access to their database.
- **A central point for control.** Authentication, authorization, rate limiting, and audit logging happen at the server, once, rather than being re-implemented (or forgotten) in each client.
- **Consistent capabilities across tools.** A developer's IDE assistant and the company's support agent use the same "look up customer" tool, with the same permissions model.

It also introduces risks that are easy to underestimate:

- **Tool descriptions are prompt input.** The model reads a server's tool descriptions and results. A malicious or careless server can inject instructions through them. Treat an MCP server's output as untrusted, the same as a web page.
- **Servers are dependencies.** A third-party MCP server runs code with whatever credentials we give it. Vet, pin, and review servers the way we'd review a package, and prefer an approved internal list over whatever a user finds online.
- **Over-broad access.** A server that exposes "run any SQL" to every client is a single point of failure. Scope credentials to the minimum each server needs.

---

## When Not to Use MCP

MCP adds a process boundary, a transport, and a protocol. That's worth it when a capability will be shared across applications or owned by another team. For a helper that only one agent uses and that lives naturally in its codebase, a plain `@tool` is simpler, faster, and easier to debug. The two coexist happily: an agent can use local tools and MCP tools side by side.

---

## Key Takeaways

- MCP is an open standard for connecting AI applications to external tools and data: write an integration once as a server, use it from any MCP client.
- It turns M × N per-app integrations into M + N, in the same way LSP did for editors.
- Servers expose tools (actions), resources (read-only context), and prompts (templates).
- The model doesn't speak MCP; it still just sees tool schemas and emits tool calls. MCP connects the application to the tool provider.
- In an organization, MCP lets system owners publish and govern one server that every AI application reuses.
- Treat server descriptions and results as untrusted input, vet servers like dependencies, and scope their credentials tightly.
- For a tool only one app needs, a local `@tool` is still the simpler choice.

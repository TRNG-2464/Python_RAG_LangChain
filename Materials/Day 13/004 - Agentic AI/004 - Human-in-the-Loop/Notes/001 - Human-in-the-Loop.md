# Human-in-the-Loop

An agent decides its own actions, which is exactly why some of those actions shouldn't happen without a person looking first. **Human-in-the-loop** (HITL) means pausing the agent at a chosen point so a person can **approve** the step, **edit** it, or **reject** it before it runs. Done well, it lets us give an agent real capabilities — sending email, issuing refunds, changing records — without handing it unchecked authority.

---

## Where the Gates Belong

A gate belongs in front of an action based on its consequences, not on how sophisticated the tool is. The question to ask: *if the model gets this wrong, can we undo it?*

| Gate it | Usually don't |
|---|---|
| Irreversible actions: delete, drop, overwrite | Reads and searches |
| Externally visible actions: send email, post, notify a customer | Computations with no side effects |
| Money: refunds, purchases, transfers | Drafting text the user will review anyway |
| Access and configuration changes: permissions, deploys | Lookups against our own data |
| Anything the model is known to get wrong in testing | |

Gate too little and the agent can do damage. Gate too much and people start approving without reading — **approval fatigue** — which is worse than no gate, because it looks like oversight. Aim for few gates, each on an action that genuinely matters, each showing enough to decide without digging.

Gate the *action*, not the conversation. The pause should come after the model has decided what it wants to do and before our code does it. That's the same boundary as tool calling in general: the model requests, our code executes. HITL just puts a person on that boundary.

---

## The Mechanism, by Hand

In the manual tool loop from the Tool Integration notes, a gate is a few lines between receiving a tool call and running it:

```python
import json
from langchain_core.messages import ToolMessage

REQUIRES_APPROVAL = {"send_email", "issue_refund"}

for call in reply.tool_calls:
    if call["name"] in REQUIRES_APPROVAL:
        print(f"Agent wants to run {call['name']} with {call['args']}")
        choice = input("[a]pprove / [e]dit / [r]eject: ").strip().lower()

        if choice == "r":
            reason = input("Reason: ")
            messages.append(ToolMessage(
                content=f"The user rejected this action. Reason: {reason}",
                tool_call_id=call["id"],
            ))
            continue
        if choice == "e":
            call["args"] = json.loads(input("Corrected arguments as JSON: "))

    result = available[call["name"]].invoke(call["args"])
    messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))
```

*Pauses before sensitive tool calls, letting a person approve, edit the arguments, or reject with a reason.*

Three details here carry over to every HITL implementation:

- **Show the real arguments.** The reviewer approves `send_email(to='all-staff@...')`, not the model's description of what it intends. The model's summary and its actual call can differ.
- **A rejection is still a tool result.** Every `tool_call_id` needs a matching `ToolMessage`, or the next model call fails. Sending the rejection reason back lets the model adapt — pick a different approach, or ask the user a question — instead of retrying the same call.
- **An edit changes the call, not the history.** The model's original request stays in the messages; what executes is the corrected version.

---

## Pausing for Real

`input()` works in a terminal. It doesn't work in a web app, where the reviewer responds from a different request, in a different session, possibly after a server restart. A real pause means:

1. Save the agent's full state somewhere durable.
2. Return control to the application, which shows the pending action to a person.
3. When the decision arrives, load the state and continue from exactly where it stopped.

In LangChain, saving and resuming state is the job of a **checkpointer**, and each paused run is identified by a **thread id**. The built-in `HumanInTheLoopMiddleware` wires the gate, the pause, and the resume together.

---

## HumanInTheLoopMiddleware

We tell the middleware which tools to gate and which decisions are allowed for each:

```python
from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langgraph.checkpoint.memory import InMemorySaver

agent = create_agent(
    model=llm,
    tools=[get_order, send_email, issue_refund],
    middleware=[
        HumanInTheLoopMiddleware(
            interrupt_on={
                "send_email": True,                                     # any decision allowed
                "issue_refund": {"allowed_decisions": ["approve", "reject"]},  # no editing amounts
                "get_order": False,                                     # never pause on reads
            },
        ),
    ],
    checkpointer=InMemorySaver(),
)
```

*Gates two tools with different allowed decisions and lets reads run freely; the checkpointer is what makes pausing possible.*

`True` allows every decision type; a config dict narrows them. Here the refund can be approved or rejected but not edited, so a reviewer can't quietly change the amount. `InMemorySaver` keeps paused state in process memory, which is fine for learning; a real deployment uses a database-backed checkpointer so a pause survives a restart.

Running the agent now requires a thread id, and a gated call stops the run:

```python
config = {"configurable": {"thread_id": "support-ticket-812"}}

result = agent.invoke(
    {"messages": [{"role": "user", "content": "Refund order A1001 in full."}]},
    config=config,
    version="v2",
)

for pending in result.interrupts:
    for request in pending.value["action_requests"]:
        print(request["name"], request["arguments"])
```

*Runs the agent until it reaches a gated tool, then lists the pending action and its arguments.*

With `version="v2"`, `invoke` returns an object whose `.value` is the agent state and whose `.interrupts` holds any pauses. Each interrupt's `value` lists the pending `action_requests` (tool name, arguments, description) and a matching `review_configs` entry saying which decisions are allowed. The run is now suspended in the checkpointer under `support-ticket-812`. Nothing has executed.

---

## Resuming with a Decision

The decision goes back in as a `Command`, on the same thread id. There's one decision per pending action, in order:

```python
from langgraph.types import Command

# Approve as-is
agent.invoke(Command(resume={"decisions": [{"type": "approve"}]}), config=config, version="v2")

# Or reject, with feedback the model will see
agent.invoke(
    Command(resume={"decisions": [{"type": "reject", "message": "Refunds over $500 need a manager."}]}),
    config=config,
    version="v2",
)
```

*Resumes the suspended run by approving the pending call, or by rejecting it with a reason.*

The other two decision types, where allowed:

```python
{"type": "edit", "edited_action": {"name": "send_email", "args": {"to": "dana@example.com", "subject": "...", "body": "..."}}}
{"type": "respond", "message": "Tell the customer we'll call them instead."}
```

*Edit replaces the tool call's arguments before it runs; respond skips the tool and returns the person's message as its result.*

The resume call can happen anywhere — a different HTTP request, a different process — as long as it uses the same checkpointer and thread id. That's the whole point of saving state rather than blocking.

---

## Designing Good Gates

- **Make the pending action readable.** Show the tool, the exact arguments, and enough context to judge them. A reviewer who has to go look something up will eventually stop looking.
- **Restrict decisions to what's safe.** Don't allow `edit` on a tool where a changed argument could bypass a business rule.
- **Log every decision** — who, what, when, approve or reject. Gates are also an audit trail.
- **Decide what happens when nobody answers.** A pause with no timeout is a run that never finishes. Pick a default (usually reject) and apply it after a deadline.
- **Validate inside the tool anyway.** A gate is a second line of defense, not a replacement for the tool checking its own inputs.

---

## Key Takeaways

- HITL pauses an agent so a person can approve, edit, or reject a step before it runs.
- Gate by consequence: irreversible, external, financial, or access-changing actions. Gating everything causes approval fatigue.
- The gate sits between the model's tool request and our code executing it.
- Show reviewers the real arguments; send rejections back as tool results so the model can adapt.
- A real pause needs saved state: a checkpointer plus a thread id.
- `HumanInTheLoopMiddleware(interrupt_on={...})` gates tools by name with per-tool allowed decisions; resume with `Command(resume={"decisions": [...]})` on the same thread.

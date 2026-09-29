# Memory Concepts

A language model has no memory. Each call is completely independent — the model sees the messages we send and nothing else. If we ask "What's the capital of France?" and then ask "What's its population?", the second call has no idea what "its" refers to.

**Memory** is how we fake continuity. There's no hidden state on the model's side; we simply resend the earlier turns of the conversation with every new request. Everything in this topic is about managing that resent history: where we keep it, and what we do when it grows too large to send.

---

## The Core Mechanism

A chat model takes a *list of messages*, not a string. The conversation is that list, and we own it:

```python
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

llm = ChatOllama(model="llama3.1")

history = [
    SystemMessage("You are a concise assistant."),
    HumanMessage("What's the capital of France?"),
]
reply = llm.invoke(history)
history.append(reply)                        # reply is an AIMessage

history.append(HumanMessage("What's its population?"))
reply = llm.invoke(history)                  # now 'its' resolves — Paris is in the list
print(reply.content)
```

*Manages conversation state as a plain Python list, appending each turn before the next call.*

That's memory in its entirety. Every abstraction we'll see is a convenience wrapper over this loop.

The three message types cover almost everything we do:

| Type | Role | Purpose |
|---|---|---|
| `SystemMessage` | system | Standing instructions — persona, rules, constraints. Usually first, usually one. |
| `HumanMessage` | user | What the person said. |
| `AIMessage` | assistant | What the model said. Appending these is what creates continuity. |

There's a fourth, `ToolMessage`, which carries the result of a tool call — we'll meet it in the Tool Integration notes.

---

## Slotting History into a Prompt

Hand-building message lists gets awkward once there's a prompt template involved. `MessagesPlaceholder` reserves a slot in a `ChatPromptTemplate` where a list of messages gets spliced in:

```python
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful assistant specializing in {topic}."),
    MessagesPlaceholder("history"),
    ("human", "{input}"),
])

chain = prompt | llm

reply = chain.invoke({
    "topic": "Python",
    "history": [
        HumanMessage("What's a list comprehension?"),
        AIMessage("A compact way to build a list from an iterable."),
    ],
    "input": "Show me one.",
})
```

*Reserves a `history` slot in the prompt so prior turns are injected between the system message and the new input.*

Note the ordering: system instructions first, then history, then the new turn. Keeping the system message at the top means it stays in force no matter how long the conversation gets.

---

## Storing History per Conversation

A real app has many conversations at once, so history needs a key. A dict of message lists, keyed by session, is all that requires:

```python
sessions: dict[str, list] = {}

def get_history(session_id: str) -> list:
    if session_id not in sessions:
        sessions[session_id] = [SystemMessage("You are a helpful assistant.")]
    return sessions[session_id]

def chat(session_id: str, text: str) -> str:
    history = get_history(session_id)
    history.append(HumanMessage(text))
    reply = llm.invoke(history)
    history.append(reply)
    return reply.content

chat("dana-42", "What's a decorator?")
print(chat("dana-42", "Show me one."))      # remembers the question above
print(chat("sam-17", "Show me one."))       # different session, no context
```

*Keeps one message list per session id, so conversations stay separate.*

The `session_id` is what separates one person's conversation from another's, and swapping the dict for SQLite, Redis, or Postgres is the only change needed to make history survive a restart. The chat logic doesn't move.

> **On the framework wrappers:** LangChain has classes for this — `InMemoryChatMessageHistory` and `RunnableWithMessageHistory` — and we'll meet them in existing code. They're in flux: `InMemoryChatMessageHistory` is deprecated as of `langchain-core` 1.6.4 and slated for removal in 2.0, with the current recommendation being LangGraph's checkpointers, which handle state through the agent runtime instead. The underlying idea never changes — persist the message list, replay it on the next call — which is why the plain-list version above is worth knowing regardless of which wrapper is in fashion.

---

## The Context Window Problem

Every model has a **context window**: a hard limit on how many tokens one request can contain. Everything counts against it — the system message, the entire history, the new input, and the space reserved for the reply.

A conversation that grows without bound will eventually hit that ceiling. When it does, we get an error, or silent truncation, or a sharp drop in quality as the model loses the beginning of the conversation. And long before the hard limit, we pay for it: more tokens means slower responses and, on a local Ollama model, noticeably more memory and compute per turn.

So history management isn't optional polish. Any chat app that runs longer than a few turns needs a strategy. There are two.

---

## Strategy 1: Trimming

**Trimming** drops messages to fit a budget. The usual policy keeps the system message and the most recent turns, discarding the oldest middle. LangChain's `trim_messages` handles the bookkeeping:

```python
from langchain_core.messages import trim_messages

trimmer = trim_messages(
    max_tokens=2000,
    strategy="last",              # keep the most recent messages
    token_counter=llm,            # count with the model's own tokenizer
    include_system=True,          # never drop the system message
    start_on="human",             # don't start with an orphaned AI reply
)

chain = prompt | trimmer | llm
```

*Trims history to a token budget before it reaches the model, preserving the system message and recent turns.*

Two of those arguments are easy to get wrong. `include_system=True` keeps the standing instructions from being trimmed away — without it, a long conversation quietly loses its persona and rules. `start_on="human"` avoids leaving an `AIMessage` as the first message after the system prompt, which confuses some models.

Trimming is cheap, predictable, and lossy. The model genuinely forgets what was cut.

---

## Strategy 2: Summarization

**Summarization** compresses old turns instead of deleting them. When history crosses a threshold, we make an extra model call to condense the oldest portion into a paragraph, then replace those messages with that summary:

```python
def summarize(messages: list) -> str:
    text = "\n".join(f"{m.type}: {m.content}" for m in messages)
    return llm.invoke(
        f"Summarize this conversation, preserving facts, names, and decisions:\n\n{text}"
    ).content

if len(history) > 20:
    older, recent = history[:-6], history[-6:]
    history = [SystemMessage(f"Summary of earlier conversation: {summarize(older)}")] + recent
```

*Condenses older turns into a single summary message and keeps only the most recent turns verbatim.*

This keeps the gist of a long conversation in a fraction of the tokens. The costs are real, though: an extra model call, added latency at the moment it triggers, and lossy compression — details the summarizer judged unimportant are gone for good, and a bad summary poisons every turn after it.

### Choosing Between Them

| | Trimming | Summarization |
|---|---|---|
| Cost | Free | An extra model call when it triggers |
| Latency | None | A pause on the turn that triggers it |
| What's lost | Old turns, entirely | Detail, but not the gist |
| Good for | Short task-focused chats, support widgets | Long advisory sessions, tutoring, anything where early context still matters |

The common production answer is both: summarize the distant past, keep recent turns verbatim, and trim if the result still exceeds budget.

---

## What Belongs in Memory

One more distinction worth drawing. Conversation history is **short-term memory** — the transcript of this session. It is not the right place for durable facts about a user.

If we need to remember that someone prefers Python over Java across sessions, that belongs in a database, retrieved and injected into the system prompt at the start of a conversation. Trying to keep it alive by never trimming the history is how apps end up burning their entire context window re-reading a preference from four hundred turns ago.

---

## Key Takeaways

- Models are stateless; memory is just resending earlier messages with each call.
- A conversation is a list of `SystemMessage`, `HumanMessage`, and `AIMessage` objects that we own and append to.
- `MessagesPlaceholder` reserves a slot in a prompt template for that list; a dict keyed by `session_id` is enough to keep conversations separate.
- Every model has a finite context window, so unbounded history will eventually break or degrade the app.
- `trim_messages` drops old turns to fit a budget — cheap, predictable, and lossy. Keep the system message and start on a human turn.
- Summarization compresses old turns into a paragraph — preserves the gist at the cost of an extra call and lost detail.
- Durable facts about a user belong in a database and get injected into the prompt, not carried indefinitely in the transcript.

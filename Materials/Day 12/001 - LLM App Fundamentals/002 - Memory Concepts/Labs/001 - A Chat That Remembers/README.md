# A Chat That Remembers

We'll watch a model forget, then give it memory by resending the conversation. We'll cover the message list, a working multi-turn loop, trimming with `trim_messages`, and summarizing older turns.

## Prerequisites

| Software | Required Version |
|---|---|
| Python | >=3.10 |
| langchain-core | 1.6.4 |
| langchain-ollama | 1.1.0 |
| Ollama | any current release, running locally |
| Ollama model | `llama3.1` |

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

Open `src/main.py`. The model is set up and the parts are marked out for us. Each part already has a `banner(...)` call that prints a header, so we can tell which output came from which part. Add each part's code below its banner.

### 1. Watch it forget

Add this under `# --- Part 1 ---`:

```python
print(llm.invoke("My name is Dana.").content)
print(llm.invoke("What's my name?").content)
```

*Makes two separate calls and prints both replies.*

Run it. The second call has no idea. Two `invoke` calls are two unrelated requests — nothing carries over.

### 2. Keep the list ourselves

Memory is just resending what was said. Add under `# --- Part 2 ---`:

```python
history = [SystemMessage("You are a concise assistant.")]

history.append(HumanMessage("My name is Dana."))
reply = llm.invoke(history)
history.append(reply)

history.append(HumanMessage("What's my name?"))
reply = llm.invoke(history)
print(reply.content)
```

*Builds a message list, appending each turn so the second call can see the first.*

Run it. It remembers now. Nothing clever happened — we sent the earlier messages along.

The append of `reply` is the easy step to miss. Without it, the model's own answers vanish and only our questions carry forward.

### 3. Look at what's being sent

Add this to see the list grow:

```python
for m in history:
    print(f"{m.type:10} {m.content[:60]}")
```

*Prints the role and start of every message currently in the history.*

This is the single most useful debugging habit for memory bugs — print the list before the call and see exactly what the model is being given.

### 4. A chat loop

Let's wrap it in something we can actually talk to. Add under `# --- Part 4 ---`:

```python
history = [SystemMessage("You are a concise assistant.")]

while True:
    text = input("\nyou> ")
    if text in {"quit", "exit"}:
        break
    history.append(HumanMessage(text))
    reply = llm.invoke(history)
    history.append(reply)
    print("bot>", reply.content)
    print(f"     [{len(history)} messages in history]")
```

*Runs a multi-turn chat, appending both sides of each turn and reporting how long the history is.*

Run it and have a short conversation. Refer back to something from two turns ago and confirm it follows. Watch the message count climb — every turn adds two, and all of them get resent on the next call.

### 5. Trim the history

That growth is the problem. `trim_messages` cuts the history down to a budget. This one goes near the top of the file, under `# --- Part 5 setup ---`, right after `llm` is created:

```python
trimmer = trim_messages(
    max_tokens=120,
    strategy="last",
    token_counter="approximate",
    include_system=True,
    start_on="human",
)
```

*Builds a trimmer that cuts the history to roughly 120 tokens, keeping the system message and the most recent turns.*

Why up there and not down in Part 5? Python runs the file top to bottom, and a name doesn't exist until the line that creates it has run. In a minute the Part 4 loop will use `trimmer`, and that loop runs before Part 5 is ever reached. If `trimmer` were defined below the loop, the first message we typed would fail with `NameError: name 'trimmer' is not defined`.

The budget is deliberately tiny so we can see it bite. Two arguments are doing important work: `include_system=True` keeps the standing instructions from being dropped, and `start_on="human"` avoids leaving an AI reply stranded at the top with nothing it was replying to.

`token_counter="approximate"` estimates token counts from the length of the text instead of running a real tokenizer. That's close enough for a budget this rough. Passing `token_counter=llm` looks like it should count with the model's own tokenizer, but `ChatOllama` doesn't have one — LangChain falls back to GPT-2's tokenizer, which needs the heavy `transformers` package installed.

Now let's see what it does to the conversation we just had. Add under `# --- Part 5 ---`:

```python
trimmed = trimmer.invoke(history)
print(f"{len(history)} messages -> {len(trimmed)} after trimming")
for m in trimmed:
    print(f"  {m.type:10} {m.content[:50]}")
```

*Trims the chat history and prints how many messages survived, and which ones.*

Now put the trimmer into the loop — change the invoke line in Part 4 to:

```python
    reply = llm.invoke(trimmer.invoke(history))
```

*Trims the history on the way into the model while keeping the full list in memory.*

Chat past the budget, then ask about something from the very start. It's gone — that's trimming being lossy, working as designed.

### 6. Summarize instead

Summarizing keeps the gist instead of dropping it. Add under `# --- Part 6 ---`:

```python
def summarize(messages):
    text = "\n".join(f"{m.type}: {m.content}" for m in messages)
    return llm.invoke(f"Summarize this conversation briefly:\n\n{text}").content


if len(history) > 7:
    older, recent = history[1:-4], history[-4:]
    summary = summarize(older)
    history = [history[0], SystemMessage(f"Earlier conversation: {summary}")] + recent
    print("Summary:", summary)
```

*Condenses the older turns into one summary message and keeps the last four verbatim.*

Note `history[0]` is preserved separately — that's the original system message, which we don't want summarized away.

Run the loop again with this in place. It costs an extra model call when it triggers, and we'll feel the pause. That's the tradeoff.

---

## Exercises

1. **Watch the cutoff.** Set `max_tokens=60` in the trimmer. How many turns survive? Find the point where the bot stops being able to recall your name.

2. **Drop the system message.** Set `include_system=False` and chat past the budget. Describe what changes about the bot's behavior and why.

3. **Trim from the other end.** Change `strategy` to `"first"`. Have a conversation and explain why this is the wrong choice for a chat app.

4. **Summarize on a timer.** Rewrite Part 6 so summarization triggers every 6 turns instead of on a length check, and prints the summary each time so you can watch detail get lost across several rounds.

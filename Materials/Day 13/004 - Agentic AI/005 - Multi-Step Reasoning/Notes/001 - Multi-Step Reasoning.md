# Multi-Step Reasoning

A model produces its reply one token at a time, and each token can only build on what's already been written. So a model that writes its intermediate work before its answer has that work available when it gets to the answer. **Multi-step reasoning** is any arrangement that exploits this: having the model work through a problem in stages and carry each stage's result forward.

Those stages can live in three places — inside one reply, across the tool calls of an agent run, or across separate calls our code orchestrates. Wherever they live, they end up as text in the context, and every later step pays to re-read them.

---

## Reasoning Inside One Reply

The simplest form is asking for the work before the answer, a technique called **chain-of-thought** prompting:

```python
from langchain_ollama import ChatOllama

llm = ChatOllama(model="llama3.1", temperature=0)

question = (
    "Pens are sold only in full packs of 12, at $3 per pack. "
    "What is the cheapest cost to get at least 150 pens?"
)

reply = llm.invoke([
    ("system",
     "Work through the problem step by step. "
     "Then give the result on a final line in the form 'ANSWER: <value>'."),
    ("human", question),
])

answer = reply.content.strip().splitlines()[-1].removeprefix("ANSWER:").strip()
```

*Asks for visible working followed by a marked final line, then extracts just the answer.*

The fixed `ANSWER:` marker matters: the reasoning is for the model, and our code needs a reliable way to separate it from the result. (The correct answer is $39 — 150 ÷ 12 rounds up to 13 packs.)

With structured output, the same idea is a matter of field order. Models generally fill a schema's fields in order, so putting the reasoning field first means it's generated before the answer it supports:

```python
from pydantic import BaseModel, Field

class Solution(BaseModel):
    reasoning: str = Field(description="Step-by-step working.")
    total_cost: float = Field(description="Final cost in dollars.")

solution = llm.with_structured_output(Solution).invoke(question)
print(solution.total_cost)
```

*Places a reasoning field before the answer field so the model writes its working first.*

Swap the field order and the model commits to `total_cost` before any working exists — the reasoning becomes a justification written after the fact.

---

## Reasoning Models

Some models are trained to reason before answering without being asked, emitting a separate "thinking" section first. Ollama serves several (`qwen3`, `deepseek-r1`, and others), and `ChatOllama` can keep that thinking apart from the answer:

```python
thinker = ChatOllama(model="qwen3", reasoning=True)

reply = thinker.invoke(question)
print(reply.additional_kwargs["reasoning_content"])   # the model's working
print(reply.content)                                  # the answer alone
```

*Enables reasoning mode so the model's thinking lands in `additional_kwargs` and `content` holds only the answer.*

With `reasoning=True`, the thinking lands in `reply.additional_kwargs["reasoning_content"]`. With the default (`None`), a model that thinks by default may leave its thinking tags mixed into `content`. `reasoning=False` turns thinking off for models that support that.

Reasoning models are noticeably better on multi-step problems and noticeably slower, since every thinking token is generated before the first answer token. Use them where the problem needs it, not as a default.

---

## Reasoning Across Tool Calls

In an agent run, each step lands in the message history as it happens. For a two-lookup task, the state the model sees on its final call is:

| # | Message | Added by |
|---|---|---|
| 1 | `SystemMessage` — instructions | Us, once |
| 2 | `HumanMessage` — the task | Us, once |
| 3 | `AIMessage` with `tool_calls` — step 1 request | Model call 1 |
| 4 | `ToolMessage` — step 1 result | Our code |
| 5 | `AIMessage` with `tool_calls` — step 2 request | Model call 2 |
| 6 | `ToolMessage` — step 2 result | Our code |
| 7 | `AIMessage` — the answer | Model call 3 |

This history *is* the reasoning chain. The model can use the tracking number in message 4 on its second call because message 4 is sitting in its input. It doesn't remember anything; it re-reads the list. And if an `AIMessage` carries text alongside its tool calls (some models explain what they're doing), that text is part of the chain too.

---

## Reasoning Across Separate Calls

The third form is the one our code controls: split the problem into separate calls and pass each result into the next prompt, as in chaining or plan-and-execute. The difference from the agent loop is what gets carried forward. An agent carries *everything*; our code can carry only the part the next stage needs — a summary, one extracted value, a list of findings. That choice is the main lever we have over context cost.

---

## What It Costs in Context

Every model call re-sends the whole history. That makes an agent's cost grow faster than its step count: if each tool round adds about 500 tokens, call 1 sends 500, call 2 sends 1,000, call 10 sends 5,000. Across all ten calls that's 27,500 input tokens to process 5,000 tokens of actual content — plus the system prompt and every tool schema, which are re-sent on every call too.

We can see this directly. `ChatOllama` attaches token counts to each `AIMessage`:

```python
from langchain_core.messages import AIMessage

for m in result["messages"]:
    if isinstance(m, AIMessage) and m.usage_metadata:
        print(m.usage_metadata["input_tokens"], "in /", m.usage_metadata["output_tokens"], "out")
```

*Prints input and output token counts for each model call in an agent run, showing the input side climb.*

Run that on any multi-step agent and the input column climbs every call. On a local model, this is time and memory; on a hosted model, it's also money.

There's a hard ceiling as well. Ollama runs each model with a context length (`num_ctx`) set by the Ollama server, often well below the model's advertised maximum. When the prompt exceeds it, the oldest part of the conversation is dropped silently rather than raising an error — so a long agent run can quietly lose its original task. Set the context length explicitly when running multi-step work:

```python
llm = ChatOllama(model="llama3.1", temperature=0, num_ctx=16384)
```

*Raises the context length for this model instance so long agent runs aren't silently truncated.*

Larger contexts use more memory and run slower, so size it to the task rather than to the maximum.

Reasoning traces add to the bill. `ChatOllama` sends an `AIMessage`'s `reasoning_content` back to Ollama when that message is part of the history. How much of it the model then reads depends on the model's prompt template. To guarantee old thinking doesn't accumulate, strip it before appending:

```python
reply = thinker.invoke(history)
reply.additional_kwargs.pop("reasoning_content", None)
history.append(reply)
```

*Removes the model's thinking from a reply before it's stored, so only the answer is carried forward.*

---

## Keeping the Chain Affordable

- **Keep tool results short.** Return the three relevant rows, not the table. Every token a tool returns is re-read on every later call.
- **Carry forward summaries, not transcripts,** when orchestrating separate calls.
- **Isolate sub-tasks** in a sub-agent with its own fresh context, returning only its conclusion.
- **Trim or summarize history** in long runs, as in the Memory Concepts notes. LangChain's built-in `SummarizationMiddleware` and `ContextEditingMiddleware` do this inside `create_agent`, compressing history or clearing old tool outputs as the context fills.
- **Match the model to the step.** A reasoning model for the hard planning step; a fast model for routine execution.

---

## Key Takeaways

- A model can use its intermediate work only if it writes that work before the answer; multi-step reasoning arranges for that.
- Chain-of-thought prompting asks for working before the answer; with structured output, put the reasoning field before the answer field.
- `ChatOllama(model="qwen3", reasoning=True)` separates a reasoning model's thinking into `additional_kwargs["reasoning_content"]`.
- In an agent, the message history is the reasoning chain: an `AIMessage` with tool calls and a `ToolMessage` per step.
- Every call re-sends the full history, so input tokens grow with each step; `usage_metadata` shows it.
- Set `num_ctx` for long runs — Ollama silently drops the oldest context when a prompt exceeds it.
- Keep tool results short, carry forward summaries, and isolate sub-tasks to control context cost.

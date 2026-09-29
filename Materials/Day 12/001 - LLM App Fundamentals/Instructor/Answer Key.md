# LLM App Fundamentals — Answer Key

Mirrors `Review/Reading Questions.md` exactly: same sections, same order, same numbering.

---

## Output Parsers

**Q1. A model always returns text. What specific problems does that create when we need the model's answer to feed the next function in our code?**

**A:** The reply is unstructured and inconsistent between runs. Asking for a name, age, and email might return tidy JSON, JSON wrapped in a markdown fence, a friendly sentence with JSON buried in it, or JSON with `"age": "thirty-one"` — a string where we need an int. We can't index it, can't do arithmetic on it, and can't rely on the same shape twice.

*Discussion:* The variability is the real problem, not the format. A single successful manual test proves nothing; the same prompt will produce a different wrapper on run four.

---

**Q2. Two approaches solve this — prompt-and-parse, and native structured output. What's the practical difference, and what would make us pick one over the other?**

**A:** **Prompt-and-parse** describes the desired shape in the prompt, lets the model reply with text, then a parser reads that text into an object — the constraint is *checked after the fact*. **Native structured output** hands the schema to the provider, which constrains generation itself — the constraint is *applied during* generation.

Pick native when the model supports it (more reliable, less code). Fall back to prompt-and-parse when it doesn't — it works with any model that can produce text.

---

**Q3. `StrOutputParser` barely does anything, yet we use it constantly. What does it do, and what does its role tell us about every other parser?**

**A:** A chat model returns an `AIMessage`, not a string. `StrOutputParser` pulls out `.content`.

```python
chain = prompt | llm | StrOutputParser()
```

The lesson is structural: a parser is just another **runnable** sitting at the end of an LCEL pipeline, transforming whatever the model handed it. Every parser follows that same shape.

---

**Q4. Each Pydantic field gets a `description`. Who reads it, and what happens if it's vague?**

**A:** The **model** reads it — descriptions are serialized into the schema sent with the request. They're instructions, not documentation.

```python
age: int = Field(description="age in years")
```

*Discussion:* A field described as `"age in years"` comes back as `31`; an undescribed `age` is much likelier to come back as `"thirty-one"` or a birth year. This is the cheapest accuracy fix available and the one most often skipped.

---

**Q5. `PydanticOutputParser` does two separate jobs. What are they, and where does each happen?**

**A:** (1) It generates **format instructions** — a text description of the JSON schema — which we inject into the prompt *before* the call via `get_format_instructions()`. (2) It parses and validates the reply into the Pydantic class *after* the call.

```python
prompt = ChatPromptTemplate.from_template(
    "Extract the person's details.\n{format_instructions}\n\nText: {text}"
).partial(format_instructions=parser.get_format_instructions())
chain = prompt | llm | parser
```

*Discussion:* `.partial()` fills the instructions once so callers only supply `text`. Worth having associates print `get_format_instructions()` — seeing the injected schema demystifies the whole mechanism.

---

**Q6. We get a `Person` object instead of a dict. Name two concrete things that become possible or safer.**

**A:** (1) Types are real and validated — `person.age + 1` works because it's an `int`. (2) Typos fail loudly — `person.nmae` raises `AttributeError` immediately, where `d["nmae"]` on a dict is a `KeyError` at best and a silent `.get()` `None` at worst.

Also acceptable: IDE autocomplete, and validation failing at the boundary rather than three functions downstream.

---

**Q7. Why is `with_structured_output()` more reliable than prompt-and-parse?**

**A:** The schema is enforced by the provider *during* generation rather than checked after. The model is constrained to produce conforming output instead of being asked nicely and then graded.

```python
person = llm.with_structured_output(Person).invoke("Dana Okafor, 31, engineer.")
```

It's also a runnable, so it drops into a chain in the model's position: `prompt | llm.with_structured_output(Person)`.

---

**Q8. `with_structured_output()` produces garbage on our local Ollama model. Likely cause, and the fallback?**

**A:** The model isn't **tool-capable**. Native structured output is built on tool-calling machinery, so it needs a model trained for it — `llama3.1`, `qwen2.5`, `mistral-nemo`. Older or very small models ignore the schema or fail.

Fallback is `PydanticOutputParser` with explicit format instructions, which works on anything that emits text. A middle option is `ChatOllama(format="json")` plus `JsonOutputParser` — that forces syntactically valid JSON, though not the right *shape*.

---

**Q9. Why wrap a list inside a container model rather than asking for a list directly?**

**A:** Most providers expect a single object at the top level of a structured response.

```python
class TicketBatch(BaseModel):
    tickets: list[Ticket]
```

*Discussion:* Also worth raising `Literal["low","medium","high"]` over a field description for constrained values — Pydantic rejects anything outside the set rather than passing a plausible-looking wrong value through.

---

**Q10. Validation catches `age` as `"thirty-one"`. What will it *not* catch?**

**A:** A **plausible invented value of the correct type**. Feed the extractor "A tortoise named Shelly" against a schema requiring `age: int` and a model may return `age=0` — perfectly valid, entirely fabricated. Validation checks *shape*, never *truth*.

*Discussion:* This is the key caution before anyone trusts extraction output in a pipeline. Type validation is a floor, not a guarantee. The lab has associates trigger this deliberately.

---

**Q11. Why `temperature=0` for extraction?**

**A:** Creativity works against schema compliance. Extraction is a reading task with one right answer, not a generation task — we want the most probable token, every time. Higher temperature increases both malformed output and invented values.

Other defenses worth naming: keep schemas flat and small (deep nesting fails far more), catch `OutputParserException` deliberately, and treat `OutputFixingParser` (now in `langchain-classic`) as a safety net rather than a strategy, since it costs an extra call.

---

## Memory Concepts

**Q12. Models are stateless. What is "memory" actually made of?**

**A:** The **resent conversation history**. There is no hidden state on the model's side — we keep a list of messages and send the whole thing with every call. Each request is independent; continuity is entirely an illusion we construct.

*Discussion:* Everything else in the topic — placeholders, trimming, summarizing, LangChain's wrapper classes — is convenience over this one loop. Worth stating plainly early, because associates often assume the model is holding a session.

---

**Q13. We append the model's reply too. What breaks if we only append our questions?**

**A:** The model loses its own answers, so the conversation reads as a list of user questions with no responses. It can't refer back to anything it said, and follow-ups like "expand on that" have no antecedent.

```python
history.append(HumanMessage(text))
reply = llm.invoke(history)
history.append(reply)          # the step people forget
```

---

**Q14. Why does system-first, then history, then new input matter as a conversation grows?**

**A:** Keeping the `SystemMessage` at the top means the standing instructions — persona, rules, constraints — stay in force regardless of how long the history gets. If instructions drift into the middle of a long message list they carry much less weight, and trimming may drop them entirely.

---

**Q15. Why does history need a session key?**

**A:** A real app runs many conversations concurrently. Without a key, every user shares one message list: they see each other's turns, and the model blends unrelated conversations.

```python
sessions: dict[str, list] = {}
```

*Discussion:* In a multi-tenant app this is a privacy boundary, not just a correctness one.

---

**Q16. What is the context window, and what are the failure modes when a conversation outgrows it?**

**A:** A hard per-request limit on tokens, covering system message + full history + new input + room for the reply.

Failure modes: (1) an outright error, (2) silent truncation, (3) degraded quality as the model loses the start of the conversation. Before the hard limit there's also cost — slower responses and, on local Ollama, noticeably more memory and compute per turn.

*Discussion:* Emphasize that this makes history management mandatory for any chat that runs more than a few turns, not a nice-to-have.

---

**Q17. What do `include_system=True` and `start_on="human"` each prevent?**

**A:** `include_system=True` prevents the system message from being trimmed away — without it, a long conversation quietly loses its persona and rules. `start_on="human"` prevents an `AIMessage` being left as the first message after the system prompt, an orphaned reply with nothing it was replying to, which confuses some models.

```python
trimmer = trim_messages(
    max_tokens=2000, strategy="last", token_counter=llm,
    include_system=True, start_on="human",
)
```

*Discussion:* The lab has associates set `include_system=False` and watch the personality drift — a fast, memorable demonstration.

---

**Q18. Trimming vs summarization — costs and when to use each?**

**A:**

| | Trimming | Summarization |
|---|---|---|
| Cost | Free | An extra model call when it triggers |
| Latency | None | A pause on the triggering turn |
| What's lost | Old turns entirely | Detail, but not the gist |
| Good for | Short task-focused chats, support widgets | Long advisory sessions, tutoring |

Production answer is usually both: summarize the distant past, keep recent turns verbatim, trim if still over budget.

*Discussion:* Name the summarization risk — a bad summary poisons every subsequent turn, and there's no way to recover the detail it discarded.

---

**Q19. Where does a standing user preference belong, and why not in history?**

**A:** In a **database**, retrieved and injected into the system prompt at the start of a conversation. Conversation history is short-term memory — the transcript of this session.

Keeping durable facts alive by never trimming means burning the entire context window re-reading a preference from four hundred turns ago, and it's lost anyway the moment the session ends.

---

## Tool Integration

**Q20. When a model "calls a tool," what actually happened?**

**A:** The model emitted a **structured request** — a name and arguments. It executed nothing. Our code receives that request, decides whether to honor it, runs the function, and returns the result.

*Discussion:* This is the most important idea in the topic and the most commonly misread. That boundary is where all control and all security live — the model proposes, our code disposes. Everything in Q28 follows from it.

---

**Q21. What three things does `@tool` send, and which most determines correct selection?**

**A:** The **function name**, the **type hints**, and the **docstring**. The docstring matters most — it's the prompt the model reads when deciding whether this tool fits.

```python
print(add.name); print(add.description); print(add.args)
```

*Discussion:* Type hints do real work too: `quantity: int` is why the model sends `2` not `"two"`, and a parameter with a default becomes optional in the schema. Having associates print `.args` makes the generated schema concrete.

---

**Q22. Empty `.content` with populated `.tool_calls` — is something wrong?**

**A:** No, that's normal and expected. The model has nothing to say yet because it's waiting on us to run the requested tool and return the result. If the question needs no tool, the inverse appears: `.tool_calls` empty, `.content` holding the answer.

---

**Q23. What are the `AIMessage` append and the `tool_call_id` doing?**

**A:** Appending the `AIMessage` preserves the *request* in the history — sending a `ToolMessage` without the request that produced it is a protocol error on most providers. The `tool_call_id` pairs each result with its specific request, which is what makes parallel tool calls in one turn unambiguous.

```python
messages.append(reply)
for call in reply.tool_calls:
    result = available[call["name"]].invoke(call["args"])
    messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))
```

*Note:* `get_weather.invoke({"city": "Paris"})` — the decorated object takes an args dict, it's not a plain callable any more.

---

**Q24. What turns one exchange into an agent, and why the iteration cap?**

**A:** **Looping** — repeating invoke → execute → return until the model stops requesting tools. That's the entire definition of an agent; there's nothing else to it.

The cap exists because a model that misreads a tool result can loop indefinitely. Locally that means a pegged CPU until someone kills the process — no rate limit or bill to stop it.

---

**Q25. Why return tool errors to the model instead of raising?**

**A:** The model can often recover — fix its arguments and retry, or explain the problem to the user. `"Error: city not found"` gives it something to work with; an exception gives it nothing and kills the run.

```python
try:
    result = available[call["name"]].invoke(call["args"])
except Exception as e:
    result = f"Error: {e}"
```

---

**Q26. `.tool_calls` consistently empty. What to check first, and why not the prompt?**

**A:** Check the **model**. Tool calling requires a model trained for it; with Ollama that means `llama3.1`, `qwen2.5`, `mistral-nemo` or similar. Without that training, tool calls are silently ignored or described in prose rather than emitted as structured requests.

No amount of prompt engineering adds a capability the weights don't have. Local models are also measurably weaker than hosted ones at selection once more than a handful of tools are available.

---

**Q27. Why are two overlapping tools worse than ten unrelated ones?**

**A:** Ambiguity is what degrades selection, not count. If two tools could plausibly answer the same question, the model has to guess, and it will guess wrong some fraction of the time. Ten clearly distinct tools each have an obvious trigger.

The fix is to **merge** them into one tool, or sharpen the names and docstrings until the boundary is unambiguous.

---

**Q28. What protects a destructive tool, and who decides what's permitted?**

**A:** An **allowlist** and a **human confirmation step**, with the dangerous operation never exposed directly. Validate arguments inside the tool — the model's arguments are untrusted input and it will occasionally invent a plausible-looking id.

**Our code decides** what's permitted. The model only decides what to ask for. Anything else puts a probabilistic text generator in charge of irreversible actions.

*Discussion:* Also worth raising: tools should return text the model can actually read. A 4,000-row dump burns the context window — return a summary or the top few rows.

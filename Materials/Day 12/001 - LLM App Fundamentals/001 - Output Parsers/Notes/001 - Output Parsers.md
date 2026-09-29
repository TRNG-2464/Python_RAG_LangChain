# Output Parsers

A language model returns text. Our code needs data. **Output parsing** is the bridge between the two: getting a model's free-text reply into a Python object we can index, validate, and pass to the next function.

This sounds like a small problem until we try it. Ask a model for "the name, age, and email from this bio" and we might get a tidy JSON object, or a JSON object wrapped in a markdown fence, or a friendly sentence with the JSON buried in it, or a JSON object with `"age": "thirty-one"`. Parsing is about making that reliable.

---

## Two Approaches

There are two families of solutions, and modern LangChain supports both:

- **Prompt-and-parse.** We tell the model what shape we want in the prompt, it replies with text, and a parser object reads that text into a Python object. This works with any model.
- **Native structured output.** We hand the model a schema through the provider's API, and the provider constrains the model's generation to match it. This is more reliable, but it requires model and provider support.

We'll look at both, because prompt-and-parse teaches us what's actually happening underneath, and native structured output is what we'll reach for in practice.

---

## The Baseline: `StrOutputParser`

The simplest parser does almost nothing, and we'll still use it constantly. A chat model returns an `AIMessage` object, not a string. `StrOutputParser` pulls the `.content` out:

```python
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

llm = ChatOllama(model="llama3.1", temperature=0)
prompt = ChatPromptTemplate.from_template("Summarize this in one sentence: {text}")

chain = prompt | llm | StrOutputParser()
print(chain.invoke({"text": "..."}))   # a plain str, not an AIMessage
```

*Chains a prompt, a local Ollama model, and a parser that unwraps the message into a plain string.*

This is worth internalizing because it shows the pattern every parser follows: a parser is just another **runnable** in the LCEL pipeline, sitting at the end and transforming whatever the model handed it.

---

## Defining the Shape with Pydantic

For structured data, we start by describing what we want as a **Pydantic model**. Pydantic gives us two things at once: a schema we can show the model, and runtime validation of what comes back.

```python
from pydantic import BaseModel, Field

class Person(BaseModel):
    name: str = Field(description="the person's full name")
    age: int = Field(description="age in years")
    email: str | None = Field(default=None, description="email address if mentioned")
    skills: list[str] = Field(default_factory=list, description="technical skills mentioned")
```

*Declares the target structure; the `description` text is not decoration — it gets sent to the model as part of the schema.*

Those `description` strings matter more than they look. They're the instructions the model reads about each field. A field described as `"age in years"` is far more likely to come back as `31` than `"thirty-one"`.

---

## `PydanticOutputParser` — Prompt and Parse

`PydanticOutputParser` does two jobs. It generates **format instructions** (a text description of the JSON schema) that we inject into the prompt, and it parses and validates the reply.

```python
from langchain_core.output_parsers import PydanticOutputParser

parser = PydanticOutputParser(pydantic_object=Person)

prompt = ChatPromptTemplate.from_template(
    "Extract the person's details from the text below.\n"
    "{format_instructions}\n\n"
    "Text: {text}"
).partial(format_instructions=parser.get_format_instructions())

chain = prompt | llm | parser
person = chain.invoke({"text": "Dana Okafor is 31, a Python and Kubernetes engineer."})

print(person.name)      # 'Dana Okafor'
print(person.age + 1)   # 32 — a real int, already validated
```

*Injects a schema description into the prompt, then validates the model's reply into a `Person` instance.*

Two details to note. `.partial()` fills in the `format_instructions` variable once, up front, so callers only need to supply `text`. And the result is a genuine `Person` object — `person.age` is an `int`, so arithmetic works, and a typo like `person.nmae` raises immediately instead of silently returning `None`.

If the model returns something that doesn't fit the schema, the parser raises `OutputParserException`. That's the correct behavior — we want to know.

---

## `JsonOutputParser` — When We Don't Need a Class

If we just want a dict, `JsonOutputParser` skips the Pydantic class. It's more forgiving about markdown fences and surrounding chatter, and it supports streaming partial objects.

```python
from langchain_core.output_parsers import JsonOutputParser

parser = JsonOutputParser()
chain = prompt | llm | parser
result = chain.invoke({"text": "..."})   # a plain dict
```

*Parses the reply as JSON into a dict, with no schema validation.*

The tradeoff is that nothing is validated. A missing key becomes a `KeyError` three functions later instead of an error at the boundary. Prefer Pydantic when the shape matters.

---

## `with_structured_output()` — The One to Reach For

Modern chat models expose structured output natively, usually built on the same tool-calling machinery we'll see in the Tool Integration notes. `with_structured_output()` wraps a model so it returns parsed objects directly — no format instructions, no separate parser:

```python
structured_llm = llm.with_structured_output(Person)

person = structured_llm.invoke(
    "Extract details: Dana Okafor is 31, a Python and Kubernetes engineer."
)
print(person)   # Person(name='Dana Okafor', age=31, email=None, skills=[...])
```

*Binds the schema to the model itself so invoking it returns a validated `Person` directly.*

This is more reliable than prompt-and-parse because the constraint is applied during generation rather than checked afterward. It composes into chains exactly the same way:

```python
chain = prompt | llm.with_structured_output(Person)
```

*The structured model is still a runnable, so it drops into an LCEL pipeline in the model's position.*

### The Ollama Caveat

Native structured output needs model support. With Ollama, that means a model trained for tool calling — `llama3.1`, `qwen2.5`, `mistral-nemo`, and similar. A small or older model may ignore the schema or fail outright. If `with_structured_output()` misbehaves on the model we're running, fall back to `PydanticOutputParser` with explicit format instructions, which works on anything that can produce text.

`ChatOllama` also accepts `format="json"`, which turns on Ollama's JSON mode and forces syntactically valid JSON — though not necessarily the right *shape*. It pairs well with `JsonOutputParser` as a middle ground.

---

## Nested and Repeated Structures

Pydantic models compose, and that's how we get lists of things back. Wrapping a list in a container model is the standard move, because most providers expect a single object at the top level:

```python
from typing import Literal

class Ticket(BaseModel):
    title: str
    priority: Literal["low", "medium", "high"]

class TicketBatch(BaseModel):
    tickets: list[Ticket]

batch = llm.with_structured_output(TicketBatch).invoke(
    "Turn these notes into tickets: login is broken; the footer link 404s."
)
for t in batch.tickets:
    print(t.priority, t.title)
```

*Wraps a list in a container model so the model can return multiple items in one structured reply.*

For constrained values like `priority`, a `Literal` (or an `Enum`) is stronger than a field description — Pydantic will reject anything outside the allowed set rather than passing it through.

---

## When Parsing Fails

Even with good prompting, parsing fails sometimes. A few practical defenses:

- **Lower the temperature.** Set `temperature=0` for extraction work. Creativity is the enemy of schema compliance.
- **Keep schemas flat and small.** Deeply nested models with fifteen fields fail far more often than three flat ones. Split the task into two calls if needed.
- **Catch it explicitly.** Wrap `.invoke()` in a `try`/`except OutputParserException` and decide what a failure means for the app — a retry, a default, or an error to the user.
- **Use `OutputFixingParser`** to send the broken output back to the model with the error message and ask for a correction. It costs an extra call, so it's a safety net, not a strategy.

```python
from langchain_classic.output_parsers import OutputFixingParser

fixing = OutputFixingParser.from_llm(parser=parser, llm=llm)
chain = prompt | llm | fixing
```

*Wraps the parser so malformed output gets one repair attempt from the model before raising.*

Note the import: as of LangChain 1.x this lives in the separate `langchain-classic` package (`pip install langchain-classic`), along with other legacy helpers. It isn't in the main `langchain` package any more.

---

## Key Takeaways

- Parsers are runnables that sit at the end of a chain and turn a model's reply into a usable Python object.
- Define the target shape as a Pydantic model; field descriptions are instructions the model actually reads.
- `PydanticOutputParser` injects format instructions into the prompt and validates the reply — it works with any model.
- `with_structured_output()` constrains generation through the provider and is the more reliable default, but it requires a tool-capable model in Ollama.
- `JsonOutputParser` is the lightweight option when a dict is enough and validation isn't needed.
- Use `temperature=0`, keep schemas small, and handle `OutputParserException` deliberately rather than letting it surface downstream.

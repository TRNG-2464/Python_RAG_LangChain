# Structured Output with Pydantic

We'll get a model to hand back a validated Python object instead of a blob of text. We'll cover `PydanticOutputParser` (prompt-and-parse), `with_structured_output()` (native), and what happens when validation fails.

## Prerequisites

| Software | Required Version |
|---|---|
| Python | >=3.10 |
| langchain-core | 1.6.4 |
| langchain-ollama | 1.1.0 |
| pydantic | 2.13.5 |
| Ollama | any current release, running locally |
| Ollama model | `llama3.1` (or another tool-capable model) |

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

Open `src/main.py`. It has the imports and a model already set up, with numbered sections for us to fill in. Each section (except Part 2, which prints nothing) already has a `banner(...)` call that prints a header, so we can tell which output came from which part. Add each part's code below its banner.

### 1. See the problem

Let's first watch a plain model call fail to give us data. Add this under `# --- Part 1 ---`:

```python
reply = llm.invoke(
    "Extract the person's name and age from this text: "
    "'Dana Okafor, 31, is an engineer.'"
)
print(repr(reply.content))
```

*Asks for the details with no structure requested, and prints the raw reply.*

Run it. We get a string — maybe prose, maybe JSON, maybe JSON inside a code fence. Run it a couple of times to see it vary. There's no reliable way to get `age` out of that.

### 2. Describe the shape

Now we'll tell Pydantic what we want. Add this under `# --- Part 2 ---`:

```python
class Person(BaseModel):
    name: str = Field(description="the person's full name")
    age: int = Field(description="age in years")
    job: str = Field(description="their job title")
```

*Declares the target structure; the descriptions get sent to the model as part of the schema.*

### 3. Prompt and parse

`PydanticOutputParser` writes schema instructions for the prompt and validates the reply. Add under `# --- Part 3 ---`:

```python
parser = PydanticOutputParser(pydantic_object=Person)

prompt = ChatPromptTemplate.from_template(
    "Extract the person's details.\n{format_instructions}\n\nText: {text}"
).partial(format_instructions=parser.get_format_instructions())

chain = prompt | llm | parser
person = chain.invoke({"text": "Dana Okafor, 31, engineer."})

print(person)
print(person.age + 1)
```

*Injects the schema into the prompt, then parses and validates the reply into a `Person`.*

Run it. `person.age + 1` prints `32` — it's a real `int`, not the string `"31"`. That arithmetic is the whole point: we got data, not text.

It's worth seeing what got injected. Add these lines and run again:

```python
print("\n--- format instructions ---")
print(parser.get_format_instructions())
```

*Prints the schema text the parser put into the prompt.*

### 4. Let the model do it natively

`with_structured_output()` skips the format instructions entirely and constrains the model directly. Add under `# --- Part 4 ---`:

```python
person = llm.with_structured_output(Person).invoke("Dana Okafor, 31, engineer.")
print(person)
```

*Binds the schema to the model so invoking it returns a validated `Person` directly.*

Same result, much less code. This is the version we'd normally reach for.

### 5. Break it

Let's see validation do its job. Add under `# --- Part 5 ---`:

```python
try:
    person = chain.invoke({"text": "A tortoise named Shelly."})
    print(person)
except Exception as e:
    print(type(e).__name__, "->", e)
```

*Feeds the chain text that doesn't contain the required fields, and catches the failure.*

Depending on the model, this either raises or returns something odd like `age=0`. Both are informative: validation catches the wrong *type*, but it can't catch a plausible-looking invented value. That's worth knowing before trusting extraction output.

### 6. Get a list back

Most providers want a single object at the top level, so a list goes inside a wrapper model. Add under `# --- Part 6 ---`:

```python
class People(BaseModel):
    people: list[Person]

result = llm.with_structured_output(People).invoke(
    "Dana Okafor, 31, engineer. Sam Reyes, 45, designer."
)
for p in result.people:
    print(p.name, p.age, p.job)
```

*Wraps a list in a container model so the model can return several items in one reply.*

---

## Exercises

1. **A different schema.** Write a `Book` model with `title: str`, `year: int`, and `genres: list[str]`. Extract it from a sentence you write yourself, using `with_structured_output()`.

2. **Constrain a field.** Add `rating: Literal["good", "bad"]` to `Book` (import `Literal` from `typing`). Try to get the model to return something outside that set and see what happens.

3. **Optional fields.** Add `publisher: str | None = None`. Extract from a sentence that doesn't mention a publisher — confirm you get `None` rather than an invented name.

4. **Compare the two approaches.** Run the same extraction ten times through `PydanticOutputParser` and ten times through `with_structured_output()`, counting failures for each. Which is more reliable on your model?

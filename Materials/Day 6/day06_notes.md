# DevMate Notes
## Topic: LangChain Fundamentals — Prompt Templates, Chains, and LCEL

## Executive Summary

Everything built before today talked to DevMate's own data — pandas
DataFrames, plain Python loops, FastAPI routes returning numbers and
booleans computed from `Ticket`/`Document`/`User` objects. Today
introduced a fundamentally different kind of dependency: a local
language model, reached through a library (LangChain) whose entire job
is standardizing how an application talks to any language model,
regardless of which one.

Three ideas anchor everything else in these notes, and it's worth
holding onto all three before diving into specifics:

1. **A chain is just a pipeline of swappable pieces.** A prompt
   template turns structured data into text a model can read; a chat
   model turns that text into a response; an output parser turns that
   response into something a normal Python caller can use. LangChain's
   `|` operator composes these three (or more) pieces into one
   callable object — nothing more mysterious than that, however
   unfamiliar the syntax looks at first.
2. **Model output is not deterministic, and that changes what
   "correct" means.** Every previous day's expected output was exact —
   run the code correctly, get that text, character for character.
   Today's is different: the same chain given the same input can
   produce differently-worded (but equally correct) output on two
   separate runs. Testing and grading have to shift from "does it
   match" to "does it accurately reflect what it was given, with
   nothing invented."
3. **LangChain moves fast, and a lot of what's out there about it is
   already outdated.** The library removed a once-standard class
   (`LLMChain`) entirely in a recent major version, and deprecated an
   entire package (`langchain-community`) that a huge fraction of
   existing tutorials and blog posts still reference. This isn't a
   footnote — it's the single most important practical fact for
   working with LangChain safely, especially when leaning on an AI
   coding assistant that may have been trained on now-outdated
   material.

---

## Deep Dive: What LangChain Actually Is

- **The core problem LangChain solves.** Every LLM provider (OpenAI,
  Anthropic, a local Ollama model, and dozens more) exposes its own
  API, with its own request/response shape. Code written directly
  against one provider's API is locked to that provider. LangChain's
  job is to sit in between: it defines a common, provider-agnostic
  interface, so that swapping the model underneath a chain is a
  one-line change (a different class, same `.invoke(...)` contract)
  rather than a rewrite.
- **The package is deliberately split up.** `langchain` itself is a
  slimmed-down core framework — prompt templates, output parsers, and
  the composition machinery (LCEL, covered below) — with no
  provider-specific code baked in. Talking to a specific provider
  requires installing that provider's small, separately-versioned
  "partner package" — `langchain-ollama` for Ollama, and similarly
  named packages exist for OpenAI, Anthropic, and others. A project
  only pulls in the one it actually uses, instead of every provider's
  dependencies at once. (`langchain-core`, which both `langchain` and
  every partner package depend on, is a transitive dependency — it's
  not something a project normally installs directly.)
- **`langchain-community` is a name worth actively avoiding now.**
  This was, for a long time, a large grab-bag package containing
  integrations for hundreds of third-party tools, including an older
  `Ollama` LLM class. It has been declared unmaintained, and its
  source repository has been archived — meaning no further updates,
  security fixes, or compatibility work will happen there, ever. A
  huge amount of existing tutorial content, StackOverflow answers, and
  AI-assistant training data still imports from this package (`from
  langchain_community.llms import Ollama`, for instance) because it
  used to be the standard way to do exactly what `langchain-ollama`
  does now. That code will very likely still *run*, if the archived
  package happens to be installed — but "still runs" and "still
  correct/maintained" are different claims, the same distinction that
  came up repeatedly discussing AI-assisted coding and silent data
  loss.
- **What to actually install today, and why it's exactly two
  packages.** `pip install langchain langchain-ollama` — `langchain`
  for the framework pieces (prompt templates, output parsers, LCEL),
  `langchain-ollama` for the one class that actually knows how to talk
  to a local Ollama server (`ChatOllama`). Nothing else is needed for
  what today's chains do.

---

## Deep Dive: Chat Models vs. Plain LLMs

- **Two different shapes of "model" in LangChain's vocabulary.** A
  plain `LLM` takes a single string in and returns a single string
  out — modeling the older style of language model that just continues
  a block of text. A `ChatModel` takes a *list of messages* in (each
  tagged with a role — `system`, `human`, `ai`) and returns a single
  message out. Every current, instruction-tuned model — including
  Llama 3.2 running through Ollama — is meant to be used as a chat
  model, because that's the format it was actually trained to follow.
- **`ChatOllama`, not `Ollama`.** `ChatOllama` (from `langchain_ollama`)
  is the current, correct class for talking to a local Ollama model as
  a chat model. It is what every current LangChain example and
  integration guide uses for Ollama. The plain `Ollama` LLM class
  still exists in the deprecated `langchain-community` package, but
  reaching for it means working against the wrong abstraction on top
  of working against an unmaintained package — two separate reasons
  to avoid it, not one.
- **Constructor arguments worth understanding, not just copying.**
  ```python
  _llm = ChatOllama(
      model="llama3.2",
      base_url="http://localhost:11434",
      temperature=0.2,
  )
  ```
  `model` is the exact tag Ollama should look up in its local cache —
  this single string is the entire connection between LangChain's code
  and whatever `ollama pull` actually downloaded, and a mismatch
  between the two is the root cause of the most common error working
  with Ollama (covered in detail in the troubleshooting case study
  below). `base_url` is spelled out explicitly even though it matches
  Ollama's own default (`http://localhost:11434`), purely so it's
  obvious at a glance, reading the code cold, exactly where this is
  talking to — a small but genuinely useful habit for any code that
  reaches out to a network service, local or not. `temperature`
  controls how much randomness the model injects into its own
  word choices; `0.2` is deliberately low for a task (summarizing a
  ticket or document) where a close-to-consistent, factual answer is
  wanted rather than creative variation.
- **One shared instance, reused across every chain.** Both of today's
  chains reuse the exact same `_llm` object rather than each
  constructing its own `ChatOllama(...)`. This matters for a reason
  beyond tidiness: if a real project ever needs different model
  settings for genuinely different purposes (a higher `temperature`
  for something creative, say), that should be a deliberate second
  instance built for a stated reason — not an accident from
  copy-pasting the same constructor call a second time and letting the
  two silently drift apart later when only one gets edited.

---

## Deep Dive: Prompt Templates

- **`ChatPromptTemplate`, not plain `PromptTemplate`.** Plain
  `PromptTemplate` formats a single string — the right tool for a
  plain `LLM`. `ChatPromptTemplate` formats a *list of messages*, which
  is what a `ChatModel` like `ChatOllama` expects as input. Reaching
  for the wrong one is a very easy mistake to make by pattern-matching
  on the name alone.
- **`.from_messages([...])` builds the template from role/text pairs.**
  ```python
  ChatPromptTemplate.from_messages([
      ("system", "You are DevMate, an internal engineering assistant..."),
      ("human", "Title: {title}\nPriority: {priority}\nStatus: {status}"),
  ])
  ```
  Each tuple is `(role, text)`. `"system"` sets the model's role and
  behavioral rules for the entire conversation; `"human"` carries the
  actual request. `{title}`, `{priority}`, `{status}` are placeholders
  — plain Python `str.format()`-style syntax — that stay unfilled until
  the template is actually invoked with real values.
- **The system message is doing real work, not just being polite.**
  Both of today's prompts end their system message with an explicit
  instruction not to invent details beyond what's provided. A language
  model asked to describe something with very little information will
  happily produce plausible-sounding specifics that were never in the
  input — this is a well-documented behavior worth knowing by name
  (commonly called "hallucination"), and one line of instruction is a
  real, if imperfect, mitigation for it. This is deliberately the
  first appearance of a theme that becomes the central design
  constraint once retrieval-based question answering is introduced
  later: an LLM's fluency is not the same thing as its accuracy, and a
  well-written prompt is one honest tool for narrowing that gap, not a
  complete solution to it.
- **`MessagesPlaceholder` — a placeholder for a variable-length list of
  messages, not a single value.** Not used in today's chains, but
  worth knowing it exists: `MessagesPlaceholder(variable_name="history")`
  slots into a `ChatPromptTemplate` wherever a prior conversation's
  messages need to appear, letting a chain "remember" earlier turns.
  Every fixed `("system", ...)`/`("human", ...)` pair contributes
  exactly one message; a `MessagesPlaceholder` can contribute zero,
  one, or many, depending on what list gets passed in for it at
  invocation time.

---

## Deep Dive: LCEL and the Runnable Protocol

- **What "chain" means today, and what it used to mean.** Older
  LangChain tutorials very commonly show `LLMChain(llm=llm,
  prompt=prompt)` — a class built specifically to bundle a prompt and
  a model together. As of LangChain's 1.0 release, `LLMChain` has been
  **removed from the main package entirely** (it now lives in a
  separate `langchain-classic` package, for legacy code that still
  needs it). It is not simply discouraged — it is not there to import
  by default anymore. The current, and now *only*, way to build a
  chain is **LCEL** (LangChain Expression Language).
- **The `Runnable` interface is the whole trick.** Every composable
  LangChain piece — a prompt template, a chat model, an output parser
  — implements a shared interface called `Runnable`, and every
  `Runnable` exposes the same core methods: `.invoke(...)` (run once,
  get one result), `.batch([...])` (run over a list of inputs),
  `.stream(...)` (get the result incrementally, piece by piece, as
  it's produced, rather than waiting for the whole thing), plus async
  twins of all three (`.ainvoke`, `.abatch`, `.astream`). Because
  every piece shares this interface, the `|` operator can compose any
  sequence of `Runnable`s into a new `Runnable` — one that supports the
  exact same methods itself.
- **`_ticket_summary_prompt | _llm | StrOutputParser()` reads like a
  Unix pipe, because it works like one.** Format the prompt into
  messages, feed those messages to the model, feed the model's
  response to the parser. Each stage's output becomes the next stage's
  input, in order, left to right. The resulting `ticket_summary_chain`
  is itself a `Runnable` — it can be invoked, streamed, batched, or
  even composed into a *larger* chain by piping it into something
  else.
- **`.invoke(...)` takes a single dict of the template's variables.**
  ```python
  ticket_summary_chain.invoke({
      "title": title,
      "priority": priority,
      "status": status,
  })
  ```
  The dict's keys must match the template's placeholder names exactly
  (`{title}`, `{priority}`, `{status}`) — a typo or a missing key here
  raises an error at the prompt-formatting stage, before the model is
  ever called.
- **Why LCEL replaced the class-based approach.** `LLMChain` bundled
  exactly one prompt and one model together, in a fixed shape. LCEL's
  `|` operator generalizes that into an arbitrary pipeline of any
  number of `Runnable`s — a prompt, a model, a parser, another chain,
  a piece of custom logic wrapped as a `Runnable` — all composed the
  same uniform way, and all inheriting the same `.invoke`/`.stream`/
  `.batch` behavior for free rather than needing it reimplemented per
  chain class.

---

## Deep Dive: Output Parsers

- **A chat model's raw output is a message object, not a string.**
  `_llm.invoke(...)` on its own returns an `AIMessage` — an object
  carrying the model's response text alongside metadata (which role
  produced it, token usage, and more) — not a plain Python `str`.
- **`StrOutputParser()` extracts exactly the text.** It's the piece
  that pulls `AIMessage.content` out and returns it as a plain string,
  so a function like `summarize_ticket(...)` can return `str` and its
  caller never needs to know anything about LangChain's message
  objects at all. This is a small illustration of a bigger LCEL
  pattern: each piece in a chain has one narrow job (format a prompt,
  produce a response, extract the useful part of it), the same
  single-responsibility instinct behind every focused module built so
  far in this project.
- **Other output parsers exist for structured output** (parsing a
  model's response into JSON, a specific Pydantic model, or a list),
  worth knowing about by name even though today's chains only need the
  plain-string case.

---

## Deep Dive: Non-Determinism — Why Today's "Expected Output" Looks Different

- **Every previous day's expected output was exact.** Correct code
  plus a fixed input always produced the exact same text, character
  for character, because plain Python and pandas/numpy operations are
  deterministic — the same inputs and the same operations always
  produce the same outputs.
- **A language model's output is fundamentally different, even at low
  temperature.** The same chain, given the exact same input, run twice
  in a row, can produce two differently-worded (but equally accurate)
  responses. Lowering `temperature` reduces the *degree* of variation;
  it does not eliminate it.
- **What "correct" has to mean instead.** Grading or testing a chain's
  output can't be "does this string match exactly." It has to be:
  does the output accurately reflect the facts it was actually given
  (the ticket's or document's title, priority/category, status/staleness
  signal), with nothing invented that wasn't provided. This is exactly
  why the demo and challenge material both label their sample output
  "illustrative," not "expected" — a deliberate, permanent shift in
  vocabulary for every LLM-based chain going forward, not a one-time
  caveat.

---

## Deep Dive: AI-Assisted Coding, LangChain Edition

- **The same review habit from earlier work, applied to a fast-moving
  library.** Reviewing an AI suggestion for silent failure modes
  (covered in depth in earlier notes, using a `.map(dict).sum()`
  example) generalizes directly to a new risk here: an AI coding
  assistant suggesting a pattern that is *outdated* rather than
  *wrong* in the traditional sense.
- **Why this specific risk is unusually high for LangChain right now.**
  LangChain has changed fast and publicly — a fully removed core class
  (`LLMChain`), an entire package moved from "standard" to
  "unmaintained and archived" (`langchain-community`) — and a large
  share of the tutorials, blog posts, and Q&A content an AI model was
  trained on necessarily predates both of these changes. A suggestion
  built on `LLMChain` or importing `Ollama` from `langchain_community`
  will frequently still *run*, exactly as long as the deprecated
  package or class happens to still be installed somewhere — which
  makes it a genuinely dangerous kind of wrong, the same "no error,
  but built on something already abandoned" shape as last time's
  silent-data-loss bugs, just showing up as a maintenance risk instead
  of a wrong number.
- **A concrete self-check before trusting a LangChain suggestion:**
  is the chain built with `|` (LCEL) or with a class called
  `...Chain` being constructed directly? Is a model class imported
  from a `langchain_community` path? Either signal is worth pausing on
  and checking against current documentation before accepting.

---

## Deep Dive: Testing a Chain Without a Real Model

- **`FakeListLLM` — canned responses, no network call, no Ollama
  required.** Found in `langchain_core.language_models.fake`,
  `FakeListLLM` returns responses from a fixed list handed to it at
  construction time, in order, instead of actually calling any model.
  Swapping `_llm` for a `FakeListLLM` instance while testing lets a
  test verify a chain's *plumbing* — does the prompt template format
  correctly, does the parser correctly extract the fake response —
  without needing a real, running local model at all, and without the
  test's outcome depending on non-deterministic model output.
- **What this does and doesn't prove.** A test built this way proves
  the chain's *composition* is correct — the right variables reach the
  prompt, the right object shape flows through each stage. It says
  nothing about whether a *real* model, given a real prompt, will
  produce a good answer — that's a separate, harder-to-automate
  concern that non-determinism makes fundamentally different from
  testing deterministic code.

---

## Real Case Study: Ollama `model not found (status code: 404)`

- **The symptom.** A chain that built and ran correctly up through
  LangChain's own code failed at the very last step — the actual
  network call to Ollama — with
  `ollama._types.ResponseError: model 'llama3.2' not found (status code: 404)`.
  This is a genuinely useful error to see once deliberately, because
  it's an error from *Ollama itself*, arriving after LangChain has
  already done its job correctly (formatted the prompt, built the
  request) — a good illustration of how to localize a bug to the right
  layer instead of assuming the newest code (the LangChain chain) is
  automatically the guilty party.
- **First checkpoint: does the model actually exist locally?**
  `ollama list` is the ground truth for what's actually cached and
  runnable — not what `ollama pull` was *typed*, but what actually
  finished downloading. Two distinct failure shapes surfaced against
  this exact error, worth knowing apart:
  - **A tag mismatch.** `ollama list` shows an entry, but not under a
    `:latest`-tagged name matching the bare string passed as `model=`.
    A bare model name like `"llama3.2"` in `ChatOllama(model=...)`
    only resolves successfully if a `latest` alias actually exists in
    the local cache under that name.
  - **Nothing pulled at all.** `ollama list` prints only its header
    row (`NAME ID SIZE MODIFIED`) with zero rows underneath — meaning
    no model has ever successfully finished downloading to this
    machine's Ollama instance, regardless of what a prior `ollama
    pull` command appeared to do (interrupted before completing, run
    against a different Ollama instance, or similar). This is a more
    fundamental gap than a tag mismatch — there is nothing local for
    any tag to match.
- **The fix for each.** A tag mismatch: either re-pull with the bare
  name (`ollama pull llama3.2`, no explicit tag) so the `:latest`
  alias gets created, or change `ChatOllama(model=...)` to match
  whatever exact tag `ollama list` actually shows. Nothing pulled at
  all: run `ollama pull llama3.2` and watch it run to completion (a
  manifest download followed by one or more layer downloads, ending in
  a success line) — then re-run `ollama list` to confirm a row now
  appears with a real size and timestamp before trying the chain
  again.
- **The general lesson.** A `404` from a well-known, well-documented
  model name is essentially never a sign that the model's naming
  scheme changed — it is a local-environment fact: either the model
  isn't actually in the local cache under any name, or it's in the
  cache under a different exact tag than the code is asking for.
  `ollama list`, checked directly, resolves the question faster than
  any amount of reasoning about the code.

---

## Architectural Analysis: One Chain Invocation, Start to Finish

Tracing `summarize_ticket(title="Runbook missing rollback step",
priority="High", status="Open")` end to end, through the `Runnable`
protocol LCEL is built on:

1. `summarize_ticket(...)` calls
   `ticket_summary_chain.invoke({"title": ..., "priority": ...,
   "status": ...})` — a single dict, matching the prompt template's
   three placeholder names exactly.
2. Because `ticket_summary_chain` is `_ticket_summary_prompt | _llm |
   StrOutputParser()`, LCEL calls `.invoke(...)` on the *first* piece
   first: `_ticket_summary_prompt.invoke({...})` formats the system
   and human messages, substituting the three placeholders, and
   returns a formatted prompt value (a list of concrete messages, no
   more `{title}`-style templating left in them).
3. That formatted output becomes the *input* to the next piece:
   `_llm.invoke(<formatted messages>)`. This is the actual network
   call to Ollama's local server at `http://localhost:11434` — the
   step that can fail with the `404` covered above, or hang if Ollama
   isn't running at all. On success, it returns an `AIMessage`
   carrying the model's response.
4. That `AIMessage` becomes the input to the last piece:
   `StrOutputParser().invoke(<AIMessage>)`, which extracts
   `.content` and returns it as a plain `str`.
5. That final string is exactly what `ticket_summary_chain.invoke(...)`
   returns to `summarize_ticket`, and what `summarize_ticket` itself
   returns to its own caller.

A question worth asking directly: "at which of these five steps would
a `ModuleNotFoundError` from running the script incorrectly actually
show up?" The honest answer: none of them — that error happens before
step 1 even begins, at Python's own import time, while it's still
trying to load `scripts\day6_demo.py`'s own `from app.ai.chains import
summarize_ticket` line. It's a completely different layer of failure
from the Ollama `404`, which only happens once step 3 actually reaches
the network — worth keeping the two failure modes mentally separate
when debugging either one.

---

## Quiz-Prep Quick Reference

| Term | One-line definition |
|---|---|
| `ChatModel` | Takes a list of role-tagged messages in, returns one message out — the correct abstraction for current instruction-tuned models |
| `ChatOllama` | The current LangChain class (from `langchain_ollama`) for talking to a local Ollama chat model |
| `ChatPromptTemplate` | Formats a list of messages from role/text pairs and named placeholders — the chat-model counterpart to plain `PromptTemplate` |
| `MessagesPlaceholder` | A `ChatPromptTemplate` slot for a variable-length list of prior messages (e.g. conversation history) |
| LCEL | LangChain Expression Language — composing `Runnable`s with `\|` into a pipeline |
| `Runnable` | The shared interface every composable LangChain piece implements: `.invoke`/`.batch`/`.stream` plus async twins |
| `LLMChain` | The old, class-based way to bundle a prompt and model — fully removed from the main `langchain` package as of version 1.0 |
| `AIMessage` | What a `ChatModel.invoke(...)` actually returns — an object with `.content`, not a plain string |
| `StrOutputParser` | Extracts `AIMessage.content` as a plain string — the last stage of a simple text-generating chain |
| `langchain-community` | A large integration package, now unmaintained and archived — avoid importing model classes from it |
| `FakeListLLM` | Returns canned responses instead of calling a real model — used for testing chain plumbing without a live LLM |
| Illustrative output | This topic's replacement for "expected output" — the shape and accuracy should match, exact wording will not |
| `python -m package.module` | Runs a script as a module, adding the current directory to the import path — required whenever a `scripts\` file imports from a sibling package like `app\` |
| Ollama `404 model not found` | Almost always a local cache issue — either nothing was successfully pulled, or the cached tag doesn't match the exact string passed to `model=` |

---

## Common Pitfalls & Anti-Patterns

- **Reaching for `LLMChain` because a tutorial or an AI assistant
  suggested it.** It no longer exists in the current `langchain`
  package at all — any code depending on it either fails to import
  outright, or is quietly relying on a separate, legacy
  `langchain-classic` package installed alongside it.
- **Importing a model class from `langchain_community`.** Likely to
  still run today, but built on a package with no further maintenance,
  fixes, or security updates going forward — a maintenance liability
  hiding behind code that currently works.
- **Using plain `PromptTemplate` with a chat model,** or vice versa —
  the two produce different shapes of output (a single string vs. a
  list of messages), and a `ChatModel` expects the latter.
- **Grading or testing LLM output for an exact string match.** Model
  output is non-deterministic even at low `temperature`; the right
  standard is factual accuracy against the input, not verbatim
  reproduction of any single sample output.
- **Dropping the "don't invent details" instruction from a system
  prompt "to save time" or because it feels like boilerplate.** It's a
  deliberate, repeated mitigation for a real and well-documented
  failure mode, not incidental phrasing.
- **Constructing a second `ChatOllama` instance instead of reusing an
  existing one** for a second chain in the same module — works today,
  but creates two independent configurations that can silently drift
  apart the moment only one gets edited later.
- **Running a `scripts\` file that imports from `app\` directly
  (`python scripts/file.py`) instead of as a module** (`python -m
  scripts.file`) — produces a `ModuleNotFoundError` that has nothing
  to do with whether the imported code itself is correct.
- **Assuming an Ollama `model not found` error means the model name or
  tagging scheme changed,** rather than checking `ollama list` first
  to see what's actually cached locally right now.

---

## Troubleshooting Guide

| Symptom | Likely Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'app'` when running a script under `scripts\` | The script was run directly (`python scripts/file.py`), which sets the import path to the script's own directory, not the project root | Run it as a module instead: `python -m scripts.file` (dotted path, no `.py`), from the project's root directory |
| `ollama._types.ResponseError: model '<name>' not found (status code: 404)` | Either the model was never successfully pulled, or the cached tag doesn't match the exact string passed to `ChatOllama(model=...)` | Run `ollama list`; if empty, `ollama pull <name>` and wait for it to finish; if it shows a different tag, either re-pull with the bare name or match the exact tag shown |
| `ollama list` prints only the header row, no models | No model has ever successfully finished downloading to this Ollama instance | Run `ollama pull <name>` and watch it complete (manifest + layer downloads, ending in success) before trying again |
| A chain raises a `KeyError`-style error, or complains about a missing variable, when `.invoke(...)` is called | The dict passed to `.invoke(...)` doesn't have a key matching one of the template's `{placeholder}` names exactly | Compare the dict's keys against every `{...}` placeholder in the `ChatPromptTemplate` character-for-character |
| A function meant to return a plain string instead returns something with `.content`, roles, or metadata attached | `StrOutputParser()` was left out of the chain, so `.invoke(...)` returns the raw `AIMessage` from the chat model instead of extracted text | Add `\| StrOutputParser()` as the last stage of the chain |
| Code that imports `LLMChain` fails immediately at the `import` line | `LLMChain` was removed from the main `langchain` package in version 1.0 | Rewrite the chain using LCEL (`prompt \| llm \| output_parser`) instead of the class-based pattern |
| An AI-suggested import references `langchain_community` | Suggestion is likely based on older, now-unmaintained patterns | Use the correct current partner package instead (`langchain_ollama` for Ollama, and the equivalent for any other provider) |
| A chain's output reads correctly but doesn't match a saved "expected output" sample exactly | Model output is non-deterministic — this is expected, not a bug | Grade/test against factual accuracy (the input's actual title, priority/category, status) rather than exact wording |
| A test of chain logic depends on Ollama actually being installed and running | The test is exercising the real model instead of just the chain's plumbing | Swap `_llm` for a `FakeListLLM` with a canned response list to test prompt formatting and parsing in isolation |

---
*DevMate — Northbeam Engineering Assistant — Notes: LangChain Fundamentals — Prompt Templates, Chains, and LCEL*

# DevMate Notes
## Topic: Structured Output, Conversation Memory, and Tool Calling

---

## Executive Summary

The chain built the day before this one did exactly one thing: format
a prompt, call a model, extract a string. Everything covered here
takes that same three-piece pattern and asks it to do more —
returning a typed object instead of a sentence, remembering earlier
turns of a conversation, and reaching outside the prompt entirely to
fetch a specific fact it wasn't handed directly. None of these three
capabilities replace LCEL; all three are just different pieces
composed into or wrapped around the exact same `_llm` instance from
before.

One thread runs through all three, and it's worth stating up front
because it shows up again and again below: **LangChain is a
fast-moving library, and "current" has a shelf life.** A once-standard
way to do each of today's three things either already has, or is in
the process of, being replaced by something else — and knowing which
technique is current right now, versus which one merely still runs
without erroring, is itself part of what's being taught today.

---

## Deep Dive: Structured Output

- **The problem being solved.** A chain ending in `StrOutputParser()`
  hands back a sentence. Code that wants to actually *do* something
  with a model's answer — check a boolean, compare a value, store a
  field — has to parse that sentence somehow, which is fragile the
  moment a model phrases things slightly differently. Structured
  output solves this by having the model's response conform to a
  known shape (a Pydantic model) from the start.
- **`.with_structured_output(SomeModel)`, called directly on the chat
  model, is the current, recommended technique.** Not a separate
  parser piped in afterward — a method on `_llm` itself, returning a
  new `Runnable` that composes into LCEL exactly like any other piece:
  `prompt | _llm.with_structured_output(SomeModel)`. No
  `StrOutputParser` follows it, because there's no plain string left
  to extract — the chain's final output is already a `SomeModel`
  instance.
- **An older technique still exists, and still works, but is now the
  fallback.** `PydanticOutputParser` (from `langchain_core.
  output_parsers`) requires manually calling `.get_format_instructions()`
  and pasting that string into the prompt by hand, then hoping the
  model's raw text response happens to parse as valid JSON matching
  the schema afterward. Nothing about this has changed — it's the same
  prompt-engineering-based coaxing it always was. It's not deprecated,
  exactly, but `.with_structured_output(...)` is the more reliable
  path today because the shape gets enforced by the model provider
  itself during generation, not hoped for after the fact.
- **A specific, version-dependent detail worth knowing exactly.**
  `.with_structured_output(...)` accepts a `method` argument —
  `"json_schema"`, `"function_calling"`, or `"json_mode"` — and the
  *default* changed from `"function_calling"` to `"json_schema"` in a
  past `langchain-ollama` release. `"json_schema"` sends the model's
  full JSON schema through Ollama's own native structured-output
  parameter, which Ollama enforces during generation (grammar-
  constrained decoding) — meaningfully more reliable for a small local
  model than hoping a text response parses correctly, and the current
  default for exactly that reason. An older tutorial or an AI
  assistant trained on older material may show `method=
  "function_calling"` explicitly, because that used to be the only
  option, or the default before it changed — both still work, but
  `"json_schema"` is the one to reach for today, default and all.
- **A known rough edge, not a blocker.** Deeply nested Pydantic models
  have, in the past, exposed a real bug where `"function_calling"`
  mode passed only a flattened tool schema rather than the full JSON
  schema, so the model never saw nested field requirements correctly.
  `"json_schema"` mode — sending the complete schema through Ollama's
  native `format` parameter — is exactly the fix path for this. Worth
  knowing about as a "if a deeply nested model misbehaves, this is
  why" fact, not as a reason to avoid structured output generally;
  today's `TicketTriageSuggestion`/`DocumentHealthAssessment` are both
  flat enough to not be affected at all.

---

## Deep Dive: Conversation Memory

- **The mechanism is a list, not magic.** `MessagesPlaceholder("history")`
  reserves a spot in a `ChatPromptTemplate` for a variable-length list
  of prior messages — contributing zero, one, or many messages to the
  final prompt depending on whatever list gets passed in for
  `"history"` at invocation time. The chain itself has no memory of
  anything between calls; a function built around it is stateless.
  What actually "remembers" is a plain Python list of
  `HumanMessage`/`AIMessage` objects (from `langchain_core.messages`)
  that the *caller* builds up by hand, appending a `HumanMessage` and
  an `AIMessage` after every turn and passing the growing list back in
  on the next call.
- **This is the single easiest thing to get wrong.** Forgetting to
  append after a turn is the most common way memory "stops working" —
  the chain isn't broken; the list being threaded through it simply
  never grew. A follow-up question that suddenly gets answered as if
  it were the *first* question is a strong signal to check whether
  `history.append(...)` actually ran on the previous turn.
- **A once-standard shortcut for this has been formally deprecated.**
  `RunnableWithMessageHistory` (from `langchain_core.runnables.
  history`) used to automate exactly this list-management step —
  wrapping a chain so that appending happened automatically, keyed by
  a session id. It still exists, still imports, and still runs, but
  it now emits a deprecation warning on every construction and is
  slated for removal in a future major `langchain-core` release, in
  favor of LangGraph's built-in persistence. Since LangGraph is
  deliberately not introduced until much later — as a concept-only
  topic, no code — the plain list-and-`MessagesPlaceholder` pattern
  used today is the current, stable, *non*-deprecated way to get
  multi-turn memory without pulling LangGraph in early. Seeing
  `RunnableWithMessageHistory` in older material is worth recognizing
  by name, not worth adopting.
- **What today's memory does and doesn't survive.** The `history` list
  only lasts as long as whatever process is holding onto it in memory
  — nothing here is written to disk or a database. Restarting the
  script, or moving to a second, unrelated call site with its own
  fresh empty list, loses everything. Real, persisted, multi-session
  memory — surviving past one running Python process — is exactly
  what a proper memory system (LangGraph's checkpointer, eventually)
  is for; today's version is a genuine, working illustration of the
  *mechanism*, not the production-grade version of the *feature*.

---

## Deep Dive: Tool Calling

- **What a "tool" actually is.** `@tool` (from `langchain_core.tools`)
  turns a plain, type-hinted, docstring-documented Python function
  into something a chat model can be told about and asked to call.
  The function's type hints become its argument schema; its docstring
  becomes its description — both get sent to the model as part of the
  request once the tool is bound.
- **Binding is what makes a model tool-aware.** `_llm.bind_tools([my_tool])`
  returns a new, bound variant of the model — every request that bound
  variable sends includes the tool's name, description, and argument
  schema. The original `_llm` is untouched; binding a tool to it
  doesn't mutate it, it produces something new. Binding a *second*
  tool to an *already-bound* variable doesn't add to the first tool —
  each `bind_tools(...)` call defines the complete tool set for that
  particular bound variable, which is exactly why today's two
  tool-calling functions each keep their own separate bound variable
  (one per tool) rather than sharing one.
- **What the model actually returns when it wants to call a tool.**
  `.invoke(...)` on a tool-bound model doesn't necessarily return
  plain text. It returns an `AIMessage` whose `.tool_calls` attribute
  is a list — empty if the model chose not to call anything, or
  populated with dicts like `{"name": ..., "args": {...}, "id": ...}`
  if it did. The message's `.content` is typically empty in this case;
  the useful information lives in `.tool_calls`, not `.content`.
- **Running the tool and getting the result back in the right shape.**
  Calling `my_tool.invoke(tool_call)` — passing the *entire* tool-call
  dict, not just the extracted argument — runs the real Python
  function *and* wraps its return value into a `ToolMessage` already
  tagged with the matching `tool_call_id`. That id match is what lets
  the model connect "the result I'm looking at" to "the specific call
  I asked for," especially once more than one tool call is in play.
  Appending that `ToolMessage` to the running message list and
  invoking the tool-bound model one more time gives it everything it
  needs to produce a real final answer.
- **A single-step loop is a deliberate scope choice, not a shortcut.**
  Today's pattern calls the tool-bound model once, checks
  `.tool_calls`, resolves at most one round of tool calls, and calls
  once more for a final answer. A model *could*, in principle, decide
  it needs to call a second tool based on the first tool's result —
  handling that requires a real loop (call, check, resolve, repeat
  until `.tool_calls` comes back empty), which is exactly the kind of
  multi-step reasoning a proper agent framework exists to manage
  cleanly. Today's scope is intentionally the simplest version of the
  mechanism.
- **Whether this even works depends on the model, not just the
  library.** Tool-calling support in Ollama comes from a model's own
  chat template, not from its parameter count — Llama 3.2 (the 3B size
  included) is documented as supporting tool use; some other models
  and older Llama versions simply aren't built with a tool-calling
  template at all, regardless of size. Verified separately: this
  specific model requires a reasonably current Ollama version — tool
  support for Llama 3.2 landed at a specific Ollama release, slightly
  after the original Llama 3.1 tool-support release — so an outdated
  local Ollama install is a real, if easy to overlook, reason a
  tool-bound model might simply never produce a tool call at all.

---

## Deep Dive: The Official Docs Have Moved On (and Why This Project Hasn't, Yet)

- **Worth naming directly.** The current top-level LangChain
  documentation has shifted toward an agent-first narrative —
  `create_agent(...)`, which runs on LangGraph under the hood, is now
  the example shown for nearly everything, including plain chat and
  tool use. The underlying pieces used today — `ChatPromptTemplate`,
  LCEL's `|`, `.with_structured_output(...)`, `@tool`/`bind_tools`,
  `MessagesPlaceholder` — are all still fully shipped and documented,
  just increasingly in the *reference* docs rather than the top-level
  narrative ones.
- **Why this project is deliberately staying at this layer a bit
  longer.** Agents, and LangGraph specifically, are coming later as
  their own dedicated, concept-first topics — introduced by building
  understanding of what a chain actually does and how its pieces
  compose, before wrapping that understanding in a framework that
  handles the looping and state management automatically. Reaching
  for `create_agent(...)` today would work, but would skip over
  exactly the mechanics these notes just spent several sections on:
  what a `Runnable` is, what an `AIMessage.tool_calls` actually looks
  like, why a `ToolMessage`'s `tool_call_id` has to match.
- **A practical implication for anyone reading LangChain's docs
  independently right now:** don't be surprised to find that most
  current official examples reach for `create_agent` by default —
  that's a real, current shift in how the library is documented, not
  a sign that today's LCEL-based approach is outdated or wrong. It's
  one layer below where the docs' own examples currently sit, on
  purpose.

---

## Real Case Study: A Tool That "Worked" and Still Gave the Wrong Answer

- **The symptom.** Asking a tool-bound chain about a ticket's related
  document returned an answer saying no such document could be found
  — for a document that plainly exists and had already been verified,
  by hand, as real data in a prior lookup.
- **First checkpoint: is the model even trying to call the tool?**
  Printing `ai_message.tool_calls` confirmed yes — the model correctly
  decided to call `look_up_related_document`, and correctly extracted
  `document_id: 1` from the ticket context it was given. This ruled
  out the most obvious suspects (the model failing to understand it
  had a tool, or extracting the wrong argument).
- **Second checkpoint: what did the tool itself actually return?**
  Printing the `ToolMessage`'s content showed exactly the string the
  tool produces for a lookup miss: `"No document found with id 1."`
  This is where the investigation had to shift — the tool ran, with
  the correct argument, and *still* came back empty. That's a strong
  signal the problem isn't in the tool-calling machinery at all, but
  in the data the tool is looking through.
- **The actual root cause.** The script exercising this chain loaded
  tickets (`load_tickets_from_csv(...)`) but never loaded documents
  (`load_documents_from_folder(...)`) before running the tool-calling
  step. `Document.find_by_id(...)` searches `Document.registry` —
  which was simply empty at that point in the script, because nothing
  had ever populated it. The tool wasn't malfunctioning; it was
  functioning perfectly against a dataset that was never actually
  loaded.
- **Why this is worth generalizing, not just fixing once.** Every
  piece involved here behaved exactly as designed: the model chose
  correctly, extracted the argument correctly, the tool ran without
  raising an exception, and the tool's own error-handling produced a
  clean, honest message rather than crashing. Nothing here looks
  broken in isolation. The actual defect was a missing setup step
  *earlier* in the script — a category of bug that specifically
  resists being found by inspecting the chain or the tool function
  themselves, because both are innocent. This is the same general
  shape as the very first inner-join bug from weeks ago (a row simply
  wasn't there, and everything downstream computed an honest, wrong-
  because-incomplete answer) wearing a new costume: a *dataset* that
  was never populated, discovered a layer further downstream, inside
  a tool call instead of a merge.
- **The fix.** Add the missing `load_documents_from_folder("docs")`
  call before any code that depends on `Document.registry` being
  populated — obvious in hindsight, and exactly why checking "is the
  data actually there" belongs earlier in the debugging order than
  "is the LLM plumbing correct," not later.

---

## Architectural Analysis: One Tool-Calling Round Trip, Start to Finish

Tracing a question about a ticket's related document, with the
documents correctly loaded this time:

1. A `SystemMessage` (explaining the tool's existence) and a
   `HumanMessage` (the ticket's title, its `related_document_id`, and
   the actual question) are assembled into a plain list — no
   `ChatPromptTemplate` involved in this particular pattern, unlike
   yesterday's chains.
2. `_llm_with_tools.invoke(messages)` sends that list, plus the bound
   tool's schema, to Ollama. The model decides whether it needs more
   information than it was directly given.
3. The response comes back as an `AIMessage`. If the model decided it
   needed the tool, `.tool_calls` is populated with the tool's name
   and the arguments the model extracted (`{"document_id": 1}`); if
   not, `.tool_calls` is empty and `.content` already holds a usable
   answer.
4. Assuming a tool call was requested: that `AIMessage` is appended to
   the running `messages` list, then `look_up_related_document.invoke(
   tool_call)` actually runs the Python function — a plain,
   synchronous, in-process call, nothing about it goes back to Ollama
   — and returns a `ToolMessage` tagged with the matching
   `tool_call_id`.
5. That `ToolMessage` is appended to `messages`, and
   `_llm_with_tools.invoke(messages)` is called a second time — now
   with the full history (system instructions, the original question,
   the model's own tool request, and the tool's real answer) available
   to it.
6. The second `AIMessage`'s `.content` is the actual final answer,
   grounded in the tool's real return value rather than anything the
   model had to guess or recall from training.

A question worth asking directly: "at which of these six steps would
last section's real bug actually have been visible, if someone had
been watching closely enough?" The honest answer: step 4 — the moment
`look_up_related_document.invoke(tool_call)` runs, using a correct
`document_id` against an empty `Document.registry`. Steps 1 through 3
all complete with no hint anything is wrong; step 4 is where a correct
argument meets missing data and produces an honest miss. Recognizing
that step 4 specifically is "where the data lives" is exactly what
made checking the tool's actual result — rather than second-guessing
the model's tool-selection logic — the fast way to the real cause.

---

## Quiz-Prep Quick Reference

| Term | One-line definition |
|---|---|
| `.with_structured_output(SomeModel)` | Current method on a chat model returning a `Runnable` whose output is parsed straight into `SomeModel`, no separate parser needed |
| `PydanticOutputParser` | Older technique requiring manual `.get_format_instructions()` injected into the prompt; still works, no longer the primary recommendation |
| `method="json_schema"` | Current default for `.with_structured_output(...)` on Ollama — sends the full schema through Ollama's native structured-output enforcement |
| `MessagesPlaceholder` | A `ChatPromptTemplate` slot for a variable-length list of prior messages |
| Conversation memory (current pattern) | A plain `list[BaseMessage]` the caller builds and threads through `MessagesPlaceholder`, appending after every turn |
| `RunnableWithMessageHistory` | Automated the list-appending step; still runs, but deprecated in favor of LangGraph persistence |
| `@tool` | Decorator (from `langchain_core.tools`) turning a type-hinted, documented function into a model-callable tool |
| `bind_tools([...])` | Method on a chat model returning a new bound variant that includes the given tool(s)' schemas in every request; does not mutate the original or accumulate across calls |
| `AIMessage.tool_calls` | List of `{name, args, id}`-shaped dicts describing what the model wants called; empty if it chose not to call anything |
| `ToolMessage` | Produced by `my_tool.invoke(tool_call)`, tagged with a matching `tool_call_id`, carrying the tool's real return value back to the model |
| Single-step tool loop | Call once, resolve any requested tool calls, call once more for a final answer — sufficient for one round of tool use, not for a model chaining multiple tool calls together |
| "Ran correctly, wrong answer" | A tool or lookup that executes without error but searches an empty/incomplete dataset because a setup step ran out of order or was skipped entirely |

---

## Common Pitfalls & Anti-Patterns

- **Reaching for `PydanticOutputParser` by habit** when
  `.with_structured_output(...)` is available and more reliable —
  the older technique still works, but leans on the model's raw text
  happening to parse correctly rather than an enforced schema.
- **Not knowing which `method` `.with_structured_output(...)` is
  actually using.** The default changed over time; assuming an older
  tutorial's explicit `method="function_calling"` is still the
  default can lead to debugging the wrong thing when behavior differs
  from what's currently expected.
- **Forgetting to append to a conversation's `history` list after a
  turn.** The chain isn't stateful — a follow-up question answered as
  if it were the first one is almost always a missing `.append(...)`,
  not a broken chain.
- **Adopting `RunnableWithMessageHistory` because it looks like the
  "proper" solution** to conversation memory. It's a real, working
  class, but it's on a deprecation path — the plain list pattern is
  the current, stable choice for anything not yet ready to bring in
  LangGraph.
- **Assuming a model's failure to call an available tool means the
  tool is broken.** `.tool_calls` coming back empty is a model
  decision, not necessarily a bug — check it directly with a debug
  print before assuming the tool-binding code itself is at fault.
- **Debugging a wrong tool-calling answer by staring at the chain's
  logic first**, instead of checking — in order — whether the model
  requested the right tool call, whether the tool itself received the
  right arguments, and whether the *data the tool searches* was
  actually loaded. The real bug covered above lived in the last of
  those three, and would have been found immediately by checking data
  presence before re-reading the tool-calling loop's code for the
  fifth time.
- **Re-binding an already-tool-bound model with a second tool**,
  rather than binding a fresh variable from the original `_llm` — the
  first tool doesn't disappear, it silently accumulates alongside the
  second, which usually isn't what was intended.

---

## Troubleshooting Guide

| Symptom | Likely Cause | Fix |
|---|---|---|
| A structured-output chain raises a validation error instead of returning the typed object | The model's response didn't match the schema — more likely with `PydanticOutputParser` (no enforcement) than `.with_structured_output(...)` | Prefer `.with_structured_output(SomeModel)` with the default `method="json_schema"`; if already using it, check for deeply nested fields, a known rough edge |
| A follow-up question gets answered as if no prior context existed | The `history` list was never appended to after the previous turn | Confirm `history.append(HumanMessage(...))` and `history.append(AIMessage(...))` both ran before the next call |
| Deprecation warning mentioning `RunnableWithMessageHistory` | Using a class that's still functional but on a removal path | Switch to a plain `list[BaseMessage]` threaded through `MessagesPlaceholder`, or accept the warning as a known, temporary situation |
| A tool-bound model never seems to call the tool, `.tool_calls` is always empty | Either the model genuinely doesn't need the tool for that input, or the local Ollama version predates tool-calling support for this specific model | Confirm `ollama --version` meets the model's tool-support requirement; try a more clearly tool-requiring question to confirm the binding itself works at all |
| A tool call's arguments look wrong (unexpected value or type) | The model mis-extracted the argument from the human message's phrasing | Rephrase the human message to state the relevant value more explicitly (e.g. `related_document_id=1` rather than embedding it in prose) |
| A tool executes without error but reports "not found" for something that should exist | The registry/data source the tool searches was never populated in this run, even though the tool's own logic is correct | Check that every relevant loader (`load_documents_from_folder`, seeding `User` records, etc.) ran before the tool-calling code, not just the loaders the *rest* of the script happens to need |
| A second tool doesn't seem to be available even though `bind_tools([...])` was called for it | It was bound onto a variable that was already tool-bound from a previous `bind_tools(...)` call, unintentionally combining or overwriting the tool set | Bind each distinct tool set from the original `_llm`, not from an already-bound variant, unless combining tools on one variable is actually the goal |

---
*DevMate — Northbeam Engineering Assistant — Notes: Structured Output, Conversation Memory, and Tool Calling*

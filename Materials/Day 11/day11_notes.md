# DevMate Notes
## Topic: Formalizing Retrieval into an LCEL Chain, and Summarizing Conversation Memory
---

## Executive Summary

Two things got built, related but separate. First, yesterday's
grounded-answer logic — retrieve, format, generate, called as three
plain Python statements — got formalized into one composed LCEL
chain, `retrieval_chain`, using `RunnablePassthrough.assign(...)` to
thread state through the pipeline instead of juggling separate
variables by hand. Second, that formal chain gained **conversation
memory**, so a follow-up question can build on what was already asked
without repeating context — and specifically **summarizing** memory,
so a long-running conversation doesn't grow an ever-larger block of
raw history that has to get re-sent on every single turn.

Today is also notable for something that doesn't usually make it into
a curriculum this directly: real, hands-on execution against a real
model surfaced a genuine bug — a prompt ending its message sequence on
the wrong kind of turn — that no amount of research, static analysis,
or pure-Python simulation could have caught on its own. That bug, the
debugging process that found it, and the fix are covered in detail
below, because the general lesson it teaches is worth more than the
specific line of code it happened to be in.

And today is the last day this project gets new code at all. Every
prior day's build made something new; today's two additions round the
whole thing out into a shape stable enough to build on for the rest of
this material without touching this codebase again. What comes next is
covered briefly at the end of these notes.

---

## Deep Dive: From Three Function Calls to One Composed Chain

- **Yesterday's grounded-answer function called retrieval, formatting,
  and generation as three separate statements, on purpose — that
  choice is exactly what today's chain replaces.** The reasoning at
  the time was sound: composing a plain Python function into an LCEL
  chain with `|` requires wrapping it as a `Runnable` first, and
  reaching for that wrapping before there was an actual reason to need
  it would have been solving a problem that didn't exist yet.
  Conversation memory is that reason. Threading a summary and a list
  of recent messages through three separately-called functions by hand
  gets unwieldy fast in a way that a properly composed chain doesn't —
  so the formalization that was previewed as "planned future work" is
  exactly what happened today, sequenced to arrive precisely when it
  was actually needed.
- **`RunnablePassthrough.assign(...)` is the specific tool that makes
  this composition possible without a `RunnableLambda` wrapper
  anywhere.** Each call to `.assign(...)` takes the dict flowing
  through the chain so far and returns a *new* dict with one or more
  additional keys merged in — never replacing what was already there,
  only adding to it. Three calls chained together with `|` — one
  assigning `documents`, one assigning `context`, one assigning
  `answer` — mean every later stage can see everything every earlier
  stage already produced, without any stage needing to explicitly pass
  data forward itself.
- **The values handed to `.assign(...)` can be plain Python callables,
  not just `Runnable` objects — and that's a genuine convenience, not
  a shortcut that quietly hides something important.** `_retrieve` is
  an ordinary function; the context-building step is an ordinary
  `lambda`. Neither needed wrapping in a `RunnableLambda(...)` the way
  composing directly with `|` would have required, because
  `.assign(...)`'s own keyword arguments coerce a plain callable
  automatically. This resolves something left open earlier: LCEL's `|`
  operator itself does need that explicit wrapping step, but
  `.assign(...)` is a different entry point into the same ecosystem,
  with a more forgiving contract.
- **Calling `retrieval_chain.invoke(...)` returns a dict, not just an
  answer string — and that's the entire point of building it this
  way.** The result carries every key accumulated along the way:
  the original inputs, plus `documents`, `context`, and finally
  `answer`. Retrieved documents being right there in the result, with
  no separate variable ever having to capture them along the way, is
  what makes building a citation list from the *same* invocation this
  cheap.

---

## Deep Dive: Two Prompts, Not One

- **A second, separate prompt was built for history-aware answering,
  rather than adding optional history fields onto yesterday's
  existing prompt.** It would have been technically possible to add a
  `{summary}` reference and a `MessagesPlaceholder` to the original
  prompt and try to make both conditional. It would have been the
  wrong call: yesterday's grounded-answer function and its
  strict-threshold sibling both still call their chain with only
  `{context, question}` — no summary, no recent turns — and neither of
  them owns or wants conversation state. A `{summary}` reference in a
  system message is a required substitution once it's there; there's
  no clean way to make it silently optional without extra handling
  either way.
- **Two small, single-purpose prompts are more honest than one prompt
  serving two jobs with conditional logic bolted on.** One prompt
  stays exactly as simple as a single-turn grounded answer needs to
  be; the other explicitly carries a running summary and a
  placeholder for recent raw turns, because that's specifically what
  it's for. Neither one has to apologize for fields the other doesn't
  use. This is the same instinct that's shown up repeatedly this
  week whenever a new capability needed a new prompt or chain instead
  of a mutation of an existing one: new, separate, additive, rather
  than editing shared code out from under callers that don't need the
  change.

---

## Deep Dive: Summarizing Memory — What Gets Kept Raw, and What Gets Folded

- **Conversation memory here means two things living side by side: a
  short buffer of the most recent raw turns, and a running summary of
  everything older than that.** A pure "keep everything, forever"
  approach would let a long conversation's history grow without
  bound, getting more expensive — and eventually impossible — to
  re-send on every single question. A pure "summarize everything,
  always" approach would lose the exact wording of a question asked
  just a moment ago, right when a natural follow-up is most likely to
  depend on that exact wording. Keeping a small number of full, raw
  turns while folding anything older into a running summary is a
  middle ground that keeps recent context precise and older context
  merely present, rather than either unbounded or immediately lossy.
- **The threshold controlling how much stays raw is a real, tunable
  design choice, not an arbitrary number.** Two full question/answer
  pairs staying available verbatim means a follow-up almost always
  benefits from seeing the exact original wording of the last couple
  of exchanges. Once a third pair would push past that limit, the
  *oldest* pair — never the newest — gets folded into the summary and
  dropped from the raw list. A real system would tune this number
  against real conversation patterns and real cost pressure; today's
  value is small enough to demonstrate and observe easily, the same
  "small on purpose, for demonstration" reasoning already applied to a
  retrieval parameter's default earlier this week.
- **Each summarization call is handed the existing summary as an
  input, not just the new turns to fold in — so a summary keeps
  building on itself instead of getting replaced.** Without that,
  every time the buffer filled up again, the previous summary would
  simply be thrown away and replaced with a summary of only the
  *newest* overflow — silently losing anything the first summary had
  already captured. Passing the existing summary back in every time
  means the second summarization is really "update what's already
  known," not "start over and forget everything before this point."
- **The summarization step reuses the same chat model instance already
  used for grounded answering, not a third dedicated one.**
  Summarizing faithfully is the same kind of low-variance,
  low-creativity task grounded answering already is — both want the
  model reproducing what it was given accurately, not adding
  conversational flourish. Reaching for the already-tuned instance
  here is consistent with a pattern already established: a dedicated
  instance gets built when a use case's needs genuinely differ, not
  by default for every new chain that happens to need a model.

---

## Deep Dive: The Real Gotcha — a `MessagesPlaceholder` Ending on the Wrong Kind of Turn

This is worth its own deep dive, separate from the general
summarization discussion above, because of *how* it was found: not by
research, not by reading documentation, not by any static check this
project's own verification habits could run — but by an instructor
actually running the code against a real model and noticing the output
looked wrong.

- **The bug:** the summarization prompt originally ended immediately
  after its `MessagesPlaceholder` for the turns being folded in, with
  no message after it. Since that placeholder is always filled with a
  human/AI pair — a question and its answer — the very last message
  the model actually saw, right before being asked to respond, was an
  **AI message**: the assistant's own prior turn, not a human one.
- **Why that matters to a chat model specifically.** Most chat models
  are trained to expect a conversation to end on a human turn — that's
  the model's cue that it's now its turn to generate something new.
  Ending on an AI message instead is genuinely ambiguous input, not a
  cosmetic imperfection. And ambiguous input to a language model
  doesn't fail loudly or consistently the way a type error or a
  missing argument would — it produces *inconsistent* behavior, which
  is exactly what showed up in practice: on one real run, the model
  produced what read like a direct continuation of its own earlier
  answer, picking up mid-thought as if it were still writing that
  earlier message. On another turn in that same run, it returned a
  completely empty string. No exception, no warning, nothing pointing
  at the cause — just quietly wrong or missing output.
- **How this was actually diagnosed — worth walking through, because
  the process generalizes beyond this one bug.** The first symptom
  reported was simply "the summary shows content on one turn but
  nothing on two others." The control-flow logic deciding *when* to
  summarize had already been proven correct through direct execution
  of a stand-in simulation — so the trigger logic itself wasn't a
  suspect. That narrowed the question to what the summarization call
  itself was actually producing. The next step was targeted
  instrumentation: a debug print showing exactly what went *into* the
  summarization call and exactly what came *out* of it, raw, before
  anything else touched it. That single piece of evidence — a
  non-empty but clearly continuation-like string on one turn, and a
  genuinely empty string on another — was what turned "something's
  wrong somewhere in summarization" into "the model itself is
  returning bad output," which pointed straight at the prompt's
  message shape rather than the surrounding Python logic.
- **The fix, and why it worked.** A working sibling prompt already
  existed in the very same file: the history-aware answering prompt
  from earlier in this same stretch of work already ended on an
  explicit trailing human message *after* its own `MessagesPlaceholder`
  — and it never showed this problem. Giving the summarization prompt
  that identical shape — an explicit `("human", "...")` message
  directly asking for the summary, placed after the placeholder —
  gave the model an unambiguous "respond now" cue every time,
  regardless of what kind of message happened to land last inside the
  placeholder itself. After this fix, a second, smaller issue
  surfaced: the model sometimes narrated *about* the summarization
  task itself ("there is no existing summary to build on...") instead
  of just writing the summary. A small addition to the system
  message — explicitly instructing the model to write only the
  summary itself, and not comment on whether one already existed —
  resolved that too, confirmed by a second real run producing clean
  output.
- **The lesson generalizes well past this one prompt.** Any prompt
  built from a `MessagesPlaceholder` filled with a raw list of
  human/AI message pairs needs to end on a human turn before the model
  is asked to respond — never assume that whatever happens to be last
  inside the placeholder will be the right kind of message to end on.
  This is a category of bug that's specific to working with real
  generative models: it isn't a syntax error, a type error, or a logic
  error in the ordinary sense — the code runs, and produces *some*
  output, just not reliably the right output. Research, careful
  reading, and even direct source inspection can confirm a chain is
  built correctly in every mechanical sense while still missing a
  defect like this one entirely, because the defect only exists in how
  a trained model responds to a particular shape of input. This is
  exactly why running real code against a real model, whenever that's
  possible, catches an entire category of problem that no other
  verification method available this term can.

---

## Worth Knowing: Why This Memory Pattern Is Hand-Built, Not a LangChain Memory Class

- **LangChain has shipped, and then moved away from, more than one
  "official" way to add memory to a chain.** An earlier generation of
  dedicated memory classes — a buffer-based one, and summary-based
  variants — has been relocated entirely to a separate,
  legacy-labeled package, the same relocation a few other
  now-superseded classes went through earlier this week. Their
  successor, a wrapper that added message history to an existing
  chain, is *itself* now deprecated in current LangChain, with a
  direct warning pointing away from it and toward LangGraph's own
  persistence mechanism instead, and a scheduled removal in a future
  version.
- **Current official documentation for summarizing memory specifically
  shows exactly one path, and it isn't the one used here.** That path
  wires a dedicated summarization component into an *agent*, backed by
  a graph-based persistence layer — a meaningfully heavier piece of
  infrastructure than anything built so far. There is currently no
  documented, non-legacy way to get summarizing conversation memory
  without adopting that heavier infrastructure.
- **That heavier infrastructure is deliberately out of scope for this
  stretch of the project — it gets covered later, as a concept, not as
  code.** So what got built today is an honest, capable pattern
  assembled entirely from pieces already covered: a prompt, a chat
  model, an output parser, and a plain Python dataclass holding state.
  It is not the currently "blessed" path through the ecosystem, and
  that's worth being direct about rather than presenting a hand-rolled
  pattern as if it were the industry-standard one. It works, it's
  simple enough to fully understand end to end, and it does everything
  this project actually needs — but a real production system reaching
  for durable, multi-process-safe conversation memory today would most
  likely be pointed toward that graph-based approach instead, not this
  one.
- **This is a useful, general lesson about working in a fast-moving
  ecosystem, independent of memory specifically.** "The officially
  recommended way to do X" is a moving target in a library under this
  much active development — something that was the documented,
  standard approach two versions ago can be deprecated, relocated, or
  quietly superseded by the next one. Building something correct and
  well-understood from stable primitives is a legitimate response to
  that instability, as long as it's framed honestly as exactly that,
  rather than mistaken for "the current best practice."

---

## Architectural Analysis: One Conversation's Path Across Several Turns

Tracing a multi-turn conversation through today's pieces, from the
first question to the fourth:

1. A caller creates one piece of state — a summary starting empty, and
   an empty list of recent messages — and holds onto it across every
   turn of one conversation. Nothing about this state lives anywhere
   but in that caller's own memory for as long as the process runs.
2. On the first question, that state (empty summary, empty recent
   messages) is handed into the composed chain alongside the question
   itself. Retrieval, formatting, and generation happen exactly as
   they would for a single, memory-free question, because there's
   nothing yet for the model to build on.
3. After the chain returns its answer, that turn's question and answer
   get appended to the raw message list. Two messages now sit in raw
   form — well under the threshold that would trigger folding anything
   into a summary.
4. The second question repeats this: the chain runs (now with two raw
   messages already available to the model, though still an empty
   summary, since nothing has crossed the threshold yet), and its
   turn's question and answer get appended, bringing the raw list to
   four messages — right at the threshold, but not yet past it.
5. The third question is where the buffer actually overflows: after
   this turn's messages are appended, the raw list would hold six
   messages, past the four-message limit. The oldest pair — the very
   first question and its answer — gets folded into a summary and
   removed from the raw list, which settles back down to four: the
   third turn's two messages, plus the second turn's two messages.
6. The fourth question repeats step 5's pattern: the second turn's pair
   now becomes the oldest and gets folded into the summary — which
   already has the first turn's content in it — extending it rather
   than replacing it, while the raw list settles back to four messages
   again: the third and fourth turns.
7. At every step, the model actually answering a question sees three
   distinct kinds of context at once: the freshly retrieved document
   chunks for *this* question, the handful of most recent raw turns
   verbatim, and a running summary of anything older than that. None
   of the three replaces either of the others — they're three
   different windows onto what's relevant, at three different levels
   of detail and recency.

A question worth sitting with: what would happen to a follow-up
question if the raw-message threshold were set to zero — that is, if
every turn were folded into the summary immediately, with nothing ever
kept verbatim? The answer isn't obviously catastrophic, but it is a
real, tangible loss: a follow-up that hinges on the *exact wording* of
the immediately preceding question or answer would only ever see a
paraphrased summary of it, not the original phrasing — sometimes
enough, sometimes not, depending entirely on how much a summary
happens to compress. That's the concrete reason a threshold above zero
exists at all, rather than summarizing unconditionally from the very
first turn.

---

## Looking Ahead: The Last Code This Project Gets

Everything built up to and including today forms the complete DevMate
codebase this project ends up with — nothing after this adds a new
file, a new function, or a new dependency to it. What comes next
covers real, substantial territory — agent-based reasoning, modeling
that reasoning explicitly as an inspectable graph, and a standard
protocol for exposing tools to other systems — but it does so entirely
through discussion and diagramming against the application exactly as
it stands right now, not by writing more of it.

That's a deliberate scoping decision, not an afterthought: everything
built across this stretch of work was chosen specifically so it could
be fully built, run, and understood using only free, self-hosted
tooling, and specifically so each new piece rested on primitives
already covered rather than introducing an entirely new paradigm every
single day. The topics still ahead genuinely do require a different
paradigm — reasoning about a system that plans and acts, not just one
that answers a single question — and that shift is exactly why they're
better taught as concepts against a finished, working example than as
more code bolted onto a codebase that was never designed to grow in
that direction. The RAG-and-chains foundation this project now has,
solid and fully understood end to end, is precisely what makes those
later, more abstract discussions concrete instead of hypothetical.

---

## Quiz-Prep Quick Reference

| Term | One-line definition |
|---|---|
| `RunnablePassthrough.assign(...)` | Merges new key(s) into the existing input dict flowing through a chain, without replacing what's already there |
| Why no `RunnableLambda` today | `.assign(...)`'s keyword arguments coerce a plain callable automatically — only composing directly with `\|` requires the explicit wrapper |
| `retrieval_chain.invoke(...)`'s return value | A dict carrying every accumulated key (inputs plus `documents`, `context`, `answer`) — not just the final answer string |
| Why two separate prompts | A shared prompt would force `answer_question`/`answer_question_strict` to pass summary/history fields they don't have or want |
| `MAX_RECENT_MESSAGES` | The number of raw messages kept verbatim before the oldest turn gets folded into the running summary — small here, tunable in a real system |
| Existing-summary threading | Every summarization call receives the prior summary as input, so each one builds on the last instead of replacing it |
| The `MessagesPlaceholder` gotcha | A prompt ending on an AI message (not a human one) right before generation is ambiguous to a chat model and produces inconsistent real output |
| Why this bug wasn't caught by research or static checks | It's a defect in how a trained model responds to a message shape — only observable by running real code against a real model |
| `RunnableWithMessageHistory` | LangChain's own prior "official" memory wrapper — now itself deprecated, pointing users toward LangGraph-based persistence instead |
| Why this project's memory is hand-built | The current documented, non-legacy path to summarizing memory requires LangGraph, which is deliberately out of scope for this stretch |

---

## Common Pitfalls & Anti-Patterns

- **Composing a plain function into LCEL with `\|` and forgetting it
  needs an explicit `RunnableLambda(...)` wrapper first** — a mistake
  easy to make specifically *because* `RunnablePassthrough.assign(...)`
  doesn't need that same wrapping for its own keyword arguments; the
  two entry points into LCEL have different rules for what counts as
  composable.
- **Building a `MessagesPlaceholder`-based prompt and assuming whatever
  ends up last inside the placeholder will be fine to end on** — it
  won't always be. Any such prompt needs an explicit trailing human
  message after the placeholder, regardless of what the placeholder
  itself happens to be filled with on a given call.
- **Treating "the code runs and returns something" as proof a
  generative-model-backed chain is correct** — a chain can produce
  fluent, plausible-looking output while still being subtly, silently
  wrong, in a way that only shows up as inconsistent behavior across
  multiple real runs, not as an error the first time it's tried.
- **Replacing an existing summary outright instead of threading it
  into the next summarization call** — silently discards everything
  the summary had already captured the moment a second round of
  folding happens, defeating the entire point of building on
  conversation history progressively.
- **Reaching for a legacy or deprecated LangChain memory class because
  it still technically works today** — it may run without error right
  now, but it's explicitly slated for removal, and building on it
  means inheriting a migration that will eventually be required
  anyway.
- **Presenting a hand-built pattern as "the standard way to do this"**
  — when the ecosystem's own current documentation actually
  recommends something different (here, a graph-based approach), the
  honest framing is "a capable pattern built from stable primitives,"
  not "the way it's supposed to be done."
- **Assuming a threshold like `MAX_RECENT_MESSAGES` is an arbitrary
  number not worth thinking about** — it's a real tradeoff between
  how much verbatim recency a follow-up question can rely on and how
  much raw history has to be re-sent on every call; a real system
  would tune it deliberately, not leave it at whatever value happened
  to be convenient for a demo.

---

## Troubleshooting Guide

| Symptom | Likely Cause | Fix |
|---|---|---|
| A summarization call sometimes returns a garbled continuation of a prior answer | The prompt's message sequence ends on an AI turn instead of a human one | Add an explicit trailing human message after any `MessagesPlaceholder` filled with human/AI pairs |
| A summarization call sometimes returns an empty string with no error | Same root cause as above — ambiguous "who should respond" cue to the model | Same fix — an explicit trailing human message removes the ambiguity |
| A summary narrates about the summarization task itself instead of just summarizing | The system prompt doesn't explicitly forbid commenting on the instructions or on whether a summary already existed | Add an explicit instruction to write only the summary itself, nothing else |
| A later summary appears to have completely forgotten something an earlier summary captured | The existing summary wasn't passed into the next summarization call, so it was replaced rather than built on | Always pass `memory.summary` into the summarization call as the existing-summary input, every time |
| `retrieval_chain.invoke(...)`'s result is missing a key a later step expects | An `.assign(...)` step's key name doesn't match what a later step reads from the dict | Check that each `.assign(key=...)` call's key name matches exactly what downstream code reads via that name |
| A composed chain raises an error about an object not being callable or composable | A plain function was passed directly to `\|` instead of to `.assign(...)`, without a `RunnableLambda(...)` wrapper | Either wrap the function explicitly for `\|` composition, or restructure the step as an `.assign(...)` call instead |
| Conversation memory grows without bound across a very long conversation | Nothing here caps the running summary's own size — only the raw message list is capped | Expected at this stage; periodically re-summarizing the summary itself is a real technique worth researching further, not yet implemented here |
| A supposedly memory-aware endpoint doesn't remember anything between requests | Each request built a brand-new state object instead of reusing the same one keyed by a stable identifier | Confirm state is looked up and reused by a stable id, not recreated fresh on every call |

---
*DevMate — Northbeam Engineering Assistant — Notes: Formalizing Retrieval into an LCEL Chain, and Summarizing Conversation Memory*

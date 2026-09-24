# DevMate Notes
## Topic: Retrievers, MMR, and Confidence-Threshold Filtering

---

## Executive Summary

The last piece of work left a searchable, persisted vector store and
nothing more: `search_documents` could find the closest chunks to a
query, but every caller had to know Chroma's own method names
(`.similarity_search(...)`, `filter=`) to use it. Today's work wraps
that store in LangChain's **retriever** abstraction — a standardized,
swappable interface that any LangChain-aware code can call the same
way, `.invoke(query)`, regardless of which vector database sits behind
it. On top of that abstraction, today also covers *how* a retriever
decides which results come back: plain nearest-neighbor similarity
isn't the only option. **MMR (Maximal Marginal Relevance)** re-ranks
results to avoid near-duplicates crowding out genuinely different
matches, and **confidence-threshold filtering** returns fewer than *k*
results — including zero — when nothing in the corpus is actually a
good match, rather than always forcing exactly *k* results regardless
of quality.

Nothing today calls an LLM. The output is a configurable retriever and
a citation-ready context string — exactly the shape a prompt will need
to answer a question grounded in real documents, still one step away.

---

## Deep Dive: The Retriever Abstraction

- **What `as_retriever()` actually is, and why it exists at all.**
  `as_retriever()` is a method defined once on `langchain_core`'s base
  vector store class, inherited by every vector store integration —
  Chroma included — with zero extra code required on this project's
  side. Calling `vector_store.as_retriever(...)` doesn't create a new
  index or touch the data; it returns a `VectorStoreRetriever` object
  that wraps the *same* underlying vector store and just standardizes
  how it gets called. The entire point: code written against a
  retriever doesn't know or care that Chroma is underneath. Swapping in
  a different vector database later — Postgres with `pgvector`, a
  hosted service, anything else `langchain_core` has an integration
  for — would mean changing what's inside `get_similarity_retriever`
  and its siblings, not every place downstream that calls them. That's
  a meaningfully different design than calling `.similarity_search(...)`
  directly, which is exactly what yesterday's `search_documents` did
  and exactly why today introduces this new layer on top of it rather
  than replacing it.
- **A retriever is a `Runnable`, which is what makes it fit into
  everything else built this week.** Like a prompt template or a chat
  model, a `VectorStoreRetriever` implements the same `Runnable`
  interface — it can be called with `.invoke(query)`, and it composes
  into an LCEL chain with the `|` operator exactly the way a prompt or
  an LLM does. This isn't a coincidence or a nice-to-have: it's the
  entire reason a retriever gets built as its own piece today, separate
  from any prompt or LLM call — a future chain can slot it in with
  `|` once there's a prompt on the other side of it, without the
  retriever itself needing to know that chain exists yet.
- **`.invoke(query)` is the only current, correct way to call a
  retriever — and this is a real, current gotcha, not a hypothetical
  one.** Older material, and older versions of this same ecosystem,
  called `.get_relevant_documents(query)` instead. That method has been
  **removed entirely** from the current `langchain-core` — not merely
  deprecated with a warning, the way a softer transition might work.
  Code copied from an older tutorial that still calls it fails with an
  `AttributeError`, the exact same "the library moved, the old pattern
  still gets suggested by search results and old blog posts" shape
  already seen with Chroma's own `.persist()` removal. Anywhere a
  retriever needs to be called from here forward, `.invoke(...)` is the
  only spelling to reach for.
- **A retriever's job ends at returning documents — nothing about
  formatting, ranking philosophy, or prompt-shaping lives inside it.**
  Every retriever built today returns the same thing: a plain
  `list[LCDocument]`. What differs between them is entirely *how* that
  list gets chosen — closest-first, re-ranked for diversity, or
  filtered by a confidence floor — never the shape of what comes back.
  That consistency is what lets one formatting function
  (`format_retrieved_context`, covered below) work identically
  regardless of which retriever produced the list it's handed.

---

## Deep Dive: The Three Search Types

- **`search_type` accepts exactly three string values, and validation
  is strict.** `"similarity"` (the default, plain nearest-neighbor),
  `"mmr"` (re-ranked for diversity), and `"similarity_score_threshold"`
  (filtered by a minimum confidence floor) — and nothing else.
  Confirmed directly against `VectorStoreRetriever`'s current source: a
  Pydantic validator runs *before* the retriever is even constructed,
  checking `search_type` against exactly those three allowed values and
  raising a `ValueError` immediately for anything else — a typo like
  `search_type="threshold"` fails loudly at construction time, not
  silently at query time with some default behavior standing in for
  what was actually meant.
- **Each search type expects a different shape of `search_kwargs`, and
  mixing them up produces real, distinct failure modes:**
  - `"similarity"` — `k` (how many results, default 4) and, optionally,
    `filter` (a metadata filter dict, omitted entirely rather than
    passed as `None` when no filtering is wanted, mirroring
    `search_documents`'s own established rule).
  - `"mmr"` — `k`, `fetch_k` (how many candidates to pull before
    re-ranking, default 20), and `lambda_mult` (the diversity/relevance
    dial, default 0.5).
  - `"similarity_score_threshold"` — `score_threshold` (**required**,
    no default — omitting it raises at construction) and, optionally,
    `k` as an upper bound on how many results can come back even if
    more chunks clear the threshold.
  Passing `fetch_k` to a `"similarity"` retriever, or omitting
  `score_threshold` from a `"similarity_score_threshold"` one, are both
  realistic mistakes worth watching for — the second one is explicitly
  the failure mode the challenge's own Constraints section asks to be
  left alone rather than caught and suppressed.
- **Each search type dispatches internally to a different underlying
  vector store method** — this is worth knowing as a mental model, not
  just a syntax table. `"similarity"` calls `.similarity_search(...)`
  under the hood (the exact method `search_documents` already calls
  directly); `"similarity_score_threshold"` calls
  `.similarity_search_with_relevance_scores(...)`, a method introduced
  in the notes on distance vs. relevance scores below; `"mmr"` calls a
  dedicated `.max_marginal_relevance_search(...)` method that performs
  its own two-phase candidate-pull-then-re-rank internally. A retriever
  is, in every real sense, just a thin, standardized dispatcher over
  methods that already existed on the vector store itself.

---

## Deep Dive: MMR (Maximal Marginal Relevance)

- **The specific problem MMR solves, stated plainly.** Plain similarity
  search always returns the *k* vectors closest to the query, full
  stop — if the five closest chunks in an entire corpus all happen to
  express roughly the same idea in slightly different words, that's
  exactly what comes back, even though a human skimming the results
  would almost certainly prefer some variety. MMR exists specifically
  to counter this: it's a **re-ranking** step, not an alternative
  distance metric.
- **The two-phase mechanism.** First, MMR pulls a larger candidate pool
  of `fetch_k` results using ordinary similarity search (20 by
  default) — this phase is identical in kind to what
  `get_similarity_retriever` already does, just with a larger `k`.
  Second, it greedily builds the final list of `k` results one at a
  time, at each step picking whichever remaining candidate best
  balances two competing scores: how relevant it is to the original
  query, and how *dissimilar* it is to results already selected. A
  candidate that's highly relevant but nearly identical to something
  already picked can lose out to a candidate that's slightly less
  relevant but meaningfully different — that trade-off is the entire
  mechanism.
- **`lambda_mult` is the dial that controls the trade-off, and both
  ends of its range are worth knowing by name.** `lambda_mult=1.0`
  collapses MMR back to plain relevance ranking — minimum diversity,
  identical in spirit to `"similarity"` search. `lambda_mult=0.0`
  maximizes diversity at the expense of pure relevance, willing to pick
  a much weaker match purely because it's different from what's
  already selected. `0.5`, the default, splits the difference. There is
  no universally "correct" value — it's a genuine product decision
  about what a downstream use case actually wants more of.
- **A specific, verified fact about this project's own data that
  changes what MMR can actually demonstrate right now.** This project's
  real document corpus currently has exactly 5 chunks total — fewer
  than `fetch_k`'s default of 20. That means, for this project's data
  specifically, MMR's initial candidate pool is simply *every chunk
  that exists in the entire store* — there's no meaningfully larger
  pool being filtered down the way there would be against a real,
  much-larger corpus with hundreds or thousands of chunks. The
  re-ranking logic still runs, and still runs correctly, but a small
  corpus like this one won't show a dramatic before/after diversity
  difference the way a large one would. Don't read too much into two
  results swapping order, or not swapping order, on a dataset this
  size — the mechanism being correct is what matters at this scale, not
  a dramatic visible effect.
- **MMR is not "better" than plain similarity search in some absolute
  sense — it answers a different question.** Plain similarity search
  answers "what's most relevant." MMR answers "what's a useful,
  non-redundant set of relevant results." For a query where the corpus
  genuinely only has one relevant angle, MMR has nothing meaningful to
  diversify against and will tend to converge toward the same results
  plain similarity search would already return — which is exactly the
  expected, correct behavior in that situation, not a sign that MMR
  "isn't doing anything."

---

## Deep Dive: Confidence Thresholds and the Distance-vs-Relevance Gotcha

- **The problem confidence thresholds solve.** Both plain similarity
  search and MMR share one property: they always return exactly *k*
  results, no matter how weak the worst of those matches actually is.
  If a query has no good answer anywhere in the corpus, a `k=4`
  similarity search still confidently hands back 4 results — just the
  4 least-bad ones. `search_type="similarity_score_threshold"` is the
  tool for a different question: "only give me results I'm actually
  confident about, and tell me honestly when there aren't any."
- **A real, easy-to-get-backwards distinction: relevance score and raw
  distance are not the same number, and are not even on the same
  scale.** A separate method covered when the store was first queried,
  `.similarity_search_with_score(...)`, returns a raw distance where
  **lower** means more similar. `similarity_score_threshold` filters
  against something different entirely — a **relevance score**, on a
  documented 0–1 scale where a value closer to `1.0` means *more*
  similar — produced internally by
  `.similarity_search_with_relevance_scores(...)`. Treating these two
  numbers as interchangeable, or assuming a `score_threshold` of `0.3`
  means "distance under `0.3`," produces exactly backwards filtering:
  a threshold meant to be lenient would behave as if it were strict, or
  vice versa, depending on which scale got assumed.
- **How that conversion actually works for this project's default (L2)
  Chroma collection — verified directly against the current library
  source, and worth knowing as a real, documented limitation rather
  than a clean guarantee.** For a collection using the L2 (squared
  Euclidean) space, the underlying relevance-score function converts a
  raw distance into a 0–1 score using the formula `1.0 - distance /
  sqrt(2)`. That formula is real and does exist in the current source
  — but its own accompanying comment is explicit that it's a
  **heuristic**, not a rigorous, universally-correct transform: it
  assumes the distance being converted is a plain (non-squared)
  Euclidean norm between *unit-normalized* embedding vectors, ranging
  from `0` (identical) to `sqrt(2)` (maximally dissimilar). Chroma's
  own default `l2` space, however, is documented as **squared**
  Euclidean distance, not the plain norm this formula assumes — a real
  mismatch, not a hypothetical edge case, and one confirmed by a
  still-open issue in LangChain's own tracker describing exactly this
  formula producing out-of-range or negative "relevance scores" for
  Chroma and FAISS collections under real conditions. **The honest
  takeaway: on this project's default-configured collection, a
  `similarity_score_threshold` retriever's scores should be treated as
  an approximate, directionally-correct signal — higher genuinely means
  more similar — but not as a precisely calibrated 0–1 probability a
  specific numeric cutoff can be reasoned about with confidence.** A
  Chroma collection explicitly configured for `cosine` space instead
  uses a cleaner, exact formula (`1.0 - distance`, with no
  normalization assumptions baked in) — worth knowing as the more
  threshold-friendly configuration choice for anywhere confidence
  filtering is actually load-bearing in production, versus this
  project's default, which prioritizes matching yesterday's already-
  established L2 behavior over threshold-filtering precision.
- **What actually happens when nothing clears the threshold — verified
  directly against current source, not assumed.** A `score_threshold`
  strict enough that zero chunks clear it does **not** raise an
  exception. The underlying implementation is a plain list
  comprehension that filters out anything below the threshold, followed
  by a logged warning when the result is empty — `.invoke(query)`
  simply returns an empty list, `[]`. This matters directly for how any
  code calling a threshold retriever needs to be written: checking
  `if not results:` is the correct, expected way to detect "nothing
  confident enough was found," not a `try`/`except` block — there is no
  exception to catch here, and wrapping the call in one anyway would
  silently hide a real, different kind of failure (a genuine connection
  or configuration error) behind the same handling meant for a
  perfectly normal "no good match" outcome.
- **A threshold tuned against a tiny corpus is not the same threshold a
  large corpus needs.** With only a handful of chunks in the entire
  store, the *worst* result among the top few is often still a
  reasonably close match purely because there's so little competing
  content — a threshold that looks appropriately strict against five
  chunks may turn out to be far too lenient once a corpus grows to
  thousands of chunks covering many more topics, where genuinely
  irrelevant content becomes much easier to retrieve accidentally.
  There's no single "correct" default value quotable independent of a
  corpus's actual size and topic diversity — it's a value worth
  revisiting as a corpus grows, not a constant to set once and forget.

---

## Deep Dive: `format_retrieved_context` and Separation of Concerns

- **Why formatting is its own function, not folded into the
  retriever.** A retriever's contract ends at "return the relevant
  `LCDocument` objects" — it has no opinion about how those objects
  should look once they're inside a prompt. `format_retrieved_context`
  is the missing translation step: it turns a `list[LCDocument]` into
  one plain string, labeling each chunk by the document title it came
  from, in exactly the shape a prompt template will need for its
  context variable. Keeping this separate from both the retriever
  itself and from whatever prompt code comes next keeps each piece
  independently testable — a habit already established the first time
  the vector-store module's own docstring drew the same kind of line
  between ingestion and querying.
- **This function works identically regardless of which retriever
  produced its input.** Because every retriever built today returns
  the same `list[LCDocument]` shape, `format_retrieved_context` never
  needs to know or care whether it's formatting results from plain
  similarity search, MMR, or a threshold-filtered search — including
  the specific case of formatting an *empty* list, which simply
  produces an empty string rather than an error. That's a direct,
  practical consequence of the retriever abstraction paying off: one
  formatting function, reusable against every retrieval strategy this
  project has built or will build.

---

## Worth Knowing: Why This Project's Retriever Code Isn't "Legacy" LangChain

- **The ecosystem context worth understanding, even though nothing
  about today's code needs to change because of it.** LangChain
  reached a 1.0 stable release, and the broader package restructured
  substantially around that milestone: older convenience chains
  (`LLMChain`, already encountered as a removed pattern earlier this
  week) and older retriever *wrapper* classes that used to live in
  `langchain.retrievers` — things like `MultiQueryRetriever` and
  `EnsembleRetriever` — moved out into a separate `langchain-classic`
  package, a deliberate signal that they're considered legacy relative
  to the current recommended patterns, even though they still work.
- **What's explicitly unaffected by that split, confirmed directly
  against current source: `VectorStoreRetriever` and `as_retriever()`
  itself.** Both live in `langchain_core`, not the classic package, and
  neither has changed shape since the 1.0 release — the same three
  `search_type` values, validated the same strict way, are still
  exactly current. Everything built today is built on the
  actively-maintained, current layer of the library, not a pattern on
  its way out.
- **Worth knowing as an honest caveat, not a contradiction of the
  above: LangChain's own current flagship RAG documentation now leads
  with agent- and tool-based retrieval** — wiring a retriever up as a
  tool an LLM agent decides whether and when to call, rather than
  always running it as a fixed step in a hand-assembled chain — over
  the classic LCEL pattern of manually composing a retriever, a prompt,
  and a model with `|`. That doesn't mean the LCEL pattern is
  deprecated or going away; it's still fully functional, fully current,
  and exactly the layer this project deliberately continues building
  on for now. Agent-based retrieval sits conceptually one level above
  everything covered today, and is intentionally reserved as later,
  concept-only material rather than something built into working code
  at this stage of the project.
- **A specific, narrower gap worth knowing about rather than assuming
  away: not every vector store integration supports
  `similarity_score_threshold` equally well.** At least one other
  vector store integration in the current ecosystem has a known,
  open gap where it doesn't implement the relevance-score function
  `similarity_score_threshold` depends on internally, and raises
  `NotImplementedError` rather than silently falling back to something
  else. Chroma isn't affected by that particular gap — but it's a good
  reminder that "the retriever abstraction is standardized" doesn't
  automatically mean "every search type behaves identically well across
  every vector store backend." The abstraction standardizes the
  *interface*; the underlying implementation quality still varies by
  integration.

---

## Architectural Analysis: One Query's Path Through Three Retrievers

Tracing the same query — "What should I do first when a P1 incident
starts?" — through all three retrieval strategies built today:

1. `load_vector_store()` reopens the already-persisted collection —
   identical first step for all three retriever functions, and the
   same non-negotiable "never rebuild just to search" discipline
   established the first time a query-only function was written
   against this store.
2. **Similarity path:** `get_similarity_retriever(k=3)` wraps the store
   with `search_type="similarity"`. `.invoke(query)` embeds the query
   with the same embedding model every chunk was originally embedded
   with, asks the store's nearest-neighbor index for the 3 closest
   chunks by raw distance, and returns them in closest-first order —
   no re-ranking, no filtering beyond `k`.
3. **MMR path:** `get_diverse_retriever(k=3)` wraps the same store with
   `search_type="mmr"`. Internally, this pulls a candidate pool (in
   this project's case, effectively the entire 5-chunk corpus, since
   `fetch_k`'s default of 20 exceeds it), then greedily re-ranks that
   pool down to 3 results balancing relevance against difference from
   results already chosen. The single closest chunk tends to come back
   first in both paths — the same chunk is still the closest chunk
   regardless of which strategy builds the rest of the list — but
   membership or ordering among the remaining results can differ.
4. **Threshold path:** `get_threshold_retriever(score_threshold=...)`
   wraps the same store with `search_type="similarity_score_threshold"`.
   Internally, this calls a method that computes a normalized 0–1
   relevance score for every candidate, keeps only the ones meeting or
   exceeding `score_threshold`, and returns however many chunks
   actually cleared that bar — anywhere from `0` up to `k`, with no
   guarantee of hitting `k` the way the other two paths always do.
5. In every path, the result is the same shape: a plain
   `list[LCDocument]`, ready to be handed to `format_retrieved_context`
   without that function needing to know which of the three paths
   produced it.
6. What comes after step 5 — assembling that formatted context into an
   actual prompt, calling an LLM with it, and returning a grounded
   answer with citations — is still ahead. Every retriever built here
   answers "what's relevant," never "what's the answer."

A question worth sitting with: which of these three retrievers would
be the right default for a real `/ask` endpoint answering questions
from actual engineers? The honest answer is "probably not a single
fixed choice" — plain similarity search is the simplest and often
good enough; MMR earns its cost specifically when a corpus has genuine
topical redundancy worth diversifying against; a threshold retriever
earns its cost specifically when silently returning weak, low-confidence
results is worse than honestly returning nothing. A real system might
reasonably use different strategies for different kinds of questions,
rather than picking one retriever and using it everywhere.

---

## Quiz-Prep Quick Reference

| Term | One-line definition |
|---|---|
| `as_retriever()` | Method on the base vector store class returning a `VectorStoreRetriever` — a standardized wrapper, not a new index |
| `VectorStoreRetriever` | A `Runnable` — callable with `.invoke(query)`, composable into LCEL with `\|` |
| `.invoke(query)` | The only current way to call a retriever — `.get_relevant_documents(query)` has been removed entirely, not just deprecated |
| `search_type="similarity"` | Plain nearest-neighbor retrieval, ranked by raw distance; the default |
| `search_type="mmr"` | Maximal Marginal Relevance — re-ranks an initial candidate pool to balance relevance against diversity |
| `search_type="similarity_score_threshold"` | Filters by a normalized 0–1 relevance score; can return fewer than `k` results, including zero |
| `fetch_k` | MMR-only: how many candidates to pull via similarity search before re-ranking (default 20) |
| `lambda_mult` | MMR's relevance/diversity dial — `1.0` = plain relevance ranking, `0.0` = maximum diversity, `0.5` = balanced default |
| `score_threshold` | Required (no default) for `similarity_score_threshold`; a collection-scale-dependent minimum relevance score, not a raw distance |
| Raw distance vs. relevance score | Distance: lower = more similar, unbounded scale. Relevance score: higher = more similar, normalized 0–1 scale — not interchangeable |
| Chroma's default (L2) relevance-score formula | `1.0 - distance / sqrt(2)` — a documented heuristic, not a rigorous transform; can produce out-of-range scores on Chroma's actual squared-L2 distances |
| Zero results clearing a threshold | Returns an empty list, `[]` — does not raise an exception |
| `format_retrieved_context` | Turns any `list[LCDocument]` into one citation-labeled string, regardless of which retriever produced the list |
| `langchain-classic` | Where older convenience chains and retriever *wrapper* classes moved; `VectorStoreRetriever` itself is unaffected, still in `langchain_core` |

---

## Common Pitfalls & Anti-Patterns

- **Calling `.get_relevant_documents(query)` instead of
  `.invoke(query)`.** Fails immediately with an `AttributeError` on
  current `langchain-core` — this method has been removed, not
  deprecated, the same "library moved" shape as `.persist()`'s earlier
  removal.
- **Treating a relevance score and a raw distance as the same number on
  the same scale.** They're produced by different methods, on opposite
  directions of meaning (`similarity_search_with_score`: lower is
  better; `similarity_score_threshold`'s relevance score: higher is
  better) — assuming interchangeability produces exactly backwards
  filtering.
- **Assuming Chroma's default-configuration relevance score is a
  precisely calibrated 0–1 probability.** The L2-space formula behind
  it is a documented heuristic with a known mismatch against Chroma's
  actual squared-distance metric — treat the direction (higher is more
  similar) as reliable, and specific numeric cutoffs as approximate,
  not exact.
- **Wrapping a threshold retriever's `.invoke(...)` call in a
  `try`/`except` to "handle" a strict threshold.** A zero-result
  outcome is not an error — it's a plain empty list. Catching an
  exception that's never raised does nothing useful and can mask a
  genuinely different failure.
- **Giving `get_threshold_retriever` a hardcoded default
  `score_threshold` inside the function body.** The caller should
  always control how strict the filter is, the same way `k` is
  caller-controlled on every other retriever function in this project.
- **Assuming MMR will always visibly diversify results.** Against a
  small corpus — or any query where the corpus genuinely has only one
  relevant angle — MMR's re-ranked output can look nearly identical to
  plain similarity search, and that's correct behavior, not a sign the
  mechanism isn't working.
- **Passing MMR-specific (`fetch_k`, `lambda_mult`) or
  threshold-specific (`score_threshold`) keys into a `"similarity"`
  retriever's `search_kwargs`, or vice versa.** Each `search_type`
  expects its own distinct shape of `search_kwargs` — mismatched keys
  are either silently ignored or produce a construction-time error,
  depending on which key and which search type.
- **Assuming a `score_threshold` tuned for a small demo corpus will
  still be appropriate once real data volume grows.** A threshold
  calibrated against a handful of chunks can become far too lenient
  once a corpus grows to cover many more topics with genuinely
  irrelevant content to filter out.

---

## Troubleshooting Guide

| Symptom | Likely Cause | Fix |
|---|---|---|
| `AttributeError` on `.get_relevant_documents(...)` | Copied code from an older tutorial or library version | Use `.invoke(query)` instead — the only current way to call a retriever |
| `ValueError` at retriever construction, naming `search_type` | A typo or unsupported value passed to `search_type` | Use exactly `"similarity"`, `"mmr"`, or `"similarity_score_threshold"` — no other values are accepted |
| `ValueError` (or similar construction-time error) when building a `"similarity_score_threshold"` retriever | `score_threshold` was omitted from `search_kwargs` | `score_threshold` is required for this search type — always include it explicitly |
| A threshold retriever always returns exactly `k` results, never fewer | `score_threshold` was set too low (lenient) for the corpus, or the wrong search type is actually being used | Confirm `search_type="similarity_score_threshold"` is actually set, then raise `score_threshold` to see fewer results come back |
| A threshold retriever's results seem "backwards" — weak matches pass, strong matches get filtered out | Treating a raw distance value as if it were a relevance score, or vice versa | Remember: relevance score is 0–1, higher = more similar; raw distance is unbounded, lower = more similar — they are not the same number |
| MMR output looks identical to plain similarity search | A small corpus, or a query with only one genuinely relevant angle in the data | Expected behavior, not a bug — MMR has nothing meaningful to diversify against when there's no real redundancy to break up |
| `format_retrieved_context` returns an empty string | Was handed an empty `list[LCDocument]` — most likely a threshold retriever that returned zero results | Expected behavior; check the retriever's result length before formatting if a caller needs to distinguish "no context" from "some context" |
| Code written to catch an exception from a strict `score_threshold` never triggers, or errors elsewhere unexpectedly | Zero-result threshold filtering doesn't raise — it returns `[]` | Check `if not results:` instead of wrapping the call in `try`/`except` |

---
*DevMate — Northbeam Engineering Assistant — Notes: Retrievers, MMR, and Confidence-Threshold Filtering*

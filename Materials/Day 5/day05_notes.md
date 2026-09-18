# DevMate Notes
## Topic: pandas & numpy Analytics, AI-Assisted Coding

---

## Executive Summary

Everything built before today answered questions about DevMate's data
one record at a time (a document, a ticket) or with a plain Python
loop over the whole collection (stale documents, team mismatches).
Today introduced a genuinely different way of asking a question:
building small, in-memory tables out of existing `Ticket`/`Document`/
`User` objects with `pandas`, and computing real aggregate statistics
over them with `numpy` — a join, a group-by, a mean and a standard
deviation, all done as array operations instead of Python loops.

The two analytics functions built today — Team Workload Distribution
and Document Ownership & Staleness by Team — turned out to be a
genuinely good vehicle for a second, equally important topic: what it
actually means to use an AI coding assistant well. Both halves of
today share the same underlying lesson, and it's worth stating
plainly up front, because everything below elaborates on it: **code
that runs without error is not the same as code that's correct**, and
the gap between those two things is exactly where both a naive AI
suggestion and a one-character data typo can hide for a long time
before anything visibly breaks.

---

## Deep Dive: pandas Fundamentals

- **A DataFrame built from objects is a read-only view, not a new
  source of truth.** Both `_tickets_to_frame`/`_users_to_frame` and
  `_documents_to_frame`/`_users_to_frame` pull only the specific
  columns one particular question needs from existing `Ticket`,
  `Document`, and `User` objects. The DataFrame gets thrown away at
  the end of the function call; nothing about the underlying objects
  changes, and nothing is cached or persisted. This matters because it
  keeps analytics purely additive — a new way of *looking at* data
  that already has one clear source of truth, not a second copy that
  could drift out of sync with it.
- **`.merge(...)` is a join, with the same semantics as a SQL join.**
  `documents_df.merge(users_df, left_on="owner_id", right_on="id")`
  matches each row on the left to a row on the right wherever the two
  specified columns are equal — conceptually identical to `JOIN users
  ON documents.owner_id = users.id` in SQL.
- **The default join type is `inner`, and inner joins drop unmatched
  rows silently.** This is the single most important fact from today,
  confirmed the hard way during a real debugging session: if a
  document's `owner_id` doesn't match any user's `id`, that document's
  row simply **disappears** from the merged result. No exception, no
  warning, nothing printed — the row count just quietly goes down by
  one, and everything downstream of the merge (grouping, counting,
  percentages) computes a wrong-but-plausible-looking answer using
  only the documents that happened to match.
- **How that actually surfaced.** A team-by-team document ownership
  report was returning only one team where two were expected — every
  number for the team that *did* appear was completely correct, which
  is what made it non-obvious this was a missing-row problem rather
  than a wrong-math problem. The real fix was two lines of temporary
  debug output right after the merge:
  ```python
  print(f"DEBUG: merged has {len(merged)} rows (expected 5)")
  print("DEBUG documents owner_id:", documents_df["owner_id"].tolist(), documents_df["owner_id"].dtype)
  print("DEBUG users id:", users_df["id"].tolist(), users_df["id"].dtype)
  ```
  which immediately showed a document with `owner_id: 2` sitting
  alongside four real users numbered `301`–`304` — a one-character
  typo in a markdown file's front matter (`owner_id: 2` instead of
  `owner_id: 302`), sitting completely unnoticed since the ingestion
  layer was first built, because nothing had ever actually checked
  that a document's `owner_id` points to a real person until today's
  merge did.
- **Two ways to make an inner join's silent drop visible instead of
  invisible.** First, the blunt-instrument version: compare row counts
  before and after — `len(merged) != len(documents_df)` is a plain,
  cheap assertion that something didn't match. Second, the precise
  version: `merge(..., how="left", indicator=True)` keeps every row
  from the left side regardless of whether it matched, and adds a
  `_merge` column reading `"both"`, `"left_only"`, or `"right_only"`
  for every row — filtering to `merged[merged["_merge"] ==
  "left_only"]` shows *exactly* which rows failed to find a partner,
  by name, without having to go hunting through raw ids by hand:
  ```python
  >>> merged[merged["_merge"] == "left_only"]
     id_doc  owner_id  id_user team     _merge
  3       2         2      NaN  NaN  left_only
  ```
- **`.groupby("team")` buckets rows by a column's value.**
  `.size()` counts rows per bucket; `["some_column"].sum()` totals one
  specific column per bucket. Both were used today — `.size()` for
  ticket/document counts, `.sum()` on a boolean column (`is_stale`,
  `priority_weight`) for a per-team total.
- **Summing a boolean column per group already produces an explicit
  zero, not a missing row — but only for that specific construction.**
  `merged.groupby("team")["is_stale"].sum()` gives every team present
  in `merged` a row, including teams whose sum is `0`. That stops
  being true the moment the *order* changes: filtering to only the
  `True` rows first, and grouping/counting *after* that
  (`merged[merged["is_stale"]].groupby("team").size()`), makes a team
  with zero `True` rows disappear from the result entirely, the same
  way an unmatched merge row disappears — a different mechanism,
  reaching the same kind of "quietly incomplete" result.

---

## Deep Dive: numpy Fundamentals

- **numpy is for whole-array math, not one-value-at-a-time loops.**
  Everywhere today's code needed `mean`, `std`, or a percentage split
  across however many teams happened to have data, it used `np.mean`,
  `np.std`, and plain array arithmetic (`load_array / total_load *
  100`) rather than a Python `for` loop computing one team's number at
  a time. `overloaded = load_array > (mean_load + std_load)` is a
  single vectorized comparison producing a whole array of
  `True`/`False` values in one step — the essence of "thinking in
  numpy" instead of "thinking in loops."
- **`np.divide(..., where=...)` guards division by zero without a
  branch.** `np.divide(stale_array, owned_array, out=np.zeros_like(
  stale_array), where=owned_array != 0)` computes the division only
  where the denominator is nonzero, and leaves the pre-filled `0.0` in
  `out` everywhere else — the array-wide equivalent of writing `x / y
  if y != 0 else 0.0` for a single value, but working correctly across
  an entire array of teams at once, some of which might have a
  zero denominator and some of which might not.
- **numpy scalar types cross into Pydantic cleanly.** A question worth
  having asked and settled today: does returning `np.float64`/
  `np.int64`/`np.bool_` values into a Pydantic model declared with
  plain `float`/`int`/`bool` fields cause a problem? Verified directly
  — it doesn't. Pydantic v2 coerces numpy scalars into native Python
  types automatically. Both analytics functions still explicitly wrap
  every value in `int(...)`/`float(...)`/`bool(...)` before returning,
  not because it's required, but because it makes the function's own
  return contract (a plain `dict` of plain Python values) honest on
  its own terms, independent of whichever library happens to consume
  it next.
- **A statistical outlier check needs more than one data point to mean
  anything.** `is_overloaded = load_score > (mean + std)` is
  mathematically correct even when every team ties at the same value
  — `std` comes out to exactly `0.0`, and nothing can be "more than
  zero above the mean" when everything already equals the mean. That's
  not a bug; it's the right answer for a dataset that happens to be
  perfectly balanced. Worth remembering that an outlier check like
  this only becomes informative once there's enough spread in the data
  for "outlier" to mean something.

---

## Deep Dive: AI-Assisted Coding — Reviewing, Not Just Accepting

- **The tool matters far less than the habit.** Whether the assistant
  is an IDE-integrated one, a browser chat tab, or a plain question
  asked directly — the exercise doesn't change. What's being practiced
  is a review habit: get a suggestion, then go find the one unstated
  assumption it's quietly resting on.
- **"Runs without error" and "correct" are different claims.** A naive
  AI suggestion for summing ticket priority weights
  (`priority_series.map(weight_map).sum()`) never raises an exception,
  even when handed a priority value with no entry in `weight_map` —
  `.map()` produces `NaN` for the unmapped value, and `.sum()` treats
  `NaN` as `0` by default. The ticket's *existence* doesn't crash
  anything; its contribution to the total just silently disappears.
  That's a materially more dangerous failure mode than a crash,
  precisely because nothing visible signals that anything went wrong.
- **An AI assistant can only reason about what it's been shown.**
  Working from a bare function signature (a list of priorities, a
  weight dict), there's no way for an assistant to know that
  `TicketPriority` is a validated enum in this specific codebase, or
  that the dict needs to be kept in lockstep with it by hand. That's
  exactly the kind of codebase-specific context a person reviewing the
  suggestion has to supply — accepting a suggestion fast is the easy
  part; knowing which assumption to go stress-test before trusting it
  is the actual skill being practiced.
- **The general pattern, not just this one example.** Both of today's
  real bugs — the `NaN`-from-an-unmapped-priority hazard reviewed
  deliberately in the demo, and the inner-join-drops-a-row hazard
  actually encountered live — share the same shape: an operation that
  completes successfully while quietly doing less than intended. This
  is worth generalizing past today's specific `.map()` and `.merge()`
  examples: any pandas operation that can produce `NaN` (`.map()`,
  `.merge()` with unmatched keys, an out-of-bounds `.loc[]` lookup) or
  otherwise silently exclude data deserves the same instinct — check
  what happened to the row count, or explicitly account for every
  input, before trusting the output.

---

## Deep Dive: Data Integrity Across Layers

- **Validating a field exists is not the same as validating it's
  meaningful.** The ingestion layer built early on checks that a
  document has an `owner_id` field at all, and that it's a value of
  the right shape — but it never checked that the value actually
  corresponds to a real, known user. That's a reasonable scope
  decision at the time it was made (there was no `User` collection to
  check against yet), but it leaves a gap that doesn't announce
  itself until something *else* relies on the assumption the
  ingestion layer never enforced.
- **A bad value can sit unnoticed for a long time if nothing exercises
  it.** The `owner_id: 2` typo existed in `docs/onboarding-local-dev-
  setup.md` since early on, and never once caused a visible problem —
  not because it was fine, but because nothing had a reason to look
  up that specific document's owner. The Team Mismatch report only
  looks up an owner when a ticket's `related_document_id` happens to
  point at that document, and no ticket in this dataset does. Today's
  analytics endpoint was the first piece of code to join *every*
  document against *every* user, which is exactly why a days-old typo
  only surfaced today.
- **This is a general lesson about test coverage, not just about one
  typo.** A test suite (or a person, manually clicking through
  Swagger UI) only catches problems in code paths it actually
  exercises. "It's worked fine so far" is weak evidence for "it's
  correct" if the path that would expose a bug has simply never been
  taken yet — which is a good reason today's new analytics code, like
  everything before it, deserves its own test coverage rather than
  being trusted purely because it doesn't currently raise an
  exception.

---

## Architectural Analysis: One Analytics Request, Start to Finish

Tracing `GET /analytics/document-ownership` with a valid key, after
today's data was corrected:

1. `uvicorn` hands the request to the FastAPI/Starlette application;
   the logging middleware begins timing.
2. The `analytics` router's `dependencies=[Depends(require_api_key)]`
   resolves first — a missing or wrong key stops the request right
   here, before any analytics work happens at all.
3. `Depends(get_knowledge_base_service)` resolves to the cached
   `KnowledgeBaseService` instance — the same one every other route
   already shares, not something rebuilt for this one endpoint.
4. The route function calls
   `service.get_document_ownership_report()`, which delegates
   immediately to `compute_document_ownership(self._documents,
   self._users)` — `KnowledgeBaseService` itself contains no
   pandas/numpy logic; it only owns the data and hands it off.
5. Inside `compute_document_ownership`: two DataFrames get built,
   merged (an inner join — every document's `owner_id` now correctly
   matches a real user, so no rows get silently dropped), tagged with
   an `is_stale` column, grouped by `team`, and reduced to per-team
   counts and percentages using `numpy`'s array operations.
6. The function returns a plain `dict` of native Python types, which
   the route unpacks into `DocumentOwnershipReport(**report)` —
   FastAPI validates it against the `response_model` and serializes
   it to JSON.
7. Control returns to the logging middleware, which logs the request
   and status code, then the response goes back to the client.

A quiz-style question worth asking here: "what would happen to this
trace if one document's `owner_id` didn't match any real user?" The
honest answer, now directly experienced rather than hypothetical: step
5's merge would silently produce one fewer row, every subsequent step
would run without any error at all, and the response would come back
as a confident, well-formed `200 OK` with a quietly wrong number of
documents attributed to whichever teams remained.

---

## Quiz-Prep Quick Reference

| Term | One-line definition |
|---|---|
| `.merge(...)` | pandas' join operation; default `how="inner"` keeps only rows whose join keys matched on both sides |
| Inner join row drop | An unmatched row simply disappears from the result — no exception, no warning |
| `indicator=True` | A `merge(...)` option adding a `_merge` column (`"both"`/`"left_only"`/`"right_only"`) that names exactly which rows failed to match |
| `.groupby(...).size()` | Counts rows per group |
| `.groupby(...)[col].sum()` | Totals one column per group |
| `np.mean` / `np.std` | Vectorized mean/standard deviation across a whole array in one call, no explicit loop |
| `np.divide(..., where=...)` | Divides only where the condition holds, leaving a pre-filled fallback value everywhere else — guards division by zero across an array |
| `NaN` from `.map(dict)` | A value with no entry in the mapping dict becomes `NaN`; `.sum()` then treats it as `0` by default, silently |
| numpy scalar → Pydantic | `np.int64`/`np.float64`/`np.bool_` coerce cleanly into plain `int`/`float`/`bool` Pydantic fields — verified, not assumed |
| Silent data-loss bug | Code that completes successfully while quietly processing less data than intended — the common thread across today's `.map()`, `.merge()`, and typo examples |

---

## Common Pitfalls & Anti-Patterns

- **Trusting "it ran with no errors" as proof of correctness.** Both of
  today's real bugs ran cleanly from FastAPI's perspective — a `200
  OK`, no traceback, no warning. Correctness has to be checked
  separately from "did it crash."
- **Not checking row counts across a merge.** `len(merged) ==
  len(left_df)` (for a merge that's supposed to keep every left-side
  row) is a nearly free sanity check that would have caught today's
  real bug in seconds rather than requiring a debugging session.
- **Assuming a foreign-key-shaped field is actually valid just because
  it exists.** `owner_id` being present and being an integer says
  nothing about whether it points at a real `User` — those are two
  separate claims, and only the first one was ever actually checked.
- **Accepting an AI-generated `.map(dict)` call without asking what
  happens to a value the dict doesn't cover.** The failure mode isn't
  a crash; it's a smaller-than-expected sum with no error message
  anywhere near it.
- **Filtering before grouping when summing-a-boolean-after-grouping
  would keep every group present.** Both accomplish similar-looking
  goals, but only one of them guarantees a zero-count group still
  shows up in the result rather than vanishing.
- **Treating `is_overloaded`/`is_stale_risk` being `false` for
  everyone as evidence the calculation is broken**, without first
  checking whether the underlying data is genuinely balanced (a `std`
  of exactly `0.0` is a real, valid outcome, not a red flag on its
  own).

---

## Troubleshooting Guide

| Symptom | Likely Cause | Fix |
|---|---|---|
| An analytics endpoint returns fewer teams/rows than expected, with no error | An inner join (`.merge()`'s default) silently dropped a row whose join key didn't match on the other side | Compare `len(merged)` against the expected count; or re-run with `how="left", indicator=True` and filter to `_merge == "left_only"` to see exactly which row(s) failed to match |
| A per-team total is smaller than manually adding up the visible rows | A `.map(dict)` call produced `NaN` for a value missing from the dict, and `.sum()` silently treated it as `0` | Check `series.isna().any()` right after the `.map(...)` call, before summing |
| A team's percentage field is `NaN` or the whole request 500s on a percentage calculation | Dividing by a denominator that's `0` for a team with no owned items | Use `np.divide(..., out=np.zeros_like(...), where=denominator != 0)` instead of a bare `/` |
| A group that should show `0` for some metric is simply missing from the result entirely | Rows were filtered down to only the "positive" cases *before* grouping/counting, rather than grouping first and summing a boolean column | Group on the full, unfiltered data and sum a boolean column, or explicitly `.reindex(...)` against the full set of expected group keys with `fill_value=0` |
| A value that "should never happen" (an id from before an enum/relationship existed) turns up in the data | An earlier ingestion or seeding step validated that a field exists, but never validated that it refers to something real | Add an explicit check where the two collections actually get joined, since that's the first place the mismatch becomes meaningful |
| Debug `print(...)` statements are still sitting in analytics code after a bug is fixed | Left in place after the investigation that needed them | Remove them once the row counts/values are confirmed correct — they were a diagnostic tool, not permanent logging |

---
*DevMate — Northbeam Engineering Assistant — Notes: pandas & numpy Analytics, AI-Assisted Coding*

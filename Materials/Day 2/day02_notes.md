# DevMate Notes
## Topic: Modules & Packages, Exception Handling, File Handling

---

## Executive Summary


When we built our plain Python models, every `Document`, `Ticket`, and
`Comment` came from a hardcoded `seed_demo_data()` function living
inside a single script. That was deliberate scaffolding, not a
finished design — real documents don't come from Python code, they
come from files. Today replaces that hardcoded seed with a real
`docs\` folder full of files, a loader that turns them into `Document`
objects, and a custom exception hierarchy that keeps one bad file from
taking down the whole load. Two new packages, `core` and `ingestion`,
give that new code a home instead of cramming it into the existing
`models` package.

You've now written three Python packages by hand (`models`, `core`,
`ingestion`) and can probably predict the pattern before being told
it: a folder, an `__init__.py`, done. That repetition is the point —
by the time packages get their own dedicated deep-dive treatment, the
mechanics should already feel unremarkable.

---

## Deep Dive: Modules & Packages

- **A package is a folder plus an `__init__.py`.** Nothing else is
  required — no manifest, no build step, no name declaration inside
  the file matching the folder name. This is much lighter-weight than
  a Java package, which is tied to your directory structure **and** a
  `package com.northbeam.something;` line that has to match it exactly.
  Get the folder structure right in Python and the "package declaration"
  problem simply doesn't exist.
- **Why three packages instead of one.** `models` holds the domain
  objects themselves (`Document`, `Ticket`, `Comment`, `User`). `core`
  holds cross-cutting concerns that shouldn't depend on anything else
  in the codebase — today that's just the exception hierarchy, but
  configuration or logging setup would live here too. `ingestion` holds
  anything that turns *outside* data into domain objects — files today,
  eventually something else. None of those three is really a "model,"
  and folding them all into one package would make that package mean
  too many different things at once.
- **The dependency direction matters.** `ingestion` imports from
  `core` and from `models`. `models` imports from neither `core` nor
  `ingestion`. Keeping that arrow pointing one way is what makes each
  package independently understandable — you can read `models` in
  isolation and never need to know `ingestion` exists. If `models` ever
  started importing something from `ingestion`, that would be a
  circular dependency, and Python would raise an `ImportError` the
  moment both modules tried to load each other. There's no compiler
  catching this ahead of time the way some other languages might; the
  discipline of "which package is allowed to depend on which" is a
  convention you enforce by design, not something Python enforces for
  you.
- **`__init__.py` curates the public surface.** Same pattern as
  before: `from .exceptions import DocumentLoadError` inside
  `core\__init__.py` (if we'd added one) lets other code write
  `from app.core import DocumentLoadError` instead of reaching into
  `app.core.exceptions` directly. Today's `core` and `ingestion`
  packages keep their `__init__.py` files empty — with only one module
  inside each so far, there's nothing yet worth re-exporting.

**Why it matters for DevMate:** this is the same package layout a
Grounded Q&A feature will eventually need — a `retrieval` package
sitting alongside `ingestion`, both feeding the same domain models,
neither one needing to know how the other works internally.

---

## Deep Dive: Exception Handling

- **Custom exceptions are just classes.** `class DocumentLoadError
  (Exception): pass` (or, as written today, a docstring instead of
  `pass` — either is a valid empty class body) is the entire syntax.
  No special keyword, no interface to implement. What makes it useful
  isn't the class body, it's the *name* — a caller can write
  `except DocumentLoadError:` and know precisely what category of
  problem they're catching, instead of catching (and potentially
  hiding) anything and everything.
- **Inheritance builds a hierarchy you can catch at any level.**
  `UnsupportedFileTypeError` extends `DocumentLoadError`, so
  `except DocumentLoadError:` catches both the base error *and* the
  more specific one — the same is-a relationship Java's exception
  classes rely on. The difference: Python has no `throws` clause and
  no checked/unchecked distinction. Nothing forces a caller to
  acknowledge that a function might raise `DocumentLoadError` — the
  exception's name and your documentation are the only signal. That
  makes choosing a clear, well-organized hierarchy more important in
  Python, not less.
- **Sibling vs. child matters.** `TicketLoadError` was deliberately
  written as its own class inheriting directly from `Exception`, not
  as a child of `DocumentLoadError` — a ticket failing to load isn't a
  *kind of* document problem, even though the two loaders look similar.
  Nesting it under `DocumentLoadError` would technically run fine, but
  it would make a broad `except DocumentLoadError:` silently start
  catching ticket errors too, which is the wrong behavior hiding behind
  code that looks reasonable at a glance.
- **`raise ... from exc` chains exceptions instead of hiding them.**
  Every conversion in today's loaders — turning a string into a
  `date`, a string into an enum member, a string into an `int` — is
  wrapped in its own `try`/`except ValueError`, and each one re-raises
  a `DocumentLoadError` or `TicketLoadError` **from** the original
  exception. The traceback then shows both: the low-level cause (a
  `ValueError` from `date.fromisoformat`, say) and the higher-level,
  more meaningful error your code raised in response. Dropping the
  `from exc` doesn't break anything functionally, but it throws away
  debugging information for free.
- **Catch specific exceptions, not bare `except:`.** Every loop today
  writes `except DocumentLoadError as exc:` or `except TicketLoadError
  as exc:` — never a bare `except:`. A bare `except:` would also
  swallow a genuine bug (a typo'd variable name, a wrong attribute
  access) and make it disappear silently instead of crashing loudly,
  which is exactly the failure mode you want for a real programming
  mistake. Catching a named, specific exception type is what lets you
  handle the failures you *expect* while still letting the failures
  you *don't* expect surface immediately.
- **The "skip and continue" resilience pattern.** Both loaders put the
  `try`/`except` *inside* a loop, around the processing of one file or
  one CSV row at a time — not around the whole loop. That's the
  difference between "one bad document stops every document from
  loading" and "one bad document gets logged and skipped while
  everything else loads normally." This is the concrete meaning behind
  "handle errors instead of crashing": it's not about avoiding crashes
  altogether, it's about controlling *scope* — deciding how much work
  a single bad input is allowed to take down with it.

---

## Deep Dive: File Handling

- **`pathlib.Path` instead of string paths.** `Path("docs")`,
  `path.suffix`, `path.name`, `path.iterdir()`, `path.read_text(...)`
  — all of this reads as method calls on an object representing a
  path, rather than string concatenation and `os.path.join(...)` calls.
  It also handles Windows vs. other path separators for you
  automatically, which matters the moment this code runs anywhere
  besides the machine that wrote it.
- **`with open(...) as handle:` is a context manager.** The file
  closes automatically when the `with` block ends — including if an
  exception is raised partway through reading it. This is the direct
  equivalent of Java's try-with-resources, and for the same reason:
  forgetting to close a file handle is a real, common bug, and a
  context manager makes it structurally impossible to forget.
- **Two different file formats, two different parsing strategies.**
  The document loader hand-parses a small `key: value` header format
  using plain string operations (`str.partition`, `str.splitlines`) —
  appropriate for a format simple enough that a dedicated library
  would be overkill. The ticket loader instead uses Python's built-in
  `csv` module and `csv.DictReader`, which handles the genuinely fiddly
  parts of CSV (quoted fields containing commas, escaped quote
  characters) that a hand-written `line.split(",")` would get wrong on
  real-world data. Recognizing "is this simple enough to hand-parse, or
  does it need a real parser" is its own useful judgment call.
- **`csv.DictReader` keys rows by the header row.** `row["priority"]`
  instead of `row[2]` — far more readable, and far less fragile if a
  column ever gets reordered. The trade-off: `open(..., newline="")`
  is required alongside it on every platform, because the CSV format
  has its own line-ending rules that Python's normal universal-newline
  handling would otherwise interfere with.
- **Order of checks affects cost, not just correctness.** The document
  loader checks a file's extension *before* opening and reading it —
  rejecting `deploy-notes.txt` costs nothing beyond checking
  `path.suffix`. Reading a file's contents first, then discovering it's
  the wrong type, wastes a disk read that a one-line check up front
  would have avoided entirely.
- **Real files mean real dates, which drift.** Every `last_reviewed_at`
  value in `docs\` is a static, hand-written date rather than a
  `date.today() - timedelta(...)` calculation. That's a trade-off:
  it's honest about what a real file actually looks like, but it also
  means the exact "days ago" numbers in any printed report will slowly
  change as real time passes, unlike the earlier hardcoded version
  where the ages were always relative to whenever the script happened
  to run. Worth refreshing the sample dates periodically so the
  stale/not-stale split stays illustrative.

---

## Architectural Analysis

The most important thing that did **not** change today: `Document`
itself, and the `find_stale_documents` business-question function,
are both untouched. Only the *source* of the data changed — a file
loader instead of a hardcoded seed function — and the function that
answers the business question kept working without a single edit.
That's a direct payoff of having kept "what does a stale document
report look like" separate from "where do documents come from" from
the start: the two concerns were never tangled together, so swapping
one out didn't require touching the other.

The same split shows up again in the Team Mismatch function: it's the
exact function from before, copied over unchanged, now fed
file-loaded tickets and file-loaded documents instead of hardcoded
ones. If that function had reached directly into a hardcoded
`Ticket.registry` instead of accepting `tickets` as a parameter, none
of today's work would have been possible without rewriting it.
Accepting data as parameters, rather than assuming where it comes
from, is what made today's swap a clean one instead of a rewrite.

This also previews something worth naming explicitly: the same `docs\`
folder being built today is not throwaway scaffolding. Once retrieval
enters the picture, these exact files become the corpus that gets
chunked and embedded — the loader that turns them into `Document`
objects today is the same loader (or a close cousin of it) that will
hand documents to a chunking step later. Nothing about today's file
format was chosen arbitrarily; it's meant to still make sense once
there's a vector store on the other end of it.

The exception hierarchy is also scaffolding for something bigger than
it looks today. Right now, `DocumentLoadError` gets caught and printed
as a log line. Once a REST layer exists, a caught exception like this
is exactly the kind of thing that becomes a structured HTTP error
response instead of a `print()` statement — the *shape* of "something
specific went wrong, here's a named type describing what" carries
forward even as *what happens* when it's caught changes completely.

---

## Common Pitfalls & Anti-Patterns

- **Bare `except:` clauses.** Swallows real bugs along with expected
  failures — a typo'd attribute name disappears silently instead of
  raising `AttributeError` where you'd actually see it. Always name
  the exception type you're catching.
- **Building the wrong exception hierarchy.** Making an unrelated
  exception inherit from an existing one "for consistency" (like
  nesting `TicketLoadError` under `DocumentLoadError`) runs fine today
  and quietly breaks the meaning of a broad `except` clause later.
- **Putting `try`/`except` around the whole loop instead of one
  iteration.** Wrapping the entire `for` loop in a single `try` block
  means the *first* bad file or row stops every later one from being
  processed — defeating the entire point of handling the error in the
  first place. The `try`/`except` has to live inside the loop body.
- **Forgetting `newline=""` when opening a CSV file.** Works fine on
  simple sample data; becomes a real, hard-to-reproduce bug the moment
  a CSV with different line-ending conventions shows up (very common
  when a file has been edited on both Windows and macOS/Linux at
  different points).
- **Hand-rolling a validity check instead of reusing an existing
  enum.** Writing `if row["priority"] not in ["Low", "Medium", "High",
  "Critical"]:` duplicates information that already lives in
  `enums.py`, and silently drifts out of sync the moment a priority
  level is renamed or added there. Constructing the actual enum
  (`TicketPriority(row["priority"])`) and catching the `ValueError` it
  raises on a bad value keeps there being exactly one source of truth.
- **Treating a legitimately blank field as an error.** A blank
  `related_document_id` in a CSV row is valid — "no related
  document" — and should become `None`, not raise an exception. Only a
  non-blank value that *isn't* a valid integer should raise. Collapsing
  those two very different cases into one check is an easy mistake.
- **A silently-wrong result instead of a loud crash.** Skipping a
  required setup step (forgetting to seed users before running a
  report that depends on them, for example) doesn't always crash — it
  can just produce an empty or misleadingly-small result that looks
  like a valid answer. This is a worse bug than a crash, precisely
  because nothing draws your attention to it. When a report comes back
  suspiciously empty, checking "did every piece of setup actually run"
  should be an early instinct, not a last resort.

---

## Troubleshooting Guide

| Symptom | Likely Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'app'` | Running a script from the wrong directory | Run from the `backend\` folder using `python -m scripts.<name>`, not `python scripts\<name>.py` |
| `FileNotFoundError` when loading `docs\` or `tickets.csv` | The relative path (`"docs"`, `"tickets.csv"`) is being resolved against the wrong current working directory | Confirm you're running the command from `backend\` — relative paths in these loaders are relative to wherever the process was started, not to the script's own location |
| `UnicodeDecodeError` while reading a file | A file was saved with an encoding other than UTF-8 | Re-save the file as UTF-8, or confirm `encoding="utf-8"` is present on the `open()`/`read_text()` call |
| `DocumentLoadError: ... missing required field(s) [...]` | A file in `docs\` is missing one of the required frontmatter keys | Check the file's header block against the required field list; a common cause is a typo in the key name (`owner_ID` instead of `owner_id`) |
| `UnsupportedFileTypeError` for a file you expected to load | The file's extension isn't `.md` | Rename the file, or confirm it actually belongs in `docs\` at all — a stray `.txt` or `.docx` file will always be rejected by design |
| `TicketLoadError: ... invalid priority` / `invalid status` | The CSV value doesn't exactly match one of the enum's string values | Enum matching is case-sensitive and exact — `"open"` or `"OPEN"` will not match `TicketStatus.OPEN`'s value of `"Open"` |
| Every row in a CSV fails to load | Header row typo, or extra whitespace in a header/value | Print `reader.fieldnames` right after creating the `DictReader` and compare it character-for-character against what the code expects |
| Team Mismatch Report is always empty, even though the CSV clearly has a mismatched row | Users were never seeded before the report ran | Confirm the function that creates the `User` records actually runs in `main()` before the report is generated — an empty `User.registry` makes every lookup return `None` and silently produces zero mismatches instead of an error |
| `IndentationError` inside a `try`/`except` block | A line inside the `try` or `except` body isn't indented consistently with the rest of that block | Configure your editor to insert spaces (4) for tabs; re-indent the block consistently |

---
*DevMate — Northbeam Engineering Assistant — Notes: Modules & Packages, Exception Handling, File Handling*

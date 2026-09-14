# DevMate Notes
## Python OOP, Virtual Environments, pip

---

## Executive Summary

**Target version:** Python 3.10+. This isn't just a recommendation —
today's code uses the `X | None` union-type syntax (PEP 604), which
only exists on 3.10 and later. Run `python --version` before starting
and confirm 3.10.0 or higher (this course standardizes on 3.11).

Today we laid the foundation of DevMate, Northbeam's internal
engineering assistant: a plain-Python domain model with no database and
no API, just three classes — `Document`, `Ticket`, `Comment` — living
entirely in memory. That's a deliberate choice, not a shortcut we'll
regret. A later session adds a real database, another brings in
FastAPI, and eventually this same shape is backing a retrieval-
augmented `/ask` endpoint — but the *fields* you defined today survive
largely unchanged all the way there. Getting comfortable with how Python
classes differ from Java classes, and with the pip/virtual-environment
workflow that scopes every dependency to this one project, is the whole
game today.

You come in with some Java training already. Good news: object-oriented
thinking transfers directly. What changes is syntax, some conventions,
and a few genuinely different design defaults (duck typing instead of
static typing, no access modifiers, everything "public" by convention
rather than by keyword). This document leans on Java comparisons
throughout for exactly that reason — not because Python and Java are
similar under the hood, but because contrast is often the fastest way
to make new syntax feel familiar.

---

## Deep Dive: Python OOP

This is where the Java background helps most, and where the syntax
differs most. Key points, tied directly to the `Document` class from
today's demo:

```python
class Document:
    registry: ClassVar[list["Document"]] = []
    STALE_THRESHOLD_DAYS: ClassVar[int] = 90

    def __init__(self, document_id, title, category, body, owner_id,
                 last_reviewed_at=None):
        self.id = document_id
        ...
```

- **`__init__` is the constructor.** The double underscores ("dunder")
  mark it as a special method Python calls automatically — comparable
  to a Java constructor matching the class name, but Python only ever
  has one `__init__` per class (no constructor overloading; you
  simulate it with default arguments instead, as `last_reviewed_at`
  does above).
- **`self` must be explicit** in every instance method's parameter
  list, and you use `self.attribute` to reference instance state —
  there's no implicit `this`. This is the single most common muscle-
  memory slip coming from Java: forgetting to write `self` as the
  first parameter.
- **Class attributes vs. instance attributes.** `registry` and
  `STALE_THRESHOLD_DAYS` are declared directly inside the class body
  (outside `__init__`) — they're shared by every instance, the Python
  equivalent of Java's `static` fields. `self.id`, `self.title`, etc.
  are set inside `__init__` and belong to each individual object, like
  normal (non-static) Java fields.
- **`@classmethod`** — `find_by_id` receives `cls`, the class itself,
  so it can reach the shared `registry`. Closest Java equivalent is a
  `public static Document findById(int id)` method. We didn't need
  `@staticmethod` anywhere today (no helper that needs neither `self`
  nor `cls`), but you'll see it as soon as some later validation logic
  needs one.
- **`__repr__`** — a dunder method controlling how an object prints.
  Roughly equivalent to overriding `toString()` in Java, though Python
  distinguishes `__repr__` (developer-facing, unambiguous) from
  `__str__` (user-facing) — we only defined `__repr__` today, which
  Python falls back to for both when `__str__` is absent.
- **No access modifiers.** There's no `private`, `protected`, `public`
  keyword. Convention marks "internal" members with a leading
  underscore — it's a signal to other developers, not an enforced
  restriction. Nothing in today's code needed this yet, but you'll see
  it as soon as some later validation logic needs an internal-only
  helper method.
- **Optional / union types** — `last_reviewed_at: date | None = None`,
  `-> "Document | None"` (PEP 604, Python 3.10+) rather than the older
  `typing.Optional[date]` form; both mean the same thing, but `X | None`
  is the current idiomatic style and doesn't require a `typing` import.
  This mirrors Java's `Optional<LocalDate>` or a nullable field
  conceptually, but Python's `None` can be assigned to *any* variable
  regardless of its type hint — the hint is advisory, not enforced by
  the runtime the way Java's compiler enforces `Optional`.

**Supporting concepts used alongside OOP today** (each gets its own
full treatment on a later day — this is just enough to read today's
code):

- **`enum.Enum`**, as used in `enums.py`. Exactly like Java's `enum`
  keyword in spirit, though the mechanics differ: Python enums are
  regular classes under the hood, and by inheriting from `str` (as we
  did with `class DocumentCategory(str, Enum)`), each member is *also*
  a string, which makes JSON serialization trivial once FastAPI enters
  the picture later on.
- **f-strings** (`f"{document.title!r} last reviewed {days} days ago"`)
  — the modern way to build strings, directly comparable to Java's
  text blocks / `String.format`, but with the expression embedded
  inline. The `!r` conversion flag calls `repr()` on the value instead
  of `str()` — useful for wrapping a string value in quotes in output,
  so it's visually distinct from surrounding text.
- **List comprehensions**, used in `find_stale_documents`:
  ```python
  [document for document in documents
   if document.category != DocumentCategory.POSTMORTEM
   and document.is_stale(threshold)]
  ```
  A functional, single-line alternative to a `for` loop with an `if`
  and an `append` — roughly analogous to a Java Stream pipeline
  (`.filter(...).collect(...)`), compressed into one expression.
- **Package structure** (`app\models\__init__.py`) gets its full
  treatment in a later session on Modules & Packages — today, just
  know that it's what lets `from app.models import Document` work.

**Why it matters for DevMate:** every method you wrote today on plain
Python objects — `is_stale`, `find_by_id` — has a near-identical shape
once `Document` becomes a SQLAlchemy model down the line. You're not
learning throwaway code; you're learning the domain.

---

## Deep Dive: Virtual Environments

A **virtual environment** solves the problem of every Python project on
your machine wanting different (and possibly conflicting) package
versions. `python -m venv .venv` creates an isolated interpreter +
package directory scoped to just this project; activating it
(`.\.venv\Scripts\Activate.ps1` on Windows/PowerShell) points your
shell's `python` and `pip` commands at that isolated copy instead of
the system-wide install.

This is conceptually similar to how a Java project's
`pom.xml`/`build.gradle` scopes dependencies to the project — except
Python's isolation happens at the *interpreter* level via `venv`, not
just a dependency manifest. A Java build tool downloads jars into a
project-local cache but still runs on whatever JDK is on `PATH`; a
Python venv goes one step further and gives the project its own private
copy of the interpreter's package directory, so `pip install` from
inside an activated venv can never leak a package into some other
project on the same machine (or the system Python).

**What "activated" actually changes:** your shell's `PATH` gets a new
entry pointing at `.venv\Scripts\` inserted ahead of everything else,
so typing `python` or `pip` resolves to the venv's copies first. This
is why `where.exe python` before and after activation is worth running
explicitly — it's the fastest way to *see* the isolation rather than
just trust that it happened.

**A Windows-specific wrinkle worth internalizing now, because it
recurs all course long:** PowerShell's default execution policy blocks
running unsigned `.ps1` scripts — including `.venv\Scripts\Activate.ps1`
itself. `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`
fixes this for the current terminal session only (it does not weaken
security machine-wide, and needs re-running in any brand-new terminal
tab where activation fails the same way).

---

## Deep Dive: pip

- **`pip`** is Python's package manager — the rough equivalent of
  Maven/Gradle dependency management, though pip installs packages
  directly rather than managing a project's whole build lifecycle
  (compiling, packaging, running tests are separate tools in the
  Python world, not bundled into pip itself the way Gradle bundles
  more of the pipeline).
- **`requirements.txt`**, generated via `pip freeze > requirements.txt`,
  is Python's rough equivalent of a `pom.xml`'s dependency list — a
  reproducible record of exactly which packages (and versions) the
  project needs. Today's is empty (no third-party packages needed yet),
  but the workflow matters: `pip install -r requirements.txt` on any
  machine recreates an identical environment, which is exactly what a
  teammate — or an evaluator picking up this project cold — will run
  first.
- **Why `pip install --upgrade pip` runs before anything else.** A
  stale bundled `pip` version inside a freshly created venv can fail on
  newer package metadata formats. Upgrading it first, inside the
  activated venv, is a habit worth building now rather than debugging
  a confusing install failure later in the course when real
  dependencies (FastAPI, LangChain) show up.
- **Scope discipline.** Every `pip install` you run for the rest of
  this course should happen with the venv active. An install run
  *outside* an activated venv lands in the system-wide Python instead —
  it will often still "work" locally, which is precisely what makes it
  a dangerous habit: the project's `requirements.txt` silently stops
  being the truth about what it actually needs.

---

## Architectural Analysis

Today's three classes are intentionally **not** persisted anywhere —
`registry` is a Python list living in process memory, wiped the moment
the script ends. That's the point. We're isolating "what does the data
look like" (today's question) from "how does it get stored" (a later
question, once `Document`, `Ticket`, and `Comment` become SQLAlchemy
models backed by a real database).

Look at how closely today's `__init__` parameters already anticipate
the shape a database table will need:

```
Document: id, title, category, body, owner_id, last_reviewed_at
```

That's deliberate scaffolding. When SQLAlchemy enters the picture, the
*fields* won't change; only the base class changes (from nothing, to
`Base` from `sqlalchemy.orm`), and the `registry` pattern gets replaced
by an actual database session. Every method you wrote today that
operates on plain Python objects (`is_stale`, `find_by_id`) has a
near-identical shape once it becomes a database query down the line —
you're not learning throwaway code, you're learning the domain.

`find_stale_documents` is also your first hands-on encounter with a
**business question** — answered in the cheapest possible way (a list
comprehension over an in-memory list) before you ever see it answered
the "real" way (a database query, then a FastAPI endpoint, then
eventually a retrieval-augmented answer). That progression — plain
Python → database → API → AI — is the throughline for the rest of this
sprint.

The deliberate omission of `User` from today's Phase A build (even
though `Document.owner_id` and `Ticket.assignee_id` already exist) is
also intentional, not an oversight: it mirrors how a real domain model
often grows — a foreign-key-shaped field arrives before the entity it
points at gets modeled explicitly. Today's Phase B challenge is that
exact moment, made concrete.

---

## Common Pitfalls & Anti-Patterns

- **Forgetting `self`.** Leaving `self` off an instance method
  signature causes a `TypeError` the moment it's called on an
  instance, because Python automatically passes the instance as the
  first argument regardless of what you named the parameter — or
  whether you included one at all.
- **Mutable default arguments.** `def __init__(self, tags=[]):` shares
  one list across every instance that doesn't pass its own — always
  default to `None` and construct the mutable object inside the method
  body instead. We sidestepped the same class of bug today in
  `Comment.__init__` by using `created_at: datetime | None = None`
  and then `self.created_at = created_at or datetime.now()` inside the
  body, rather than defaulting the parameter directly to
  `datetime.now()`.
- **Confusing class attributes with instance attributes.** Writing
  `self.registry = []` inside `__init__` (instead of declaring
  `registry` at the class level) would silently break the pattern —
  every `Document` would get its *own* empty registry instead of
  sharing one, and `Document.registry` would still be an empty list.
- **Reassigning a class attribute through an instance.**
  `some_document.STALE_THRESHOLD_DAYS = 30` creates a *new instance
  attribute* that shadows the class attribute for that one object
  only — it does not change the shared value. Always mutate class-level
  state via the class itself
  (`Document.STALE_THRESHOLD_DAYS = 30`).
- **Treating `X | None` as a runtime guarantee.** A type hint of
  `date | None` doesn't stop `None` from causing a `TypeError` if you
  then try `(today - None).days` without checking for `None` first.
  Hints guide humans and tools; they don't guard your code at runtime
  the way Java's compiler does.
- **Running 3.10+ syntax on an older interpreter.** If a student's
  machine has multiple Python versions installed and the venv gets
  created against a pre-3.10 one by accident, every `X | None`
  annotation in these files raises `TypeError: unsupported operand
  type(s) for |: 'type' and 'NoneType'` immediately on import — before
  any of the actual logic runs. Always confirm `python --version`
  *after* activating the venv, not just before creating it.
- **Installing packages with the venv inactive.** The install
  "succeeds" and `import` even works in that same terminal, but the
  package lands in the system-wide Python, not the project's isolated
  copy — `requirements.txt` then silently stops describing what the
  project actually needs.

---

## Troubleshooting Guide

| Symptom | Likely Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'app'` | Running a script from the wrong directory, so Python can't resolve the `app` package | Run commands from `backend\` (the directory containing `app\`), and use `python -m scripts.day1_demo` rather than `python scripts\day1_demo.py` |
| `.\.venv\Scripts\Activate.ps1` errors about scripts being disabled | PowerShell's default execution policy blocks unsigned scripts | Run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in the current terminal, then re-run activation |
| `IndentationError: unexpected indent` | Mixed tabs/spaces, or inconsistent indentation width | Configure your editor to insert spaces (4) for tabs; re-indent the offending block consistently |
| `TypeError: unsupported operand type(s) for \|: 'type' and 'NoneType'` | The active interpreter is older than 3.10, so `X \| None` union syntax isn't supported | Run `python --version` inside the activated venv; if it's below 3.10, delete `.venv` and recreate it with a 3.10+ interpreter |
| `TypeError: __init__() missing 1 required positional argument` | Forgot a required constructor argument, or accidentally used a keyword argument before a positional one | Check the parameter order against the class definition; supply all required positional args before any keyword args |
| `AttributeError: 'NoneType' object has no attribute '...'` | Called `.find_by_id()` and got `None` back (no match), then tried to use it directly | Always check `if result is not None:` before using a lookup's return value |
| Changing `Document.STALE_THRESHOLD_DAYS` on one document doesn't affect others | Accidentally set it on the *instance* instead of the class | Set it via the class name directly: `Document.STALE_THRESHOLD_DAYS = 30` |
| `(.venv)` doesn't appear in your prompt after activating | Wrong activation script, or venv not actually created | Confirm `.venv\` exists; on Windows use `.\.venv\Scripts\Activate.ps1`, not the macOS/Linux `source .venv/bin/activate` form |
| `pip install` succeeds but `import` still fails | venv not activated when `pip install` was run, so the package landed in the system Python instead | Activate the venv first, then reinstall; verify with `where.exe pip` pointing into `.venv` |

---
*DevMate — Northbeam Engineering Assistant — Notes: Python OOP, Virtual Environments, pip*

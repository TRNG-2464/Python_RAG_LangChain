# DevMate Notes
## Topic: OpenAPI & Swagger UI, REST API Design (Pagination & Status Codes), Route Ordering, and pytest Testing

---

## Executive Summary

When the API layer first went up, it did the simplest thing that
could work: `GET /documents` returned every document at once, there
was no way to ask for just one, and none of it had a single automated
test protecting it from regressions. Today closed all three gaps —
pagination, a get-by-id lookup, and a real `pytest` suite — and, along
the way, took a proper tour of the tooling FastAPI had already been
generating behind the scenes the whole time: the OpenAPI schema, and
the Swagger UI / ReDoc pages built from it.

None of this changed what the service *does* at the business-logic
level — `KnowledgeBaseService` still answers the same two questions it
always has (which documents are stale, which tickets have a
team-mismatch). What changed is how carefully the API around that
logic behaves: it can now hand back one page of results instead of a
firehose, it can be asked about a single record by id and get a clean
answer either way (found, or a proper `404`), and there's now a
suite of tests that will fail loudly the moment either behavior
regresses.

Four ideas make up today as a topic, and each gets its own section
below: **OpenAPI and its generated docs** (what they are and why they
exist), **pagination and HTTP status codes** (the REST design
patterns behind today's new routes), **route declaration order** (a
subtle but real correctness bug), and **pytest** (fixtures, the
in-process `TestClient`, and the difference between a unit test and an
integration test).

---

## Deep Dive: OpenAPI, Swagger UI, and ReDoc

- **One schema, three views.** FastAPI has been generating a complete
  OpenAPI schema — a JSON document describing every route, its
  parameters, its request/response shapes, and its security
  requirements — since the very first route was written. That schema
  was always available at `/openapi.json`; today was just the first
  time it got looked at directly, along with the two human-readable
  pages built from it: `/docs` (Swagger UI) and `/redoc` (ReDoc).
  All three are reading the exact same underlying schema — they just
  render it differently.
- **Where the schema actually comes from.** Nothing about it is
  hand-written. It's assembled automatically from: the routes and
  their HTTP methods, each parameter's type hints and `Query(...)` /
  `Path(...)` constraints, each route's `response_model`, and any
  security schemes (like `APIKeyHeader`) wired in through
  `dependencies=[...]`. Change any of those in the code, and the
  schema — and everything rendered from it — changes automatically on
  the next request. This is the same underlying mechanism that made
  the Swagger "Authorize" button appear once `APIKeyHeader` was
  introduced: nothing was configured specifically to show it, it fell
  out of the schema generation for free.
- **Swagger UI (`/docs`) is interactive.** It's not just
  documentation — the "Try it out" button on each route actually
  sends a real request to the running server and shows the real
  response, which is why it needed the Authorize flow wired up before
  it was useful for anything other than reading.
- **ReDoc (`/redoc`) is read-only, reference-style documentation.**
  Same schema, no "Try it out" — better suited for handing to someone
  who needs to *read* the API's contract than to someone actively
  poking at it.
- **`/openapi.json` is the raw material.** Useful on its own for
  generating client SDKs, feeding into API gateways, or just
  confirming exactly what a route's schema looks like when Swagger
  UI's rendering of it seems ambiguous.

---

## Deep Dive: REST API Design — Pagination

- **The problem pagination solves.** `GET /documents` returning
  *everything* is fine with five documents and a disaster with five
  million — the response gets huge, slow to generate, slow to
  transfer, and mostly wasted if the caller only wanted to look at the
  first handful. Pagination lets a client ask for a bounded slice
  instead.
- **The `skip`/`limit` pattern.** Today's routes accept `skip` (how
  many records to skip before starting) and `limit` (the maximum
  number to return), both as `Query(...)` parameters with
  constraints: `skip: int = Query(0, ge=0)`, `limit: int = Query(10,
  ge=1, le=100)`. This is called **offset-based pagination** — the
  client is always saying "give me results starting at this
  position."
- **This is a convention, not a standard.** There's no single official
  REST specification mandating `skip`/`limit` or the exact envelope
  shape used here. Cursor-based pagination (where the client passes
  back an opaque token pointing at "where it left off" instead of a
  numeric offset), `page`/`page_size` parameters, and even HTTP `Link`
  headers (RFC 8288, used by some APIs to point at "next"/"previous"
  URLs) are all legitimate alternative designs other APIs use for the
  same underlying problem. `skip`/`limit` was chosen here because it's
  simple to reason about and easy to test, not because it's the only
  correct answer.
- **The envelope, and why `total` matters.** Rather than returning a
  bare list, `list_documents` and `list_tickets` both return an
  object: `{"items": [...], "total": N, "skip": ..., "limit": ...}`.
  `total` is the single most important field in that envelope, and
  the one most likely to get implemented wrong — it has to reflect
  the size of the **entire** underlying collection, not the length of
  the current page. A client paging through results has no other way
  to know when to stop asking for more; `total` equal to the current
  page's length would make every page look like the last one.

---

## Deep Dive: HTTP Status Codes, Precisely

- **`200 OK`** — the default for a successful response; explicit here
  (`status_code=status.HTTP_200_OK`) mostly for clarity, since it's
  already FastAPI's default for a `GET` route that doesn't raise.
- **`404 Not Found`, done correctly.** The right way to signal "no
  record with that id" is to explicitly `raise HTTPException(
  status_code=status.HTTP_404_NOT_FOUND, detail=...)` from inside the
  route function, *after* checking whether the lookup returned
  `None`. Letting a function typed to return `TicketOut` fall through
  and actually return `None` does **not** produce a clean `404` — see
  the next point.
- **`422 Unprocessable Entity`** is FastAPI's default status for
  *request* validation failures — a `Query(...)`/`Path(...)`
  constraint violated, a request body that doesn't match its Pydantic
  schema, a path parameter that can't be coerced to its declared type
  (this is exactly what happens in the route-ordering bug covered
  below). It means "the request itself was malformed," which is a
  meaningfully different situation from a 404.
- **`401 Unauthorized` vs. `403 Forbidden` — a real, commonly-confused
  distinction.** `401` means the request is missing valid credentials
  entirely (no API key, or the wrong one) — exactly what
  `require_api_key` returns. `403` means the credentials *were* valid,
  but the authenticated caller still isn't allowed to do the specific
  thing they asked for (a real user, correctly identified, trying to
  access something outside their permissions). This codebase only
  ever needs `401`, since there's just one API key and no per-user
  permission levels — but conflating the two is a common mistake worth
  being able to name correctly.
- **A `500` you didn't raise on purpose: response validation
  failure.** If a route declares `response_model=TicketOut` (a model
  with required fields) and the function returns `None` — or anything
  else that doesn't actually satisfy that schema — FastAPI's *response*
  validation fails after the function has already run, and that
  surfaces to the client as a generic `500 Internal Server Error`,
  not a clean `404` or `422`. This is deliberate on FastAPI's part: a
  response failing to match its own declared schema is treated as a
  bug in the server's code, not a problem with the client's request,
  so it doesn't get the friendlier automatic error-formatting request
  validation gets. It's exactly why `get_document`/`get_ticket` check
  for `None` and raise `HTTPException` explicitly, rather than ever
  letting a `None` reach the `response_model` check.

---

## Deep Dive: Route Declaration Order

This is the single most important "gotcha" from today, and it isn't
specific to FastAPI — it's true of essentially any web framework that
matches incoming paths against a list of route patterns.

- **Routes are matched in the order they were declared, first match
  wins.** A path segment written as a parameter placeholder —
  `/{document_id}`, `/{ticket_id}` — will structurally match *any*
  single path segment, including ones that were actually meant for a
  different, more specific route. `/{document_id}` matches the literal
  text `/stale` just as readily as it matches `/17`, purely at the
  routing level; type coercion only happens *after* a route has
  already been selected.
- **What actually happens when it's declared in the wrong order.** If
  `/{document_id}` (typed as `int`) were declared before `/stale`, a
  request to `GET /documents/stale` would be routed to the
  `/{document_id}` handler, and only then would FastAPI try — and
  fail — to convert the text `"stale"` into an `int`. The visible
  symptom is a `422 Unprocessable Entity`, which can be genuinely
  confusing to debug, because the error message is about type
  conversion, giving no hint that the real problem is which route got
  matched in the first place.
- **The fix is just ordering.** Literal, specific routes (`/stale`,
  `/mismatches`) have to be declared *before* the parameterized route
  that could also structurally match them (`/{document_id}`,
  `/{ticket_id}`). This isn't a workaround or a special case — it's
  the correct, permanent shape of a router that has both kinds of
  routes on the same prefix.
- **Why this is easy to miss.** A route added in the wrong order
  passes almost every manual, happy-path test — `GET /documents/17`
  still works fine, because a real integer id never collides with the
  literal word "stale." The bug only shows up when someone actually
  requests the specific literal path, which is exactly why a
  regression test for it (`test_stale_documents_endpoint_still_
  reachable`, `test_mismatches_endpoint_still_reachable`) earns its
  place in the suite — it's testing something a casual manual check is
  very likely to skip.

---

## Deep Dive: pytest Fundamentals

- **What pytest actually is.** A test framework that automatically
  discovers test files (by default, `test_*.py` or `*_test.py`) and,
  within them, functions whose names start with `test_`. No explicit
  registration is required — naming a function correctly is what
  makes pytest find and run it.
- **Fixtures are pytest's dependency injection.** A fixture is a
  function decorated `@pytest.fixture` that provides some piece of
  setup a test needs. A test function requests a fixture simply by
  naming it as a parameter — pytest matches that parameter name
  against fixture names visible in scope (defined in the same file, or
  in a `conftest.py` anywhere at or above that test file in the
  directory tree) and calls the fixture to supply the value.
- **Two built-in fixtures used today.** `tmp_path` hands a test a
  fresh, empty, uniquely-named temporary directory (a real
  `pathlib.Path`) that pytest creates before the test and cleans up
  afterward — using it instead of pointing at the project's real
  `docs/` folder is what makes a loader test a true, isolated *unit*
  test, independent of whatever happens to be checked into that
  folder at the time. `capsys` captures anything printed to
  stdout/stderr during a test, so a plain `print(...)` call (like the
  loader's own `SKIPPED` message) can be asserted on the same way a
  return value would be.
- **`autouse=True` fixtures run for everyone, automatically.** A
  fixture decorated `@pytest.fixture(autouse=True)` runs for *every*
  test within its scope, without any test needing to request it by
  name as a parameter. `conftest.py`'s `reset_registries` fixture uses
  this specifically so no individual test file has to remember to
  clean up after itself.
- **Unit tests vs. integration tests — the real distinction, not just
  a label.** `test_loader.py` never imports FastAPI at all — it calls
  `load_documents_from_folder(...)` directly, checking pure business
  logic in isolation. `test_documents.py` and `test_tickets.py`, by
  contrast, drive the *actual, running* FastAPI application —
  routing, dependency injection, the security scheme, and response
  validation are all genuinely exercised, not simulated or mocked.
  Both kinds of test matter, and they catch different categories of
  bug: a unit test can tell you the loader itself is correct even if
  the whole HTTP layer is broken; an integration test can catch a
  wiring mistake (a missing `include_router` call, a router declared
  in the wrong order) that a unit test, by design, would never see.
- **`TestClient`: a real app, no real server.**
  `fastapi.testclient.TestClient` drives the actual FastAPI/Starlette
  application in-process — no server process, no open port, no real
  network socket — while still exercising the genuine ASGI request/
  response cycle, middleware included. Internally, it's built on
  `httpx` to actually construct and drive the request/response
  objects; a very recent development (worth knowing about, since it
  can otherwise look alarming) is that Starlette has begun steering
  `TestClient` toward a newer, actively-maintained fork of that
  library called `httpx2`, stewarded by the Pydantic team now that the
  original `httpx` project has seen less active maintenance. Today,
  plain `httpx` still works and nothing breaks — it just emits a
  `DeprecationWarning` nudging toward `httpx2` — but this is the kind
  of fast-moving ecosystem detail worth re-checking against whatever
  exact versions a given project has pinned.
- **The `ClassVar` registry problem, revisited.** Back when
  `Document`, `Ticket`, `Comment`, and `User` were first designed as
  plain Python classes, each was given a class-level `registry` list —
  a single list, shared by the *class itself*, that every constructor
  call appends to, no matter which object or which part of the code
  created it. That design choice was harmless in a script that runs
  once and exits, but it becomes a real hazard under `pytest`: without
  cleanup, objects built by one test silently persist into every test
  that runs afterward in the same session, which can corrupt
  `find_by_id()` lookups the Team Mismatch logic depends on, and
  cause values seen by one test to depend on what some *other*,
  unrelated test happened to run first. `reset_registries` clears all
  four registries after every single test (via `autouse=True`), and
  also calls `get_knowledge_base_service.cache_clear()` — since that
  provider is `@lru_cache`d at the process level, the *next* test that
  touches the real app needs to rebuild a fresh `KnowledgeBaseService`
  rather than silently reusing one built by an earlier test.

---

## Deep Dive: Writing Better Tests

- **`@pytest.mark.parametrize`.** Decorating a test function with
  `@pytest.mark.parametrize("arg1,arg2", [(a, b), (c, d), ...])` runs
  that same test body once per tuple of values supplied, each showing
  up as its own separate result in the test report. This is the
  natural next step for something like
  `test_get_document_by_id_found`/`test_get_ticket_by_id_found` — two
  nearly identical test functions differing only in which collection
  and which id they check are a strong candidate for collapsing into
  one parametrized test.
- **Regression tests as a named concept.** A test whose entire purpose
  is confirming a *specific, previously-real* bug doesn't come back —
  `test_stale_documents_endpoint_still_reachable`,
  `test_mismatches_endpoint_still_reachable` — is called a regression
  test. It's not testing a new feature; it's a permanent, automated
  record of a mistake that once existed, positioned exactly where that
  mistake would resurface if the code were ever restructured carelessly.
- **A related-but-separate FastAPI feature: `response_model_
  exclude_unset`.** Setting `response_model_exclude_unset=True` on a
  route causes fields that were left at their Pydantic default (never
  explicitly set on the model instance being returned) to be dropped
  from the JSON response entirely, rather than always serializing
  every declared field. It's most useful for `PATCH`-style partial
  update endpoints, where "this field wasn't included" and "this
  field was explicitly set back to its default value" need to remain
  distinguishable to the client — not something today's read-only
  routes need, but a natural next question once `response_model` is
  understood.
- **pytest's CLI has more than just `-v`.** `-v` (verbose) prints one
  line per test, naming it explicitly; the default with no flag prints
  a compact single character per test instead (a dot for a pass), which
  is easier to scan at a glance once a suite grows into the hundreds
  of tests. `-k EXPRESSION` runs only tests whose name matches an
  expression (supporting `and`/`or`/`not`, not just a plain substring
  match) — useful for running just `pytest -k tickets` while working
  only on that file. `--lf` (`--last-failed`) re-runs only the tests
  that failed on the previous run, which is often much faster than a
  full run while iterating on a fix; its close relative `--ff`
  (`--failed-first`) runs the whole suite but puts last run's failures
  first.

---

## Architectural Analysis: Two Requests, Start to Finish

**Request 1 — `GET /documents?limit=2`, a valid key:**

1. `uvicorn` (via `fastapi dev` or otherwise) hands the request to the
   FastAPI/Starlette application.
2. The logging middleware begins timing and calls `await
   call_next(request)`.
3. Routing matches the path against the `documents` router. Because
   `""` was declared before `/stale` and `/{document_id}`, this is an
   unambiguous match — there's no literal-vs-parameter collision on
   the bare `/documents` path itself.
4. The router's `dependencies=[Depends(require_api_key)]` resolves
   first, before the route function runs at all: the API key checks
   out, so nothing is rejected here.
5. The route function's own parameters resolve: `skip` defaults to
   `0`, `limit` is parsed and validated as `2` against its
   `Query(10, ge=1, le=100)` constraints, and `Depends(
   get_knowledge_base_service)` resolves to the cached service
   instance.
6. The function body runs: `all_documents = service.
   get_all_documents()`, slices `[0:2]`, and builds a `DocumentPage`
   with `total=len(all_documents)` (the full count, not `2`).
7. FastAPI validates the returned `DocumentPage` against its
   `response_model` and serializes it to JSON.
8. Control returns to the logging middleware, which logs the request
   and its status code, then hands the response back to `uvicorn`.

**Request 2 — `GET /tickets/9999`, a valid key, no such ticket:**

1–5. Identical shape to above, except routing now has to correctly
   pass over `""` and `/mismatches` before matching `/{ticket_id}`
   with `ticket_id=9999` — which only works correctly because
   `/mismatches` was declared *before* `/{ticket_id}` in the file.
6. The function body runs: `service.get_ticket_by_id(9999)` returns
   `None`.
7. Because the function explicitly checks for `None` and raises
   `HTTPException(status_code=404, ...)` right there, execution never
   reaches a `return` statement at all — no `response_model`
   validation happens on this path, because there's no model instance
   being returned to validate.
8. FastAPI's exception handling converts the raised `HTTPException`
   into a `404` response with the given `detail`, which flows back
   through the middleware and out to the client exactly like a normal
   response would.

A quiz question shaped like "why doesn't returning `None` from
`get_ticket` produce a clean 404 on its own" is really asking whether
this distinction — an explicitly raised `HTTPException` vs. a
`response_model` check quietly failing on bad data — is understood.

---

## Quiz-Prep Quick Reference

| Term | One-line definition |
|---|---|
| OpenAPI schema | The auto-generated JSON description of every route, parameter, and response shape; `/docs`, `/redoc`, and `/openapi.json` are three views of the same schema |
| Swagger UI (`/docs`) | The interactive API explorer, with "Try it out" sending real requests |
| ReDoc (`/redoc`) | The read-only, reference-style rendering of the same schema |
| Offset pagination | The `skip`/`limit` pattern — a common convention, not a mandated REST standard |
| Pagination envelope | `{items, total, skip, limit}` — `total` must reflect the full collection, not the current page |
| `422 Unprocessable Entity` | FastAPI's default status for a *request* validation failure (bad type, failed constraint) |
| `401 Unauthorized` | Missing or invalid credentials entirely |
| `403 Forbidden` | Valid credentials, but not permitted to do this specific thing (not used in this codebase) |
| Response validation failure | A route's own return value doesn't satisfy its declared `response_model` — surfaces as a `500`, not a `404`/`422` |
| Route ordering rule | Literal/specific paths (`/stale`, `/mismatches`) must be declared before a parameterized path (`/{id}`) that could also match them |
| pytest fixture | A `@pytest.fixture`-decorated function supplying setup, injected into a test by matching its parameter name |
| `autouse=True` | A fixture that runs for every test in scope automatically, without being named as a parameter |
| `tmp_path` / `capsys` | Built-in fixtures: a fresh temp directory per test / captured stdout+stderr for a test |
| `TestClient` | Drives a real FastAPI/Starlette app in-process, no real server socket; built on `httpx` (migrating toward `httpx2`) |
| Unit test vs. integration test | Tests pure logic in isolation vs. tests the real, running, wired-together app |
| `@pytest.mark.parametrize` | Runs one test function repeatedly over a list of input/expected-value tuples |
| Regression test | A test that exists specifically to catch a previously-real bug if it's ever reintroduced |

---

## Common Pitfalls & Anti-Patterns

- **Declaring a parameterized route before the literal routes it could
  collide with.** The single most important mistake from today —
  `/{document_id}` or `/{ticket_id}` declared before `/stale` or
  `/mismatches` silently breaks the literal route with a confusing
  `422`, and passes almost every manual happy-path check.
- **Letting a function typed to return a `response_model` actually
  return `None` on a "not found" path**, instead of explicitly raising
  `HTTPException(status_code=404, ...)`. The symptom (a generic `500`)
  gives almost no hint that the real bug is a missing `None` check.
- **Treating `skip`/`limit` as if it were a REST-wide standard.** It's
  one common convention among several legitimate designs (cursor-based
  pagination, `page`/`page_size`, `Link` headers) — worth knowing
  there are alternatives, not just this one shape.
- **Setting `total` to the current page's length instead of the full
  collection size.** This silently breaks pagination for any client
  actually trying to page through all the results — every page looks
  like the last one.
- **Confusing `401` and `403`.** `401` is "no valid credentials
  presented at all"; `403` is "valid credentials, but not allowed to
  do this." This codebase only ever needs `401`, but conflating the
  two is a common, quiz-worthy mistake.
- **Forgetting that `ClassVar` registries never clear themselves.**
  Without the `autouse=True` `reset_registries` fixture (and its
  matching `get_knowledge_base_service.cache_clear()` call), tests
  would silently leak state into one another in whatever order pytest
  happens to run them — a subtle, order-dependent kind of failure that
  can be very confusing to debug from the symptom alone.
- **Writing a second, separate `TestClient(app)` inside a new test
  file** instead of reusing the shared `client` fixture from
  `conftest.py`. Functionally similar in the moment, but it duplicates
  setup that belongs in one shared place, and skips whatever cleanup
  ordering the shared fixtures were designed around.
- **Reacting to every `pytest` warning as if it were a failure.**
  Warnings and test results are reported separately — a suite can be
  green (`N passed`) while still printing a `warnings summary` block
  underneath it. Read the actual pass/fail line, not just whether
  anything was printed.

---

## Troubleshooting Guide

| Symptom | Likely Cause | Fix |
|---|---|---|
| A literal route (like `/stale` or `/mismatches`) returns a `422` instead of its expected data | It's declared *after* a parameterized route (`/{document_id}`, `/{ticket_id}`) that structurally matches it first | Move the literal route's declaration above the parameterized one in the file |
| A `500 Internal Server Error` with no useful detail in the response body | Almost always a response validation failure — the route returned something (often `None`) that doesn't satisfy its own `response_model` | Check the server's own console output/traceback (not the HTTP response) for the real cause; add or fix a `None` check that raises `HTTPException` instead |
| `test_..._rejects_limit_over_max` (or similar) fails with `200` instead of `422` | The `le=100` (or matching) constraint is missing from the `Query(...)` declaration | Compare the parameter's `Query(...)` call against the working reference route |
| A test passes in isolation but fails when the whole suite runs together | `ClassVar` registry state (or the cached `KnowledgeBaseService`) leaking between tests | Confirm `reset_registries` is present in `conftest.py` and is `autouse=True`; confirm it also calls `get_knowledge_base_service.cache_clear()` |
| `pytest -v` prints a `warnings summary` block mentioning `httpx`/`httpx2` | `TestClient`'s underlying `httpx` dependency is being deprecated in favor of `httpx2` in current Starlette versions | Safe to ignore for now — check the actual `N passed`/`N failed` line, which is unaffected; install `httpx2` alongside existing dependencies if the warning should be silenced |
| A new test file's tests don't reset shared state between runs | A second, separate `TestClient(app)` (or otherwise bypassing the shared fixtures) was created instead of using `conftest.py`'s `client` fixture | Request `client` and `auth_headers` as parameters instead of constructing new ones |
| Swagger UI's `/docs` page shows a route with the wrong parameters, or missing ones entirely | The OpenAPI schema is generated from the code as written — a stale browser tab, not a stale schema, is the usual cause | Refresh `/docs`; if it's still wrong, the discrepancy is in the code itself, not a caching issue |

---
*DevMate — Northbeam Engineering Assistant — Notes: OpenAPI & Swagger UI, REST API Design (Pagination & Status Codes), Route Declaration Order, pytest Testing*

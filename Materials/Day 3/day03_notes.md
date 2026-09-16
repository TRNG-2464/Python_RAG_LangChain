# DevMate Notes
## Topic: FastAPI, Dependency Injection, Pydantic Models, Routers, Middleware, and Security Schemes

---

## Executive Summary

Today turned DevMate from a script you run by hand into a real,
running web service — the same domain objects and the same two
business-question functions built earlier, now reachable over HTTP.
Nothing about `Document`, `Ticket`, `find_stale_documents`, or the
team-mismatch logic changed; an entirely new layer was built *around*
that existing logic. That's the single most important idea to carry
out of today: a well-separated business layer doesn't need to change
just because you change how the outside world reaches it.

Five ideas make up "FastAPI" as a topic, and each gets its own section
below: **Pydantic models** (data validation), **dependency injection**
(how routes get the things they need), **routers** (organizing many
routes), **middleware** (code that wraps every request), and
**security schemes** (a specific, OpenAPI-aware flavor of dependency
injection used for authentication).

---

## Deep Dive: FastAPI Fundamentals

- **What FastAPI actually is.** FastAPI is not a from-scratch web
  framework — it's built directly on top of two other libraries:
  **Starlette** (which provides the actual ASGI web framework
  machinery: routing, middleware, request/response objects) and
  **Pydantic** (which provides data validation). FastAPI's own
  contribution is the layer that connects your Python type hints to
  both of those — reading a function's parameter types to know what to
  validate, and using Pydantic models to generate an OpenAPI schema
  automatically.
- **ASGI, briefly.** ASGI (Asynchronous Server Gateway Interface) is
  the modern, async-capable standard for how a Python web application
  talks to a web server — the async-friendly successor to WSGI (Web
  Server Gateway Interface), the older standard frameworks like
  classic Flask and Django originally used. `uvicorn` is an ASGI
  *server*; FastAPI (via Starlette) is the ASGI *application* it runs.
  This is why FastAPI can support `async def` route functions natively
  — the underlying protocol was designed for it from the start, unlike
  WSGI.
- **Type hints are the entire mechanism, not documentation.** Every
  path parameter, query parameter, and request body FastAPI validates
  comes directly from reading your function's own parameter type
  hints — `document_id: int` in a path means FastAPI converts and
  validates the URL segment as an integer before your function body
  ever runs, and rejects the request with a `422 Unprocessable Entity`
  automatically if it can't.
- **`def` vs `async def` path operation functions — this is a genuine,
  precise distinction, not a style choice.** A plain `def` route
  function is automatically run by FastAPI in an external thread pool
  — this is why a normal, blocking, synchronous function (like every
  route written today) doesn't freeze the whole server while it runs.
  An `async def` route function instead runs directly on the same
  event loop as everything else. The trap: if you write `async def`
  and then call something slow and *blocking* inside it without
  `await`ing an async-aware version, you block that single event loop
  for **every concurrent request being served**, not just your own —
  a plain `def` function doing the same slow blocking work would only
  tie up its own thread. Today's routes are all plain `def` on
  purpose, for exactly this reason: nothing in them is `await`-aware.
- **Auto-generated docs are a byproduct, not a separate feature.**
  `/docs` (Swagger UI), `/redoc` (ReDoc, an alternate viewer), and
  `/openapi.json` (the raw machine-readable schema) are all generated
  from the *same* underlying OpenAPI schema FastAPI builds by
  inspecting your routes, path/query parameter types, `response_model`
  declarations, and security dependencies. Nothing about any of these
  three pages is separately authored — they're three different
  renderings of one schema.
- **`fastapi dev` / `fastapi run` vs raw `uvicorn`.** `fastapi dev
  app/api/main.py` is a CLI wrapper (from the separate `fastapi-cli`
  package, bundled by installing `fastapi[standard]`) around the exact
  same `uvicorn` server underneath. It auto-detects the `app` object
  in the file you point it at instead of needing an explicit
  `module:app` import string, defaults to binding only to
  `127.0.0.1` (safer for local development), and enables auto-reload
  by default. `fastapi run` is the equivalent for production — reload
  off, binds to `0.0.0.0` so it's reachable from outside the machine
  (appropriate for a container).

---

## Deep Dive: Pydantic Models

- **A Pydantic `BaseModel` validates the moment it's constructed.**
  This is the central difference from the plain Python classes
  (`Document`, `Ticket`, etc.) built earlier: `DocumentOut(id="not a
  number", ...)` doesn't just silently store a bad value — it raises a
  `ValidationError` immediately, naming exactly which field failed and
  why. A plain class with `self.id = document_id` has no such
  protection; it only breaks later, wherever that bad value eventually
  gets used.
- **Pydantic v2's default "lax" validation mode allows some type
  coercion**, not just outright type matching — a numeric string
  passed for an `int` field, for instance, can be accepted and
  converted rather than rejected outright, while a clearly incompatible
  value (like the string `"banana"` for an `int`) is still rejected. A
  model can be configured for **strict** validation (rejecting anything
  that isn't already exactly the declared type) via `model_config =
  ConfigDict(strict=True)` — today's schemas use the default lax mode.
- **`model_config = ConfigDict(...)` is Pydantic v2's configuration
  pattern.** `from_attributes=True` (used on `DocumentOut` and
  `TicketOut`) is the v2 name for what Pydantic v1 called `orm_mode`
  — it's what allows `SomeModel.model_validate(plain_object)` to read
  values off a plain object's **attributes** (`obj.id`, `obj.title`,
  ...) instead of only accepting a dictionary. Without it,
  `model_validate` would raise an error on anything that isn't already
  dict-shaped.
- **Three ways to end up with a validated instance:** constructing one
  directly with keyword arguments (`StaleDocumentOut(id=1, ...)` —
  used whenever a field, like `days_since_reviewed`, comes from a
  method call rather than a plain attribute); `SomeModel.model_validate(obj)`
  (reading attributes off an existing object, requires
  `from_attributes=True`); and `SomeModel.model_validate_json(json_string)`
  (parsing a raw JSON string directly). All three run the exact same
  validation logic — they differ only in where the raw data comes from.
- **`model_dump()` / `model_dump_json()`** convert a validated instance
  back out — to a plain Python `dict`, or directly to a JSON string,
  respectively. **Naming note, worth knowing cold:** these are the
  Pydantic **v2** names. Pydantic v1 (which a lot of older tutorials,
  Stack Overflow answers, and even some still-unupdated library docs
  show) used `.dict()` and `.json()` instead, and `orm_mode` instead of
  `from_attributes`. If example code found online doesn't match what's
  in this codebase, checking which Pydantic major version it was
  written for is the first thing to check — the concepts transfer, the
  method names don't.
- **`response_model=SomeSchema` on a route does two jobs at once, not
  one:** it validates the *outgoing* data against that schema (same as
  request validation, just in the other direction), **and** it
  silently **filters out any extra fields** the returned object or
  dict has that aren't declared on the schema — even if the underlying
  domain object has more attributes than the response model exposes.
  This is a genuine security-relevant feature, not just a formatting
  convenience: it's what stops an accidental internal field from
  leaking into an API response just because it happened to exist on
  the object being returned.

---

## Deep Dive: Dependency Injection

- **The core pattern:** a route function declares a parameter with a
  default of `Depends(some_provider_function)`. FastAPI calls
  `some_provider_function()` itself and passes the return value in as
  that parameter — the route function never constructs its own
  dependency and never reaches into a global variable for it. The
  provider function can itself take parameters (including its own
  `Depends(...)`), and FastAPI resolves the whole chain.
- **Caching scope — precise and worth stating carefully, because it's
  easy to get backwards.** By default, FastAPI caches a dependency's
  return value **only for the duration of a single request**: if two
  different parameters (or two different sub-dependencies) within that
  *same* request both depend on the same provider function, it's
  called exactly once and the cached value is reused for both. A
  **new, separate request always calls the provider fresh again** —
  this per-request cache does **not**, by itself, persist anything
  across requests. (`Depends(dep, use_cache=False)` disables even the
  within-one-request caching, forcing a fresh call every single time
  it's needed, even twice in the same request — rarely needed, but
  it exists.)
- **`@lru_cache` is a completely different, Python-level mechanism —
  not a FastAPI feature.** Wrapping the provider function itself in
  `@lru_cache` (from `functools`, standard library) makes the *cache
  live on the function object*, which persists for as long as the
  running process does — across every request, not just one. This is
  the actual mechanism that makes `get_knowledge_base_service` load
  `docs/` and `tickets.csv` from disk exactly once per server run,
  rather than once per request. Worth internalizing the distinction:
  FastAPI's own per-request caching would *not* have prevented
  re-reading every file on every single request — `@lru_cache` is
  what does that.
- **A consequence of `@lru_cache` worth naming explicitly:** the
  cached `KnowledgeBaseService` instance is the exact same object,
  shared across every concurrent request being handled by the server.
  That's safe here because nothing ever mutates it after construction
  — every method only reads. If a future service needed to be *written
  to* during a request, sharing one `@lru_cache`d mutable instance
  across concurrent requests would be a real concurrency hazard.
- **`Depends(...)` as a route parameter vs. `dependencies=[Depends(...)]`
  on a router or route — two different jobs.** The parameter form
  captures the dependency's return value into a variable your route
  body uses (`service: KnowledgeBaseService = Depends(get_knowledge_base_service)`).
  The `dependencies=[...]` list form runs a dependency purely for its
  *side effects* (or to let it raise an exception) — its return value
  is discarded entirely, and no route function parameter receives it.
  `require_api_key` is written to return the validated key, but
  nothing in `documents.py` or `tickets.py` actually captures that
  return value, because it's wired in via the router's `dependencies=[...]`
  list, not as a per-route parameter.

---

## Deep Dive: Security Schemes

- **`fastapi.security.APIKeyHeader`** is one of three "API key" style
  security scheme classes FastAPI provides — the other two are
  `APIKeyQuery` (the key travels in the URL as a query parameter) and
  `APIKeyCookie` (the key comes from a cookie). All three work
  identically in concept; they differ only in *where* the client is
  expected to place the key. A header is generally the better default
  for a secret value specifically because URLs (and therefore query
  parameters) tend to get logged, cached, and saved in far more places
  — browser history, web server access logs, shared links — than a
  header value ever does.
- **`Security(...)` vs. `Depends(...)` — the precise relationship,
  since it's easy to overstate.** `fastapi.Security` is literally
  implemented as a subclass of `fastapi.Depends` — not a separate
  mechanism. Its only actual addition is an optional `scopes`
  parameter, used for declaring OAuth2 scopes (not used anywhere in
  today's code, since `APIKeyHeader` doesn't have scopes). **The
  Swagger UI "Authorize" button and the OpenAPI security-scheme
  integration are not exclusive to `Security()`** — they appear
  because FastAPI detects that the dependency's callable (`APIKeyHeader`
  in this case) is an instance of `SecurityBase`, and that detection
  happens whether the dependency is wired up with `Security(...)` or
  plain `Depends(...)`. Using `Security(...)` for auth-flavored
  dependencies is the documented convention (and it's the only form
  that supports scopes, if a later security scheme needs them), but
  today's `require_api_key` would have produced the exact same
  Swagger UI Authorize behavior written as `Depends(_api_key_header)`
  instead of `Security(_api_key_header)`.
- **`auto_error=False` on `APIKeyHeader(name="X-API-Key", auto_error=False)`**
  changes what happens when the header is simply missing: instead of
  `APIKeyHeader` raising its own generic `403 Forbidden` automatically,
  it hands back `None`, letting `require_api_key`'s own code decide
  what to do (raising a `401` with a specific, DevMate-authored
  message). Without `auto_error=False`, a missing header would never
  even reach `require_api_key`'s own `if key != API_KEY` check — the
  library's own default error would fire first.
- **Why this whole scheme exists instead of checking headers by hand
  in middleware** (which was the very first version of this code,
  before being reworked): a manual `request.headers.get("X-API-Key")`
  check inside middleware enforces the *exact same rule* at runtime —
  a request without the right header is still rejected either way —
  but it's completely invisible to FastAPI's OpenAPI schema generation.
  Nothing about "this route needs a header" exists anywhere FastAPI can
  see it, so Swagger UI has no way to display a padlock icon or an
  Authorize button, and no way to attach the header automatically to a
  "Try it out" request. A `Security`/`Depends`-based scheme is
  route-aware and schema-aware specifically because it's declared as
  part of the route's own dependency graph, not hidden inside
  unconditional request-wrapping code.

---

## Deep Dive: Routers

- **`APIRouter()`** is a lightweight, standalone object you attach
  routes to independently of the main `FastAPI()` app instance — it
  supports the same `@router.get(...)`, `@router.post(...)`, etc.
  decorators `app` does. `app.include_router(some_router)` merges its
  routes into the running application. This is what keeps `main.py`
  from becoming one enormous file listing every single route directly.
- **`prefix="/documents"`** is prepended to every path defined on that
  router — a route decorated `@router.get("/stale")` actually serves
  `GET /documents/stale`, and `@router.get("")` serves exactly
  `GET /documents`.
- **`tags=["documents"]`** doesn't affect routing or behavior at all —
  it's purely a Swagger UI display grouping, controlling which
  collapsible section a route appears under on the `/docs` page.
- **`dependencies=[Depends(require_api_key)]` on the router itself**
  (rather than repeating it on every individual route) applies that
  dependency to every route the router defines, current and future —
  adding a new route to `tickets.py` automatically inherits the
  authorization requirement without anyone needing to remember to add
  it again.

---

## Deep Dive: Middleware

- **`@app.middleware("http")`** registers a function that wraps
  **every single request**, regardless of which route (or no route at
  all) ends up matching — this is the defining property of middleware
  as a concept, and the main thing that distinguishes it from a
  router-level dependency, which only applies to the routes on that
  specific router.
- **`call_next(request)`** is the hand-off point. Code written *before*
  `await call_next(request)` runs before the matching route (or a 404,
  if nothing matches); code written *after* it runs once that route's
  response already exists, and can inspect or even modify that
  response before it goes out.
- **Short-circuiting:** returning a response directly, without ever
  calling `call_next(...)`, skips the actual route handler entirely —
  it never runs. (This was exactly how the very first version of the
  API key check worked, before the security-scheme rework: a missing
  header caused middleware to return its own response immediately,
  bypassing routing altogether.)
- **Today's middleware does logging only, on purpose.** It's a
  legitimate, common use of middleware precisely *because* logging
  genuinely needs to apply unconditionally to everything — there's no
  meaningful sense in which only some routes should be logged, and
  logging has no reason to appear in an OpenAPI schema. That's the
  clean split to remember: **middleware for cross-cutting behavior
  that's schema-irrelevant and universally applicable; a dependency
  (via `Security`/`Depends`) for anything that's route-specific or
  needs to be visible in the API's own documentation.**

---

## Architectural Analysis: One Request, Start to Finish

Tracing a single `GET /documents/stale` request with a valid
`X-API-Key` header end to end, in the order things actually happen:

1. The request reaches `uvicorn` (whether started directly or via
   `fastapi dev`), which hands it to the FastAPI/Starlette application.
2. `log_requests` middleware begins timing and calls
   `await call_next(request)`, handing control forward.
3. FastAPI's routing matches the path to the `documents` router's
   `/stale` route.
4. Before the route function's body runs, the router's
   `dependencies=[Depends(require_api_key)]` resolves: `APIKeyHeader`
   reads the `X-API-Key` header, `require_api_key` compares it against
   the expected value. If it doesn't match, a `401` is raised **right
   here** — the route function below never executes at all.
5. If the key is valid, the route function's own
   `Depends(get_knowledge_base_service)` resolves — reusing the
   `@lru_cache`d instance from any prior request, or building it fresh
   exactly once if this is the very first request the server has
   handled.
6. The route function body runs: `service.get_stale_documents(90)`,
   then builds a list of `StaleDocumentOut` instances by hand.
7. Because the route declares `response_model=list[StaleDocumentOut]`,
   FastAPI validates that returned list against the schema and
   serializes it to JSON.
8. Control returns to `log_requests`, which now has the real response
   and its status code, logs the line, and returns the response to
   `uvicorn` to send back to the client.

A quiz question shaped like "put these in order" or "which step
happens first, the API key check or loading the KnowledgeBaseService"
is really just asking whether this sequence is understood — the answer
is that authorization (step 4) is deliberately positioned to happen
*before* anything else request-specific, so that rejected requests do
as little work as possible.

---

## Quiz-Prep Quick Reference

| Term | One-line definition |
|---|---|
| ASGI | The async-capable standard for how a Python app talks to a web server (Starlette/FastAPI's foundation; the successor to WSGI) |
| Path operation | FastAPI's term for one route + one HTTP method combination (e.g., `GET /documents`) |
| `response_model` | Declares a route's response schema; validates AND filters the returned data to exactly that shape |
| `Depends(fn)` | Tells FastAPI to call `fn` and inject its return value as a parameter |
| `dependencies=[Depends(fn)]` | Runs `fn` for its side effects only, on every route of a router (or one route); its return value is discarded |
| `Security(fn)` | A subclass of `Depends` adding an OAuth2 `scopes` parameter; conventional for auth dependencies, not required for OpenAPI integration |
| `SecurityBase` | The base class (`APIKeyHeader`, `OAuth2PasswordBearer`, etc.) FastAPI detects to populate OpenAPI security schemes / the Swagger "Authorize" button |
| `@lru_cache` | A standard-library decorator (not FastAPI-specific) that caches a function's return value across calls for the life of the process |
| `from_attributes=True` | Pydantic v2 config letting `model_validate()` read a plain object's attributes instead of requiring a dict (v1 called this `orm_mode`) |
| `model_dump()` / `model_dump_json()` | Pydantic v2 names for converting a model instance to a dict / JSON string (v1: `.dict()` / `.json()`) |
| `APIRouter` | A standalone collection of routes, merged into the app with `app.include_router(...)` |
| Middleware | Code wrapping every request regardless of route; invisible to the OpenAPI schema |
| `call_next(request)` | Inside middleware, hands control to the next layer (another middleware, or the matched route) and returns its response |

---

## Common Pitfalls & Anti-Patterns

- **Assuming `Depends()` alone caches across requests.** It doesn't —
  only within one request. Without `@lru_cache` on the provider
  function itself, `load_documents_from_folder("docs")` would re-run,
  and re-print every `SKIPPED` line, on every single request.
- **Confusing the two `dependencies` mechanisms.** A route parameter
  (`service: X = Depends(...)`) captures a return value you use. A
  router's `dependencies=[Depends(...)]` list runs something for its
  side effects and discards the return value — mixing these up (e.g.,
  expecting to receive the validated API key as a parameter somewhere
  it was declared via the `dependencies=[...]` list) leads to
  confusion about where a value "went."
- **Believing `Security()` is required for the Authorize button to
  appear.** It isn't — a plain `Depends()` wrapping a `SecurityBase`
  instance (like `APIKeyHeader`) produces identical OpenAPI/Swagger UI
  behavior. `Security()` only adds the optional `scopes` parameter.
- **Putting an authorization check in middleware and expecting it to
  show up in Swagger UI.** It won't — middleware is structurally
  invisible to OpenAPI schema generation, no matter how correctly it
  enforces the rule at runtime.
- **Writing `async def` on a route and then calling something slow and
  blocking inside it without awaiting an async-aware version.** This
  blocks the *entire* event loop — every other concurrent request the
  server is handling — not just the one making the slow call. A plain
  `def` route doing the same slow work only ties up its own thread
  from the pool.
- **Mixing up Pydantic v1 and v2 method names** when reading examples
  found online — `.dict()`/`.json()`/`orm_mode`/a nested `class
  Config:` are all v1; `.model_dump()`/`.model_dump_json()`/
  `from_attributes`/`model_config = ConfigDict(...)` are v2. This
  codebase is v2 throughout.
- **Forgetting `app.include_router(...)`.** Defining a router with
  routes on it does nothing on its own if it's never registered on the
  `app` — every route on it returns a `404`, indistinguishable from a
  typo in the URL, unless you specifically check whether the router
  was actually included.

---

## Troubleshooting Guide

| Symptom | Likely Cause | Fix |
|---|---|---|
| `422 Unprocessable Entity` | A path/query parameter or request body didn't match its declared type hint | Read the response body — FastAPI's default 422 response names exactly which field failed and why |
| `401` on every request, even with the header set | Header name typo (`X-Api-Key` vs `X-API-Key` — HTTP header names are case-insensitive, but a completely different name won't match), or the key value itself doesn't match `API_KEY` exactly | Print or log the received header value inside `require_api_key` temporarily to compare it byte-for-byte against the expected constant |
| `404` on a route you're sure you defined | The router was never registered with `app.include_router(...)`, or the router's `prefix` doesn't match the URL being requested | Check `main.py` for the `include_router` call; check the router's `prefix` against the exact URL |
| No padlock icon on a route in Swagger UI | The route's router doesn't have `dependencies=[Depends(require_api_key)]`, or the route was added to the wrong router entirely | Compare against `documents.py`, which is the confirmed-working reference |
| `SKIPPED` lines print on every single request instead of only at server startup | `@lru_cache` missing (or accidentally removed) from the dependency provider function | Confirm the decorator is directly above `def get_knowledge_base_service():` |
| A `500` error with no useful detail in the response body | Most likely a response validation failure — the route returned data that doesn't actually satisfy its own `response_model` (a missing required field, usually) | Check the server's own console output (not the HTTP response) for the full traceback; response validation errors are logged there even when the client only sees a generic 500 |
| `Could not find a default file to run, please provide an explicit path` | Ran `fastapi dev` with no file argument | Always run `fastapi dev app/api/main.py` from `backend\`, spelled out explicitly |
| Changes to a route aren't showing up after saving the file | The dev server wasn't actually running with reload enabled, or it's a second, stale server process still bound to the port from an earlier run | Confirm `fastapi dev` (not `fastapi run`) is being used locally, and check for an orphaned process still holding port 8000 |

---
*DevMate — Northbeam Engineering Assistant — Notes: FastAPI, Dependency Injection, Pydantic Models, Routers, Middleware, Security Schemes*

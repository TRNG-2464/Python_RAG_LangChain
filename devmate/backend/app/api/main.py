"""
FastAPI application entrypoint
Run from the /backend directory (with the .venv active):
    fastapi dev app/api/main.py
"""

import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routers import documents, tickets, analytics, ask

# a hardcoded mock API key - a real deployment would pull this from an env variable or
# a secrets manager, never from source code
API_KEY = "devmate-local-key"

PATHS_EXEMPT_FROM_AUTH = {"/", "/docs", "/openapi.json", "/redoc"}

app = FastAPI(title="DevMate", version="0.1.0")

"""
this runs for EVERY request, before it reaches any route function below.
Two jobs: reject requests missing a valid X-API-Key header (unless the path 
is exempt), and log every request's method, path, status code, and how
long it took to execute
"""
@app.middleware("http")
async def log_and_check_api_key(request: Request, call_next):

    start = time.perf_counter()

    if request.url.path not in PATHS_EXEMPT_FROM_AUTH:
        if request.headers.get("X-API-Key") != API_KEY:
            duration_ms = (time.perf_counter()-start) * 1000
            print(f"{request.method} {request.url.path} -> 401 ({duration_ms:.1f}ms)")

            #Returning here means call_next() never runs - the route function itself never excutes
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing or invalid x-API-Key header"}
            )

    """
    call_next actually invokes the matching route (or the next middleware, if there were more than one)
    and it gives back its response - this is the pass control forward step
    """
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    print(f"{request.method} {request.url.path} -> {response.status_code} ({duration_ms:.1f}ms)")
    return response

@app.get("/")
def health_check() -> dict[str, str]:
    return {"status": "Ok", "Service":"DevMate"}

#register our routers here, so all endpoints are reachable
app.include_router(documents.router)
app.include_router(tickets.router)
app.include_router(analytics.router)
app.include_router(ask.router)
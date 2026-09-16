"""
Shared API-key security scheme

Declaring this with fastapi.security (instead of manually reading the header in middleware)
makes FastAPI itself aware that certain routes require an api key header (it shows up in the auto-generated
OpenAPI schema, which is what makes Swagger UI display the 'authentication' button and lets you supply
your own api key for authentication)
"""

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

API_KEY = "devmate-local-key"

"""
auto_error=False: if the header is missing, then APIKeyHeader hands back
None instead of raising its own generic 403 - that lets require_api_key
raise a 401 error with a more clear, DevMate-specific message instead
"""
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def require_api_key(key: str | None = Security(_api_key_header)) -> str:
    if key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid X-API-Key header"
        )
    return key
"""
This is our shared pytest fixtures for the test suite.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_knowledge_base_service
from app.api.main import app
from app.models import Comment, Document, Ticket, User

AUTH_HEADERS = {"X-API-Key": "devmate-local-key"}

@pytest.fixture(autouse=True)
def reset_registries():
    """
    Document/Ticket/Comment/User each keep a class-level 'registry' list that acts
    as a single, shared, mutable list every constructor call appends to, regardless of which test/request
    created the object. Without resetting between these tests, objects built by one test can silently leak
    into every test that runs after it within the same pytest session - and that can specifically
    corrupt our get by id endpoints, which the team mismatch logic depends on directly.

    autouse=True means that every test in this whole suite gets this fixture automatically and no test file
    needs to explicitly request it by name
    """
    yield
    Document.registry.clear()
    Ticket.registry.clear()
    User.registry.clear()
    Comment.registry.clear()

    """
    The knowledgeBaseService provider is using @lru-cache at the process level -
    clear that cache as well so that the NEXT test that touches the real app will
    rebuild it fresh instead of using any stale instance that had been built by 
    an earlier test
    """
    get_knowledge_base_service.cache_clear()

@pytest.fixture
def client() -> TestClient:
    #A fresh TestClient wrapping the real FastAPI app, for integration tests
    return TestClient(app)

@pytest.fixture
def auth_headers() -> dict[str, str]:
    return AUTH_HEADERS
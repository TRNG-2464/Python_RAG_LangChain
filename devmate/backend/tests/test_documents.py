"""
TestClient integration tests for the /documents routes

unlike test_loader.py, these exercise the REAL running fastapi app -
routing, dependency injection, the security scheme, and response validation
all included - through fastapi.testclient.TestClient, which drives the ap
in-process without needing an actual server or network socket.
"""

def test_list_documents_requires_api_key(client):
    response = client.get("/documents")

    assert response.status_code == 401

def test_list_documents_returns_paginated_envelope(client, auth_headers):
    response = client.get("/documents", headers=auth_headers)

    assert response.status_code==200
    body = response.json()
    assert body["total"] == 5
    assert body["skip"] == 0
    assert body["limit"] == 10
    assert len(body["items"]) == 5

def test_list_documents_respects_limit(client, auth_headers):
    response = client.get("/documents?limit=2", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 5
    assert body["limit"] == 2

def test_list_documents_rejects_limit_over_max(client, auth_headers):
    response = client.get("/documents?limit=500", headers=auth_headers)

    #FastAPI's own request validation will return 422 before any route code runs
    assert response.status_code == 422

def test_get_document_by_id_found(client, auth_headers):
    response = client.get("/documents/1", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() ["id"] == 1

def test_get_by_id_not_found(client, auth_headers):
    response = client.get("/documents/9999", headers=auth_headers)
    assert response.status_code == 404

def test_stale_documents_endpoint_still_reachable(client, auth_headers):
    response = client.get("/documents/stale", headers=auth_headers)

    assert response.status_code == 200
    titles = {document["title"] for document in response.json()}
    assert "Incident Response Runbook" in titles
    assert "Deploy Pipeline Wiki" in titles
"""
TestClient integration tests for the /tickets routes
 Answer key to phase B student challenge for day 4
"""

def test_list_tickets_requires_api_key(client):
    response = client.get("/tickets")
    assert response.status_code == 401

def test_list_tickets_returns_paginated_envelope(client, auth_headers):
    response = client.get("/tickets", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["skip"] == 0
    assert body["limit"] == 10
    assert len(body["items"]) == 3

def test_list_tickets_respects_limit(client, auth_headers):
    response = client.get("/tickets?limit=2", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2

def test_list_tickets_rejects_limit_over_max(client, auth_headers):
    response = client.get("/tickets?limit=500", headers=auth_headers)

    assert response.status_code == 422

def test_get_ticket_by_id_found(client, auth_headers):
    response = client.get("/tickets/1", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == 1
    assert body["title"] == "Runbook missing rollback step"

def test_get_ticket_by_id_not_found(client, auth_headers):
    response = client.get("/tickets/9999", headers=auth_headers)

    assert response.status_code == 404

def test_mismatches_endpoint_still_reachable(client, auth_headers):
    response = client.get("/tickets/mismatches", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["ticket_id"] == 1
    assert body[0]["assignee_team"] == "Platform"
    assert body[0]["owner_team"] == "SRE"
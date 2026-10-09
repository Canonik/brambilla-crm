"""Mirrors the organizers' form check: health, token, reset, migrate, agente shape."""
import pytest


def test_health_no_token(anon):
    r = anon.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["version"] == "2026-09"
    ui = body["ui"]
    assert isinstance(ui, dict) and ui
    for key in ("companies", "contacts", "deals", "tickets", "lists", "assistant"):
        assert key in ui, f"ui map misses {key}"
        assert ui[key].startswith("/")


def test_ui_routes_serve_html(anon):
    r = anon.get("/health")
    for route in r.json()["ui"].values():
        page = anon.get(route, follow_redirects=True)
        assert page.status_code == 200, route
        assert "text/html" in page.headers.get("content-type", ""), route


@pytest.mark.parametrize("path", ["/crm/v3/objects/contacts", "/crm/v3/properties/companies", "/crm/v3/pipelines/deals"])
def test_api_without_token_401(anon, path):
    r = anon.get(path)
    assert r.status_code == 401
    body = r.json()
    assert body["status"] == "error"
    assert body["category"] == "INVALID_AUTHENTICATION"
    assert "correlationId" in body


def test_wrong_token_401(anon):
    r = anon.get("/crm/v3/objects/contacts", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


@pytest.mark.parametrize("path", ["/__reset", "/__migrate", "/__agente"])
def test_organizer_endpoints_need_token(anon, path):
    r = anon.post(path, json={})
    assert r.status_code == 401


def test_reset_is_fast_and_idempotent(client):
    import time

    for _ in range(3):
        t0 = time.time()
        r = client.post("/__reset")
        assert r.status_code == 204, r.text
        assert time.time() - t0 < 2.0, "reset must be fast (called hundreds of times)"
    r = client.get("/crm/v3/objects/contacts")
    assert r.status_code == 200
    assert r.json()["results"] == []
    pipes = client.get("/crm/v3/pipelines/deals").json()["results"]
    assert [p["id"] for p in pipes] == ["default"], "fresh account has only the default deal pipeline"
    stages = [s["id"] for s in pipes[0]["stages"]]
    assert stages == ["appointmentscheduled", "qualifiedtobuy", "presentationscheduled", "decisionmakerboughtin", "contractsent", "closedwon", "closedlost"]
    tpipes = client.get("/crm/v3/pipelines/tickets").json()["results"]
    assert len(tpipes) == 1 and tpipes[0]["id"] == "0"
    props = {p["name"] for p in client.get("/crm/v3/properties/companies").json()["results"]}
    assert "id_legacy" not in props, "custom properties come from the migration, not the reset"
    assert {"name", "domain", "city", "state", "hs_additional_domains"} <= props


def test_migrate_bad_body(client):
    r = client.post("/__migrate", json={})
    assert r.status_code in (400, 422)
    r = client.post("/__migrate", json={"export_url": "http://127.0.0.1:9/nothing.zip"})
    assert r.status_code >= 400


def test_agente_contract_shape(client):
    """Only the shape: a nonsense message should still give a 200 with a reply."""
    body = {
        "context": {"now": "2026-12-02T10:00:00+01:00", "user": "elena.silvestri@brambillaforniture.it"},
        "messages": [{"role": "user", "content": "ciao"}],
    }
    r = client.post("/__agente", json=body, timeout=65)
    assert r.status_code == 200, r.text[:300]
    assert isinstance(r.json().get("reply"), str)

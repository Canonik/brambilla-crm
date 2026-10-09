"""The brief points at HubSpot's 2026-09 documentation, whose URLs carry the version in the
path (`/crm/objects/2026-09/contacts`). The organizer's form check used that family. Every
legacy family must therefore also answer under its dated twin, with the same shapes."""
import uuid

V = "2026-09"


def _mk(client, object_type, props):
    r = client.post(f"/crm/objects/{V}/{object_type}", json={"properties": props})
    assert r.status_code == 201, (object_type, r.status_code, r.text[:200])
    return r.json()["id"]


def test_dated_objects_and_search(client):
    tag = uuid.uuid4().hex[:8]
    cid = _mk(client, "contacts", {"email": f"dated-{tag}@example.com", "firstname": "Dated"})
    r = client.get(f"/crm/objects/{V}/contacts/{cid}")
    assert r.status_code == 200 and r.json()["id"] == cid
    r = client.post(f"/crm/objects/{V}/contacts/search", json={"filterGroups": [{"filters": [{"propertyName": "email", "operator": "EQ", "value": f"dated-{tag}@example.com"}]}]})
    assert r.status_code == 200 and r.json()["total"] >= 1
    r = client.patch(f"/crm/objects/{V}/contacts/{cid}", json={"properties": {"firstname": "Dated2"}})
    assert r.status_code == 200 and r.json()["properties"]["firstname"] == "Dated2"


def test_dated_properties(client):
    r = client.get(f"/crm/properties/{V}/companies")
    assert r.status_code == 200 and any(p["name"] == "name" for p in r.json()["results"])
    r = client.get(f"/crm/properties/{V}/companies/name")
    assert r.status_code == 200 and r.json()["name"] == "name"


def test_dated_pipelines(client):
    r = client.get(f"/crm/pipelines/{V}/deals")
    assert r.status_code == 200, r.text[:200]
    ids = {p["id"] for p in r.json()["results"]}
    assert "default" in ids
    r = client.get(f"/crm/pipelines/{V}/deals/default/stages")
    assert r.status_code == 200 and any(s["id"] == "closedwon" for s in r.json()["results"])
    r = client.get(f"/crm/pipelines/{V}/tickets")
    assert r.status_code == 200 and r.json()["results"]


def test_dated_owners(client):
    r = client.get(f"/crm/owners/{V}/")
    if r.status_code == 404:
        r = client.get(f"/crm/owners/{V}")
    assert r.status_code == 200 and "results" in r.json()


def test_dated_lists(client):
    tag = uuid.uuid4().hex[:8]
    co = _mk(client, "companies", {"name": f"Dated list co {tag}"})
    r = client.post(f"/crm/lists/{V}", json={"name": f"Dated list {tag}", "objectTypeId": "0-2", "processingType": "MANUAL"})
    assert r.status_code in (200, 201), r.text[:200]
    lid = r.json()["list"]["listId"] if "list" in r.json() else r.json()["listId"]
    r = client.put(f"/crm/lists/{V}/{lid}/memberships/add", json=[co])
    assert r.status_code == 200, r.text[:200]
    r = client.get(f"/crm/lists/{V}/{lid}/memberships")
    assert r.status_code == 200 and {str(x["recordId"]) for x in r.json()["results"]} == {co}
    r = client.get(f"/crm/lists/{V}/object-type-id/0-2/name/Dated list {tag}")
    assert r.status_code == 200
    r = client.get(f"/crm/lists/{V}/{lid}")
    assert r.status_code == 200
    r = client.delete(f"/crm/lists/{V}/{lid}")
    assert r.status_code == 204


def test_dated_record_associations_and_batches(client):
    tag = uuid.uuid4().hex[:8]
    c = _mk(client, "contacts", {"email": f"dated-assoc-{tag}@example.com"})
    co = _mk(client, "companies", {"name": f"Dated assoc co {tag}"})
    d = _mk(client, "deals", {"dealname": f"Dated deal {tag}", "pipeline": "default", "dealstage": "appointmentscheduled"})
    r = client.put(f"/crm/objects/{V}/contacts/{c}/associations/companies/{co}", json=[{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 279}])
    assert r.status_code in (200, 201), r.text[:200]
    r = client.put(f"/crm/objects/{V}/deals/{d}/associations/default/companies/{co}")
    assert r.status_code in (200, 201), r.text[:200]
    r = client.get(f"/crm/objects/{V}/contacts/{c}/associations/companies")
    assert r.status_code == 200, r.text[:200]
    res = r.json()["results"]
    assert str(res[0]["toObjectId"]) == co and "associationTypes" in res[0], res
    r = client.post(f"/crm/associations/{V}/deals/contacts/batch/create", json={"inputs": [{"from": {"id": d}, "to": {"id": c}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 3}]}]})
    assert r.status_code in (200, 201), r.text[:200]
    r = client.post(f"/crm/associations/{V}/deals/contacts/batch/read", json={"inputs": [{"id": d}]})
    assert r.status_code == 200, r.text[:200]
    assert {str(t["toObjectId"]) for x in r.json()["results"] for t in x["to"]} == {c}
    r = client.get(f"/crm/associations/{V}/contacts/companies/labels")
    assert r.status_code == 200 and r.json()["results"]
    r = client.delete(f"/crm/objects/{V}/contacts/{c}/associations/companies/{co}")
    assert r.status_code == 204
    assert client.get(f"/crm/objects/{V}/contacts/{c}/associations/companies").json()["results"] == []


def test_dated_exports(client):
    r = client.post(f"/crm/exports/{V}/export/async", json={"exportType": "VIEW", "format": "CSV", "exportName": "dated", "objectType": "contacts", "objectProperties": ["email"], "language": "EN"})
    assert r.status_code in (200, 202), r.text[:200]
    eid = r.json()["id"]
    r = client.get(f"/crm/exports/{V}/export/async/tasks/{eid}/status")
    assert r.status_code == 200 and r.json()["status"] in ("PENDING", "PROCESSING", "COMPLETE")

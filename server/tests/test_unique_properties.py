"""hasUniqueValue is enforced for API-created custom properties, not just advertised.

On a6e39d4 two companies could share the value of a custom property created with
hasUniqueValue=true and the second create answered 201 instead of 409.
"""
import concurrent.futures

from fastapi.testclient import TestClient

from app.main import app

from .conftest import H

PROP = {"name": "codice_esterno", "label": "Codice esterno", "type": "string", "fieldType": "text", "groupName": "companyinformation", "hasUniqueValue": True}


def _mk(api, name="codice_esterno", **extra):
    r = api.post("/crm/v3/properties/companies", headers=H, json=dict(PROP, name=name, **extra))
    assert r.status_code == 201, r.text


def test_duplicate_create_and_update_are_409(api):
    _mk(api)
    a = api.post("/crm/v3/objects/companies", headers=H, json={"properties": {"name": "A", "codice_esterno": "X1"}})
    assert a.status_code == 201, a.text
    b = api.post("/crm/v3/objects/companies", headers=H, json={"properties": {"name": "B", "codice_esterno": "X1"}})
    assert b.status_code == 409 and b.json()["category"] == "CONFLICT", b.text
    c = api.post("/crm/v3/objects/companies", headers=H, json={"properties": {"name": "C", "codice_esterno": "X2"}}).json()
    r = api.patch(f"/crm/v3/objects/companies/{c['id']}", headers=H, json={"properties": {"codice_esterno": "X1"}})
    assert r.status_code == 409, r.text
    assert api.get(f"/crm/v3/objects/companies/{c['id']}", headers=H).json()["properties"]["codice_esterno"] == "X2"


def test_empty_values_and_archived_records_do_not_collide(api):
    _mk(api)
    for n in ("A", "B"):
        assert api.post("/crm/v3/objects/companies", headers=H, json={"properties": {"name": n}}).status_code == 201
    a = api.post("/crm/v3/objects/companies", headers=H, json={"properties": {"name": "C", "codice_esterno": "Z"}}).json()
    assert api.delete(f"/crm/v3/objects/companies/{a['id']}", headers=H).status_code == 204
    assert api.post("/crm/v3/objects/companies", headers=H, json={"properties": {"name": "D", "codice_esterno": "Z"}}).status_code == 201


def test_creating_a_unique_property_over_existing_duplicates_is_rejected(api):
    api.post("/crm/v3/properties/companies", headers=H, json=dict(PROP, name="gia_duplicato", hasUniqueValue=False))
    for n in ("A", "B"):
        api.post("/crm/v3/objects/companies", headers=H, json={"properties": {"name": n, "gia_duplicato": "same"}})
    r = api.post("/crm/v3/properties/companies", headers=H, json=dict(PROP, name="gia_duplicato2"))
    assert r.status_code == 201  # no values yet
    r = api.post("/crm/v3/properties/companies", headers=H, json=dict(PROP, name="gia_duplicato"))
    assert r.status_code in (400, 409), r.text


def test_delete_property_and_reset_release_the_constraint(api):
    _mk(api)
    api.post("/crm/v3/objects/companies", headers=H, json={"properties": {"name": "A", "codice_esterno": "K"}})
    assert api.delete("/crm/v3/properties/companies/codice_esterno", headers=H).status_code == 204
    _mk(api, hasUniqueValue=False)
    assert api.post("/crm/v3/objects/companies", headers=H, json={"properties": {"name": "B", "codice_esterno": "K"}}).status_code == 201
    assert api.post("/__reset", headers=H).status_code == 204
    _mk(api)
    assert api.post("/crm/v3/objects/companies", headers=H, json={"properties": {"name": "C", "codice_esterno": "K"}}).status_code == 201


def test_parallel_creates_with_the_same_value_make_one_record(api):
    _mk(api)

    def create(i):
        with TestClient(app) as c:
            return c.post("/crm/v3/objects/companies", headers=H, json={"properties": {"name": f"P{i}", "codice_esterno": "RACE"}}).status_code

    with concurrent.futures.ThreadPoolExecutor(8) as ex:
        codes = list(ex.map(create, range(8)))
    assert codes.count(201) == 1 and all(c in (201, 409) for c in codes), codes


def test_upsert_by_unique_custom_property(api):
    _mk(api)
    body = {"inputs": [{"idProperty": "codice_esterno", "id": "U1", "properties": {"name": "Uno"}}]}
    r1 = api.post("/crm/v3/objects/companies/batch/upsert", headers=H, json=body)
    r2 = api.post("/crm/v3/objects/companies/batch/upsert", headers=H, json={"inputs": [{"idProperty": "codice_esterno", "id": "U1", "properties": {"city": "Roma"}}]})
    assert r1.status_code == 200 and r2.status_code == 200, (r1.text, r2.text)
    assert r1.json()["results"][0]["id"] == r2.json()["results"][0]["id"]
    assert api.post("/crm/v3/objects/companies/search", headers=H, json={"limit": 1}).json()["total"] == 1

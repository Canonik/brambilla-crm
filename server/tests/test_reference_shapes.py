"""Status codes and response fields taken from the 2026-09 reference pages (OpenAPI of each
endpoint), exercised through the dated URLs the organizer's checks use."""
import json

from .conftest import H

V = "2026-09"
BATCH_KEYS = {"status", "results", "startedAt", "completedAt"}


def _pair(api):
    c = api.post(f"/crm/objects/{V}/contacts", headers=H, json={"properties": {"email": "ref.shape@example.com"}}).json()["id"]
    co = api.post(f"/crm/objects/{V}/companies", headers=H, json={"properties": {"name": "Ref Co"}}).json()["id"]
    return c, co


def _spec(t=279):
    return [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": t}]


def test_association_batches(api):
    c, co = _pair(api)
    inp = {"inputs": [{"from": {"id": c}, "to": {"id": co}, "types": _spec()}]}
    r = api.post(f"/crm/associations/{V}/contacts/companies/batch/create", headers=H, json=inp)
    assert r.status_code == 201 and BATCH_KEYS <= set(r.json()), r.text
    r = api.post(f"/crm/associations/{V}/contacts/companies/batch/associate/default", headers=H, json={"inputs": [{"from": {"id": c}, "to": {"id": co}}]})
    assert r.status_code == 200 and BATCH_KEYS <= set(r.json()), (r.status_code, r.text)
    r = api.post(f"/crm/associations/{V}/contacts/companies/batch/labels/archive", headers=H, json=inp)
    assert r.status_code == 200 and BATCH_KEYS <= set(r.json()), (r.status_code, r.text)
    r = api.post(f"/crm/associations/{V}/contacts/companies/batch/archive", headers=H, json={"inputs": [{"from": {"id": c}, "to": [{"id": co}]}]})
    assert r.status_code == 200 and BATCH_KEYS <= set(r.json()), (r.status_code, r.text)
    assert api.get(f"/crm/objects/{V}/contacts/{c}/associations/companies", headers=H).json()["results"] == []


def test_association_labels(api):
    r = api.post(f"/crm/associations/{V}/contacts/companies/labels", headers=H, json={"label": "Referente", "name": "referente", "inverseLabel": "Azienda del referente"})
    assert r.status_code == 200 and r.json()["results"][0]["label"] == "Referente", (r.status_code, r.text)
    tid = r.json()["results"][0]["typeId"]
    r = api.put(f"/crm/associations/{V}/contacts/companies/labels", headers=H, json={"associationTypeId": tid, "label": "Referente 2"})
    assert r.status_code == 204
    assert api.delete(f"/crm/associations/{V}/contacts/companies/labels/{tid}", headers=H).status_code == 204


def test_labeled_record_association_is_201_default_is_documented(api):
    c, co = _pair(api)
    r = api.put(f"/crm/objects/{V}/contacts/{c}/associations/companies/{co}", headers=H, json=_spec())
    assert r.status_code == 201, (r.status_code, r.text)
    assert {"fromObjectTypeId", "fromObjectId", "toObjectTypeId", "toObjectId", "labels"} <= set(r.json())


def test_export_by_id_and_cancel_import_shapes(api):
    api.post(f"/crm/objects/{V}/contacts", headers=H, json={"properties": {"email": "exp.id@example.com"}})
    r = api.post(f"/crm/exports/{V}/export/async", headers=H, json={"exportType": "VIEW", "format": "CSV", "exportName": "uno", "objectType": "contacts", "objectProperties": ["email"], "language": "EN"})
    eid = r.json()["id"]
    g = api.get(f"/crm/exports/{V}/export/{eid}", headers=H)
    assert g.status_code == 200, g.text
    assert {"id", "createdAt", "updatedAt", "exportState", "exportType", "objectType", "objectProperties"} <= set(g.json())
    assert g.json()["exportState"] == "DONE" and g.json()["recordCount"] == 1
    assert api.get(f"/crm/exports/{V}/export/999999", headers=H).status_code == 404
    imp = api.post(f"/crm/imports/{V}", headers=H, data={"importRequest": json.dumps({"name": "i", "files": [{"fileName": "f.csv", "fileFormat": "CSV", "fileImportPage": {"hasHeader": True, "columnMappings": [{"columnObjectTypeId": "0-1", "columnName": "email", "propertyName": "email"}]}}]})}, files={"files": ("f.csv", b"email\nimp.cancel@example.com\n", "text/csv")}).json()
    c = api.post(f"/crm/imports/{V}/{imp['id']}/cancel", headers=H)
    assert c.status_code == 200 and {"status", "startedAt", "completedAt"} <= set(c.json()), c.text
    assert api.post(f"/crm/imports/{V}/999999/cancel", headers=H).status_code == 404


def test_list_record_memberships_and_all(api):
    co = api.post(f"/crm/objects/{V}/companies", headers=H, json={"properties": {"name": "In lista"}}).json()["id"]
    lid = api.post(f"/crm/lists/{V}", headers=H, json={"name": "Una", "objectTypeId": "0-2", "processingType": "MANUAL"}).json()["list"]["listId"]
    api.put(f"/crm/lists/{V}/{lid}/memberships/add", headers=H, json=[co])
    r = api.get(f"/crm/lists/{V}/records/0-2/{co}/memberships", headers=H)
    assert r.status_code == 200 and r.json()["total"] == 1, r.text
    m = r.json()["results"][0]
    assert m["listId"] == lid and {"listVersion", "isPublicList", "firstAddedTimestamp", "lastAddedTimestamp"} <= set(m)
    r = api.post(f"/crm/lists/{V}/records/memberships/batch/read", headers=H, json={"inputs": [{"objectTypeId": "0-2", "recordId": co}]})
    assert r.status_code == 200 and BATCH_KEYS <= set(r.json()), r.text
    r = api.post(f"/crm/lists/{V}/all", headers=H, json={"processingTypes": ["MANUAL"], "additionalProperties": []})
    assert r.status_code == 200 and [x["listId"] for x in r.json()["results"]] == [lid] and r.json()["total"] == 1, r.text
    other = api.post(f"/crm/lists/{V}", headers=H, json={"name": "Due", "objectTypeId": "0-2", "processingType": "MANUAL"}).json()["list"]["listId"]
    assert api.put(f"/crm/lists/{V}/{other}/memberships/add-from/{lid}", headers=H).status_code == 204
    assert api.get(f"/crm/lists/{V}/{other}/memberships", headers=H).json()["total"] == 1

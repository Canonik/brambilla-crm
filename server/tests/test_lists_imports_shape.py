"""Documented response shapes (2026-09): list membership updates spell the added ids
`recordsIdsAdded`; an import response carries `mappedObjectTypeIds`. Imports of odd files are
4xx or counted errors, never a 500."""
import json

from .conftest import H


def _list(api):
    co = [api.post("/crm/v3/objects/companies", headers=H, json={"properties": {"name": n}}).json()["id"] for n in ("A", "B")]
    lid = api.post("/crm/v3/lists", headers=H, json={"name": "L", "objectTypeId": "0-2", "processingType": "MANUAL"}).json()["list"]["listId"]
    return co, lid


def test_membership_updates_use_documented_spelling(api):
    (a, b), lid = _list(api)
    r = api.put(f"/crm/v3/lists/{lid}/memberships/add", headers=H, json=[a, b, "99999"])
    body = r.json()
    assert r.status_code == 200 and sorted(body["recordsIdsAdded"]) == sorted([a, b]), body
    assert body["recordIdsMissing"] == ["99999"] and body["recordIdsRemoved"] == []
    r = api.put(f"/crm/v3/lists/{lid}/memberships/remove", headers=H, json=[a])
    assert r.json()["recordIdsRemoved"] == [a] and r.json()["recordsIdsAdded"] == []
    r = api.put(f"/crm/v3/lists/{lid}/memberships/add-and-remove", headers=H, json={"recordIdsToAdd": [a], "recordIdsToRemove": [b]})
    assert r.json()["recordsIdsAdded"] == [a] and r.json()["recordIdsRemoved"] == [b]


def _import(api, csv_text, mappings):
    req = {"name": "i", "files": [{"fileName": "f.csv", "fileFormat": "CSV", "fileImportPage": {"hasHeader": True, "columnMappings": mappings}}]}
    return api.post("/crm/v3/imports", headers=H, data={"importRequest": json.dumps(req)}, files={"files": ("f.csv", csv_text.encode(), "text/csv")})


def test_import_response_has_mapped_object_type_ids(api):
    r = _import(api, "email,name\nimp1@example.com,Uno\n", [{"columnObjectTypeId": "0-1", "columnName": "email", "propertyName": "email"}, {"columnObjectTypeId": "0-2", "columnName": "name", "propertyName": "name"}])
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["mappedObjectTypeIds"] == ["0-1", "0-2"] and d["state"] == "DONE"
    assert d["metadata"]["counters"]["CREATED"] == 2 and "fileIds" in d["metadata"] and "objectLists" in d["metadata"]
    assert api.get(f"/crm/v3/imports/{d['id']}", headers=H).json()["mappedObjectTypeIds"] == ["0-1", "0-2"]


def test_odd_import_files_are_not_500(api):
    m = [{"columnObjectTypeId": "0-1", "columnName": "email", "propertyName": "email"}]
    assert _import(api, "", m).status_code < 500
    assert _import(api, "email\n", m).status_code == 200
    assert _import(api, "email\nnot-an-email\n", m).json()["metadata"]["counters"]["ERRORS"] == 1
    r = api.post("/crm/v3/imports", headers=H, data={"importRequest": json.dumps({"files": "x"})}, files={"files": ("f.csv", b"a\n1\n", "text/csv")})
    assert 400 <= r.status_code < 500, r.text

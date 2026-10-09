"""The 2026-09 date-versioned URL families answer exactly like their legacy twins.

The organizer's form check called /crm/objects/2026-09/contacts and got 404 before d818d52.
On a6e39d4 only objects and properties were mounted under the dated prefix: pipelines, lists,
imports, exports, owners, v4 associations and the record-association family were 404.
"""
from .conftest import H

V = "2026-09"


def _same(api, dated, legacy, method="GET", **kw):
    a = api.request(method, dated, headers=H, **kw)
    b = api.request(method, legacy, headers=H, **kw)
    assert a.status_code == b.status_code, (dated, a.status_code, a.text[:200], legacy, b.status_code)
    return a


def test_pipelines(api):
    r = _same(api, f"/crm/pipelines/{V}/deals", "/crm/v3/pipelines/deals")
    assert r.status_code == 200 and [p["id"] for p in r.json()["results"]] == ["default"]
    r = _same(api, f"/crm/pipelines/{V}/tickets/0/stages", "/crm/v3/pipelines/tickets/0/stages")
    assert r.status_code == 200 and r.json()["results"]


def test_lists_by_name_and_memberships(api):
    co = api.post("/crm/v3/objects/companies", headers=H, json={"properties": {"name": "Dormiente"}}).json()["id"]
    r = api.post(f"/crm/lists/{V}", headers=H, json={"name": "Clienti dormienti", "objectTypeId": "0-2", "processingType": "MANUAL"})
    assert r.status_code in (200, 201), r.text
    lid = r.json()["list"]["listId"]
    assert api.put(f"/crm/lists/{V}/{lid}/memberships/add", headers=H, json=[co]).status_code == 200
    r = _same(api, f"/crm/lists/{V}/object-type-id/0-2/name/Clienti%20dormienti", "/crm/v3/lists/object-type-id/0-2/name/Clienti%20dormienti")
    assert r.status_code == 200 and r.json()["list"]["listId"] == lid
    r = _same(api, f"/crm/lists/{V}/{lid}/memberships", f"/crm/v3/lists/{lid}/memberships")
    assert [x["recordId"] for x in r.json()["results"]] == [co]
    assert api.post(f"/crm/lists/{V}/search", headers=H, json={"query": "dormienti"}).json()["total"] == 1


def test_owners_and_imports(api):
    r = _same(api, f"/crm/owners/{V}", "/crm/v3/owners")
    assert r.status_code == 200 and "results" in r.json()
    r = _same(api, f"/crm/imports/{V}", "/crm/v3/imports")
    assert r.status_code == 200


def test_exports_create_status_and_public_download(api, client):
    api.post("/crm/v3/objects/contacts", headers=H, json={"properties": {"email": "dated.export@example.com", "firstname": "Datata"}})
    r = api.post(f"/crm/exports/{V}/export/async", headers=H, json={"exportType": "VIEW", "format": "CSV", "exportName": "c", "objectType": "contacts", "objectProperties": ["email", "firstname"], "language": "EN"})
    assert r.status_code in (200, 202), r.text
    eid = r.json()["id"]
    st = api.get(f"/crm/exports/{V}/export/async/tasks/{eid}/status", headers=H)
    assert st.status_code == 200 and st.json()["status"] == "COMPLETE", st.text
    dl = client.get(st.json()["result"])
    assert dl.status_code == 200 and "Datata" in dl.text


def test_associations_v4_batch_and_labels(api):
    c = api.post("/crm/v3/objects/contacts", headers=H, json={"properties": {"email": "dated.assoc@example.com"}}).json()["id"]
    co = api.post("/crm/v3/objects/companies", headers=H, json={"properties": {"name": "Dated Co"}}).json()["id"]
    r = api.post(f"/crm/associations/{V}/contacts/companies/batch/create", headers=H, json={"inputs": [{"from": {"id": c}, "to": {"id": co}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 279}]}]})
    assert r.status_code in (200, 201), r.text
    r = _same(api, f"/crm/associations/{V}/contacts/companies/batch/read", "/crm/v4/associations/contacts/companies/batch/read", "POST", json={"inputs": [{"id": c}]})
    assert r.status_code == 200 and str(r.json()["results"][0]["to"][0]["toObjectId"]) == co
    r = _same(api, f"/crm/associations/{V}/contacts/companies/labels", "/crm/v4/associations/contacts/companies/labels")
    assert {x["typeId"] for x in r.json()["results"]} >= {1, 279}


def test_record_associations_are_v4_shaped(api):
    d = api.post("/crm/v3/objects/deals", headers=H, json={"properties": {"dealname": "Dated deal", "dealstage": "appointmentscheduled"}}).json()["id"]
    co = api.post("/crm/v3/objects/companies", headers=H, json={"properties": {"name": "Dated Co 2"}}).json()["id"]
    r = api.put(f"/crm/objects/{V}/deals/{d}/associations/default/companies/{co}", headers=H)
    assert r.status_code in (200, 201), r.text
    r = _same(api, f"/crm/objects/{V}/deals/{d}/associations/companies", f"/crm/v4/objects/deals/{d}/associations/companies")
    res = r.json()["results"]
    assert str(res[0]["toObjectId"]) == co and res[0]["associationTypes"], res
    c = api.post("/crm/v3/objects/contacts", headers=H, json={"properties": {"email": "dated.rec@example.com"}}).json()["id"]
    r = api.put(f"/crm/objects/{V}/contacts/{c}/associations/deals/{d}", headers=H, json=[{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 4}])
    assert r.status_code in (200, 201), r.text
    assert {str(x["toObjectId"]) for x in api.get(f"/crm/objects/{V}/deals/{d}/associations/contacts", headers=H).json()["results"]} == {c}
    assert api.delete(f"/crm/objects/{V}/contacts/{c}/associations/deals/{d}", headers=H).status_code == 204
    assert api.get(f"/crm/v4/objects/deals/{d}/associations/contacts", headers=H).json()["results"] == []


def test_dated_routes_need_the_token(client):
    for path in (f"/crm/pipelines/{V}/deals", f"/crm/lists/{V}/1", f"/crm/owners/{V}", f"/crm/associations/{V}/contacts/companies/labels"):
        assert client.get(path).status_code == 401, path


def test_legacy_v3_record_association_route_still_works(api):
    c = api.post("/crm/v3/objects/contacts", headers=H, json={"properties": {"email": "legacy.v3@example.com"}}).json()["id"]
    co = api.post("/crm/v3/objects/companies", headers=H, json={"properties": {"name": "Legacy Co"}}).json()["id"]
    assert api.put(f"/crm/v3/objects/contacts/{c}/associations/companies/{co}/279", headers=H).status_code == 200
    r = api.get(f"/crm/v3/objects/contacts/{c}/associations/companies", headers=H)
    assert r.status_code == 200 and r.json()["results"][0]["id"] == co

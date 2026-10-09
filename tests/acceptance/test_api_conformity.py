"""HubSpot CRM API conformity on a fresh account (after /__reset)."""
import uuid

import pytest


@pytest.fixture(scope="module", autouse=True)
def fresh(client):
    assert client.post("/__reset").status_code == 204


def _email():
    return f"test.{uuid.uuid4().hex[:10]}@example.com"


def test_contact_crud_shape(client):
    r = client.post("/crm/v3/objects/contacts", json={"properties": {"email": _email(), "firstname": "Anna", "lastname": "Sala"}})
    assert r.status_code == 201, r.text
    body = r.json()
    cid = body["id"]
    assert cid.isdigit()
    assert body["properties"]["firstname"] == "Anna"
    assert body["properties"]["hs_object_id"] == cid
    assert "createdate" in body["properties"] and "lastmodifieddate" in body["properties"]
    assert body["createdAt"].endswith("Z") and body["archived"] is False

    r = client.get(f"/crm/v3/objects/contacts/{cid}", params={"properties": "firstname,email"})
    assert r.status_code == 200
    assert r.json()["properties"]["firstname"] == "Anna"

    r = client.patch(f"/crm/v3/objects/contacts/{cid}", json={"properties": {"phone": "+39 02 1234567", "firstname": ""}})
    assert r.status_code == 200, r.text
    p = r.json()["properties"]
    assert p["phone"] == "+39 02 1234567"
    assert not p.get("firstname"), "empty string clears a property"

    r = client.delete(f"/crm/v3/objects/contacts/{cid}")
    assert r.status_code == 204
    r = client.get(f"/crm/v3/objects/contacts/{cid}")
    assert r.status_code == 404
    assert r.json()["category"] == "OBJECT_NOT_FOUND"
    r = client.get(f"/crm/v3/objects/contacts/{cid}", params={"archived": "true"})
    assert r.status_code == 200 and r.json()["archived"] is True


def test_validation_errors(client):
    r = client.post("/crm/v3/objects/contacts", json={"properties": {"email": "not-an-email"}})
    assert r.status_code == 400
    assert r.json()["status"] == "error" and r.json()["category"] == "VALIDATION_ERROR"
    r = client.post("/crm/v3/objects/contacts", json={"properties": {"nonexistent_prop": "x"}})
    assert r.status_code == 400
    r = client.post("/crm/v3/objects/deals", json={"properties": {"dealname": "x", "amount": "abc"}})
    assert r.status_code == 400
    r = client.get("/crm/v3/objects/contacts/999999999")
    assert r.status_code == 404
    r = client.get("/crm/v3/objects/nonsense_type")
    assert r.status_code in (400, 404)


def test_duplicate_email_409(client):
    e = _email()
    assert client.post("/crm/v3/objects/contacts", json={"properties": {"email": e}}).status_code == 201
    r = client.post("/crm/v3/objects/contacts", json={"properties": {"email": e.upper()}})
    assert r.status_code == 409, r.text
    assert r.json()["status"] == "error"


def test_list_pagination_exactly_once(client):
    emails = {_email() for _ in range(23)}
    for e in emails:
        assert client.post("/crm/v3/objects/contacts", json={"properties": {"email": e}}).status_code == 201
    seen = []
    after = None
    for _ in range(50):
        params = {"limit": 5, "properties": "email"}
        if after:
            params["after"] = after
        r = client.get("/crm/v3/objects/contacts", params=params)
        assert r.status_code == 200
        body = r.json()
        seen += [x["properties"]["email"] for x in body["results"]]
        nxt = body.get("paging", {}).get("next", {}).get("after")
        if not nxt:
            break
        after = nxt
    assert len(seen) == len(set(seen)), "duplicates across pages"
    assert emails <= set(seen)


def test_search_filters_sort_total_and_paging(client):
    tag = uuid.uuid4().hex[:8]
    ids = []
    for i in range(7):
        r = client.post("/crm/v3/objects/deals", json={"properties": {"dealname": f"{tag} deal {i}", "amount": str(100 * (i + 1)), "dealstage": "appointmentscheduled"}})
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
    body = {
        "filterGroups": [{"filters": [{"propertyName": "dealname", "operator": "CONTAINS_TOKEN", "value": tag}, {"propertyName": "amount", "operator": "GTE", "value": "300"}]}],
        "sorts": [{"propertyName": "amount", "direction": "DESCENDING"}],
        "properties": ["dealname", "amount"],
        "limit": 2,
    }
    r = client.post("/crm/v3/objects/deals/search", json=body)
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["total"] == 5
    amounts = [float(x["properties"]["amount"]) for x in res["results"]]
    assert amounts == [700.0, 600.0]
    assert res["paging"]["next"]["after"]
    body["after"] = res["paging"]["next"]["after"]
    res2 = client.post("/crm/v3/objects/deals/search", json=body).json()
    assert [float(x["properties"]["amount"]) for x in res2["results"]] == [500.0, 400.0]
    # IN / NOT_IN / HAS_PROPERTY / BETWEEN / EQ on id
    r = client.post("/crm/v3/objects/deals/search", json={"filterGroups": [{"filters": [{"propertyName": "hs_object_id", "operator": "IN", "values": ids[:3]}]}]})
    assert r.json()["total"] == 3
    r = client.post("/crm/v3/objects/deals/search", json={"filterGroups": [{"filters": [{"propertyName": "amount", "operator": "BETWEEN", "value": "150", "highValue": "350"}, {"propertyName": "dealname", "operator": "CONTAINS_TOKEN", "value": tag}]}]})
    assert r.json()["total"] == 2
    r = client.post("/crm/v3/objects/deals/search", json={"filterGroups": [{"filters": [{"propertyName": "closedate", "operator": "HAS_PROPERTY"}, {"propertyName": "dealname", "operator": "CONTAINS_TOKEN", "value": tag}]}]})
    assert r.json()["total"] == 0
    # free text query
    r = client.post("/crm/v3/objects/deals/search", json={"query": tag, "limit": 100})
    assert r.json()["total"] == 7
    # OR between filter groups
    r = client.post("/crm/v3/objects/deals/search", json={"filterGroups": [{"filters": [{"propertyName": "hs_object_id", "operator": "EQ", "value": ids[0]}]}, {"filters": [{"propertyName": "hs_object_id", "operator": "EQ", "value": ids[1]}]}]})
    assert r.json()["total"] == 2


def test_batch_endpoints(client):
    r = client.post("/crm/v3/objects/companies/batch/create", json={"inputs": [{"properties": {"name": "Batch A", "domain": "batch-a.example"}}, {"properties": {"name": "Batch B", "domain": "batch-b.example"}}]})
    assert r.status_code in (200, 201), r.text
    body = r.json()
    assert body["status"] == "COMPLETE" and len(body["results"]) == 2
    ids = [x["id"] for x in body["results"]]
    r = client.post("/crm/v3/objects/companies/batch/read", json={"inputs": [{"id": i} for i in ids], "properties": ["name"]})
    assert r.status_code == 200
    assert {x["properties"]["name"] for x in r.json()["results"]} == {"Batch A", "Batch B"}
    r = client.post("/crm/v3/objects/companies/batch/update", json={"inputs": [{"id": ids[0], "properties": {"city": "Milano"}}]})
    assert r.status_code == 200 and r.json()["results"][0]["properties"]["city"] == "Milano"
    r = client.post("/crm/v3/objects/companies/batch/archive", json={"inputs": [{"id": i} for i in ids]})
    assert r.status_code == 204
    assert client.get(f"/crm/v3/objects/companies/{ids[0]}").status_code == 404


def test_batch_upsert_contacts_by_email(client):
    e = _email()
    body = {"inputs": [{"idProperty": "email", "id": e, "properties": {"firstname": "Up", "lastname": "Sert"}}]}
    r = client.post("/crm/v3/objects/contacts/batch/upsert", json=body)
    assert r.status_code in (200, 201), r.text
    first = r.json()["results"][0]
    assert first["properties"]["email"] == e
    body["inputs"][0]["properties"] = {"lastname": "Changed"}
    r = client.post("/crm/v3/objects/contacts/batch/upsert", json=body)
    second = r.json()["results"][0]
    assert second["id"] == first["id"]
    assert second["properties"]["lastname"] == "Changed"
    assert second["properties"]["firstname"] == "Up"


def test_associations_v4(client):
    c = client.post("/crm/v3/objects/contacts", json={"properties": {"email": _email()}}).json()["id"]
    co = client.post("/crm/v3/objects/companies", json={"properties": {"name": "Assoc Co", "domain": "assoc-co.example"}}).json()["id"]
    d = client.post("/crm/v3/objects/deals", json={"properties": {"dealname": "Assoc deal", "dealstage": "appointmentscheduled"}}).json()["id"]
    r = client.put(f"/crm/v4/objects/contacts/{c}/associations/companies/{co}", json=[{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 279}])
    assert r.status_code in (200, 201), r.text
    r = client.put(f"/crm/v4/objects/deals/{d}/associations/default/companies/{co}")
    assert r.status_code in (200, 201), r.text
    r = client.get(f"/crm/v4/objects/contacts/{c}/associations/companies")
    assert r.status_code == 200
    res = r.json()["results"]
    assert len(res) == 1 and str(res[0]["toObjectId"]) == co
    types = res[0]["associationTypes"]
    assert any(t["typeId"] == 279 and t["category"] == "HUBSPOT_DEFINED" for t in types)
    # inverse direction readable
    r = client.get(f"/crm/v4/objects/companies/{co}/associations/contacts")
    assert {str(x["toObjectId"]) for x in r.json()["results"]} == {c}
    r = client.get(f"/crm/v4/objects/companies/{co}/associations/deals")
    assert {str(x["toObjectId"]) for x in r.json()["results"]} == {d}
    # associations embedded in object read
    r = client.get(f"/crm/v3/objects/contacts/{c}", params={"associations": "companies"})
    assert r.status_code == 200
    assert str(r.json()["associations"]["companies"]["results"][0]["id"]) == co
    # labels
    r = client.get("/crm/v4/associations/contacts/companies/labels")
    assert r.status_code == 200
    assert {x["typeId"] for x in r.json()["results"]} >= {1, 279}
    # batch create and archive
    r = client.post("/crm/v4/associations/deals/contacts/batch/create", json={"inputs": [{"from": {"id": d}, "to": {"id": c}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 3}]}]})
    assert r.status_code in (200, 201), r.text
    assert {str(x["toObjectId"]) for x in client.get(f"/crm/v4/objects/deals/{d}/associations/contacts").json()["results"]} == {c}
    r = client.delete(f"/crm/v4/objects/contacts/{c}/associations/companies/{co}")
    assert r.status_code == 204
    assert client.get(f"/crm/v4/objects/contacts/{c}/associations/companies").json()["results"] == []


def test_properties_api(client):
    name = f"custom_{uuid.uuid4().hex[:6]}"
    r = client.post("/crm/v3/properties/companies", json={"name": name, "label": "Custom", "type": "string", "fieldType": "text", "groupName": "companyinformation"})
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["name"] == name and p["type"] == "string" and p["fieldType"] == "text"
    r = client.get(f"/crm/v3/properties/companies/{name}")
    assert r.status_code == 200
    r = client.patch(f"/crm/v3/properties/companies/{name}", json={"label": "Custom 2"})
    assert r.status_code == 200 and r.json()["label"] == "Custom 2"
    co = client.post("/crm/v3/objects/companies", json={"properties": {"name": "P", name: "value"}})
    assert co.status_code == 201 and co.json()["properties"][name] == "value"
    r = client.post("/crm/v3/properties/companies", json={"name": name, "label": "Dup", "type": "string", "fieldType": "text", "groupName": "companyinformation"})
    assert r.status_code in (400, 409), "duplicate property name is rejected"
    r = client.get("/crm/v3/properties/deals")
    names = {x["name"] for x in r.json()["results"]}
    assert {"dealname", "amount", "dealstage", "pipeline", "closedate", "deal_currency_code"} <= names
    num = client.post("/crm/v3/properties/companies", json={"name": name + "_n", "label": "N", "type": "number", "fieldType": "number", "groupName": "companyinformation"})
    assert num.status_code == 201
    r = client.delete(f"/crm/v3/properties/companies/{name}")
    assert r.status_code == 204


def test_pipelines_api(client):
    r = client.post("/crm/v3/pipelines/deals", json={"label": "Test pipe", "displayOrder": 1, "stages": [{"label": "One", "displayOrder": 0, "metadata": {"probability": "0.5"}}, {"label": "Won", "displayOrder": 1, "metadata": {"probability": "1.0", "isClosed": "true"}}]})
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["label"] == "Test pipe" and len(p["stages"]) == 2
    pid = p["id"]
    sid = p["stages"][0]["id"]
    assert p["stages"][0]["metadata"]["probability"] == "0.5"
    r = client.get(f"/crm/v3/pipelines/deals/{pid}")
    assert r.status_code == 200
    r = client.get(f"/crm/v3/pipelines/deals/{pid}/stages")
    assert r.status_code == 200 and len(r.json()["results"]) == 2
    d = client.post("/crm/v3/objects/deals", json={"properties": {"dealname": "In custom pipe", "pipeline": pid, "dealstage": sid}})
    assert d.status_code == 201, d.text
    assert d.json()["properties"]["pipeline"] == pid
    bad = client.post("/crm/v3/objects/deals", json={"properties": {"dealname": "bad stage", "pipeline": pid, "dealstage": "closedwon"}})
    assert bad.status_code == 400
    r = client.patch(f"/crm/v3/pipelines/deals/{pid}", json={"label": "Renamed"})
    assert r.status_code == 200 and r.json()["label"] == "Renamed"
    tr = client.get("/crm/v3/pipelines/tickets").json()["results"][0]
    assert tr["stages"][0]["metadata"]["ticketState"] == "OPEN"
    r = client.delete(f"/crm/v3/pipelines/deals/{pid}")
    assert r.status_code == 204


def test_lists_api(client):
    co = client.post("/crm/v3/objects/companies", json={"properties": {"name": "Listed"}}).json()["id"]
    r = client.post("/crm/v3/lists", json={"name": "Test list", "objectTypeId": "0-2", "processingType": "MANUAL"})
    assert r.status_code in (200, 201), r.text
    lst = r.json()["list"]
    lid = lst["listId"]
    assert lst["name"] == "Test list" and lst["objectTypeId"] == "0-2"
    r = client.put(f"/crm/v3/lists/{lid}/memberships/add", json=[co])
    assert r.status_code == 200, r.text
    r = client.get(f"/crm/v3/lists/{lid}/memberships")
    assert r.status_code == 200
    assert [str(x["recordId"]) for x in r.json()["results"]] == [co]
    r = client.get("/crm/v3/lists/object-type-id/0-2/name/Test list")
    assert r.status_code == 200 and r.json()["list"]["listId"] == lid
    r = client.get(f"/crm/v3/lists/{lid}")
    assert r.status_code == 200
    r = client.delete(f"/crm/v3/lists/{lid}")
    assert r.status_code == 204


def test_export_async_and_public_link(client, anon):
    client.post("/crm/v3/objects/contacts", json={"properties": {"email": _email(), "firstname": "Exp"}})
    r = client.post("/crm/v3/exports/export/async", json={"exportType": "VIEW", "format": "CSV", "exportName": "contacts", "objectType": "contacts", "objectProperties": ["email", "firstname"], "language": "EN"})
    assert r.status_code in (200, 202), r.text
    eid = r.json()["id"]
    import time

    for _ in range(20):
        st = client.get(f"/crm/v3/exports/export/async/tasks/{eid}/status").json()
        if st["status"] == "COMPLETE":
            break
        time.sleep(0.5)
    assert st["status"] == "COMPLETE", st
    url = st["result"]
    r = anon.get(url, follow_redirects=True)
    assert r.status_code == 200
    assert "Exp" in r.text


def test_activities_and_tasks(client):
    c = client.post("/crm/v3/objects/contacts", json={"properties": {"email": _email()}}).json()["id"]
    r = client.post("/crm/v3/objects/notes", json={"properties": {"hs_note_body": "ciao", "hs_timestamp": "2025-05-01T10:00:00Z"}, "associations": [{"to": {"id": c}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 202}]}]})
    assert r.status_code == 201, r.text
    n = r.json()
    assert n["properties"]["hs_note_body"] == "ciao"
    assert {str(x["toObjectId"]) for x in client.get(f"/crm/v4/objects/notes/{n['id']}/associations/contacts").json()["results"]} == {c}
    r = client.post("/crm/v3/objects/tasks", json={"properties": {"hs_task_subject": "Call", "hs_task_status": "NOT_STARTED", "hs_timestamp": "1764586800000"}})
    assert r.status_code == 201, r.text
    ts = r.json()["properties"]["hs_timestamp"]
    assert ts.startswith("2025-12-01T11:00:00")
    for t in ("calls", "emails", "meetings"):
        r = client.post(f"/crm/v3/objects/{t}", json={"properties": {"hs_timestamp": "2025-01-01T00:00:00Z"}})
        assert r.status_code == 201, (t, r.text)


def test_rate_limit_headers_present(client):
    r = client.get("/crm/v3/objects/contacts", params={"limit": 1})
    assert r.status_code == 200
    assert "x-hubspot-ratelimit-remaining" in {k.lower() for k in r.headers}

from .conftest import H


def test_health_no_token(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["version"] == "2026-09" and "contacts" in body["ui"]


def test_auth_required(client):
    assert client.get("/crm/v3/objects/contacts").status_code == 401
    assert client.get("/crm/v3/objects/contacts", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.post("/__reset").status_code == 401


def test_reset(api):
    r = api.post("/__reset", headers=H)
    assert r.status_code == 204
    r = api.get("/crm/v3/objects/contacts", headers=H)
    assert r.status_code == 200 and r.json()["results"] == []


def test_contact_crud_and_search(api):
    r = api.post("/crm/v3/objects/contacts", headers=H, json={"properties": {"email": "Mario.Rossi@Example.com", "firstname": "Mario", "lastname": "Rossi"}})
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["properties"]["email"] == "mario.rossi@example.com"
    assert c["properties"]["hs_object_id"] == c["id"]
    cid = c["id"]
    r = api.get(f"/crm/v3/objects/contacts/{cid}", headers=H, params={"properties": "firstname,email"})
    assert r.status_code == 200 and r.json()["properties"]["firstname"] == "Mario"
    r = api.get("/crm/v3/objects/contacts/mario.rossi@example.com", headers=H, params={"idProperty": "email"})
    assert r.status_code == 200 and r.json()["id"] == cid
    r = api.patch(f"/crm/v3/objects/contacts/{cid}", headers=H, json={"properties": {"phone": "+39 02 1234"}})
    assert r.status_code == 200 and r.json()["properties"]["phone"] == "+39 02 1234"
    # duplicate email -> 409
    r = api.post("/crm/v3/objects/contacts", headers=H, json={"properties": {"email": "mario.rossi@example.com"}})
    assert r.status_code == 409
    # invalid email -> 400
    r = api.post("/crm/v3/objects/contacts", headers=H, json={"properties": {"email": "not-an-email"}})
    assert r.status_code == 400 and r.json()["category"] == "VALIDATION_ERROR"
    # unknown property -> 400
    r = api.post("/crm/v3/objects/contacts", headers=H, json={"properties": {"nope": "x"}})
    assert r.status_code == 400
    # search
    r = api.post("/crm/v3/objects/contacts/search", headers=H, json={"filterGroups": [{"filters": [{"propertyName": "email", "operator": "EQ", "value": "mario.rossi@example.com"}]}], "properties": ["firstname"]})
    assert r.status_code == 200 and r.json()["total"] == 1 and r.json()["results"][0]["properties"]["firstname"] == "Mario"
    r = api.post("/crm/v3/objects/contacts/search", headers=H, json={"query": "mario"})
    assert r.json()["total"] == 1
    # archive
    r = api.delete(f"/crm/v3/objects/contacts/{cid}", headers=H)
    assert r.status_code == 204
    assert api.get(f"/crm/v3/objects/contacts/{cid}", headers=H).status_code == 404
    assert api.get("/crm/v3/objects/contacts/999999", headers=H).status_code == 404


def test_associations_and_rules(api):
    comp = api.post("/crm/v3/objects/companies", headers=H, json={"properties": {"name": "Acme", "domain": "acme.it", "partita_iva": "IT 12345678901"}})
    assert comp.status_code == 201, comp.text
    assert comp.json()["properties"]["partita_iva"] == "12345678901"
    comp_id = comp.json()["id"]
    # R7
    dup = api.post("/crm/v3/objects/companies", headers=H, json={"properties": {"name": "Acme 2", "partita_iva": "12345678901"}})
    assert dup.status_code == 409
    # R12 auto association by email domain
    c = api.post("/crm/v3/objects/contacts", headers=H, json={"properties": {"email": "a@acme.it"}})
    assert c.status_code == 201
    a = api.get(f"/crm/v4/objects/contacts/{c.json()['id']}/associations/companies", headers=H).json()
    assert [x["toObjectId"] for x in a["results"]] == [int(comp_id)]
    assert any(t["typeId"] == 1 for t in a["results"][0]["associationTypes"])
    # deal with association, won -> R10 ticket
    d = api.post("/crm/v3/objects/deals", headers=H, json={"properties": {"dealname": "Fornitura X", "amount": "1.000,50", "dealstage": "closedwon", "commerciale": "anna.sala@brambillaforniture.it"}, "associations": [{"to": {"id": comp_id}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 5}]}]})
    assert d.status_code == 201, d.text
    assert d.json()["properties"]["amount"] == "1000.5"
    assert d.json()["properties"]["pipeline"] == "default"
    assert d.json()["properties"]["hs_is_closed_won"] == "true"
    did = d.json()["id"]
    t = api.post("/crm/v3/objects/tickets/search", headers=H, json={"filterGroups": [{"filters": [{"propertyName": "subject", "operator": "EQ", "value": "Avvio fornitura - Fornitura X"}]}]}).json()
    assert t["total"] == 1
    tk = t["results"][0]
    assert tk["properties"]["assegnatario"] == "anna.sala@brambillaforniture.it"
    pls = api.get("/crm/v3/pipelines/tickets", headers=H).json()["results"]
    ass = next(p for p in pls if p["label"] == "Assistenza")
    assert tk["properties"]["hs_pipeline"] == ass["id"]
    assert tk["properties"]["hs_pipeline_stage"] == ass["stages"][0]["id"]
    ta = api.get(f"/crm/v4/objects/tickets/{tk['id']}/associations/companies", headers=H).json()
    assert [x["toObjectId"] for x in ta["results"]] == [int(comp_id)]
    # once only: move back and forth
    api.patch(f"/crm/v3/objects/deals/{did}", headers=H, json={"properties": {"dealstage": "contractsent"}})
    api.patch(f"/crm/v3/objects/deals/{did}", headers=H, json={"properties": {"dealstage": "closedwon"}})
    t = api.post("/crm/v3/objects/tickets/search", headers=H, json={"query": "Avvio fornitura"}).json()
    assert t["total"] == 1
    # lost -> R11 task
    r = api.patch(f"/crm/v3/objects/deals/{did}", headers=H, json={"properties": {"dealstage": "closedlost"}})
    assert r.status_code == 200
    tasks = api.get(f"/crm/v4/objects/deals/{did}/associations/tasks", headers=H).json()["results"]
    assert len(tasks) == 1
    task = api.get(f"/crm/v3/objects/tasks/{tasks[0]['toObjectId']}", headers=H).json()
    assert task["properties"]["hs_task_subject"] == "Richiamare: Fornitura X"
    assert task["properties"]["hs_task_status"] == "NOT_STARTED"
    # invalid stage -> 400
    assert api.patch(f"/crm/v3/objects/deals/{did}", headers=H, json={"properties": {"dealstage": "nope"}}).status_code == 400


def test_list_pagination(api):
    ids = []
    for i in range(7):
        r = api.post("/crm/v3/objects/companies", headers=H, json={"properties": {"name": f"C{i}"}})
        ids.append(r.json()["id"])
    seen = []
    after = None
    while True:
        params = {"limit": 3}
        if after:
            params["after"] = after
        r = api.get("/crm/v3/objects/companies", headers=H, params=params).json()
        seen += [x["id"] for x in r["results"]]
        after = r.get("paging", {}).get("next", {}).get("after")
        if not after:
            break
    assert seen == ids
    r = api.post("/crm/v3/objects/companies/search", headers=H, json={"limit": 4, "after": "4", "sorts": [{"propertyName": "name", "direction": "DESCENDING"}]}).json()
    assert r["total"] == 7 and [x["properties"]["name"] for x in r["results"]] == ["C2", "C1", "C0"]


def test_batch_and_upsert(api):
    r = api.post("/crm/v3/objects/contacts/batch/create", headers=H, json={"inputs": [{"properties": {"email": "a@x.it"}}, {"properties": {"email": "b@x.it"}}]})
    assert r.status_code == 201 and len(r.json()["results"]) == 2
    r = api.post("/crm/v3/objects/contacts/batch/upsert", headers=H, json={"inputs": [{"idProperty": "email", "id": "a@x.it", "properties": {"firstname": "A"}}, {"idProperty": "email", "id": "c@x.it", "properties": {"firstname": "C"}}]})
    assert r.status_code == 200, r.text
    res = r.json()["results"]
    assert {x["properties"]["email"]: x["new"] for x in res} == {"a@x.it": False, "c@x.it": True}
    r = api.post("/crm/v3/objects/contacts/batch/read", headers=H, json={"inputs": [{"id": "a@x.it"}, {"id": "zz@x.it"}], "idProperty": "email", "properties": ["firstname"]})
    assert r.status_code == 207 and len(r.json()["results"]) == 1 and r.json()["numErrors"] == 1

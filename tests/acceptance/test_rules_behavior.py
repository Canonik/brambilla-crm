"""R7, R10, R11, R12 as the checks exercise them: through the API after a migration."""
import time
import uuid

import pytest

pytestmark = pytest.mark.migration


def _pipeline(client, object_type, label):
    for p in client.get(f"/crm/v3/pipelines/{object_type}").json()["results"]:
        if p["label"] == label:
            return p
    raise AssertionError(f"pipeline {label} missing")


def _wait(fn, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        v = fn()
        if v:
            return v
        time.sleep(0.5)
    return fn()


def test_r7_partita_iva_unique(client, migrated):
    piva = "%011d" % (int(uuid.uuid4().int % 10**11))
    r = client.post("/crm/v3/objects/companies", json={"properties": {"name": "Prima", "partita_iva": piva}})
    assert r.status_code == 201, r.text
    assert r.json()["properties"]["partita_iva"] == piva
    r = client.post("/crm/v3/objects/companies", json={"properties": {"name": "Seconda", "partita_iva": piva}})
    assert r.status_code == 409, r.text
    r = client.post("/crm/v3/objects/companies", json={"properties": {"name": "Terza", "partita_iva": f"IT {piva[:5]} {piva[5:]}"}})
    assert r.status_code == 409, "VAT is normalized before the uniqueness check"
    found = client.post("/crm/v3/objects/companies/search", json={"filterGroups": [{"filters": [{"propertyName": "partita_iva", "operator": "EQ", "value": piva}]}]}).json()
    assert found["total"] == 1
    prop = client.get("/crm/v3/properties/companies/partita_iva").json()
    assert prop["hasUniqueValue"] is True


def test_r10_won_deal_opens_ticket_once(client, migrated):
    co = client.post("/crm/v3/objects/companies", json={"properties": {"name": "R10 Co"}}).json()["id"]
    d = client.post("/crm/v3/objects/deals", json={"properties": {"dealname": "Fornitura R10", "dealstage": "qualifiedtobuy", "commerciale": "anna.sala@brambillaforniture.it"}}).json()
    client.put(f"/crm/v4/objects/deals/{d['id']}/associations/default/companies/{co}")
    assert client.patch(f"/crm/v3/objects/deals/{d['id']}", json={"properties": {"dealstage": "closedwon"}}).status_code == 200
    assist = _pipeline(client, "tickets", "Assistenza")
    aperto = next(s for s in assist["stages"] if s["label"] == "Aperto")

    def tickets():
        ids = {str(x["toObjectId"]) for x in client.get(f"/crm/v4/objects/deals/{d['id']}/associations/tickets").json()["results"]}
        return ids or None

    tids = _wait(tickets)
    assert tids and len(tids) == 1, tids
    t = client.get(f"/crm/v3/objects/tickets/{list(tids)[0]}", params={"properties": "subject,hs_pipeline,hs_pipeline_stage,assegnatario"}).json()["properties"]
    assert t["subject"] == "Avvio fornitura - Fornitura R10"
    assert t["hs_pipeline"] == assist["id"] and t["hs_pipeline_stage"] == aperto["id"]
    assert t["assegnatario"] == "anna.sala@brambillaforniture.it"
    assert co in {str(x["toObjectId"]) for x in client.get(f"/crm/v4/objects/tickets/{list(tids)[0]}/associations/companies").json()["results"]}
    # back and forth: still one
    client.patch(f"/crm/v3/objects/deals/{d['id']}", json={"properties": {"dealstage": "contractsent"}})
    client.patch(f"/crm/v3/objects/deals/{d['id']}", json={"properties": {"dealstage": "closedwon"}})
    time.sleep(1.5)
    assert len(tickets()) == 1
    # created directly in closedwon
    d2 = client.post("/crm/v3/objects/deals", json={"properties": {"dealname": "Diretta", "dealstage": "closedwon"}}).json()
    assert _wait(lambda: client.get(f"/crm/v4/objects/deals/{d2['id']}/associations/tickets").json()["results"] or None)


def test_r11_lost_deal_creates_task(client, migrated):
    d = client.post("/crm/v3/objects/deals", json={"properties": {"dealname": "Persa R11", "dealstage": "presentationscheduled"}}).json()
    t0 = time.time()
    assert client.patch(f"/crm/v3/objects/deals/{d['id']}", json={"properties": {"dealstage": "closedlost"}}).status_code == 200
    tasks = _wait(lambda: {str(x["toObjectId"]) for x in client.get(f"/crm/v4/objects/deals/{d['id']}/associations/tasks").json()["results"]} or None)
    assert tasks and len(tasks) == 1
    p = client.get(f"/crm/v3/objects/tasks/{list(tasks)[0]}", params={"properties": "hs_task_subject,hs_task_status,hs_timestamp"}).json()["properties"]
    assert p["hs_task_subject"] == "Richiamare: Persa R11"
    assert p["hs_task_status"] == "NOT_STARTED"
    from datetime import datetime, timezone

    due = datetime.fromisoformat(p["hs_timestamp"].replace("Z", "+00:00"))
    assert abs((due - datetime.fromtimestamp(t0, tz=timezone.utc)).total_seconds() - 180 * 86400) < 120
    client.patch(f"/crm/v3/objects/deals/{d['id']}", json={"properties": {"dealstage": "qualifiedtobuy"}})
    client.patch(f"/crm/v3/objects/deals/{d['id']}", json={"properties": {"dealstage": "closedlost"}})
    time.sleep(1.5)
    assert len(client.get(f"/crm/v4/objects/deals/{d['id']}/associations/tasks").json()["results"]) == 1


def test_r12_contact_finds_company_by_domain(client, migrated):
    dom = f"r12-{uuid.uuid4().hex[:6]}.example"
    co = client.post("/crm/v3/objects/companies", json={"properties": {"name": "R12 Co", "domain": dom}}).json()["id"]
    c = client.post("/crm/v3/objects/contacts", json={"properties": {"email": f"mario@{dom}"}}).json()["id"]
    got = _wait(lambda: {str(x["toObjectId"]) for x in client.get(f"/crm/v4/objects/contacts/{c}/associations/companies").json()["results"]} or None)
    assert got == {co}
    # unknown domain: no company created
    before = client.post("/crm/v3/objects/companies/search", json={"limit": 1}).json()["total"]
    c2 = client.post("/crm/v3/objects/contacts", json={"properties": {"email": f"x@unknown-{uuid.uuid4().hex[:5]}.example"}}).json()["id"]
    time.sleep(1)
    assert client.get(f"/crm/v4/objects/contacts/{c2}/associations/companies").json()["results"] == []
    assert client.post("/crm/v3/objects/companies/search", json={"limit": 1}).json()["total"] == before
    # existing association untouched
    other = client.post("/crm/v3/objects/companies", json={"properties": {"name": "Other"}}).json()["id"]
    c3 = client.post("/crm/v3/objects/contacts", json={"properties": {"email": f"luca@{dom}"}, "associations": [{"to": {"id": other}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 279}]}]}).json()["id"]
    time.sleep(1)
    assert {str(x["toObjectId"]) for x in client.get(f"/crm/v4/objects/contacts/{c3}/associations/companies").json()["results"]} == {other}
    # additional domains count too
    co2 = client.post("/crm/v3/objects/companies", json={"properties": {"name": "Multi", "domain": f"main-{dom}", "hs_additional_domains": f"alt-{dom}"}}).json()["id"]
    c4 = client.post("/crm/v3/objects/contacts", json={"properties": {"email": f"p@alt-{dom}"}}).json()["id"]
    assert _wait(lambda: {str(x["toObjectId"]) for x in client.get(f"/crm/v4/objects/contacts/{c4}/associations/companies").json()["results"]} or None) == {co2}


def test_concurrent_writes_lose_nothing(client, migrated, base_url, token):
    import concurrent.futures

    import httpx

    co = client.post("/crm/v3/objects/companies", json={"properties": {"name": "Concurrent"}}).json()["id"]

    def patch(i):
        with httpx.Client(base_url=base_url, headers={"Authorization": f"Bearer {token}"}, timeout=30) as c:
            return c.patch(f"/crm/v3/objects/companies/{co}", json={"properties": {f"description": f"d{i}", "city": f"c{i}"} if i % 2 else {"state": f"s{i}", "zip": f"{i:05d}"}}).status_code

    with concurrent.futures.ThreadPoolExecutor(10) as ex:
        codes = list(ex.map(patch, range(20)))
    assert all(c == 200 for c in codes), codes
    p = client.get(f"/crm/v3/objects/companies/{co}").json()["properties"]
    assert p.get("description") and p.get("city") and p.get("state") and p.get("zip")

    e = f"race.{uuid.uuid4().hex[:8]}@example.com"

    def upsert(i):
        with httpx.Client(base_url=base_url, headers={"Authorization": f"Bearer {token}"}, timeout=30) as c:
            r = c.post("/crm/v3/objects/contacts/batch/upsert", json={"inputs": [{"idProperty": "email", "id": e, "properties": {"firstname": f"n{i}"}}]})
            return r.status_code

    with concurrent.futures.ThreadPoolExecutor(10) as ex:
        codes = list(ex.map(upsert, range(10)))
    assert all(c in (200, 201) for c in codes), codes
    found = client.post("/crm/v3/objects/contacts/search", json={"filterGroups": [{"filters": [{"propertyName": "email", "operator": "EQ", "value": e}]}]}).json()
    assert found["total"] == 1

    def create(i):
        with httpx.Client(base_url=base_url, headers={"Authorization": f"Bearer {token}"}, timeout=30) as c:
            return c.post("/crm/v3/objects/contacts", json={"properties": {"email": f"dup.{e}"}}).status_code

    with concurrent.futures.ThreadPoolExecutor(8) as ex:
        codes = list(ex.map(create, range(8)))
    assert codes.count(201) == 1 and all(c in (201, 409) for c in codes), codes

"""Durability: parallel writes lose nothing and create no duplicates (brief, "What holding up means")."""
import collections
import concurrent.futures as cf
import time

from fastapi.testclient import TestClient

from app.main import app

from .conftest import H


def _run(fn, n, workers=16):
    with cf.ThreadPoolExecutor(workers) as ex:
        return list(ex.map(fn, range(n)))


def _client():
    return TestClient(app)


def test_parallel_updates_of_one_record_keep_every_value(api):
    co = api.post("/crm/v3/objects/companies", headers=H, json={"properties": {"name": "Race"}}).json()["id"]
    keys = ["description", "zip", "industry", "phone", "address", "website", "country", "city"]

    def upd(i):
        with _client() as c:
            return c.patch(f"/crm/v3/objects/companies/{co}", headers=H, json={"properties": {keys[i % len(keys)]: f"v{i % len(keys)}"}}).status_code

    assert set(_run(upd, 48)) == {200}
    got = api.get(f"/crm/v3/objects/companies/{co}", headers=H).json()["properties"]
    assert {k: got.get(k) for k in keys} == {k: f"v{i}" for i, k in enumerate(keys)}


def test_parallel_creates_and_upserts_on_one_email_make_one_contact(api):
    e = "race.same@example.com"

    def create(i):
        with _client() as c:
            return c.post("/crm/v3/objects/contacts", headers=H, json={"properties": {"email": e}}).status_code

    codes = collections.Counter(_run(create, 24))
    assert codes[201] == 1 and codes[409] == 23, codes
    e2 = "race.upsert@example.com"
    fields = [("firstname", "F"), ("lastname", "L"), ("phone", "+39 1"), ("jobtitle", "J"), ("city", "C"), ("zip", "Z")]

    def up(i):
        k, v = fields[i % len(fields)]
        with _client() as c:
            return c.post("/crm/v3/objects/contacts/batch/upsert", headers=H, json={"inputs": [{"idProperty": "email", "id": e2, "properties": {k: v}}]}).status_code

    assert set(_run(up, 36)) == {200}
    res = api.post("/crm/v3/objects/contacts/search", headers=H, json={"filterGroups": [{"filters": [{"propertyName": "email", "operator": "EQ", "value": e2}]}], "properties": [k for k, _ in fields]}).json()
    assert res["total"] == 1
    assert {k: res["results"][0]["properties"].get(k) for k, _ in fields} == dict(fields)


def test_parallel_moves_into_won_open_exactly_one_ticket(api):
    d = api.post("/crm/v3/objects/deals", headers=H, json={"properties": {"dealname": "Race won", "dealstage": "qualifiedtobuy"}}).json()["id"]

    def move(i):
        with _client() as c:
            return c.patch(f"/crm/v3/objects/deals/{d}", headers=H, json={"properties": {"dealstage": "closedwon"}}).status_code

    assert set(_run(move, 12)) == {200}
    time.sleep(0.5)
    assert len(api.get(f"/crm/v4/objects/deals/{d}/associations/tickets", headers=H).json()["results"]) == 1


def test_reset_is_fast_with_data_and_unique_indexes(api):
    api.post("/crm/v3/properties/companies", headers=H, json={"name": "chiave", "label": "k", "type": "string", "fieldType": "text", "groupName": "companyinformation", "hasUniqueValue": True})
    for i in range(300):
        api.post("/crm/v3/objects/companies", headers=H, json={"properties": {"name": f"c{i}", "chiave": f"k{i}"}})
    t = time.time()
    assert api.post("/__reset", headers=H).status_code == 204
    assert time.time() - t < 1.0

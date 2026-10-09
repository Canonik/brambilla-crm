"""A process restart must keep what the migration created; only /__reset returns to defaults.

Every startup runs db.init_schema(), which seeds the HubSpot defaults. Before the fix it
deleted properties, property groups, pipelines and association labels first, so a Railway
restart after /__migrate dropped id_legacy, partita_iva, fatturato_2025, the Rinnovi and
Assistenza pipelines and every stage id the migrated tickets point at.
"""
from app import db
from app.store import invalidate_caches

from .conftest import H

ASSISTENZA = {"label": "Assistenza", "displayOrder": 1, "stages": [
    {"label": "Aperto", "displayOrder": 0, "metadata": {"ticketState": "OPEN"}},
    {"label": "Chiuso", "displayOrder": 1, "metadata": {"ticketState": "CLOSED"}},
]}


def _simulate_process_start():
    db.init_schema()
    invalidate_caches()


def test_startup_keeps_migrated_properties_and_pipelines(api):
    r = api.post("/crm/v3/properties/companies", headers=H, json={"name": "partita_iva", "label": "Partita IVA", "type": "string", "fieldType": "text", "groupName": "companyinformation", "hasUniqueValue": True})
    assert r.status_code == 201, r.text
    r = api.post("/crm/v3/pipelines/tickets", headers=H, json=ASSISTENZA)
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    stage = r.json()["stages"][0]["id"]
    t = api.post("/crm/v3/objects/tickets", headers=H, json={"properties": {"subject": "Prima del riavvio", "hs_pipeline": pid, "hs_pipeline_stage": stage}})
    assert t.status_code == 201, t.text
    # a user edit of a default definition survives too
    assert api.patch("/crm/v3/properties/companies/city", headers=H, json={"label": "Citta"}).status_code == 200

    _simulate_process_start()

    r = api.get("/crm/v3/properties/companies/partita_iva", headers=H)
    assert r.status_code == 200, "restart dropped the migration's partita_iva definition"
    assert r.json()["hasUniqueValue"] is True
    assert api.get("/crm/v3/properties/companies/city", headers=H).json()["label"] == "Citta"
    r = api.get(f"/crm/v3/pipelines/tickets/{pid}", headers=H)
    assert r.status_code == 200, "restart dropped the Assistenza pipeline"
    assert [s["id"] for s in r.json()["stages"]][0] == stage
    labels = api.get("/crm/v4/associations/contacts/companies/labels", headers=H).json()["results"]
    assert {x["typeId"] for x in labels} >= {1, 279}
    got = api.get(f"/crm/v3/objects/tickets/{t.json()['id']}", headers=H, params={"properties": "hs_pipeline,hs_pipeline_stage"}).json()["properties"]
    assert (got["hs_pipeline"], got["hs_pipeline_stage"]) == (pid, stage)


def test_reset_still_returns_to_a_fresh_account(api):
    assert api.post("/crm/v3/properties/companies", headers=H, json={"name": "id_legacy", "label": "ID legacy", "type": "string", "fieldType": "text", "groupName": "companyinformation"}).status_code == 201
    assert api.post("/crm/v3/pipelines/tickets", headers=H, json=ASSISTENZA).status_code == 201
    assert api.patch("/crm/v3/properties/companies/city", headers=H, json={"label": "Citta"}).status_code == 200

    assert api.post("/__reset", headers=H).status_code == 204

    assert api.get("/crm/v3/properties/companies/id_legacy", headers=H).status_code == 404
    assert api.get("/crm/v3/properties/companies/city", headers=H).json()["label"] == "City"
    assert [p["id"] for p in api.get("/crm/v3/pipelines/tickets", headers=H).json()["results"]] == ["0"]
    assert [p["id"] for p in api.get("/crm/v3/pipelines/deals", headers=H).json()["results"]] == ["default"]

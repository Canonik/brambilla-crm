"""Exports per the 2026-09 reference: create is 202 with a TaskLocator, VIEW exports honor
publicCrmSearchRequest.filterGroups, sorts and query, status carries startedAt/completedAt.

On a6e39d4 create answered 200 and only publicCrmSearchRequest.filters was read, so a VIEW
export with filterGroups exported every record of the type.
"""
import csv
import io

from .conftest import H


def _export(api, client, body):
    r = api.post("/crm/v3/exports/export/async", headers=H, json=body)
    assert r.status_code == 202, (r.status_code, r.text)
    assert r.json()["id"] and isinstance(r.json().get("links"), dict)
    st = api.get(f"/crm/v3/exports/export/async/tasks/{r.json()['id']}/status", headers=H)
    assert st.status_code == 200, st.text
    s = st.json()
    assert s["status"] == "COMPLETE" and s["startedAt"] and s["completedAt"] and s["result"], s
    dl = client.get(s["result"])
    assert dl.status_code == 200
    return list(csv.DictReader(io.StringIO(dl.text)))


def _seed(api):
    for name, city in (("Alfa", "Milano"), ("Beta", "Torino"), ("Gamma", "Milano"), ("Delta", "Roma")):
        assert api.post("/crm/v3/objects/companies", headers=H, json={"properties": {"name": name, "city": city}}).status_code == 201


BASE = {"exportType": "VIEW", "format": "CSV", "exportName": "aziende", "objectType": "companies", "objectProperties": ["name", "city"], "language": "EN"}


def test_view_export_honors_filter_groups_and_sorts(api, client):
    _seed(api)
    body = dict(BASE, publicCrmSearchRequest={
        "filterGroups": [{"filters": [{"propertyName": "city", "operator": "EQ", "value": "Milano"}]}, {"filters": [{"propertyName": "name", "operator": "EQ", "value": "Delta"}]}],
        "sorts": ["-name"],
    })
    rows = _export(api, client, body)
    assert [r["name"] for r in rows] == ["Gamma", "Delta", "Alfa"]


def test_view_export_guide_filter_shape_and_query(api, client):
    _seed(api)
    body = dict(BASE, publicCrmSearchRequest={
        "filterGroups": [{"filters": [{"property": "city", "operator": "EQ", "value": "Torino"}]}],
        "sorts": [{"propertyName": "name", "order": "ASC"}],
    })
    assert [r["name"] for r in _export(api, client, body)] == ["Beta"]
    assert [r["name"] for r in _export(api, client, dict(BASE, publicCrmSearchRequest={"query": "Gamma"}))] == ["Gamma"]


def test_unfiltered_view_export_has_every_record(api, client):
    _seed(api)
    assert len(_export(api, client, BASE)) == 4


def test_unknown_export_task_is_404(api):
    r = api.get("/crm/v3/exports/export/async/tasks/987654/status", headers=H)
    assert r.status_code == 404 and r.json()["category"] == "OBJECT_NOT_FOUND"

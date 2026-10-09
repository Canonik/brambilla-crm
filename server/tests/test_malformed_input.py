"""Malformed requests get a 4xx error envelope, never a 5xx.

A sweep with malformed bodies found 141 5xx responses on a6e39d4: every one was a Python
exception (AttributeError on .get of a list/string body, ValueError from int() on a record id)
escaping as 500, and the connection carrying it was reset for the next request. The durability
check counts any 5xx, so input validation has to answer 400/404 instead.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers.admin import reset_database

from .conftest import H

NON_OBJECT_BODIES = [[], [1, 2], "x", 1]

OBJECT_BODY_POSTS = [
    "/crm/v3/objects/contacts", "/crm/v3/objects/contacts/search", "/crm/v3/objects/contacts/merge",
    "/crm/v3/objects/contacts/gdpr-delete", "/crm/v3/objects/contacts/batch/read", "/crm/v3/objects/contacts/batch/create",
    "/crm/v3/objects/contacts/batch/update", "/crm/v3/objects/contacts/batch/upsert", "/crm/v3/objects/contacts/batch/archive",
    "/crm/v4/associations/contacts/companies/batch/create", "/crm/v4/associations/contacts/companies/batch/read",
    "/crm/v4/associations/contacts/companies/batch/archive", "/crm/v4/associations/contacts/companies/batch/labels/archive",
    "/crm/v4/associations/contacts/companies/batch/associate/default", "/crm/v4/associations/contacts/companies/labels",
    "/crm/v3/properties/contacts", "/crm/v3/properties/contacts/batch/create", "/crm/v3/properties/contacts/batch/read",
    "/crm/v3/properties/contacts/batch/archive", "/crm/v3/properties/contacts/groups",
    "/crm/v3/pipelines/deals", "/crm/v3/pipelines/deals/default/stages",
    "/crm/v3/lists", "/crm/v3/lists/search", "/crm/v3/exports/export/async", "/__migrate",
]

BAD_BATCH_ITEMS = [1, None, "a", {"id": None}, {"id": "abc"}, {"from": None}, {"from": {"id": "x"}, "to": {"id": None}}]


@pytest.fixture()
def raw(client):
    reset_database()
    with TestClient(app, raise_server_exceptions=False) as c:
        c.headers.update(H)
        yield c


def _is_4xx_envelope(r):
    assert 400 <= r.status_code < 500, (r.status_code, r.text[:300])
    body = r.json()
    assert body["status"] == "error" and body["category"] and body["correlationId"], body


@pytest.mark.parametrize("path", OBJECT_BODY_POSTS)
@pytest.mark.parametrize("body", NON_OBJECT_BODIES, ids=["empty-list", "int-list", "string", "int"])
def test_non_object_body_is_400(raw, path, body):
    r = raw.post(path, json=body)
    _is_4xx_envelope(r)
    assert r.json()["category"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("path", [p for p in OBJECT_BODY_POSTS if "batch" in p and "properties" not in p])
def test_malformed_batch_items_are_4xx(raw, path):
    r = raw.post(path, json={"inputs": BAD_BATCH_ITEMS})
    assert r.status_code < 500, (r.status_code, r.text[:300])


@pytest.mark.parametrize("assoc", [
    [{"to": {"id": "zz"}}],
    [{"to": {"id": "1"}, "types": "x"}],
    [{"to": {"id": "1"}, "types": [None]}],
    [{"to": {"id": "1"}, "types": [{"associationTypeId": "x"}]}],
    [None], "x",
])
def test_create_with_malformed_association_is_4xx_and_writes_nothing(raw, assoc):
    r = raw.post("/crm/v3/objects/contacts", json={"properties": {"email": "malformed.assoc@example.com"}, "associations": assoc})
    _is_4xx_envelope(r)
    found = raw.post("/crm/v3/objects/contacts/search", json={"filterGroups": [{"filters": [{"propertyName": "email", "operator": "EQ", "value": "malformed.assoc@example.com"}]}]})
    assert found.json()["total"] == 0, "a rejected create left a contact behind"


@pytest.mark.parametrize("method,path,body", [
    ("POST", "/crm/v3/properties/contacts", {"name": "ok_prop", "displayOrder": "x"}),
    ("POST", "/crm/v3/properties/contacts/groups", {"name": "ok_group", "displayOrder": "x"}),
    ("POST", "/crm/v3/pipelines/deals", {"label": "p", "stages": [{"label": "s", "displayOrder": "x"}]}),
    ("POST", "/crm/v3/pipelines/deals", {"label": "p", "displayOrder": "x", "stages": [{"label": "s"}]}),
    ("POST", "/crm/v3/pipelines/deals", {"label": "p", "stages": [{"label": "s", "metadata": "x"}]}),
    ("POST", "/crm/v3/lists", {"name": "l", "objectTypeId": {"a": 1}}),
    ("POST", "/crm/v3/exports/export/async", {"exportType": "VIEW", "format": "CSV", "objectType": {"a": 1}}),
    ("POST", "/crm/v3/objects/contacts/merge", {"primaryObjectId": "x", "objectIdToMerge": "y"}),
    ("POST", "/__migrate", {"export_url": 5}),
    ("PUT", "/crm/v4/objects/contacts/x/associations/companies/y", [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 279}]),
    ("PUT", "/crm/v4/objects/contacts/1/associations/companies/1", [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": "x"}]),
    ("DELETE", "/crm/v4/objects/contacts/x/associations/companies/y", None),
    ("DELETE", "/crm/v3/objects/contacts/x/associations/companies/y/1", None),
    ("GET", "/crm/v3/objects/contacts/99999999999999999999999", None),
    ("GET", "/crm/v4/objects/contacts/99999999999999999999999/associations/companies", None),
    ("GET", "/crm/v3/lists/99999999999999999999999", None),
])
def test_malformed_values_are_4xx(raw, method, path, body):
    r = raw.request(method, path, json=body) if body is not None else raw.request(method, path)
    _is_4xx_envelope(r)


def test_numeric_list_query_is_text(raw):
    r = raw.post("/crm/v3/lists/search", json={"query": 123})
    assert r.status_code == 200 and r.json()["total"] == 0


def test_connection_survives_a_rejected_request(raw):
    assert raw.post("/crm/v3/objects/contacts/batch/create", json=[1]).status_code == 400
    assert raw.get("/crm/v3/objects/contacts").status_code == 200

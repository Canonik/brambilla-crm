"""Regression coverage for the organizer's date-versioned contacts checks."""

from .conftest import H


CONTACTS = "/crm/objects/2026-09/contacts"
CONTACT_PROPERTIES = "/crm/properties/2026-09/0-1"


def test_date_versioned_contact_routes_are_registered(client):
    registered = {
        (method, route.path)
        for route in client.app.routes
        for method in (getattr(route, "methods", None) or ())
    }

    collection = "/crm/objects/2026-09/{object_type}"
    record = collection + "/{object_id}"
    assert ("GET", collection) in registered
    assert ("POST", collection) in registered
    assert ("GET", record) in registered
    assert ("PATCH", record) in registered
    assert ("DELETE", record) in registered


def test_date_versioned_contacts_require_valid_bearer_token(client):
    assert client.get(CONTACTS).status_code == 401
    assert client.get(CONTACTS, headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_date_versioned_contact_crud_is_persistent_and_unknown_reads_are_ignored(api):
    company = api.post(
        "/crm/objects/2026-09/companies",
        headers=H,
        json={"properties": {"name": "Organizer Company", "domain": "example.com"}},
    )
    assert company.status_code == 201, company.text

    created = api.post(
        CONTACTS,
        headers=H,
        json={"properties": {"email": "organizer@example.com", "firstname": "Ada"}},
    )
    assert created.status_code == 201, created.text
    contact_id = created.json()["id"]

    listed = api.get(CONTACTS, headers=H, params={"limit": 1, "properties": "email"})
    assert listed.status_code == 200, listed.text
    assert listed.json()["results"][0]["id"] == contact_id

    retrieved = api.get(
        f"{CONTACTS}/{contact_id}",
        headers=H,
        params={"properties": "email,property_that_does_not_exist"},
    )
    assert retrieved.status_code == 200, retrieved.text
    properties = retrieved.json()["properties"]
    assert properties["email"] == "organizer@example.com"
    assert "property_that_does_not_exist" not in properties

    associations = api.get(
        f"/crm/v4/objects/contacts/{contact_id}/associations/companies", headers=H
    )
    assert associations.status_code == 200, associations.text
    assert [str(item["toObjectId"]) for item in associations.json()["results"]] == [
        company.json()["id"]
    ]

    assert api.delete(f"{CONTACTS}/{contact_id}", headers=H).status_code == 204
    assert api.get(f"{CONTACTS}/{contact_id}", headers=H).status_code == 404
    assert api.get(CONTACTS, headers=H).json()["results"] == []


def test_reset_keeps_defaults_and_allows_date_versioned_contact_creation(api):
    assert api.post("/__reset", headers=H).status_code == 204
    definitions = api.get(CONTACT_PROPERTIES, headers=H)
    assert definitions.status_code == 200, definitions.text
    names = {item["name"] for item in definitions.json()["results"]}
    assert {"email", "firstname", "lastname"} <= names

    created = api.post(CONTACTS, headers=H, json={"properties": {"email": "after-reset@example.com"}})
    assert created.status_code == 201, created.text
    assert created.json()["id"].isdigit()


def test_date_versioned_properties_expose_id_legacy_without_duplicates(api):
    created = api.post(
        CONTACT_PROPERTIES,
        headers=H,
        json={
            "name": "id_legacy",
            "label": "ID legacy",
            "type": "string",
            "fieldType": "text",
            "groupName": "contactinformation",
        },
    )
    assert created.status_code == 201, created.text

    definitions = api.get(CONTACT_PROPERTIES, headers=H)
    assert definitions.status_code == 200, definitions.text
    assert [item["name"] for item in definitions.json()["results"]].count("id_legacy") == 1

    contact = api.post(CONTACTS, headers=H, json={"properties": {"id_legacy": "C-0001"}})
    assert contact.status_code == 201, contact.text
    contact_id = contact.json()["id"]
    retrieved = api.get(
        f"{CONTACTS}/{contact_id}", headers=H, params={"properties": "id_legacy"}
    )
    assert retrieved.status_code == 200, retrieved.text
    assert retrieved.json()["properties"]["id_legacy"] == "C-0001"

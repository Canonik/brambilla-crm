"""Brambilla-specific property definitions (created by the migration, or lazily on first use)."""
from __future__ import annotations

ID_LEGACY_TYPES = ["companies", "contacts", "deals", "line_items", "tickets", "notes", "calls", "emails", "meetings"]

CUSTOM_PROPERTIES: dict[str, list[dict]] = {
    "companies": [
        {"name": "id_legacy", "label": "ID Sinergia", "type": "string", "fieldType": "text", "groupName": "companyinformation"},
        {"name": "partita_iva", "label": "Partita IVA", "type": "string", "fieldType": "text", "groupName": "companyinformation", "hasUniqueValue": True},
        {"name": "fatturato_2025", "label": "Fatturato 2025", "type": "number", "fieldType": "number", "groupName": "companyinformation"},
        {"name": "classe_cliente", "label": "Classe cliente", "type": "string", "fieldType": "text", "groupName": "companyinformation"},
    ],
    "contacts": [
        {"name": "id_legacy", "label": "ID Sinergia", "type": "string", "fieldType": "text", "groupName": "contactinformation"},
    ],
    "deals": [
        {"name": "id_legacy", "label": "ID Sinergia", "type": "string", "fieldType": "text", "groupName": "dealinformation"},
        {"name": "commerciale", "label": "Commerciale", "type": "string", "fieldType": "text", "groupName": "dealinformation"},
    ],
    "line_items": [
        {"name": "id_legacy", "label": "ID Sinergia", "type": "string", "fieldType": "text", "groupName": "lineiteminformation"},
    ],
    "tickets": [
        {"name": "id_legacy", "label": "ID Sinergia", "type": "string", "fieldType": "text", "groupName": "ticketinformation"},
        {"name": "assegnatario", "label": "Assegnatario", "type": "string", "fieldType": "text", "groupName": "ticketinformation"},
    ],
}
for _t in ("notes", "calls", "emails", "meetings"):
    CUSTOM_PROPERTIES[_t] = [
        {"name": "id_legacy", "label": "ID Sinergia", "type": "string", "fieldType": "text", "groupName": _t[:-1]},
        {"name": "autore", "label": "Autore", "type": "string", "fieldType": "text", "groupName": _t[:-1]},
    ]
CUSTOM_PROPERTIES["tasks"] = [
    {"name": "autore", "label": "Autore", "type": "string", "fieldType": "text", "groupName": "task"},
]


def custom_property(object_type: str, name: str) -> dict | None:
    for p in CUSTOM_PROPERTIES.get(object_type, []):
        if p["name"] == name:
            return p
    return None


def ensure_all(conn) -> None:
    from .routers.properties import ensure_property
    for ot, props in CUSTOM_PROPERTIES.items():
        for p in props:
            ensure_property(conn, ot, p)

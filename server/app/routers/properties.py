from __future__ import annotations

import hashlib

import psycopg
from fastapi import APIRouter, Request, Response
from psycopg import sql
from psycopg.types.json import Jsonb

from .. import db, defaults
from ..errors import ApiError, not_found, validation
from ..store import invalidate_caches
from ..util import now_iso
from .common import batch_inputs, int_field, json_body, object_type_or_404

router = APIRouter()

VALID_TYPES = {"string", "number", "date", "datetime", "enumeration", "bool"}
VALID_FIELD_TYPES = {"text", "textarea", "number", "date", "select", "radio", "checkbox", "booleancheckbox", "file", "calculation_equation", "html", "phonenumber"}


def build_definition(object_type: str, body: dict, *, hubspot_defined: bool = False) -> dict:
    name = body.get("name")
    if not name or not isinstance(name, str):
        raise validation("name is required")
    name = name.strip().lower()
    if not name.replace("_", "").isalnum() or name[0].isdigit():
        raise validation(f"Invalid property name {name!r}: use lowercase letters, numbers and underscores")
    t = body.get("type") or "string"
    if t not in VALID_TYPES:
        raise validation(f"Invalid type {t!r}")
    ft = body.get("fieldType") or {"string": "text", "number": "number", "date": "date", "datetime": "date", "enumeration": "select", "bool": "booleancheckbox"}[t]
    if ft not in VALID_FIELD_TYPES:
        raise validation(f"Invalid fieldType {ft!r}")
    for key in ("label", "description", "groupName", "fieldType"):
        if body.get(key) is not None and not isinstance(body.get(key), str):
            raise validation(f"{key} must be a string")
    if body.get("options") is not None and not isinstance(body.get("options"), list):
        raise validation("options must be an array")
    group = body.get("groupName") or (defaults.DEFAULT_GROUPS.get(object_type) or [("information", "Information")])[0][0]
    opts = []
    for i, o in enumerate(body.get("options") or []):
        if isinstance(o, dict):
            opts.append({"label": str(o.get("label", o.get("value"))), "value": str(o.get("value")), "displayOrder": int_field(o.get("displayOrder"), "options.displayOrder", i), "hidden": bool(o.get("hidden", False)), "description": o.get("description")})
    ts = now_iso()
    return {
        "name": name, "label": body.get("label") or name, "type": t, "fieldType": ft,
        "description": body.get("description") or "", "groupName": group, "options": opts,
        "displayOrder": int_field(body.get("displayOrder"), "displayOrder", -1), "calculated": False, "externalOptions": False,
        "hasUniqueValue": bool(body.get("hasUniqueValue", False)), "hidden": bool(body.get("hidden", False)),
        "hubspotDefined": hubspot_defined, "formField": bool(body.get("formField", False)),
        "modificationMetadata": {"archivable": True, "readOnlyDefinition": False, "readOnlyValue": False},
        "createdAt": ts, "updatedAt": ts, "archived": False,
    }


# These two already have dedicated unique indexes in schema.sql.
_BUILTIN_UNIQUE = {("contacts", "email"), ("companies", "partita_iva")}


def _unique_index_name(object_type: str, name: str) -> str:
    return "objects_uq_" + hashlib.md5(f"{object_type}:{name}".encode()).hexdigest()[:16]


def ensure_unique_index(conn, object_type: str, name: str) -> None:
    """Enforce hasUniqueValue with a partial unique index on the property's value."""
    if (object_type, name) in _BUILTIN_UNIQUE:
        return
    stmt = sql.SQL("CREATE UNIQUE INDEX IF NOT EXISTS {} ON objects ((properties->>{})) WHERE object_type = {} AND NOT archived AND properties ? {}").format(
        sql.Identifier(_unique_index_name(object_type, name)), sql.Literal(name), sql.Literal(object_type), sql.Literal(name))
    try:
        with conn.transaction():
            conn.execute(stmt)
    except psycopg.errors.UniqueViolation:
        raise validation(f"Cannot make {name} unique: existing {object_type} already share a value for it")


def drop_unique_index(conn, object_type: str, name: str) -> None:
    conn.execute(sql.SQL("DROP INDEX IF EXISTS {}").format(sql.Identifier(_unique_index_name(object_type, name))))


def require_fields(body: dict) -> None:
    """The reference marks these four as required when creating a property over the API."""
    missing = [k for k in ("name", "label", "type", "fieldType", "groupName") if not body.get(k)]
    if missing:
        raise validation("Missing required property fields: " + ", ".join(missing))


def create_property(conn, object_type: str, body: dict, *, replace: bool = False) -> dict:
    d = build_definition(object_type, body)
    existing = conn.execute("SELECT 1 FROM properties WHERE object_type = %s AND name = %s", (object_type, d["name"])).fetchone()
    if existing and not replace:
        raise ApiError(409, f"Property {d['name']} already exists", "CONFLICT", [{"isValid": False, "message": "Property already exists", "error": "PROPERTY_EXISTS", "name": d["name"]}])
    if d["hasUniqueValue"]:
        ensure_unique_index(conn, object_type, d["name"])
    elif existing:
        drop_unique_index(conn, object_type, d["name"])
    conn.execute(
        "INSERT INTO properties (object_type, name, definition) VALUES (%s, %s, %s) ON CONFLICT (object_type, name) DO UPDATE SET definition = EXCLUDED.definition",
        (object_type, d["name"], Jsonb(d)),
    )
    invalidate_caches()
    return d


def ensure_property(conn, object_type: str, body: dict) -> dict:
    """Create if missing; return the definition."""
    row = conn.execute("SELECT definition FROM properties WHERE object_type = %s AND name = %s", (object_type, body["name"])).fetchone()
    if row:
        return row["definition"]
    return create_property(conn, object_type, body)


@router.get("/{object_type}")
def list_properties(object_type: str, archived: str | None = None):
    ot = object_type_or_404(object_type)
    with db.connection() as conn:
        rows = conn.execute("SELECT definition FROM properties WHERE object_type = %s ORDER BY name", (ot,)).fetchall()
    return {"results": [r["definition"] for r in rows]}


@router.post("/{object_type}", status_code=201)
async def create_property_ep(object_type: str, request: Request):
    ot = object_type_or_404(object_type)
    body = await json_body(request)
    require_fields(body)
    with db.connection() as conn:
        d = create_property(conn, ot, body)
        conn.commit()
    return d


@router.post("/{object_type}/batch/create", status_code=201)
async def batch_create_properties(object_type: str, request: Request):
    ot = object_type_or_404(object_type)
    body = await json_body(request)
    results = []
    with db.connection() as conn:
        for inp in batch_inputs(body):
            require_fields(inp)
            results.append(create_property(conn, ot, inp, replace=True))
        conn.commit()
    return {"status": "COMPLETE", "results": results, "startedAt": now_iso(), "completedAt": now_iso()}


@router.post("/{object_type}/batch/read")
async def batch_read_properties(object_type: str, request: Request):
    ot = object_type_or_404(object_type)
    body = await json_body(request)
    names = [i.get("name") for i in batch_inputs(body) if isinstance(i.get("name"), str)]
    with db.connection() as conn:
        rows = conn.execute("SELECT definition FROM properties WHERE object_type = %s AND name = ANY(%s)", (ot, names)).fetchall()
    return {"status": "COMPLETE", "results": [r["definition"] for r in rows], "startedAt": now_iso(), "completedAt": now_iso()}


@router.post("/{object_type}/batch/archive", status_code=204)
async def batch_archive_properties(object_type: str, request: Request):
    ot = object_type_or_404(object_type)
    body = await json_body(request)
    names = [i.get("name") for i in batch_inputs(body) if isinstance(i.get("name"), str)]
    with db.connection() as conn:
        for n in names:
            drop_unique_index(conn, ot, n)
        conn.execute("DELETE FROM properties WHERE object_type = %s AND name = ANY(%s) AND NOT (definition->>'hubspotDefined')::boolean", (ot, names))
        conn.commit()
    invalidate_caches()
    return Response(status_code=204)


@router.get("/{object_type}/groups")
def list_groups(object_type: str):
    ot = object_type_or_404(object_type)
    with db.connection() as conn:
        rows = conn.execute("SELECT definition FROM property_groups WHERE object_type = %s ORDER BY (definition->>'displayOrder')::int", (ot,)).fetchall()
    return {"results": [r["definition"] for r in rows]}


@router.post("/{object_type}/groups", status_code=201)
async def create_group(object_type: str, request: Request):
    ot = object_type_or_404(object_type)
    body = await json_body(request)
    name = body.get("name")
    if not name or not isinstance(name, str):
        raise validation("name is required")
    d = {"name": name, "label": str(body.get("label") or name), "displayOrder": int_field(body.get("displayOrder"), "displayOrder", -1), "archived": False}
    with db.connection() as conn:
        conn.execute("INSERT INTO property_groups (object_type, name, definition) VALUES (%s, %s, %s) ON CONFLICT (object_type, name) DO UPDATE SET definition = EXCLUDED.definition", (ot, name, Jsonb(d)))
        conn.commit()
    return d


@router.get("/{object_type}/groups/{group_name}")
def get_group(object_type: str, group_name: str):
    ot = object_type_or_404(object_type)
    with db.connection() as conn:
        row = conn.execute("SELECT definition FROM property_groups WHERE object_type = %s AND name = %s", (ot, group_name)).fetchone()
    if not row:
        raise not_found(f"Property group {group_name} does not exist")
    return row["definition"]


@router.patch("/{object_type}/groups/{group_name}")
async def update_group(object_type: str, group_name: str, request: Request):
    ot = object_type_or_404(object_type)
    body = await json_body(request)
    with db.connection() as conn:
        row = conn.execute("SELECT definition FROM property_groups WHERE object_type = %s AND name = %s", (ot, group_name)).fetchone()
        if not row:
            raise not_found(f"Property group {group_name} does not exist")
        d = dict(row["definition"])
        for k in ("label", "displayOrder"):
            if k in body:
                d[k] = body[k]
        conn.execute("UPDATE property_groups SET definition = %s WHERE object_type = %s AND name = %s", (Jsonb(d), ot, group_name))
        conn.commit()
    return d


@router.delete("/{object_type}/groups/{group_name}", status_code=204)
def delete_group(object_type: str, group_name: str):
    ot = object_type_or_404(object_type)
    with db.connection() as conn:
        conn.execute("DELETE FROM property_groups WHERE object_type = %s AND name = %s", (ot, group_name))
        conn.commit()
    return Response(status_code=204)


@router.get("/{object_type}/{property_name}")
def get_property(object_type: str, property_name: str):
    ot = object_type_or_404(object_type)
    with db.connection() as conn:
        row = conn.execute("SELECT definition FROM properties WHERE object_type = %s AND name = %s", (ot, property_name)).fetchone()
    if not row:
        raise not_found(f"Property {property_name} does not exist")
    return row["definition"]


@router.patch("/{object_type}/{property_name}")
async def update_property(object_type: str, property_name: str, request: Request):
    ot = object_type_or_404(object_type)
    body = await json_body(request)
    with db.connection() as conn:
        row = conn.execute("SELECT definition FROM properties WHERE object_type = %s AND name = %s", (ot, property_name)).fetchone()
        if not row:
            raise not_found(f"Property {property_name} does not exist")
        d = dict(row["definition"])
        for k in ("label", "description", "groupName", "displayOrder", "hidden", "formField", "type", "fieldType"):
            if k in body:
                d[k] = body[k]
        if "options" in body:
            d["options"] = build_definition(ot, {"name": property_name, "options": body["options"]})["options"]
        d["updatedAt"] = now_iso()
        conn.execute("UPDATE properties SET definition = %s WHERE object_type = %s AND name = %s", (Jsonb(d), ot, property_name))
        conn.commit()
    invalidate_caches()
    return d


@router.delete("/{object_type}/{property_name}", status_code=204)
def delete_property(object_type: str, property_name: str):
    ot = object_type_or_404(object_type)
    with db.connection() as conn:
        row = conn.execute("SELECT definition FROM properties WHERE object_type = %s AND name = %s", (ot, property_name)).fetchone()
        if not row:
            raise not_found(f"Property {property_name} does not exist")
        if row["definition"].get("hubspotDefined"):
            raise validation(f"Property {property_name} is HubSpot defined and cannot be deleted")
        drop_unique_index(conn, ot, property_name)
        conn.execute("DELETE FROM properties WHERE object_type = %s AND name = %s", (ot, property_name))
        conn.commit()
    invalidate_caches()
    return Response(status_code=204)

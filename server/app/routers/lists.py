from __future__ import annotations

from fastapi import APIRouter, Request, Response
from psycopg.types.json import Jsonb

from .. import db, defaults
from ..errors import not_found, validation
from ..store import Store
from ..util import iso, parse_record_id, utcnow
from .common import _ANY, int_field, int_limit, json_body

router = APIRouter(prefix="/crm/v3/lists")


def _list_out(conn, d: dict) -> dict:
    out = dict(d)
    n = conn.execute("SELECT count(*) AS n FROM list_memberships WHERE list_id = %s", (int(d["listId"]),)).fetchone()["n"]
    out["additionalProperties"] = {"hs_list_size": str(n)}
    out["size"] = int(n)
    return out


def create_list(conn, name: str, object_type_id: str, processing_type: str = "MANUAL", filter_branch=None) -> dict:
    ot = defaults.resolve_type(object_type_id)
    if ot is None:
        raise validation(f"Unknown objectTypeId {object_type_id}")
    lid = int(conn.execute("SELECT nextval('lists_id_seq') AS id").fetchone()["id"])
    now = iso(utcnow())
    d = {
        "listId": str(lid), "listVersion": 1, "name": name, "objectTypeId": defaults.type_id(ot),
        "processingType": processing_type, "processingStatus": "COMPLETE", "createdAt": now, "updatedAt": now,
        "filtersUpdatedAt": now, "createdById": "1", "updatedById": "1", "listPermissions": {"hs_can_edit": True, "hs_can_view": True, "hs_can_delete": True},
    }
    if filter_branch is not None:
        d["filterBranch"] = filter_branch
    conn.execute("INSERT INTO lists (list_id, definition) VALUES (%s, %s)", (lid, Jsonb(d)))
    return d


def _get(conn, list_id: str) -> dict:
    lid = parse_record_id(list_id)
    if lid is None:
        raise not_found(f"List {list_id} not found")
    row = conn.execute("SELECT definition FROM lists WHERE list_id = %s", (lid,)).fetchone()
    if not row:
        raise not_found(f"List {list_id} not found")
    return row["definition"]


@router.post("")
@router.post("/")
async def create_list_ep(request: Request):
    body = await json_body(request)
    name = body.get("name")
    if not name or not isinstance(name, str):
        raise validation("name is required")
    ot = body.get("objectTypeId") or "0-1"
    with db.connection() as conn:
        d = create_list(conn, name, ot, body.get("processingType") or "MANUAL", body.get("filterBranch"))
        out = _list_out(conn, d)
        conn.commit()
    return {"list": out}


@router.post("/search")
async def search_lists(request: Request):
    body = await json_body(request)
    q = str(body.get("query") or "").strip().lower()
    types = body.get("processingTypes") or []
    if not isinstance(types, list):
        raise validation("processingTypes must be an array")
    offset = int_field(body.get("offset"), "offset", 0)
    count = int_field(body.get("count"), "count", 20)
    if offset < 0 or count < 0:
        raise validation("offset and count must not be negative")
    with db.connection() as conn:
        rows = conn.execute("SELECT definition FROM lists ORDER BY list_id").fetchall()
        items = [r["definition"] for r in rows]
        if q:
            items = [d for d in items if q in d["name"].lower()]
        if types:
            items = [d for d in items if d["processingType"] in types]
        total = len(items)
        page = [_list_out(conn, d) for d in items[offset:offset + count]]
    return {"lists": page, "hasMore": offset + count < total, "offset": offset + len(page), "total": total}


@router.get("/object-type-id/{object_type_id}/name/{list_name}")
def get_list_by_name(object_type_id: str, list_name: str):
    ot = defaults.resolve_type(object_type_id)
    if ot is None:
        raise not_found(f"Unknown objectTypeId {object_type_id}")
    with db.connection() as conn:
        rows = conn.execute("SELECT definition FROM lists WHERE definition->>'objectTypeId' = %s AND lower(definition->>'name') = lower(%s) ORDER BY list_id DESC", (defaults.type_id(ot), list_name)).fetchall()
        if not rows:
            raise not_found(f"List {list_name} not found")
        out = _list_out(conn, rows[0]["definition"])
    return {"list": out}


@router.get("")
@router.get("/")
def get_lists_by_ids(listIds: list[str] | None = None, includeFilters: str | None = None):
    with db.connection() as conn:
        if listIds:
            rows = conn.execute("SELECT definition FROM lists WHERE list_id = ANY(%s) ORDER BY list_id", ([i for i in (parse_record_id(x) for x in listIds) if i is not None],)).fetchall()
        else:
            rows = conn.execute("SELECT definition FROM lists ORDER BY list_id").fetchall()
        return {"lists": [_list_out(conn, r["definition"]) for r in rows]}


@router.get("/{list_id}")
def get_list(list_id: str):
    with db.connection() as conn:
        d = _get(conn, list_id)
        return {"list": _list_out(conn, d)}


@router.delete("/{list_id}", status_code=204)
def delete_list(list_id: str):
    with db.connection() as conn:
        d = _get(conn, list_id)
        conn.execute("DELETE FROM lists WHERE list_id = %s", (int(d["listId"]),))
        conn.execute("DELETE FROM list_memberships WHERE list_id = %s", (int(d["listId"]),))
        conn.commit()
    return Response(status_code=204)


@router.put("/{list_id}/restore", status_code=204)
def restore_list(list_id: str):
    return Response(status_code=204)


@router.put("/{list_id}/update-list-name")
def rename_list(list_id: str, listName: str | None = None, includeFilters: str | None = None):
    if not listName:
        raise validation("listName is required")
    with db.connection() as conn:
        d = _get(conn, list_id)
        d["name"] = listName
        d["updatedAt"] = iso(utcnow())
        conn.execute("UPDATE lists SET definition = %s WHERE list_id = %s", (Jsonb(d), int(d["listId"])))
        out = _list_out(conn, d)
        conn.commit()
    return {"updatedList": out}


@router.put("/{list_id}/update-list-filters")
async def update_filters(list_id: str, request: Request):
    body = await json_body(request)
    with db.connection() as conn:
        d = _get(conn, list_id)
        d["filterBranch"] = body
        d["filtersUpdatedAt"] = iso(utcnow())
        d["listVersion"] = int(d.get("listVersion", 1)) + 1
        conn.execute("UPDATE lists SET definition = %s WHERE list_id = %s", (Jsonb(d), int(d["listId"])))
        out = _list_out(conn, d)
        conn.commit()
    return {"updatedList": out}


@router.get("/{list_id}/memberships")
def list_memberships(list_id: str, request: Request, limit: str | None = None, after: str | None = None, before: str | None = None):
    lim = int_limit(limit, 100, 250)
    with db.connection() as conn:
        d = _get(conn, list_id)
        lid = int(d["listId"])
        params: list = [lid]
        sql = "SELECT record_id, added_at FROM list_memberships WHERE list_id = %s"
        if after:
            cursor = parse_record_id(after)
            if cursor is None:
                raise validation(f"Invalid paging cursor: {after}")
            sql += " AND record_id > %s"
            params.append(cursor)
        sql += " ORDER BY record_id LIMIT %s"
        params.append(lim + 1)
        rows = conn.execute(sql, params).fetchall()
        total = conn.execute("SELECT count(*) AS n FROM list_memberships WHERE list_id = %s", (lid,)).fetchone()["n"]
    more = len(rows) > lim
    rows = rows[:lim]
    out = {"results": [{"recordId": str(r["record_id"]), "membershipTimestamp": iso(r["added_at"])} for r in rows], "total": int(total)}
    if more:
        q = dict(request.query_params)
        q["after"] = str(rows[-1]["record_id"])
        out["paging"] = {"next": {"after": str(rows[-1]["record_id"]), "link": str(request.url.replace_query_params(**q))}}
    return out


@router.get("/{list_id}/memberships/join-order")
def list_memberships_join_order(list_id: str, request: Request, limit: str | None = None, after: str | None = None):
    return list_memberships(list_id, request, limit, after)


def _ids(body) -> list[int]:
    if not isinstance(body, list):
        raise validation("body must be a list of record ids")
    out = []
    for x in body:
        rid = parse_record_id(x)
        if rid is None:
            raise validation(f"invalid record id {x!r}")
        out.append(rid)
    return out


def add_members(conn, lid: int, ot: str, ids: list[int]) -> tuple[list[str], list[str]]:
    added, missing = [], []
    for rid in ids:
        ok = conn.execute("SELECT 1 FROM objects WHERE id = %s AND object_type = %s AND NOT archived", (rid, ot)).fetchone()
        if not ok:
            missing.append(str(rid))
            continue
        r = conn.execute("INSERT INTO list_memberships (list_id, record_id) VALUES (%s, %s) ON CONFLICT DO NOTHING RETURNING record_id", (lid, rid)).fetchone()
        if r:
            added.append(str(rid))
    return added, missing


@router.put("/{list_id}/memberships/add")
async def add_memberships(list_id: str, request: Request):
    ids = _ids(await json_body(request, expect=_ANY))
    with db.connection() as conn:
        d = _get(conn, list_id)
        ot = defaults.resolve_type(d["objectTypeId"])
        added, missing = add_members(conn, int(d["listId"]), ot, ids)
        conn.commit()
    return {"recordsIdsAdded": added, "recordIdsAdded": added, "recordIdsRemoved": [], "recordIdsMissing": missing}


@router.put("/{list_id}/memberships/remove")
async def remove_memberships(list_id: str, request: Request):
    ids = _ids(await json_body(request, expect=_ANY))
    with db.connection() as conn:
        d = _get(conn, list_id)
        removed = []
        for rid in ids:
            r = conn.execute("DELETE FROM list_memberships WHERE list_id = %s AND record_id = %s RETURNING record_id", (int(d["listId"]), rid)).fetchone()
            if r:
                removed.append(str(rid))
        conn.commit()
    return {"recordsIdsAdded": [], "recordIdsAdded": [], "recordIdsRemoved": removed, "recordIdsMissing": []}


@router.put("/{list_id}/memberships/add-and-remove")
async def add_remove_memberships(list_id: str, request: Request):
    body = await json_body(request)
    with db.connection() as conn:
        d = _get(conn, list_id)
        ot = defaults.resolve_type(d["objectTypeId"])
        added, missing = add_members(conn, int(d["listId"]), ot, _ids(body.get("recordIdsToAdd") or []))
        removed = []
        for rid in _ids(body.get("recordIdsToRemove") or []):
            r = conn.execute("DELETE FROM list_memberships WHERE list_id = %s AND record_id = %s RETURNING record_id", (int(d["listId"]), rid)).fetchone()
            if r:
                removed.append(str(rid))
        conn.commit()
    return {"recordsIdsAdded": added, "recordIdsAdded": added, "recordIdsRemoved": removed, "recordIdsMissing": missing}


@router.delete("/{list_id}/memberships", status_code=204)
def remove_all_memberships(list_id: str):
    with db.connection() as conn:
        d = _get(conn, list_id)
        conn.execute("DELETE FROM list_memberships WHERE list_id = %s", (int(d["listId"]),))
        conn.commit()
    return Response(status_code=204)

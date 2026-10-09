from __future__ import annotations

import csv
import io
import secrets
import threading

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from psycopg.types.json import Jsonb

from .. import db, defaults
from ..errors import not_found, validation
from ..store import Store
from ..search import build_order, build_where
from ..util import iso, parse_record_id
from .common import json_body

router = APIRouter(prefix="/crm/v3/exports")


def _filter(f):
    # the export guide's examples name the property `property`; the schema says `propertyName`
    if isinstance(f, dict) and "propertyName" not in f and "property" in f:
        f = dict(f, propertyName=f["property"])
    return f


def _sort(x):
    if isinstance(x, dict) and "direction" not in x and x.get("order"):
        order = str(x["order"]).upper()
        x = dict(x, direction="DESCENDING" if order.startswith("DESC") else "ASCENDING")
    return x


def _search_body(search: dict) -> dict:
    """publicCrmSearchRequest -> the body the CRM search understands."""
    groups = search.get("filterGroups") or []
    if not groups and search.get("filters"):
        groups = [{"filters": search["filters"]}]
    return {
        "filterGroups": [dict(g, filters=[_filter(f) for f in (g.get("filters") or [])]) for g in groups],
        "sorts": [_sort(x) for x in (search.get("sorts") or [])],
        "query": search.get("query"),
    }


def _run_export(task_id: int) -> None:
    try:
        with db.connection() as conn:
            row = conn.execute("SELECT request FROM export_tasks WHERE id = %s", (task_id,)).fetchone()
            req = row["request"]
            ot = defaults.resolve_type(req.get("objectType") or "contacts") or "contacts"
            props = req.get("objectProperties") or []
            s = Store(conn)
            params: list = []
            search = _search_body(req.get("publicCrmSearchRequest") or {})
            where = build_where(s, ot, search, params)
            if req.get("exportType") == "LIST" and req.get("listId"):
                where += " AND id IN (SELECT record_id FROM list_memberships WHERE list_id = %s)"
                params.append(int(req["listId"]))
            order = build_order(s, ot, search.get("sorts"))
            rows = conn.execute(f"SELECT id, properties FROM objects WHERE {where} ORDER BY {order}", params).fetchall()
            if not props:
                props = sorted({k for r in rows for k in r["properties"].keys()})
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(["Record ID"] + props)
            for r in rows:
                w.writerow([r["id"]] + [r["properties"].get(p, "") for p in props])
            content = buf.getvalue().encode("utf-8")
            conn.execute("UPDATE export_tasks SET status = 'COMPLETE', content = %s, filename = %s WHERE id = %s", (content, (req.get("exportName") or "export") + ".csv", task_id))
            conn.commit()
    except Exception as e:  # pragma: no cover
        with db.connection() as conn:
            conn.execute("UPDATE export_tasks SET status = 'FAILED' WHERE id = %s", (task_id,))
            conn.commit()


@router.post("/export/async")
async def start_export(request: Request):
    body = await json_body(request)
    if not body.get("exportType") or not body.get("format"):
        raise validation("exportType and format are required")
    if not body.get("objectType"):
        raise validation("objectType is required")
    if defaults.resolve_type(body.get("objectType")) is None:
        raise validation(f"Unknown objectType {body.get('objectType')!r}")
    props = body.get("objectProperties")
    if props is not None and (not isinstance(props, list) or not all(isinstance(p, str) for p in props)):
        raise validation("objectProperties must be an array of property names")
    if body.get("exportType") == "LIST" and parse_record_id(body.get("listId")) is None:
        raise validation("listId is required for a LIST export")
    search = body.get("publicCrmSearchRequest")
    if search is not None:
        if not isinstance(search, dict):
            raise validation("publicCrmSearchRequest must be an object")
        for key in ("filterGroups", "filters", "sorts"):
            if not isinstance(search.get(key) or [], list):
                raise validation(f"publicCrmSearchRequest.{key} must be an array")
        if not all(isinstance(g, dict) and isinstance(g.get("filters") or [], list) for g in search.get("filterGroups") or []):
            raise validation("each filter group must be an object with a filters array")
        # reject bad filters now, not as a FAILED task later
        with db.connection() as conn:
            body_search = _search_body(search)
            build_where(Store(conn), defaults.resolve_type(body.get("objectType")), body_search, [])
            build_order(Store(conn), defaults.resolve_type(body.get("objectType")), body_search.get("sorts"))
    token = secrets.token_urlsafe(24)
    with db.connection() as conn:
        tid = int(conn.execute("SELECT nextval('export_id_seq') AS id").fetchone()["id"])
        conn.execute("INSERT INTO export_tasks (id, status, token, request) VALUES (%s, 'PROCESSING', %s, %s)", (tid, token, Jsonb(body)))
        conn.commit()
    _run_export(tid)
    return JSONResponse(status_code=202, content={"id": str(tid), "links": {"status": f"/crm/v3/exports/export/async/tasks/{tid}/status"}})


@router.get("/export/async/tasks/{task_id}/status")
def export_status(task_id: str):
    with db.connection() as conn:
        tid = parse_record_id(task_id)
        row = conn.execute("SELECT id, status, token, created_at FROM export_tasks WHERE id = %s", (tid if tid is not None else -1,)).fetchone()
    if not row:
        raise not_found(f"Export task {task_id} not found")
    at = iso(row["created_at"])
    # exports run inside the create request, so they start and finish at creation time
    out = {"status": row["status"], "requestedAt": at, "startedAt": at, "completedAt": at, "links": {}}
    if row["status"] == "COMPLETE":
        out["result"] = f"/crm/v3/exports/download/{row['token']}"
    return out


@router.get("/export/{export_id}")
def export_by_id(export_id: str):
    with db.connection() as conn:
        eid = parse_record_id(export_id)
        row = conn.execute("SELECT id, status, request, content, created_at FROM export_tasks WHERE id = %s", (eid if eid is not None else -1,)).fetchone()
    if not row:
        raise not_found(f"Export {export_id} not found")
    req = row["request"]
    at = iso(row["created_at"])
    out = {
        "id": str(row["id"]), "exportName": req.get("exportName") or "export", "exportType": req.get("exportType"),
        "objectType": defaults.type_id(defaults.resolve_type(req.get("objectType")) or "contacts"),
        "objectProperties": req.get("objectProperties") or [], "createdAt": at, "updatedAt": at,
        "exportState": {"COMPLETE": "DONE", "FAILED": "FAILED"}.get(row["status"], "PROCESSING"),
    }
    if row["content"] is not None:
        out["recordCount"] = max(0, len(list(csv.reader(io.StringIO(bytes(row["content"]).decode("utf-8"))))) - 1)
    return out


@router.get("/download/{token}")
def download(token: str):
    with db.connection() as conn:
        row = conn.execute("SELECT content, filename FROM export_tasks WHERE token = %s AND status = 'COMPLETE'", (token,)).fetchone()
    if not row:
        raise not_found("export not found")
    return Response(content=bytes(row["content"]), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{row["filename"]}"'})

from __future__ import annotations

import csv
import io
import secrets
import threading

from fastapi import APIRouter, Request, Response
from psycopg.types.json import Jsonb

from .. import db, defaults
from ..errors import not_found, validation
from ..store import Store
from ..search import build_where
from .common import json_body

router = APIRouter(prefix="/crm/v3/exports")


def _run_export(task_id: int) -> None:
    try:
        with db.connection() as conn:
            row = conn.execute("SELECT request FROM export_tasks WHERE id = %s", (task_id,)).fetchone()
            req = row["request"]
            ot = defaults.resolve_type(req.get("objectType") or "contacts") or "contacts"
            props = req.get("objectProperties") or []
            s = Store(conn)
            params: list = []
            search = req.get("publicCrmSearchRequest") or {}
            where = build_where(s, ot, {"filterGroups": [{"filters": search.get("filters", [])}] if search.get("filters") else [], "query": search.get("query")}, params)
            if req.get("exportType") == "LIST" and req.get("listId"):
                where += " AND id IN (SELECT record_id FROM list_memberships WHERE list_id = %s)"
                params.append(int(req["listId"]))
            rows = conn.execute(f"SELECT id, properties FROM objects WHERE {where} ORDER BY id", params).fetchall()
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
    token = secrets.token_urlsafe(24)
    with db.connection() as conn:
        tid = int(conn.execute("SELECT nextval('export_id_seq') AS id").fetchone()["id"])
        conn.execute("INSERT INTO export_tasks (id, status, token, request) VALUES (%s, 'PROCESSING', %s, %s)", (tid, token, Jsonb(body)))
        conn.commit()
    _run_export(tid)
    return {"id": str(tid), "links": {"status": f"/crm/v3/exports/export/async/tasks/{tid}/status"}}


@router.get("/export/async/tasks/{task_id}/status")
def export_status(task_id: str):
    with db.connection() as conn:
        row = conn.execute("SELECT id, status, token FROM export_tasks WHERE id = %s", (int(task_id) if task_id.isdigit() else -1,)).fetchone()
    if not row:
        raise not_found(f"Export task {task_id} not found")
    out = {"status": row["status"]}
    if row["status"] == "COMPLETE":
        out["result"] = f"/crm/v3/exports/download/{row['token']}"
    return out


@router.get("/download/{token}")
def download(token: str):
    with db.connection() as conn:
        row = conn.execute("SELECT content, filename FROM export_tasks WHERE token = %s AND status = 'COMPLETE'", (token,)).fetchone()
    if not row:
        raise not_found("export not found")
    return Response(content=bytes(row["content"]), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{row["filename"]}"'})

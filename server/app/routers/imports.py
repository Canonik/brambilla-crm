from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter, Request, Response
from psycopg.types.json import Jsonb

from .. import db, defaults
from ..errors import ApiError, not_found, validation
from ..store import Store
from ..util import iso, utcnow

router = APIRouter(prefix="/crm/v3/imports")


@router.post("", status_code=200)
@router.post("/", status_code=200)
async def create_import(request: Request):
    form = await request.form()
    raw = form.get("importRequest")
    if raw is None:
        raise validation("importRequest is required")
    try:
        req = json.loads(raw if isinstance(raw, str) else await raw.read())
    except Exception:
        raise validation("importRequest must be JSON")
    files = form.getlist("files")
    if not files:
        raise validation("files are required")
    created, errors = 0, []
    with db.connection() as conn:
        s = Store(conn)
        for spec, up in zip(req.get("files") or [], files):
            data = await up.read()
            text = data.decode("utf-8-sig", errors="replace")
            fmt = spec.get("fileFormat", "CSV")
            delimiter = "," if fmt == "CSV" else ";"
            if ";" in text.splitlines()[0] and "," not in text.splitlines()[0]:
                delimiter = ";"
            reader = csv.reader(io.StringIO(text), delimiter=delimiter)
            header = next(reader, [])
            mappings = (spec.get("fileImportPage") or {}).get("columnMappings") or []
            colmap = {}
            for m in mappings:
                ot = defaults.resolve_type(m.get("columnObjectTypeId") or "0-1") or "contacts"
                colmap[m.get("columnName")] = (ot, m.get("propertyName"), m.get("idColumnType"))
            for row in reader:
                by_type: dict[str, dict] = {}
                for name, val in zip(header, row):
                    if name in colmap and colmap[name][1]:
                        ot, pname, _ = colmap[name]
                        by_type.setdefault(ot, {})[pname] = val
                for ot, props in by_type.items():
                    try:
                        with conn.transaction():
                            if ot == "contacts" and props.get("email"):
                                s.upsert(ot, "email", props["email"], props)
                            else:
                                s.create(ot, props)
                        created += 1
                    except ApiError as e:
                        errors.append({"message": e.message})
        iid = int(conn.execute("SELECT nextval('import_id_seq') AS id").fetchone()["id"])
        d = {"id": str(iid), "state": "DONE", "createdAt": iso(utcnow()), "updatedAt": iso(utcnow()), "metadata": {"objectLists": [], "counters": {"CREATED": created, "ERRORS": len(errors)}, "fileIds": []}, "importRequestJson": req, "optOutImport": False}
        conn.execute("INSERT INTO import_tasks (id, definition) VALUES (%s, %s)", (iid, Jsonb(d)))
        conn.commit()
    return d


@router.get("/{import_id}")
def get_import(import_id: str):
    with db.connection() as conn:
        row = conn.execute("SELECT definition FROM import_tasks WHERE id = %s", (int(import_id) if import_id.isdigit() else -1,)).fetchone()
    if not row:
        raise not_found(f"Import {import_id} not found")
    return row["definition"]


@router.get("")
@router.get("/")
def list_imports():
    with db.connection() as conn:
        rows = conn.execute("SELECT definition FROM import_tasks ORDER BY id DESC").fetchall()
    return {"results": [r["definition"] for r in rows]}


@router.post("/{import_id}/cancel")
def cancel_import(import_id: str):
    return {"id": import_id, "state": "CANCELED"}


@router.get("/{import_id}/errors")
def import_errors(import_id: str):
    return {"results": []}

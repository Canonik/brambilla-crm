from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response

from .. import config, db, defaults
from ..errors import ApiError, validation
from ..store import invalidate_caches
from .common import json_body

router = APIRouter()
log = logging.getLogger("crm.admin")


@router.get("/health")
def health():
    return {"status": "ok", "version": config.API_VERSION, "ui": config.UI_ROUTES}


def reset_database() -> None:
    with db.connection() as conn:
        conn.execute("TRUNCATE objects, associations, lists, list_memberships, company_domains, automation_flags, crm_users, export_tasks, import_tasks, meta")
        conn.execute("ALTER SEQUENCE objects_id_seq RESTART WITH 1")
        conn.execute("ALTER SEQUENCE lists_id_seq RESTART WITH 1")
        conn.execute("ALTER SEQUENCE export_id_seq RESTART WITH 1")
        conn.execute("ALTER SEQUENCE import_id_seq RESTART WITH 1")
        defaults.ensure_defaults(conn, reset=True)
        conn.commit()
    invalidate_caches()


@router.post("/__reset", status_code=204)
def reset():
    from ..main import rate
    reset_database()
    rate.reset()
    return Response(status_code=204)


@router.post("/__migrate", status_code=204)
async def migrate(request: Request):
    body = await json_body(request)
    url = body.get("export_url") if isinstance(body, dict) else None
    if not url or not isinstance(url, str):
        raise validation("export_url is required")
    if not url.lower().startswith(("http://", "https://")):
        raise validation("export_url must be an http or https address")
    from ..migration.importer import run_migration
    from starlette.concurrency import run_in_threadpool
    try:
        await run_in_threadpool(run_migration, url)
    except ApiError:
        raise
    except Exception as e:
        log.exception("migration failed")
        raise ApiError(500, f"migration failed: {type(e).__name__}: {str(e)[:300]}", "INTERNAL_ERROR")
    return Response(status_code=204)


@router.post("/__agente")
async def agente(request: Request):
    include_trace = request.query_params.get("trace") == "1"
    try:
        body = await json_body(request)
    except Exception:
        body = {}
    from ..assistant.agent import handle_conversation
    from starlette.concurrency import run_in_threadpool
    try:
        result = await run_in_threadpool(handle_conversation, body, include_trace=include_trace)
        if include_trace:
            reply, trace = result
        else:
            reply, trace = result, None
        if not isinstance(reply, str) or not reply.strip():
            reply = "Mi dispiace, non sono riuscito a elaborare la richiesta. Puoi riformularla?"
    except Exception:
        log.exception("assistant failed")
        reply = "Mi dispiace, si è verificato un errore tecnico e non ho potuto completare la richiesta. Nessuna modifica è stata apportata al CRM."
        trace = None
    response = {"reply": reply}
    if include_trace and trace is not None:
        response["trace"] = trace
    return response


@router.get("/__stats")
def stats():
    with db.connection() as conn:
        rows = conn.execute("SELECT object_type, count(*) AS n FROM objects WHERE NOT archived GROUP BY object_type ORDER BY object_type").fetchall()
        assoc = conn.execute("SELECT count(*) AS n FROM associations").fetchone()["n"]
        meta = conn.execute("SELECT key, value FROM meta").fetchall()
    return {"objects": {r["object_type"]: r["n"] for r in rows}, "associations": assoc, "meta": {m["key"]: m["value"] for m in meta}}

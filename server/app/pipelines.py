"""Pipeline persistence helpers shared by the API router and the migration."""
from __future__ import annotations

import json
import secrets

from psycopg.types.json import Jsonb

from . import store as store_mod
from .errors import not_found, validation
from .util import iso


def _new_id(conn) -> str:
    while True:
        cand = str(secrets.randbelow(900_000_000) + 100_000_000)
        if not conn.execute("SELECT 1 FROM pipelines WHERE id = %s", (cand,)).fetchone():
            return cand


def _norm_meta(meta: dict | None) -> dict:
    out = {}
    for k, v in (meta or {}).items():
        if isinstance(v, bool):
            out[k] = "true" if v else "false"
        else:
            out[k] = str(v)
    return out


def _stage_obj(conn, s: dict, i: int, now: str, existing_ids: set[str]) -> dict:
    if not isinstance(s, dict) or not s.get("label"):
        raise validation("each stage requires a label")
    sid = str(s.get("id") or "")
    if not sid or sid in existing_ids:
        sid = _new_id(conn)
    existing_ids.add(sid)
    return {
        "id": sid, "label": str(s["label"]), "displayOrder": int(s.get("displayOrder", i)),
        "metadata": _norm_meta(s.get("metadata")), "createdAt": now, "updatedAt": now, "archived": False,
        "writePermissions": "CRM_PERMISSIONS_ENFORCEMENT",
    }


def create_pipeline(store, object_type: str, body: dict) -> dict:
    if not isinstance(body, dict) or not body.get("label"):
        raise validation("pipeline requires a label")
    stages = body.get("stages") or []
    if not stages:
        raise validation("pipeline requires at least one stage")
    now = iso(store.now)
    pid = str(body.get("id") or _new_id(store.conn))
    ids: set[str] = set()
    pl = {
        "id": pid, "label": str(body["label"]), "displayOrder": int(body.get("displayOrder", 0)),
        "stages": [_stage_obj(store.conn, s, i, now, ids) for i, s in enumerate(stages)],
        "createdAt": now, "updatedAt": now, "archived": False,
    }
    store.conn.execute("INSERT INTO pipelines (object_type, id, definition) VALUES (%s, %s, %s)", (object_type, pid, Jsonb(pl)))
    store_mod.invalidate_caches()
    return pl


def get_pipeline(store, object_type: str, pid: str) -> dict:
    row = store.conn.execute("SELECT definition FROM pipelines WHERE object_type = %s AND id = %s", (object_type, pid)).fetchone()
    if not row:
        raise not_found(f"Pipeline {pid} not found")
    return row["definition"]


def save_pipeline(store, object_type: str, pl: dict) -> None:
    pl["updatedAt"] = iso(store.now)
    store.conn.execute("UPDATE pipelines SET definition = %s WHERE object_type = %s AND id = %s", (Jsonb(pl), object_type, pl["id"]))
    store_mod.invalidate_caches()


def delete_pipeline(store, object_type: str, pid: str) -> None:
    store.conn.execute("DELETE FROM pipelines WHERE object_type = %s AND id = %s", (object_type, pid))
    store_mod.invalidate_caches()

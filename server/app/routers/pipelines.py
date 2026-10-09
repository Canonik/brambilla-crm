from __future__ import annotations

from fastapi import APIRouter, Request, Response

from .. import db
from ..errors import not_found, validation
from ..pipelines import _int, _new_id, _norm_meta, create_pipeline, delete_pipeline, get_pipeline, save_pipeline
from ..store import Store
from ..util import iso
from .common import json_body, object_type_or_404

router = APIRouter(prefix="/crm/v3/pipelines")


@router.get("/{object_type}")
def list_pipelines(object_type: str):
    ot = object_type_or_404(object_type)
    with db.connection() as conn:
        s = Store(conn)
        return {"results": s.pipelines(ot)}


@router.post("/{object_type}", status_code=201)
async def create_pipeline_ep(object_type: str, request: Request):
    ot = object_type_or_404(object_type)
    body = await json_body(request)
    with db.connection() as conn:
        s = Store(conn)
        pl = create_pipeline(s, ot, body)
        conn.commit()
    return pl


@router.get("/{object_type}/{pipeline_id}")
def get_pipeline_ep(object_type: str, pipeline_id: str):
    ot = object_type_or_404(object_type)
    with db.connection() as conn:
        return get_pipeline(Store(conn), ot, pipeline_id)


@router.patch("/{object_type}/{pipeline_id}")
async def patch_pipeline(object_type: str, pipeline_id: str, request: Request):
    ot = object_type_or_404(object_type)
    body = await json_body(request)
    with db.connection() as conn:
        s = Store(conn)
        pl = get_pipeline(s, ot, pipeline_id)
        for k in ("label", "displayOrder", "archived"):
            if k in body:
                pl[k] = body[k]
        save_pipeline(s, ot, pl)
        conn.commit()
    return pl


@router.put("/{object_type}/{pipeline_id}")
async def replace_pipeline(object_type: str, pipeline_id: str, request: Request):
    ot = object_type_or_404(object_type)
    body = await json_body(request)
    with db.connection() as conn:
        s = Store(conn)
        pl = get_pipeline(s, ot, pipeline_id)
        if not body.get("label") or not body.get("stages"):
            raise validation("label and stages are required")
        if not isinstance(body["stages"], list) or not all(isinstance(st, dict) and st.get("label") for st in body["stages"]):
            raise validation("each stage requires a label")
        now = iso(s.now)
        existing = {st["id"]: st for st in pl["stages"]}
        new_stages = []
        for i, st in enumerate(body["stages"]):
            sid = str(st.get("id") or "")
            if sid in existing:
                d = dict(existing[sid])
                d.update({"label": st.get("label", d["label"]), "displayOrder": _int(st.get("displayOrder"), "displayOrder", i), "metadata": _norm_meta(st.get("metadata", d.get("metadata"))), "updatedAt": now})
            else:
                d = {"id": sid or _new_id(conn), "label": str(st["label"]), "displayOrder": _int(st.get("displayOrder"), "displayOrder", i), "metadata": _norm_meta(st.get("metadata")), "createdAt": now, "updatedAt": now, "archived": False, "writePermissions": "CRM_PERMISSIONS_ENFORCEMENT"}
            new_stages.append(d)
        pl["label"] = body["label"]
        pl["displayOrder"] = _int(body.get("displayOrder"), "displayOrder", pl.get("displayOrder", 0))
        pl["stages"] = new_stages
        save_pipeline(s, ot, pl)
        conn.commit()
    return pl


@router.delete("/{object_type}/{pipeline_id}", status_code=204)
def delete_pipeline_ep(object_type: str, pipeline_id: str):
    ot = object_type_or_404(object_type)
    with db.connection() as conn:
        s = Store(conn)
        get_pipeline(s, ot, pipeline_id)
        delete_pipeline(s, ot, pipeline_id)
        conn.commit()
    return Response(status_code=204)


@router.get("/{object_type}/{pipeline_id}/stages")
def list_stages(object_type: str, pipeline_id: str):
    ot = object_type_or_404(object_type)
    with db.connection() as conn:
        pl = get_pipeline(Store(conn), ot, pipeline_id)
    return {"results": pl["stages"]}


@router.post("/{object_type}/{pipeline_id}/stages", status_code=201)
async def create_stage(object_type: str, pipeline_id: str, request: Request):
    ot = object_type_or_404(object_type)
    body = await json_body(request)
    if not body.get("label"):
        raise validation("label is required")
    with db.connection() as conn:
        s = Store(conn)
        pl = get_pipeline(s, ot, pipeline_id)
        now = iso(s.now)
        st = {"id": _new_id(conn), "label": str(body["label"]), "displayOrder": _int(body.get("displayOrder"), "displayOrder", len(pl["stages"])), "metadata": _norm_meta(body.get("metadata")), "createdAt": now, "updatedAt": now, "archived": False, "writePermissions": "CRM_PERMISSIONS_ENFORCEMENT"}
        pl["stages"].append(st)
        save_pipeline(s, ot, pl)
        conn.commit()
    return st


@router.get("/{object_type}/{pipeline_id}/stages/{stage_id}")
def get_stage(object_type: str, pipeline_id: str, stage_id: str):
    ot = object_type_or_404(object_type)
    with db.connection() as conn:
        pl = get_pipeline(Store(conn), ot, pipeline_id)
    for st in pl["stages"]:
        if st["id"] == stage_id:
            return st
    raise not_found(f"Stage {stage_id} not found")


@router.patch("/{object_type}/{pipeline_id}/stages/{stage_id}")
async def patch_stage(object_type: str, pipeline_id: str, stage_id: str, request: Request):
    ot = object_type_or_404(object_type)
    body = await json_body(request)
    with db.connection() as conn:
        s = Store(conn)
        pl = get_pipeline(s, ot, pipeline_id)
        target = None
        for st in pl["stages"]:
            if st["id"] == stage_id:
                target = st
        if target is None:
            raise not_found(f"Stage {stage_id} not found")
        for k in ("label", "displayOrder", "archived"):
            if k in body:
                target[k] = body[k]
        if "metadata" in body:
            target["metadata"] = _norm_meta(body["metadata"])
        target["updatedAt"] = iso(s.now)
        save_pipeline(s, ot, pl)
        conn.commit()
    return target


@router.put("/{object_type}/{pipeline_id}/stages/{stage_id}")
async def replace_stage(object_type: str, pipeline_id: str, stage_id: str, request: Request):
    return await patch_stage(object_type, pipeline_id, stage_id, request)


@router.delete("/{object_type}/{pipeline_id}/stages/{stage_id}", status_code=204)
def delete_stage(object_type: str, pipeline_id: str, stage_id: str):
    ot = object_type_or_404(object_type)
    with db.connection() as conn:
        s = Store(conn)
        pl = get_pipeline(s, ot, pipeline_id)
        before = len(pl["stages"])
        pl["stages"] = [st for st in pl["stages"] if st["id"] != stage_id]
        if len(pl["stages"]) == before:
            raise not_found(f"Stage {stage_id} not found")
        save_pipeline(s, ot, pl)
        conn.commit()
    return Response(status_code=204)


@router.get("/{object_type}/{pipeline_id}/audit")
def pipeline_audit(object_type: str, pipeline_id: str):
    return {"results": []}


@router.get("/{object_type}/{pipeline_id}/stages/{stage_id}/audit")
def stage_audit(object_type: str, pipeline_id: str, stage_id: str):
    return {"results": []}

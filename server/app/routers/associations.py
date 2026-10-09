from __future__ import annotations

from fastapi import APIRouter, Request, Response

from .. import db, defaults
from ..errors import ApiError, not_found, validation
from ..store import Store
from ..util import iso, parse_record_id, utcnow
from .common import _ANY, batch_inputs, int_limit, json_body, object_type_or_404, ref_id

router = APIRouter()


def _assoc_result(ft, fid, tt, tid, labels):
    return {
        "fromObjectTypeId": defaults.type_id(ft), "fromObjectId": int(fid),
        "toObjectTypeId": defaults.type_id(tt), "toObjectId": int(tid),
        "labels": [l["label"] for l in labels if l.get("label")],
    }


@router.get("/crm/v4/objects/{object_type}/{object_id}/associations/{to_type}")
def list_associations(object_type: str, object_id: str, to_type: str, request: Request, limit: str | None = None, after: str | None = None):
    ot = object_type_or_404(object_type)
    tt = object_type_or_404(to_type)
    lim = int_limit(limit, 500, 500)
    with db.connection() as conn:
        s = Store(conn)
        fid = s.resolve_id(ot, object_id, None)
        if s._row(ot, fid) is None:
            raise not_found(f"No {ot} with ID {object_id} exists")
        results, next_after = s.associations_v4(ot, fid, tt, lim, after)
        conn.commit()
    out = {"results": results}
    if next_after:
        q = dict(request.query_params)
        q["after"] = next_after
        out["paging"] = {"next": {"after": next_after, "link": str(request.url.replace_query_params(**q))}}
    return out


@router.put("/crm/v4/objects/{object_type}/{object_id}/associations/default/{to_type}/{to_id}")
def put_default_association(object_type: str, object_id: str, to_type: str, to_id: str):
    ot = object_type_or_404(object_type)
    tt = object_type_or_404(to_type)
    with db.connection() as conn:
        s = Store(conn)
        fid = s.resolve_id(ot, object_id, None)
        tid = s.resolve_id(tt, to_id, None)
        labels = s.associate(ot, fid, tt, tid, None)
        conn.commit()
    return _assoc_result(ot, fid, tt, tid, labels)


@router.put("/crm/v4/objects/{object_type}/{object_id}/associations/{to_type}/{to_id}")
async def put_association(object_type: str, object_id: str, to_type: str, to_id: str, request: Request):
    ot = object_type_or_404(object_type)
    tt = object_type_or_404(to_type)
    body = await json_body(request, expect=_ANY)
    if isinstance(body, dict):
        body = [body] if body else []
    if not isinstance(body, list):
        raise validation("body must be a list of association specs")
    type_ids = []
    for spec in body:
        if not isinstance(spec, dict) or spec.get("associationTypeId") is None:
            raise validation("each association spec requires associationCategory and associationTypeId")
        tid = parse_record_id(spec["associationTypeId"])
        if tid is None:
            raise validation(f"Invalid associationTypeId: {spec['associationTypeId']!r}")
        type_ids.append(tid)
    with db.connection() as conn:
        s = Store(conn)
        fid = s.resolve_id(ot, object_id, None)
        tid = s.resolve_id(tt, to_id, None)
        labels = s.associate(ot, fid, tt, tid, type_ids or None)
        conn.commit()
    return _assoc_result(ot, fid, tt, tid, labels)


@router.delete("/crm/v4/objects/{object_type}/{object_id}/associations/{to_type}/{to_id}", status_code=204)
def delete_association(object_type: str, object_id: str, to_type: str, to_id: str):
    ot = object_type_or_404(object_type)
    tt = object_type_or_404(to_type)
    with db.connection() as conn:
        s = Store(conn)
        s.dissociate(ot, s.resolve_id(ot, object_id, None), tt, s.resolve_id(tt, to_id, None), None)
        conn.commit()
    return Response(status_code=204)


def _type_ids(types) -> list[int]:
    if types is None:
        return []
    if not isinstance(types, list) or not all(isinstance(t, dict) for t in types):
        raise validation("types must be an array of objects")
    out = []
    for t in types:
        if t.get("associationTypeId") is None:
            continue
        tid = parse_record_id(t["associationTypeId"])
        if tid is None:
            raise validation(f"Invalid associationTypeId: {t['associationTypeId']!r}")
        out.append(tid)
    return out


# ------------------------------------------------------------------ batch
@router.post("/crm/v4/associations/{from_type}/{to_type}/batch/create", status_code=201)
async def batch_create(from_type: str, to_type: str, request: Request):
    ft = object_type_or_404(from_type)
    tt = object_type_or_404(to_type)
    body = await json_body(request)
    started = iso(utcnow())
    results, errors = [], []
    with db.connection() as conn:
        s = Store(conn)
        for inp in batch_inputs(body):
            try:
                fid = ref_id(inp.get("from"), "from id")
                tid = ref_id(inp.get("to"), "to id")
                tids = _type_ids(inp.get("types"))
                with conn.transaction():
                    labels = s.associate(ft, fid, tt, tid, tids or None)
                results.append(_assoc_result(ft, fid, tt, tid, labels))
            except ApiError as e:
                errors.append({"status": "error", "category": e.category, "message": e.message, "context": {}})
        conn.commit()
    body_out = {"status": "COMPLETE", "results": results, "startedAt": started, "completedAt": iso(utcnow())}
    if errors:
        body_out["numErrors"] = len(errors)
        body_out["errors"] = errors
        return Response(content=__import__("json").dumps(body_out), status_code=207, media_type="application/json")
    return body_out


@router.post("/crm/v4/associations/{from_type}/{to_type}/batch/associate/default", status_code=201)
async def batch_create_default(from_type: str, to_type: str, request: Request):
    ft = object_type_or_404(from_type)
    tt = object_type_or_404(to_type)
    body = await json_body(request)
    started = iso(utcnow())
    results = []
    with db.connection() as conn:
        s = Store(conn)
        for inp in batch_inputs(body):
            fid = ref_id(inp.get("from"), "from id")
            tid = ref_id(inp.get("to"), "to id")
            labels = s.associate(ft, fid, tt, tid, None)
            results.append(_assoc_result(ft, fid, tt, tid, labels))
        conn.commit()
    return {"status": "COMPLETE", "results": results, "startedAt": started, "completedAt": iso(utcnow())}


@router.post("/crm/v4/associations/{from_type}/{to_type}/batch/read")
async def batch_read(from_type: str, to_type: str, request: Request):
    ft = object_type_or_404(from_type)
    tt = object_type_or_404(to_type)
    body = await json_body(request)
    started = iso(utcnow())
    results = []
    with db.connection() as conn:
        s = Store(conn)
        for inp in batch_inputs(body):
            fid = ref_id(inp, "id")
            rows, _ = s.associations_v4(ft, fid, tt, 500, None)
            if rows:
                results.append({"from": {"id": str(fid)}, "to": rows})
        conn.commit()
    return {"status": "COMPLETE", "results": results, "startedAt": started, "completedAt": iso(utcnow())}


@router.post("/crm/v4/associations/{from_type}/{to_type}/batch/archive", status_code=204)
async def batch_archive(from_type: str, to_type: str, request: Request):
    ft = object_type_or_404(from_type)
    tt = object_type_or_404(to_type)
    body = await json_body(request)
    with db.connection() as conn:
        s = Store(conn)
        for inp in batch_inputs(body):
            fid = ref_id(inp.get("from"), "from id")
            tos = inp.get("to") or []
            if not isinstance(tos, list):
                raise validation("to must be an array")
            for to in tos:
                s.dissociate(ft, fid, tt, ref_id(to, "to id"), None)
        conn.commit()
    return Response(status_code=204)


@router.post("/crm/v4/associations/{from_type}/{to_type}/batch/labels/archive", status_code=204)
async def batch_labels_archive(from_type: str, to_type: str, request: Request):
    ft = object_type_or_404(from_type)
    tt = object_type_or_404(to_type)
    body = await json_body(request)
    with db.connection() as conn:
        s = Store(conn)
        for inp in batch_inputs(body):
            fid = ref_id(inp.get("from"), "from id")
            tid = ref_id(inp.get("to"), "to id")
            tids = _type_ids(inp.get("types"))
            s.dissociate(ft, fid, tt, tid, tids)
        conn.commit()
    return Response(status_code=204)


# ------------------------------------------------------------------ schema / labels
def _label_row(r):
    return {"category": r["category"], "typeId": r["type_id"], "label": r["label"]}


@router.get("/crm/v4/associations/{from_type}/{to_type}/labels")
def get_labels(from_type: str, to_type: str):
    ft = object_type_or_404(from_type)
    tt = object_type_or_404(to_type)
    with db.connection() as conn:
        rows = conn.execute("SELECT * FROM association_labels WHERE from_type = %s AND to_type = %s ORDER BY type_id", (ft, tt)).fetchall()
    return {"results": [_label_row(r) for r in rows]}


@router.post("/crm/v4/associations/{from_type}/{to_type}/labels", status_code=201)
async def create_label(from_type: str, to_type: str, request: Request):
    ft = object_type_or_404(from_type)
    tt = object_type_or_404(to_type)
    body = await json_body(request)
    label = body.get("label")
    if not label or not isinstance(label, str):
        raise validation("label is required")
    name = body.get("name") or label.lower().replace(" ", "_")
    inverse = body.get("inverseLabel")
    if inverse is not None and not isinstance(inverse, str):
        raise validation("inverseLabel must be a string")
    if body.get("name") is not None and not isinstance(body.get("name"), str):
        raise validation("name must be a string")
    with db.connection() as conn:
        mx = conn.execute("SELECT COALESCE(MAX(type_id), 1000) AS m FROM association_labels").fetchone()["m"]
        tid = max(int(mx) + 1, 1001)
        inv_id = None
        if inverse:
            inv_id = tid + 1
            conn.execute("INSERT INTO association_labels (type_id, from_type, to_type, label, name, category, inverse_type_id) VALUES (%s, %s, %s, %s, %s, 'USER_DEFINED', %s)", (inv_id, tt, ft, inverse, inverse.lower().replace(" ", "_"), tid))
        conn.execute("INSERT INTO association_labels (type_id, from_type, to_type, label, name, category, inverse_type_id) VALUES (%s, %s, %s, %s, %s, 'USER_DEFINED', %s)", (tid, ft, tt, label, name, inv_id))
        conn.commit()
    results = [{"category": "USER_DEFINED", "typeId": tid, "label": label}]
    if inv_id:
        results.append({"category": "USER_DEFINED", "typeId": inv_id, "label": inverse})
    return {"results": results}


@router.put("/crm/v4/associations/{from_type}/{to_type}/labels")
async def update_label(from_type: str, to_type: str, request: Request):
    body = await json_body(request)
    tid = parse_record_id(body.get("associationTypeId"))
    if tid is None:
        raise validation("associationTypeId required")
    with db.connection() as conn:
        conn.execute("UPDATE association_labels SET label = %s WHERE type_id = %s", (body.get("label"), int(tid)))
        conn.commit()
    return Response(status_code=204)


@router.delete("/crm/v4/associations/{from_type}/{to_type}/labels/{type_id}", status_code=204)
def delete_label(from_type: str, to_type: str, type_id: int):
    with db.connection() as conn:
        conn.execute("DELETE FROM association_labels WHERE type_id = %s AND category = 'USER_DEFINED'", (type_id,))
        conn.execute("DELETE FROM associations WHERE type_id = %s", (type_id,))
        conn.commit()
    return Response(status_code=204)


@router.get("/crm/v4/associations/{from_type}/{to_type}/types")
def get_types(from_type: str, to_type: str):
    return get_labels(from_type, to_type)


@router.get("/crm/v3/associations/{from_type}/{to_type}/types")
def get_types_v3(from_type: str, to_type: str):
    ft = object_type_or_404(from_type)
    tt = object_type_or_404(to_type)
    with db.connection() as conn:
        rows = conn.execute("SELECT * FROM association_labels WHERE from_type = %s AND to_type = %s ORDER BY type_id", (ft, tt)).fetchall()
    return {"results": [{"id": str(r["type_id"]), "name": r["name"] or r["label"]} for r in rows]}

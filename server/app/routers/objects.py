from __future__ import annotations

from fastapi import APIRouter, Request, Response

from .. import db
from ..errors import ApiError, not_found, validation
from ..store import Store, record_out
from ..util import iso, utcnow
from .common import batch_inputs, csv_list, int_limit, json_body, object_type_or_404

router = APIRouter()


def _bool(v: str | None) -> bool:
    return str(v).lower() in ("true", "1") if v is not None else False


@router.get("/{object_type}")
def list_objects(object_type: str, request: Request, limit: str | None = None, after: str | None = None, properties: str | None = None, associations: str | None = None, archived: str | None = None):
    ot = object_type_or_404(object_type)
    lim = int_limit(limit, 10, 100)
    with db.connection() as conn:
        s = Store(conn)
        results, next_after = s.list(ot, lim, after, csv_list(properties), csv_list(associations), _bool(archived))
        conn.commit()
    out = {"results": results}
    if next_after:
        q = dict(request.query_params)
        q["after"] = next_after
        link = str(request.url.replace_query_params(**q))
        out["paging"] = {"next": {"after": next_after, "link": link}}
    return out


@router.post("/{object_type}/search")
async def search_objects(object_type: str, request: Request):
    ot = object_type_or_404(object_type)
    body = await json_body(request)
    with db.connection() as conn:
        s = Store(conn)
        out = s.search(ot, body)
        conn.commit()
    return out


@router.post("/{object_type}/merge")
async def merge_objects(object_type: str, request: Request):
    ot = object_type_or_404(object_type)
    body = await json_body(request)
    try:
        primary = int(body.get("primaryObjectId"))
        secondary = int(body.get("objectIdToMerge"))
    except (TypeError, ValueError):
        raise validation("primaryObjectId and objectIdToMerge are required")
    if primary == secondary:
        raise validation("cannot merge a record with itself")
    with db.connection() as conn:
        s = Store(conn)
        out = s.merge(ot, primary, secondary)
        conn.commit()
    return out


@router.post("/{object_type}/gdpr-delete", status_code=204)
async def gdpr_delete(object_type: str, request: Request):
    ot = object_type_or_404(object_type)
    body = await json_body(request)
    with db.connection() as conn:
        s = Store(conn)
        id_ = s.resolve_id(ot, body.get("objectId"), body.get("idProperty"))
        s.delete_permanently(ot, id_)
        conn.commit()
    return Response(status_code=204)


# ------------------------------------------------------------------ batch
@router.post("/{object_type}/batch/read")
async def batch_read(object_type: str, request: Request):
    ot = object_type_or_404(object_type)
    body = await json_body(request)
    inputs = batch_inputs(body, allow_scalars=True)
    props = body.get("properties")
    id_prop = body.get("idProperty")
    started = iso(utcnow())
    results, errors = [], []
    with db.connection() as conn:
        s = Store(conn)
        for inp in inputs:
            iv = inp.get("id") if isinstance(inp, dict) else inp
            try:
                results.append(s.get(ot, iv, props, None, id_prop))
            except ApiError as e:
                errors.append({"status": "error", "category": e.category, "message": e.message, "context": {"ids": [str(iv)]}})
        conn.commit()
    return _batch_response(results, errors, started)


def _batch_response(results, errors, started, status_code_ok=200):
    body = {"status": "COMPLETE", "results": results, "startedAt": started, "completedAt": iso(utcnow())}
    if errors:
        body["numErrors"] = len(errors)
        body["errors"] = errors
        return Response(content=_dumps(body), status_code=207, media_type="application/json")
    return Response(content=_dumps(body), status_code=status_code_ok, media_type="application/json")


def _dumps(obj) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False)


@router.post("/{object_type}/batch/create")
async def batch_create(object_type: str, request: Request):
    ot = object_type_or_404(object_type)
    body = await json_body(request)
    inputs = batch_inputs(body)
    started = iso(utcnow())
    results, errors = [], []
    with db.connection() as conn:
        s = Store(conn)
        for inp in inputs:
            try:
                with conn.transaction():
                    results.append(s.create(ot, inp.get("properties") or {}, inp.get("associations")))
            except ApiError as e:
                errors.append({"status": "error", "category": e.category, "message": e.message, "context": {}})
        conn.commit()
    return _batch_response(results, errors, started, 201)


@router.post("/{object_type}/batch/update")
async def batch_update(object_type: str, request: Request):
    ot = object_type_or_404(object_type)
    body = await json_body(request)
    inputs = batch_inputs(body)
    started = iso(utcnow())
    results, errors = [], []
    with db.connection() as conn:
        s = Store(conn)
        for inp in inputs:
            try:
                with conn.transaction():
                    results.append(s.update(ot, inp.get("id"), inp.get("properties") or {}, inp.get("idProperty")))
            except ApiError as e:
                errors.append({"status": "error", "category": e.category, "message": e.message, "context": {"ids": [str(inp.get("id"))]}})
        conn.commit()
    return _batch_response(results, errors, started)


@router.post("/{object_type}/batch/upsert")
async def batch_upsert(object_type: str, request: Request):
    ot = object_type_or_404(object_type)
    body = await json_body(request)
    inputs = batch_inputs(body)
    started = iso(utcnow())
    results, errors = [], []
    with db.connection() as conn:
        s = Store(conn)
        for inp in inputs:
            idp = inp.get("idProperty") or ("email" if ot == "contacts" else None)
            if not idp:
                errors.append({"status": "error", "category": "VALIDATION_ERROR", "message": "idProperty is required", "context": {}})
                continue
            try:
                rec, new = s.upsert(ot, idp, inp.get("id"), inp.get("properties") or {})
                rec["new"] = new
                results.append(rec)
            except ApiError as e:
                errors.append({"status": "error", "category": e.category, "message": e.message, "context": {"ids": [str(inp.get("id"))]}})
        conn.commit()
    return _batch_response(results, errors, started)


@router.post("/{object_type}/batch/archive", status_code=204)
async def batch_archive(object_type: str, request: Request):
    ot = object_type_or_404(object_type)
    body = await json_body(request)
    with db.connection() as conn:
        s = Store(conn)
        for inp in batch_inputs(body, allow_scalars=True):
            s.archive(ot, inp.get("id") if isinstance(inp, dict) else inp)
        conn.commit()
    return Response(status_code=204)


# ------------------------------------------------------------------ single record
@router.post("/{object_type}", status_code=201)
async def create_object(object_type: str, request: Request):
    ot = object_type_or_404(object_type)
    body = await json_body(request)
    if not isinstance(body, dict):
        raise validation("request body must be an object")
    with db.connection() as conn:
        s = Store(conn)
        out = s.create(ot, body.get("properties") or {}, body.get("associations"))
        conn.commit()
    return out


@router.get("/{object_type}/{object_id}")
def get_object(object_type: str, object_id: str, properties: str | None = None, associations: str | None = None, idProperty: str | None = None, archived: str | None = None):
    ot = object_type_or_404(object_type)
    with db.connection() as conn:
        s = Store(conn)
        out = s.get(ot, object_id, csv_list(properties), csv_list(associations), idProperty, include_archived=_bool(archived))
        conn.commit()
    return out


@router.patch("/{object_type}/{object_id}")
async def update_object(object_type: str, object_id: str, request: Request, idProperty: str | None = None):
    ot = object_type_or_404(object_type)
    body = await json_body(request)
    with db.connection() as conn:
        s = Store(conn)
        out = s.update(ot, object_id, body.get("properties") or {}, idProperty)
        conn.commit()
    return out


@router.delete("/{object_type}/{object_id}", status_code=204)
def delete_object(object_type: str, object_id: str, idProperty: str | None = None):
    ot = object_type_or_404(object_type)
    with db.connection() as conn:
        s = Store(conn)
        s.archive(ot, object_id, idProperty)
        conn.commit()
    return Response(status_code=204)


# v3 associations on objects (legacy style)
@router.get("/{object_type}/{object_id}/associations/{to_type}")
def get_object_associations_v3(object_type: str, object_id: str, to_type: str, limit: str | None = None, after: str | None = None):
    ot = object_type_or_404(object_type)
    tt = object_type_or_404(to_type)
    lim = int_limit(limit, 500, 500)
    with db.connection() as conn:
        s = Store(conn)
        id_ = s.resolve_id(ot, object_id, None)
        if s._row(ot, id_) is None:
            raise not_found(f"No {ot} with ID {object_id} exists")
        results, next_after = s.associations_v4(ot, id_, tt, lim, after)
        conn.commit()
    out = {"results": [{"id": str(r["toObjectId"]), "type": next((x.get("label") or "") for x in r["associationTypes"]) or f"{ot}_to_{tt}"} for r in results]}
    if next_after:
        out["paging"] = {"next": {"after": next_after}}
    return out


@router.put("/{object_type}/{object_id}/associations/{to_type}/{to_id}/{assoc_type}")
def put_object_association_v3(object_type: str, object_id: str, to_type: str, to_id: str, assoc_type: str):
    ot = object_type_or_404(object_type)
    tt = object_type_or_404(to_type)
    with db.connection() as conn:
        s = Store(conn)
        fid = s.resolve_id(ot, object_id, None)
        tid = s.resolve_id(tt, to_id, None)
        type_ids = None
        if assoc_type.isdigit() and len(assoc_type) < 10:
            type_ids = [int(assoc_type)]
        else:
            lab = conn.execute("SELECT type_id FROM association_labels WHERE name = %s", (assoc_type,)).fetchone()
            if lab:
                type_ids = [lab["type_id"]]
        s.associate(ot, fid, tt, tid, type_ids)
        out = s.get(ot, fid, None, [tt])
        conn.commit()
    return out


@router.delete("/{object_type}/{object_id}/associations/{to_type}/{to_id}/{assoc_type}", status_code=204)
def delete_object_association_v3(object_type: str, object_id: str, to_type: str, to_id: str, assoc_type: str):
    ot = object_type_or_404(object_type)
    tt = object_type_or_404(to_type)
    with db.connection() as conn:
        s = Store(conn)
        s.dissociate(ot, s.resolve_id(ot, object_id, None), tt, s.resolve_id(tt, to_id, None), None)
        conn.commit()
    return Response(status_code=204)

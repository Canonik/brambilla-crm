"""HubSpot search API semantics -> SQL."""
from __future__ import annotations

import re

from . import defaults
from .errors import validation
from .store import record_out
from .util import iso, parse_datetime

MAX_LIMIT = 200


def _typed_expr(name: str, ptype: str) -> str:
    col = f"(properties->>{_lit(name)})"
    if ptype == "number":
        return f"NULLIF({col}, '')::numeric"
    if ptype == "datetime":
        return f"NULLIF({col}, '')::timestamptz"
    if ptype == "date":
        return f"NULLIF({col}, '')::date"
    return col


def _lit(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def _coerce(value, ptype: str, name: str):
    if ptype == "number":
        from .util import normalize_number
        v = normalize_number(value)
        if v is None:
            raise validation(f"Invalid number value for property {name}: {value!r}")
        return v
    if ptype in ("datetime", "date"):
        d = parse_datetime(value)
        if d is None:
            raise validation(f"Invalid date value for property {name}: {value!r}")
        return iso(d) if ptype == "datetime" else d.strftime("%Y-%m-%d")
    if ptype == "bool":
        if isinstance(value, bool):
            return "true" if value else "false"
        return "true" if str(value).strip().lower() in ("true", "1", "yes") else "false"
    return str(value)


def _filter_sql(store, object_type: str, f: dict, params: list) -> str:
    name = f.get("propertyName")
    op = (f.get("operator") or "").upper()
    if not name or not op:
        raise validation("filters require propertyName and operator")
    defs = store.prop_defs(object_type)
    d = defs.get(name)
    ptype = d["type"] if d else "string"
    if name == "hs_object_id" or name == "id":
        ptype = "number"
    expr = _typed_expr(name, ptype)
    raw = f"(properties->>{_lit(name)})"
    is_text = ptype not in ("number", "datetime", "date", "bool")
    if op in ("EQ", "NEQ"):
        if "value" not in f:
            raise validation(f"operator {op} requires value")
        v = _coerce(f["value"], ptype, name)
        params.append(v)
        if is_text:
            cond = f"lower({raw}) = lower(%s)"
        else:
            cond = f"{expr} = %s::{'numeric' if ptype == 'number' else 'timestamptz' if ptype == 'datetime' else 'date' if ptype == 'date' else 'text'}"
        if op == "EQ":
            return cond
        return f"NOT ({cond} AND {raw} IS NOT NULL)"
    if op in ("LT", "LTE", "GT", "GTE"):
        v = _coerce(f["value"], ptype, name)
        params.append(v)
        sym = {"LT": "<", "LTE": "<=", "GT": ">", "GTE": ">="}[op]
        cast = "numeric" if ptype == "number" else "timestamptz" if ptype == "datetime" else "date" if ptype == "date" else "text"
        return f"{expr} {sym} %s::{cast}"
    if op == "BETWEEN":
        lo = _coerce(f.get("value"), ptype, name)
        hi = _coerce(f.get("highValue"), ptype, name)
        params.extend([lo, hi])
        cast = "numeric" if ptype == "number" else "timestamptz" if ptype == "datetime" else "date" if ptype == "date" else "text"
        return f"{expr} >= %s::{cast} AND {expr} <= %s::{cast}"
    if op in ("IN", "NOT_IN"):
        values = f.get("values")
        if not isinstance(values, list) or not values:
            raise validation(f"operator {op} requires values")
        vals = [_coerce(v, ptype, name) for v in values]
        params.append(vals)
        if is_text:
            cond = f"lower({raw}) = ANY(SELECT lower(x) FROM unnest(%s::text[]) AS x)"
        else:
            cast = "numeric" if ptype == "number" else "timestamptz" if ptype == "datetime" else "date" if ptype == "date" else "text"
            cond = f"{expr} = ANY(%s::{cast}[])"
        if op == "IN":
            return cond
        return f"NOT ({cond} AND {raw} IS NOT NULL)"
    if op == "HAS_PROPERTY":
        return f"{raw} IS NOT NULL AND {raw} <> ''"
    if op == "NOT_HAS_PROPERTY":
        return f"({raw} IS NULL OR {raw} = '')"
    if op in ("CONTAINS_TOKEN", "NOT_CONTAINS_TOKEN"):
        v = str(f.get("value", ""))
        pat = re.escape(v).replace(r"\*", r"[^\s]*")
        regex = r"(^|[^[:alnum:]_@.])" + pat + r"($|[^[:alnum:]_@.])"
        if "*" in v:
            regex = r"(^|\s)" + pat + r"($|\s)"
        params.append(regex)
        cond = f"{raw} ~* %s"
        if op == "CONTAINS_TOKEN":
            return cond
        return f"NOT ({cond} AND {raw} IS NOT NULL)"
    raise validation(f"Unknown operator {op}")


def build_where(store, object_type: str, body: dict, params: list) -> str:
    clauses = ["object_type = %s", "NOT archived"]
    params.append(object_type)
    groups = body.get("filterGroups") or []
    if body.get("filters") and not groups:
        groups = [{"filters": body["filters"]}]
    if not isinstance(groups, list):
        raise validation("filterGroups must be a list")
    if len(groups) > 6:
        raise validation("filterGroups cannot have more than 6 groups")
    group_sql = []
    for g in groups:
        fs = g.get("filters") or []
        if len(fs) > 6:
            raise validation("a filter group cannot have more than 6 filters")
        parts = [_filter_sql(store, object_type, f, params) for f in fs]
        if parts:
            group_sql.append("(" + " AND ".join(parts) + ")")
    if group_sql:
        clauses.append("(" + " OR ".join(group_sql) + ")")
    q = body.get("query")
    if q is not None and str(q).strip() != "":
        q = str(q).strip()
        fields = defaults.OBJECT_TYPES[object_type]["search"]
        parts = []
        for fld in fields:
            params.append(f"%{q}%")
            parts.append(f"(properties->>{_lit(fld)}) ILIKE %s")
        if q.isdigit():
            params.append(int(q))
            parts.append("id = %s")
        clauses.append("(" + " OR ".join(parts) + ")")
    return " AND ".join(clauses)


def build_order(store, object_type: str, sorts) -> str:
    if not sorts:
        return "id ASC"
    parts = []
    defs = store.prop_defs(object_type)
    for s in sorts:
        if isinstance(s, str):
            name, direction = s.lstrip("-"), ("DESCENDING" if s.startswith("-") else "ASCENDING")
        elif isinstance(s, dict):
            name = s.get("propertyName")
            direction = (s.get("direction") or "ASCENDING").upper()
        else:
            continue
        if not name:
            continue
        d = defs.get(name)
        ptype = d["type"] if d else "string"
        if name in ("hs_object_id", "id"):
            expr = "id"
        else:
            expr = _typed_expr(name, ptype)
            if ptype not in ("number", "datetime", "date"):
                expr = f"lower({expr})"
        parts.append(f"{expr} {'DESC' if direction.startswith('DESC') else 'ASC'} NULLS LAST")
    parts.append("id ASC")
    return ", ".join(parts)


def build_search(store, object_type: str, body: dict) -> dict:
    if not isinstance(body, dict):
        raise validation("request body must be an object")
    limit = body.get("limit", 10)
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        raise validation("limit must be an integer")
    if limit < 1 or limit > MAX_LIMIT:
        raise validation(f"limit must be between 1 and {MAX_LIMIT}")
    after = body.get("after", 0) or 0
    try:
        offset = int(after)
    except (TypeError, ValueError):
        raise validation("after must be an integer offset")
    params: list = []
    where = build_where(store, object_type, body, params)
    order = build_order(store, object_type, body.get("sorts"))
    total = store.conn.execute(f"SELECT count(*) AS n FROM objects WHERE {where}", params).fetchone()["n"]
    rows = store.conn.execute(f"SELECT * FROM objects WHERE {where} ORDER BY {order} OFFSET %s LIMIT %s", params + [offset, limit]).fetchall()
    props = body.get("properties")
    if props is not None and not isinstance(props, list):
        raise validation("properties must be a list")
    results = [record_out(r, props, object_type) for r in rows]
    assoc = body.get("associations")
    if assoc:
        for r, row in zip(results, rows):
            r["associations"] = store.associations_block(row["id"], assoc)
    out = {"total": int(total), "results": results}
    if offset + limit < total:
        out["paging"] = {"next": {"after": str(offset + limit)}}
    return out

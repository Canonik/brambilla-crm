from __future__ import annotations

import datetime as dt

from fastapi import Request

from .. import db
from ..defaults import resolve_type
from ..errors import not_found, validation
from ..store import Store


def object_type_or_404(name: str) -> str:
    t = resolve_type(name)
    if t is None:
        raise not_found(f"Unable to infer object type from: {name}")
    return t


def csv_list(value: str | None) -> list[str] | None:
    if value is None:
        return None
    items = [x.strip() for x in value.split(",") if x.strip()]
    return items or None


def int_limit(value, default: int, maximum: int) -> int:
    if value is None:
        return default
    try:
        v = int(value)
    except (TypeError, ValueError):
        raise validation("limit must be an integer")
    if v < 1:
        raise validation("limit must be positive")
    return min(v, maximum)


_ANY = object()


async def json_body(request: Request, expect=dict):
    """Parsed JSON body. By default it must be a JSON object; pass expect=list or expect=_ANY."""
    raw = await request.body()
    if not raw:
        return {} if expect is dict else ([] if expect is list else {})
    import json
    try:
        data = json.loads(raw)
    except Exception:
        raise validation("Invalid input JSON")
    if expect is dict and not isinstance(data, dict):
        raise validation("Invalid input JSON: the request body must be a JSON object")
    if expect is list and not isinstance(data, list):
        raise validation("Invalid input JSON: the request body must be a JSON array")
    return data


def batch_inputs(body: dict, *, allow_scalars: bool = False) -> list:
    """The `inputs` array of a batch request; every item must be an object (or an id when allowed)."""
    inputs = body.get("inputs")
    if inputs is None:
        return []
    if not isinstance(inputs, list):
        raise validation("inputs must be an array")
    for i, item in enumerate(inputs):
        if isinstance(item, dict):
            continue
        if allow_scalars and isinstance(item, (str, int)) and not isinstance(item, bool):
            continue
        raise validation(f"inputs[{i}] must be an object")
    return inputs


def int_field(value, name: str, default: int) -> int:
    """An integer request field such as displayOrder; bad values are a 400, not a 500."""
    if value is None:
        return default
    if isinstance(value, bool):
        raise validation(f"{name} must be an integer")
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        raise validation(f"{name} must be an integer")


def ref_id(ref, what: str = "id") -> int:
    """Record id inside a request body, given as `{"id": ...}` or as the bare id."""
    from ..util import parse_record_id
    value = ref.get("id") if isinstance(ref, dict) else ref
    rid = parse_record_id(value)
    if rid is None:
        raise validation(f"Invalid {what}: {value!r}")
    return rid


def store_now(request: Request) -> dt.datetime | None:
    return getattr(request.state, "now", None)

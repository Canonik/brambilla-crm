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


async def json_body(request: Request) -> dict:
    raw = await request.body()
    if not raw:
        return {}
    import json
    try:
        data = json.loads(raw)
    except Exception:
        raise validation("Invalid input JSON")
    return data


def store_now(request: Request) -> dt.datetime | None:
    return getattr(request.state, "now", None)

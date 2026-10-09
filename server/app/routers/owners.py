from __future__ import annotations

from fastapi import APIRouter

from .. import db
from ..errors import not_found

router = APIRouter()


def _owner(r) -> dict:
    return {
        "id": r["id"], "email": r["email"], "firstName": r["firstname"], "lastName": r["lastname"],
        "userId": int(r["id"][1:]) if r["id"][1:].isdigit() else None, "userIdIncludingInactive": int(r["id"][1:]) if r["id"][1:].isdigit() else None,
        "createdAt": "2026-01-01T00:00:00Z", "updatedAt": "2026-01-01T00:00:00Z", "archived": not r["active"], "type": "PERSON",
        "role": r["role"], "managerId": r["manager_id"], "active": r["active"],
    }


@router.get("/crm/v3/owners")
@router.get("/crm/v3/owners/")
def list_owners(email: str | None = None, archived: str | None = None, limit: int = 100, after: str | None = None):
    with db.connection() as conn:
        sql = "SELECT * FROM crm_users WHERE 1=1"
        params: list = []
        if email:
            sql += " AND lower(email) = lower(%s)"
            params.append(email)
        if str(archived).lower() == "true":
            sql += " AND NOT active"
        elif archived is None or str(archived).lower() == "false":
            sql += " AND active"
        sql += " ORDER BY id"
        rows = conn.execute(sql, params).fetchall()
    return {"results": [_owner(r) for r in rows]}


@router.get("/crm/v3/owners/{owner_id}")
def get_owner(owner_id: str):
    with db.connection() as conn:
        row = conn.execute("SELECT * FROM crm_users WHERE id = %s OR lower(email) = lower(%s)", (owner_id, owner_id)).fetchone()
    if not row:
        raise not_found(f"Owner {owner_id} not found")
    return _owner(row)

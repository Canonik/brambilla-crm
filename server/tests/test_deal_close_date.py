"""A deal that enters a closed stage gets closedate = the request clock unless the same write
sets one. HubSpot updates the close date automatically when a deal is closed; the assistant's
"segna come vinta" requests depend on it (Store.now is context.now there)."""
import datetime as dt

from app import db
from app.store import Store

from .conftest import H

NOW = dt.datetime(2026, 12, 2, 9, 30, tzinfo=dt.timezone.utc)


def _store(conn):
    return Store(conn, NOW)


def _deal(api, **props):
    r = api.post("/crm/v3/objects/deals", headers=H, json={"properties": dict({"dealname": "D", "dealstage": "qualifiedtobuy"}, **props)})
    assert r.status_code == 201, r.text
    return r.json()


def _move(stage, **extra):
    with db.connection() as conn:
        s = _store(conn)
        return s, conn


def test_update_into_won_sets_closedate_to_the_request_clock(api):
    d = _deal(api, closedate="2027-01-15T00:00:00Z")  # a planned close date from before
    with db.connection() as conn:
        out = _store(conn).update("deals", d["id"], {"dealstage": "closedwon"})
        conn.commit()
    assert out["properties"]["closedate"] == "2026-12-02T09:30:00.000Z"


def test_closedate_given_in_the_same_write_is_kept(api):
    d = _deal(api)
    with db.connection() as conn:
        out = _store(conn).update("deals", d["id"], {"dealstage": "closedlost", "closedate": "2026-11-20T00:00:00Z"})
        conn.commit()
    assert out["properties"]["closedate"] == "2026-11-20T00:00:00.000Z"


def test_create_directly_in_won_and_lost(api):
    with db.connection() as conn:
        s = _store(conn)
        won = s.create("deals", {"dealname": "W", "dealstage": "closedwon"})
        lost = s.create("deals", {"dealname": "L", "dealstage": "closedlost", "closedate": "2026-10-01T00:00:00Z"})
        conn.commit()
    assert won["properties"]["closedate"] == "2026-12-02T09:30:00.000Z"
    assert lost["properties"]["closedate"] == "2026-10-01T00:00:00.000Z"


def test_unchanged_stage_and_open_stages_leave_closedate_alone(api):
    d = _deal(api, closedate="2027-01-15T00:00:00Z")
    with db.connection() as conn:
        s = _store(conn)
        a = s.update("deals", d["id"], {"dealname": "renamed"})
        b = s.update("deals", d["id"], {"dealstage": "contractsent"})
        conn.commit()
    assert a["properties"]["closedate"] == b["properties"]["closedate"] == "2027-01-15T00:00:00.000Z"
    with db.connection() as conn:
        s = _store(conn)
        s.update("deals", d["id"], {"dealstage": "closedwon"})
        again = s.update("deals", d["id"], {"dealname": "again"})  # already closed, stage unchanged
        conn.commit()
    assert again["properties"]["closedate"] == "2026-12-02T09:30:00.000Z"


def test_renewals_closed_stage_counts(api):
    pls = api.get("/crm/v3/pipelines/deals", headers=H).json()["results"]
    assert len(pls) == 1  # fresh account: create the Rinnovi pipeline like the migration does
    r = api.post("/crm/v3/pipelines/deals", headers=H, json={"label": "Rinnovi", "displayOrder": 1, "stages": [
        {"label": "Da rinnovare", "displayOrder": 0, "metadata": {"probability": "0.2", "isClosed": "false"}},
        {"label": "Rinnovato", "displayOrder": 1, "metadata": {"probability": "1.0", "isClosed": "true"}}]})
    pl = r.json()
    d = api.post("/crm/v3/objects/deals", headers=H, json={"properties": {"dealname": "Rin", "pipeline": pl["id"], "dealstage": pl["stages"][0]["id"]}}).json()
    with db.connection() as conn:
        out = _store(conn).update("deals", d["id"], {"dealstage": pl["stages"][1]["id"]})
        conn.commit()
    assert out["properties"]["closedate"] == "2026-12-02T09:30:00.000Z"
    assert out["properties"]["hs_is_closed_won"] == "true"

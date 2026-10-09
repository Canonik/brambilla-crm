"""dormant_list(mine=True) returns only the writer's customers, exact total, with the last won deal."""
import datetime as dt
from app import db
from app.assistant.tools import ToolContext, run_tool
from app.store import Store


def _setup():
    with db.connection() as conn:
        s = Store(conn)
        lid = conn.execute("SELECT list_id FROM lists WHERE lower(definition->>'name') = 'clienti dormienti'").fetchone()
        if lid is None:
            conn.execute("INSERT INTO lists (list_id, definition) VALUES (nextval('lists_id_seq'), %s::jsonb)", ('{"name": "Clienti dormienti", "objectTypeId": "0-2", "processingType": "MANUAL"}',))
            lid = conn.execute("SELECT list_id FROM lists WHERE lower(definition->>'name') = 'clienti dormienti'").fetchone()
        lid = lid["list_id"]
        mine = s.create("companies", {"name": "Dormiente Mio Srl"})
        other = s.create("companies", {"name": "Dormiente Altrui Srl"})
        for co, who, d in ((mine["id"], "anna.sala@brambillaforniture.it", "2019-05-01"), (other["id"], "luca.sala@brambillaforniture.it", "2018-01-01")):
            s.create("deals", {"dealname": f"Vinta {co}", "pipeline": "default", "dealstage": "closedwon", "amount": "1500", "closedate": d, "commerciale": who},
                     [{"to": {"id": co}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 5}]}], run_rules=False)
            conn.execute("INSERT INTO list_memberships (list_id, record_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (lid, int(co)))
        conn.commit()
        return mine["id"], other["id"]


def test_dormant_mine_filters_and_reports_last_win():
    mine, other = _setup()
    ctx = ToolContext(dt.datetime(2026, 12, 2, 10, tzinfo=dt.timezone.utc), "anna.sala@brambillaforniture.it")
    out = run_tool(ctx, "dormant_list", {"mine": True, "limit": 100})
    ids = {r["id"] for r in out["results"]}
    assert mine in ids and other not in ids
    assert out["total"] == len(ids)
    row = next(r for r in out["results"] if r["id"] == mine)
    assert row["ultima_trattativa_vinta"]["closedate"] == "2019-05-01"
    assert run_tool(ctx, "dormant_list", {"limit": 100})["total"] >= 2

"""Regression coverage for exact R13 rankings, filtered customer totals and aggregates."""
import datetime as dt

from app import db, rules
from app.assistant.tools import ToolContext, run_tool
from app.store import Store


USER = "m.costa@brambillaforniture.it"


def _ctx():
    return ToolContext(dt.datetime.fromisoformat("2026-12-02T10:00:00+01:00"), USER)


def _deal_to_company(store, company_id, name, amount, owner=USER, closedate="2026-11-01", stage="qualifiedtobuy"):
    return store.create(
        "deals",
        {"dealname": name, "amount": str(amount), "deal_currency_code": "EUR", "pipeline": "default", "dealstage": stage,
         "closedate": closedate, "commerciale": owner},
        [{"to": {"id": company_id}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 5}]}],
        run_rules=False,
    )


def test_company_rankings_my_class_filter_and_read_only_stats(api):
    with db.connection() as conn:
        store = Store(conn)
        low = store.create("companies", {"name": "Classe A Piccola", "classe_cliente": "A", "fatturato_2025": "100.00"})
        high = store.create("companies", {"name": "Classe A Grande", "classe_cliente": "A", "fatturato_2025": "900.00"})
        other = store.create("companies", {"name": "Classe B", "classe_cliente": "B", "fatturato_2025": "50.00"})
        _deal_to_company(store, low["id"], "Deal piccola", 10)
        _deal_to_company(store, high["id"], "Deal grande", 20)
        _deal_to_company(store, other["id"], "Deal altro", 30, owner="other@brambillaforniture.it")
        conn.commit()

    ranked = run_tool(_ctx(), "search_companies", {"classe_cliente": "A", "sort_by": "fatturato_2025", "sort_direction": "DESCENDING", "limit": 2})
    assert [r["id"] for r in ranked["results"]] == [high["id"], low["id"]]

    mine = run_tool(_ctx(), "my_customers", {"classe_cliente": "A", "sort_by": "fatturato_2025", "sort_direction": "DESCENDING", "limit": 1})
    assert mine["total"] == 2
    assert [r["id"] for r in mine["results"]] == [high["id"]]

    with db.connection() as conn:
        before = (conn.execute("SELECT count(*) AS n FROM objects").fetchone()["n"], conn.execute("SELECT count(*) AS n FROM associations").fetchone()["n"])
    stats = run_tool(_ctx(), "company_stats", {"classe_cliente": "A", "mine": True})
    assert stats["count"] == 2
    assert stats["total_fatturato_2025_eur"] == "1000.00"
    with db.connection() as conn:
        after = (conn.execute("SELECT count(*) AS n FROM objects").fetchone()["n"], conn.execute("SELECT count(*) AS n FROM associations").fetchone()["n"])
    assert after == before


def test_deal_amount_ranking_is_numeric_before_limit(api):
    with db.connection() as conn:
        store = Store(conn)
        company = store.create("companies", {"name": "Ranking Deal Srl"})
        for name, amount in (("Nove", 9), ("Cento", 100), ("Venti", 20)):
            _deal_to_company(store, company["id"], name, amount)
        conn.commit()
    out = run_tool(_ctx(), "search_deals", {"commerciale": USER, "sort_by": "amount", "sort_direction": "DESCENDING", "limit": 2})
    assert out["total"] == 3
    assert [r["amount"] for r in out["results"]] == ["100", "20"]


def test_ticket_oldest_and_exact_priority_breakdown_are_opt_in(api):
    with db.connection() as conn:
        store = Store(conn)
        pipeline = rules.ensure_ticket_pipeline(store)
        open_stage = rules.stage_id(pipeline, "Aperto")
        for subject, priority, createdate in (("Vecchio", "HIGH", "2020-01-01"), ("Nuovo", "LOW", "2026-01-01"), ("Senza", None, "2025-01-01")):
            props = {"subject": subject, "hs_pipeline": pipeline["id"], "hs_pipeline_stage": open_stage, "createdate": createdate}
            if priority:
                props["hs_ticket_priority"] = priority
            ticket = store.create("tickets", props, run_rules=False)
            # Store owns createdate for normal writes; imported tickets retain their historical date.
            conn.execute("UPDATE objects SET properties = jsonb_set(properties, '{createdate}', to_jsonb(%s::text)) WHERE id = %s", (createdate, int(ticket["id"])))
        conn.commit()

    old_shape = run_tool(_ctx(), "search_tickets", {"open_only": True, "limit": 1})
    assert "by_priority" not in old_shape
    assert old_shape["results"][0]["subject"] == "Nuovo"

    out = run_tool(_ctx(), "search_tickets", {"open_only": True, "sort_by": "createdate", "sort_direction": "ASCENDING", "include_stats": True, "limit": 1})
    assert out["results"][0]["subject"] == "Vecchio"
    assert out["by_priority"] == {"LOW": 1, "MEDIUM": 0, "HIGH": 1, "URGENT": 0, "SENZA PRIORITÀ": 1}


def test_deal_stats_accept_exact_period_and_won_filter(api):
    with db.connection() as conn:
        store = Store(conn)
        company = store.create("companies", {"name": "Statistiche Periodo Srl"})
        _deal_to_company(store, company["id"], "Vinta dentro", 100, closedate="2026-10-15", stage="closedwon")
        _deal_to_company(store, company["id"], "Persa dentro", 70, closedate="2026-10-20", stage="closedlost")
        _deal_to_company(store, company["id"], "Vinta fuori", 900, closedate="2026-09-30", stage="closedwon")
        conn.commit()
    out = run_tool(_ctx(), "deal_stats", {"commerciale": USER, "closed_from": "2026-10-01", "closed_to": "2026-10-31", "won_only": True})
    assert out["count"] == 1
    assert out["total_eur"] == "100.00"

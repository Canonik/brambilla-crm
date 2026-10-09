"""Brambilla business rules that react to CRM writes: R10, R11, R12."""
from __future__ import annotations

import datetime as dt
import json

from psycopg.types.json import Jsonb

from . import defaults
from .util import email_domain, iso

ASSISTENZA_LABEL = "Assistenza"
ASSISTENZA_STAGES = [("Aperto", "OPEN"), ("In lavorazione", "OPEN"), ("In attesa del cliente", "OPEN"), ("Chiuso", "CLOSED")]
RINNOVI_LABEL = "Rinnovi"
RINNOVI_STAGES = [("Da rinnovare", 0.2, False), ("In trattativa", 0.6, False), ("Rinnovato", 1.0, True), ("Non rinnovato", 0.0, True)]


def _flag(store, object_id: int, rule: str) -> bool:
    """Returns True the first time a rule fires for an object."""
    row = store.conn.execute(
        "INSERT INTO automation_flags (object_id, rule) VALUES (%s, %s) ON CONFLICT DO NOTHING RETURNING object_id",
        (object_id, rule),
    ).fetchone()
    return row is not None


def ensure_ticket_pipeline(store) -> dict:
    pl = store.pipeline_by_label("tickets", ASSISTENZA_LABEL)
    if pl:
        return pl
    from .pipelines import create_pipeline
    stages = [{"label": lab, "displayOrder": i, "metadata": {"ticketState": state}} for i, (lab, state) in enumerate(ASSISTENZA_STAGES)]
    return create_pipeline(store, "tickets", {"label": ASSISTENZA_LABEL, "displayOrder": 1, "stages": stages})


def ensure_deal_pipeline(store) -> dict:
    pl = store.pipeline_by_label("deals", RINNOVI_LABEL)
    if pl:
        return pl
    from .pipelines import create_pipeline
    stages = [{"label": lab, "displayOrder": i, "metadata": {"probability": prob, "isClosed": closed}} for i, (lab, prob, closed) in enumerate(RINNOVI_STAGES)]
    return create_pipeline(store, "deals", {"label": RINNOVI_LABEL, "displayOrder": 1, "stages": stages})


def stage_id(pipeline: dict, label: str) -> str:
    for s in pipeline["stages"]:
        if s["label"].strip().lower() == label.lower():
            return s["id"]
    return pipeline["stages"][0]["id"]


def is_sales_won(store, props: dict) -> bool:
    return props.get("pipeline") == "default" and props.get("dealstage") == "closedwon"


def is_sales_lost(store, props: dict) -> bool:
    return props.get("pipeline") == "default" and props.get("dealstage") == "closedlost"


def r10_supply_kickoff(store, deal_id: int, props: dict) -> None:
    if not _flag(store, deal_id, "R10"):
        return
    pl = ensure_ticket_pipeline(store)
    companies = store.associated_ids(deal_id, "companies")
    ticket_props = {
        "subject": "Avvio fornitura - " + (props.get("dealname") or ""),
        "hs_pipeline": pl["id"],
        "hs_pipeline_stage": stage_id(pl, "Aperto"),
    }
    if props.get("commerciale"):
        ticket_props["assegnatario"] = props.get("commerciale")
    t = store.create("tickets", ticket_props, run_rules=False)
    tid = int(t["id"])
    store.associate("tickets", tid, "deals", deal_id, check=False)
    for cid in companies:
        store.associate("tickets", tid, "companies", cid, check=False)


def r11_callback_task(store, deal_id: int, props: dict) -> None:
    if not _flag(store, deal_id, "R11"):
        return
    due = store.now + dt.timedelta(days=180)
    task_props = {
        "hs_task_subject": "Richiamare: " + (props.get("dealname") or ""),
        "hs_timestamp": iso(due),
        "hs_task_status": "NOT_STARTED",
        "hs_task_type": "CALL",
        "hs_task_priority": "MEDIUM",
    }
    t = store.create("tasks", task_props, run_rules=False)
    store.associate("tasks", int(t["id"]), "deals", deal_id, check=False)


def r12_auto_company(store, contact_id: int, props: dict) -> None:
    email = props.get("email")
    dom = email_domain(email) if email else None
    if not dom:
        return
    has = store.conn.execute("SELECT 1 FROM associations WHERE from_id = %s AND to_type = 'companies' LIMIT 1", (contact_id,)).fetchone()
    if has:
        return
    row = store.conn.execute(
        "SELECT cd.company_id FROM company_domains cd JOIN objects o ON o.id = cd.company_id AND NOT o.archived WHERE cd.domain = %s ORDER BY (o.properties->>'domain' = cd.domain) DESC, cd.company_id LIMIT 1",
        (dom,),
    ).fetchone()
    if not row:
        return
    store.associate("contacts", contact_id, "companies", int(row["company_id"]), check=False)


def after_create(store, object_type: str, id_: int, props: dict) -> None:
    if object_type == "contacts":
        r12_auto_company(store, id_, props)
    elif object_type == "deals":
        if is_sales_won(store, props):
            r10_supply_kickoff(store, id_, props)
        elif is_sales_lost(store, props):
            r11_callback_task(store, id_, props)


def after_update(store, object_type: str, id_: int, old: dict, new: dict) -> None:
    if object_type == "contacts":
        if old.get("email") != new.get("email"):
            r12_auto_company(store, id_, new)
    elif object_type == "deals":
        entered = (old.get("pipeline"), old.get("dealstage")) != (new.get("pipeline"), new.get("dealstage"))
        if entered and is_sales_won(store, new):
            r10_supply_kickoff(store, id_, new)
        elif entered and is_sales_lost(store, new):
            r11_callback_task(store, id_, new)

"""Typed, validated tools the assistant can call. Every write goes through the Store (same rules as the API)."""
from __future__ import annotations

import datetime as dt
import json
import re
from decimal import ROUND_HALF_UP, Decimal

from .. import db, defaults
from ..errors import ApiError
from ..store import Store
from ..util import iso, parse_datetime

FX = {"EUR": Decimal("1"), "USD": Decimal("0.92"), "GBP": Decimal("1.17")}
MAX_LIST = 25


def _trunc(s, n=300):
    if s is None:
        return None
    s = str(s)
    return s if len(s) <= n else s[: n - 3] + "..."


class ToolContext:
    def __init__(self, now: dt.datetime, user_email: str | None):
        self.now = now
        self.user_email = (user_email or "").strip().lower() or None
        self.writes: list[str] = []
        self._stage_labels: dict[str, str] | None = None
        self._pipeline_labels: dict[str, str] | None = None

    # ---------------------------------------------------------- helpers
    def _labels(self, store: Store):
        if self._stage_labels is None:
            self._stage_labels, self._pipeline_labels = {}, {}
            for ot in ("deals", "tickets"):
                for p in store.pipelines(ot):
                    self._pipeline_labels[p["id"]] = p["label"]
                    for s in p["stages"]:
                        self._stage_labels[s["id"]] = s["label"]
        return self._stage_labels, self._pipeline_labels

    def _company_brief(self, store: Store, row: dict) -> dict:
        p = row["properties"]
        return {
            "id": str(row["id"]), "name": p.get("name"), "domain": p.get("domain"), "additional_domains": p.get("hs_additional_domains"),
            "city": p.get("city"), "state": p.get("state"), "partita_iva": p.get("partita_iva"),
            "fatturato_2025": p.get("fatturato_2025"), "classe_cliente": p.get("classe_cliente"), "id_legacy": p.get("id_legacy"),
        }

    def _contact_brief(self, store: Store, row: dict) -> dict:
        p = row["properties"]
        out = {"id": str(row["id"]), "firstname": p.get("firstname"), "lastname": p.get("lastname"), "email": p.get("email"), "phone": p.get("phone"), "lifecyclestage": p.get("lifecyclestage"), "id_legacy": p.get("id_legacy")}
        cid = p.get("associatedcompanyid")
        if cid:
            out["company_id"] = cid
            c = store.conn.execute("SELECT properties->>'name' AS n FROM objects WHERE id = %s", (int(cid),)).fetchone()
            out["company_name"] = c["n"] if c else None
        return out

    def _deal_brief(self, store: Store, row: dict) -> dict:
        p = row["properties"]
        sl, pl = self._labels(store)
        out = {
            "id": str(row["id"]), "dealname": p.get("dealname"), "amount": p.get("amount"), "currency": p.get("deal_currency_code"),
            "pipeline": pl.get(p.get("pipeline"), p.get("pipeline")), "pipeline_id": p.get("pipeline"),
            "stage": sl.get(p.get("dealstage"), p.get("dealstage")), "dealstage_id": p.get("dealstage"),
            "closedate": (p.get("closedate") or "")[:10] or None, "commerciale": p.get("commerciale"), "id_legacy": p.get("id_legacy"),
            "is_closed_won": p.get("hs_is_closed_won") == "true", "is_closed_lost": p.get("hs_is_closed_lost") == "true",
        }
        comps = store.conn.execute("SELECT o.id, o.properties->>'name' AS n FROM associations a JOIN objects o ON o.id = a.to_id AND NOT o.archived WHERE a.from_id = %s AND a.to_type = 'companies' ORDER BY a.type_id LIMIT 3", (row["id"],)).fetchall()
        if comps:
            out["company_id"] = str(comps[0]["id"])
            out["company_name"] = comps[0]["n"]
        return out

    def _ticket_brief(self, store: Store, row: dict) -> dict:
        p = row["properties"]
        sl, pl = self._labels(store)
        out = {
            "id": str(row["id"]), "subject": p.get("subject"), "content": _trunc(p.get("content"), 200),
            "pipeline": pl.get(p.get("hs_pipeline"), p.get("hs_pipeline")), "stage": sl.get(p.get("hs_pipeline_stage"), p.get("hs_pipeline_stage")), "stage_id": p.get("hs_pipeline_stage"),
            "priority": p.get("hs_ticket_priority"), "createdate": (p.get("createdate") or "")[:10], "closed_date": (p.get("closed_date") or "")[:10] or None,
            "assegnatario": p.get("assegnatario"), "id_legacy": p.get("id_legacy"),
        }
        comps = store.conn.execute("SELECT o.id, o.properties->>'name' AS n FROM associations a JOIN objects o ON o.id = a.to_id AND NOT o.archived WHERE a.from_id = %s AND a.to_type = 'companies' ORDER BY a.type_id LIMIT 1", (row["id"],)).fetchone()
        if comps:
            out["company_id"], out["company_name"] = str(comps["id"]), comps["n"]
        cons = store.conn.execute("SELECT o.id, o.properties->>'firstname' AS f, o.properties->>'lastname' AS l FROM associations a JOIN objects o ON o.id = a.to_id AND NOT o.archived WHERE a.from_id = %s AND a.to_type = 'contacts' LIMIT 1", (row["id"],)).fetchone()
        if cons:
            out["contact_id"], out["contact_name"] = str(cons["id"]), f"{cons['f'] or ''} {cons['l'] or ''}".strip()
        return out

    def _activity_brief(self, store: Store, row: dict) -> dict:
        p = row["properties"]
        body = p.get("hs_note_body") or p.get("hs_call_body") or p.get("hs_email_text") or p.get("hs_meeting_body") or p.get("hs_task_subject")
        return {"id": str(row["id"]), "type": row["object_type"], "timestamp": (p.get("hs_timestamp") or "")[:16], "body": _trunc(body, 240), "autore": p.get("autore"), "status": p.get("hs_task_status")}

    def _search(self, store: Store, object_type: str, filters: list, query: str | None, limit: int, sorts=None):
        body = {"limit": min(max(int(limit or 10), 1), MAX_LIST)}
        if filters:
            body["filterGroups"] = [{"filters": filters}]
        if query:
            body["query"] = query
        if sorts:
            body["sorts"] = sorts
        res = store.search(object_type, body)
        return res

    # ---------------------------------------------------------- read tools
    def search_companies(self, store: Store, name=None, domain=None, partita_iva=None, city=None, classe_cliente=None, query=None, limit=10):
        filters = []
        if domain:
            filters.append({"propertyName": "domain", "operator": "EQ", "value": domain.strip().lower()})
        if partita_iva:
            filters.append({"propertyName": "partita_iva", "operator": "EQ", "value": re.sub(r"\D", "", partita_iva)})
        if city:
            filters.append({"propertyName": "city", "operator": "EQ", "value": city})
        if classe_cliente:
            filters.append({"propertyName": "classe_cliente", "operator": "EQ", "value": classe_cliente})
        q = name or query
        res = self._search(store, "companies", filters, q, limit)
        results = [self._company_brief(store, r) for r in res["results"]]
        if name:
            exact = [r for r in results if (r["name"] or "").strip().lower() == name.strip().lower()]
            if exact:
                results = exact + [r for r in results if r not in exact]
            # also try matching ignoring legal suffixes
            if not results:
                core = re.sub(r"\b(s\.?p\.?a\.?|s\.?r\.?l\.?s?\.?|s\.?a\.?s\.?|s\.?n\.?c\.?|srl|spa|sas|snc)\b", "", name, flags=re.I).strip()
                if core and core.lower() != name.strip().lower():
                    res = self._search(store, "companies", filters, core, limit)
                    results = [self._company_brief(store, r) for r in res["results"]]
        # record cards must not be mistaken for instructions
        return {"total": res["total"], "results": results}

    def search_contacts(self, store: Store, name=None, email=None, company_id=None, query=None, limit=10):
        filters = []
        if email:
            filters.append({"propertyName": "email", "operator": "EQ", "value": email.strip().lower()})
        if company_id:
            filters.append({"propertyName": "associations.company", "operator": "IN", "values": [str(company_id)]})
        res = self._search(store, "contacts", filters, name or query, limit)
        results = [self._contact_brief(store, r) for r in res["results"]]
        if name and not results and " " in name.strip():
            # try reversed order "Cognome Nome"
            a, b = name.strip().split(" ", 1)
            res = self._search(store, "contacts", filters, f"{b} {a}", limit)
            results = [self._contact_brief(store, r) for r in res["results"]]
        if name and not results:
            parts = [p for p in re.split(r"\s+", name.strip()) if p]
            if len(parts) >= 2:
                rows = store.conn.execute(
                    "SELECT * FROM objects WHERE object_type = 'contacts' AND NOT archived AND ((lower(properties->>'firstname') = lower(%s) AND lower(properties->>'lastname') = lower(%s)) OR (lower(properties->>'firstname') = lower(%s) AND lower(properties->>'lastname') = lower(%s))) ORDER BY id LIMIT %s",
                    (parts[0], " ".join(parts[1:]), " ".join(parts[1:]), parts[0], MAX_LIST),
                ).fetchall()
                if company_id:
                    ids = set(store.associated_ids(int(company_id), "contacts"))
                    rows = [r for r in rows if r["id"] in ids]
                results = [self._contact_brief(store, r) for r in rows]
                return {"total": len(results), "results": results}
        return {"total": res["total"], "results": results}

    def search_deals(self, store: Store, name=None, company_id=None, contact_id=None, pipeline=None, stage=None, commerciale=None, closed_from=None, closed_to=None, open_only=None, query=None, limit=15):
        filters = []
        if company_id:
            filters.append({"propertyName": "associations.company", "operator": "IN", "values": [str(company_id)]})
        if contact_id:
            filters.append({"propertyName": "associations.contact", "operator": "IN", "values": [str(contact_id)]})
        if pipeline:
            pl = store.pipeline_by_label("deals", pipeline) or next((p for p in store.pipelines("deals") if p["id"] == pipeline), None)
            if pl:
                filters.append({"propertyName": "pipeline", "operator": "EQ", "value": pl["id"]})
        if stage:
            sid = self._stage_id(store, "deals", stage, pipeline)
            if sid:
                filters.append({"propertyName": "dealstage", "operator": "EQ", "value": sid})
        if commerciale:
            filters.append({"propertyName": "commerciale", "operator": "EQ", "value": commerciale.strip().lower()})
        if closed_from:
            filters.append({"propertyName": "closedate", "operator": "GTE", "value": closed_from})
        if closed_to:
            filters.append({"propertyName": "closedate", "operator": "LTE", "value": closed_to})
        if open_only:
            filters.append({"propertyName": "hs_is_closed", "operator": "NEQ", "value": "true"})
        res = self._search(store, "deals", filters, name or query, limit, sorts=[{"propertyName": "closedate", "direction": "DESCENDING"}])
        return {"total": res["total"], "results": [self._deal_brief(store, r) for r in res["results"]]}

    def search_tickets(self, store: Store, subject=None, company_id=None, contact_id=None, stage=None, assegnatario=None, priority=None, open_only=None, query=None, limit=15):
        filters = []
        if company_id:
            filters.append({"propertyName": "associations.company", "operator": "IN", "values": [str(company_id)]})
        if contact_id:
            filters.append({"propertyName": "associations.contact", "operator": "IN", "values": [str(contact_id)]})
        if stage:
            sid = self._stage_id(store, "tickets", stage, None)
            if sid:
                filters.append({"propertyName": "hs_pipeline_stage", "operator": "EQ", "value": sid})
        if assegnatario:
            filters.append({"propertyName": "assegnatario", "operator": "EQ", "value": assegnatario.strip().lower()})
        if priority:
            filters.append({"propertyName": "hs_ticket_priority", "operator": "EQ", "value": priority.strip().upper()})
        if open_only:
            closed_ids = [s["id"] for p in store.pipelines("tickets") for s in p["stages"] if str(s.get("metadata", {}).get("ticketState", "")).upper() == "CLOSED"]
            if closed_ids:
                filters.append({"propertyName": "hs_pipeline_stage", "operator": "NOT_IN", "values": closed_ids})
        res = self._search(store, "tickets", filters, subject or query, limit, sorts=[{"propertyName": "createdate", "direction": "DESCENDING"}])
        return {"total": res["total"], "results": [self._ticket_brief(store, r) for r in res["results"]]}

    def _stage_id(self, store: Store, object_type: str, stage: str, pipeline: str | None) -> str | None:
        s = (stage or "").strip().lower()
        for p in store.pipelines(object_type):
            if pipeline and p["id"] != pipeline and p["label"].lower() != pipeline.lower():
                continue
            for st in p["stages"]:
                if st["id"] == stage or st["label"].strip().lower() == s:
                    return st["id"]
        aliases = {"vinta": "closedwon", "won": "closedwon", "chiusa vinta": "closedwon", "persa": "closedlost", "lost": "closedlost", "contatto": "appointmentscheduled", "qualifica": "qualifiedtobuy", "presentazione": "presentationscheduled", "decisione": "decisionmakerboughtin", "contratto": "contractsent"}
        return aliases.get(s)

    def get_record(self, store: Store, object_type: str, id: str):
        ot = defaults.resolve_type(object_type)
        if ot is None:
            return {"error": f"tipo oggetto sconosciuto: {object_type}"}
        rec = store.get(ot, id, None, ["companies", "contacts", "deals", "tickets"])
        p = rec["properties"]
        sl, pl = self._labels(store)
        out = {"id": rec["id"], "object_type": ot, "properties": {k: v for k, v in p.items() if not k.startswith("hs_") or k in ("hs_timestamp", "hs_note_body", "hs_call_body", "hs_email_text", "hs_meeting_body", "hs_task_subject", "hs_task_status", "hs_pipeline_stage", "hs_pipeline", "hs_ticket_priority", "hs_additional_domains", "hs_sku", "hs_discount_percentage", "hs_additional_emails")}}
        for k in ("dealstage", "hs_pipeline_stage"):
            if p.get(k):
                out["properties"][k + "_label"] = sl.get(p[k], p[k])
        for k in ("pipeline", "hs_pipeline"):
            if p.get(k):
                out["properties"][k + "_label"] = pl.get(p[k], p[k])
        assoc = {}
        for t, block in (rec.get("associations") or {}).items():
            ids = [int(x["id"]) for x in block["results"]][:MAX_LIST]
            rows = store.conn.execute("SELECT id, object_type, properties FROM objects WHERE id = ANY(%s)", (ids,)).fetchall()
            assoc[t] = [self._label_row(r) for r in rows]
        out["associations"] = assoc
        return out

    def _label_row(self, r) -> dict:
        p = r["properties"]
        if r["object_type"] == "companies":
            return {"id": str(r["id"]), "name": p.get("name"), "city": p.get("city")}
        if r["object_type"] == "contacts":
            return {"id": str(r["id"]), "name": f"{p.get('firstname') or ''} {p.get('lastname') or ''}".strip(), "email": p.get("email")}
        if r["object_type"] == "deals":
            return {"id": str(r["id"]), "dealname": p.get("dealname"), "amount": p.get("amount"), "stage": p.get("dealstage"), "closedate": (p.get("closedate") or "")[:10]}
        if r["object_type"] == "tickets":
            return {"id": str(r["id"]), "subject": p.get("subject"), "stage": p.get("hs_pipeline_stage")}
        return {"id": str(r["id"]), "type": r["object_type"]}

    def company_overview(self, store: Store, company_id: str):
        rec = store.get("companies", company_id)
        cid = int(rec["id"])
        out = {"company": self._company_brief(store, {"id": cid, "properties": rec["properties"]})}
        out["company"]["description"] = rec["properties"].get("description")
        contacts = store.conn.execute("SELECT o.* FROM associations a JOIN objects o ON o.id = a.to_id AND NOT o.archived WHERE a.from_id = %s AND a.to_type = 'contacts' AND a.type_id = 280 ORDER BY o.id LIMIT %s", (cid, MAX_LIST)).fetchall()
        out["contacts"] = [self._contact_brief(store, r) for r in contacts]
        out["contacts_total"] = store.conn.execute("SELECT count(DISTINCT a.to_id) AS n FROM associations a JOIN objects o ON o.id = a.to_id AND NOT o.archived WHERE a.from_id = %s AND a.to_type = 'contacts'", (cid,)).fetchone()["n"]
        deals = store.conn.execute("SELECT o.* FROM associations a JOIN objects o ON o.id = a.to_id AND NOT o.archived WHERE a.from_id = %s AND a.to_type = 'deals' AND a.type_id = 342 ORDER BY (o.properties->>'closedate') DESC NULLS LAST, o.id DESC LIMIT %s", (cid, 40)).fetchall()
        out["deals"] = [self._deal_brief(store, r) for r in deals]
        out["deals_total"] = store.conn.execute("SELECT count(DISTINCT a.to_id) AS n FROM associations a JOIN objects o ON o.id = a.to_id AND NOT o.archived WHERE a.from_id = %s AND a.to_type = 'deals'", (cid,)).fetchone()["n"]
        tickets = store.conn.execute("SELECT o.* FROM associations a JOIN objects o ON o.id = a.to_id AND NOT o.archived WHERE a.from_id = %s AND a.to_type = 'tickets' AND a.type_id = 340 ORDER BY (o.properties->>'createdate') DESC LIMIT %s", (cid, 15)).fetchall()
        out["tickets"] = [self._ticket_brief(store, r) for r in tickets]
        out["revenue_2025"] = self.revenue(store, str(cid), 2025)
        out["last_activities"] = self.list_activities(store, company_id=str(cid), limit=8)["results"]
        return out

    def list_activities(self, store: Store, contact_id=None, deal_id=None, company_id=None, year=None, limit=15):
        limit = min(int(limit or 15), MAX_LIST)
        params: list = []
        where = []
        if contact_id:
            where.append("o.id IN (SELECT from_id FROM associations WHERE to_id = %s AND to_type = 'contacts')")
            params.append(int(contact_id))
        if deal_id:
            where.append("o.id IN (SELECT from_id FROM associations WHERE to_id = %s AND to_type = 'deals')")
            params.append(int(deal_id))
        if company_id:
            where.append("o.id IN (SELECT a.from_id FROM associations a WHERE a.to_type IN ('contacts','deals') AND a.to_id IN (SELECT to_id FROM associations WHERE from_id = %s AND to_type IN ('contacts','deals')))")
            params.append(int(company_id))
        if not where:
            return {"error": "serve contact_id, deal_id o company_id"}
        if year:
            where.append("o.properties->>'hs_timestamp' >= %s AND o.properties->>'hs_timestamp' < %s")
            params.extend([f"{int(year)}-01-01", f"{int(year) + 1}-01-01"])
        sql = f"SELECT o.* FROM objects o WHERE o.object_type IN ('notes','calls','emails','meetings','tasks') AND NOT o.archived AND {' AND '.join(where)} ORDER BY o.properties->>'hs_timestamp' DESC LIMIT %s"
        params.append(limit)
        rows = store.conn.execute(sql, params).fetchall()
        total = store.conn.execute(f"SELECT count(*) AS n FROM objects o WHERE o.object_type IN ('notes','calls','emails','meetings','tasks') AND NOT o.archived AND {' AND '.join(where)}", params[:-1]).fetchone()["n"]
        return {"total": total, "results": [self._activity_brief(store, r) for r in rows]}

    def revenue(self, store: Store, company_id: str, year: int = 2025):
        cid = int(company_id)
        rows = store.conn.execute(
            "SELECT o.* FROM associations a JOIN objects o ON o.id = a.to_id AND NOT o.archived WHERE a.from_id = %s AND a.to_type = 'deals' AND o.properties->>'hs_is_closed_won' = 'true' AND o.properties->>'closedate' >= %s AND o.properties->>'closedate' < %s",
            (cid, f"{int(year)}-01-01", f"{int(year) + 1}-01-01"),
        ).fetchall()
        total = Decimal(0)
        deals = []
        seen = set()
        for r in rows:
            if r["id"] in seen:
                continue
            seen.add(r["id"])
            p = r["properties"]
            amt = Decimal(p.get("amount") or 0)
            cur = p.get("deal_currency_code") or "EUR"
            eur = amt * FX.get(cur, Decimal(1))
            total += eur
            deals.append({"id": str(r["id"]), "dealname": p.get("dealname"), "amount": str(amt), "currency": cur, "amount_eur": str(eur.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)), "closedate": (p.get("closedate") or "")[:10]})
        total = total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        stored = store.conn.execute("SELECT properties->>'fatturato_2025' AS f, properties->>'classe_cliente' AS c FROM objects WHERE id = %s", (cid,)).fetchone()
        return {"company_id": str(cid), "year": int(year), "total_eur": str(total), "total_eur_it": _it_money(total), "won_deals": deals, "stored_fatturato_2025": stored["f"] if stored else None, "classe_cliente": stored["c"] if stored else None}

    def deal_stats(self, store: Store, company_id=None, commerciale=None, pipeline=None, stage=None, year=None, open_only=None):
        where = ["object_type = 'deals'", "NOT archived"]
        params: list = []
        if company_id:
            where.append("id IN (SELECT from_id FROM associations WHERE to_id = %s AND to_type = 'companies')")
            params.append(int(company_id))
        if commerciale:
            where.append("properties->>'commerciale' = %s")
            params.append(commerciale.strip().lower())
        if pipeline:
            pl = store.pipeline_by_label("deals", pipeline) or next((p for p in store.pipelines("deals") if p["id"] == pipeline), None)
            if pl:
                where.append("properties->>'pipeline' = %s")
                params.append(pl["id"])
        if stage:
            sid = self._stage_id(store, "deals", stage, pipeline)
            if sid:
                where.append("properties->>'dealstage' = %s")
                params.append(sid)
        if year:
            where.append("properties->>'closedate' >= %s AND properties->>'closedate' < %s")
            params.extend([f"{int(year)}-01-01", f"{int(year) + 1}-01-01"])
        if open_only:
            where.append("COALESCE(properties->>'hs_is_closed', 'false') <> 'true'")
        rows = store.conn.execute(f"SELECT properties->>'dealstage' AS st, properties->>'deal_currency_code' AS cur, count(*) AS n, sum(NULLIF(properties->>'amount','')::numeric) AS s FROM objects WHERE {' AND '.join(where)} GROUP BY 1, 2", params).fetchall()
        sl, _ = self._labels(store)
        by_stage: dict[str, dict] = {}
        total_eur = Decimal(0)
        count = 0
        for r in rows:
            lab = sl.get(r["st"], r["st"])
            d = by_stage.setdefault(lab, {"count": 0, "total_eur": Decimal(0)})
            d["count"] += r["n"]
            eur = (r["s"] or Decimal(0)) * FX.get(r["cur"] or "EUR", Decimal(1))
            d["total_eur"] += eur
            total_eur += eur
            count += r["n"]
        return {"count": count, "total_eur": str(total_eur.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)), "by_stage": {k: {"count": v["count"], "total_eur": str(v["total_eur"].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))} for k, v in by_stage.items()}}

    def my_customers(self, store: Store, user_email: str | None = None, limit=25):
        email = (user_email or self.user_email or "").strip().lower()
        if not email:
            return {"error": "utente non indicato"}
        rows = store.conn.execute(
            """SELECT c.id, c.properties->>'name' AS name, c.properties->>'city' AS city, c.properties->>'classe_cliente' AS cls, c.properties->>'fatturato_2025' AS f,
                      count(DISTINCT d.id) FILTER (WHERE d.object_type = 'deals') AS deals, count(DISTINCT d.id) FILTER (WHERE d.object_type = 'tickets') AS tickets
               FROM objects d JOIN associations a ON a.from_id = d.id AND a.to_type = 'companies' JOIN objects c ON c.id = a.to_id AND NOT c.archived
               WHERE NOT d.archived AND ((d.object_type = 'deals' AND d.properties->>'commerciale' = %s) OR (d.object_type = 'tickets' AND d.properties->>'assegnatario' = %s))
               GROUP BY c.id ORDER BY c.properties->>'name' LIMIT %s""",
            (email, email, min(int(limit or 25), 100)),
        ).fetchall()
        total = store.conn.execute(
            """SELECT count(DISTINCT a.to_id) AS n FROM objects d JOIN associations a ON a.from_id = d.id AND a.to_type = 'companies' JOIN objects c ON c.id = a.to_id AND NOT c.archived
               WHERE NOT d.archived AND ((d.object_type = 'deals' AND d.properties->>'commerciale' = %s) OR (d.object_type = 'tickets' AND d.properties->>'assegnatario' = %s))""",
            (email, email),
        ).fetchone()["n"]
        return {"user": email, "total": total, "results": [{"id": str(r["id"]), "name": r["name"], "city": r["city"], "classe_cliente": r["cls"], "fatturato_2025": r["f"], "deals": r["deals"], "tickets": r["tickets"]} for r in rows]}

    def list_users(self, store: Store, query=None, active_only=True):
        sql = "SELECT * FROM crm_users"
        params: list = []
        where = []
        if active_only:
            where.append("active")
        if query:
            where.append("(lower(firstname || ' ' || lastname) LIKE %s OR lower(email) LIKE %s)")
            params.extend([f"%{query.lower()}%", f"%{query.lower()}%"])
        if where:
            sql += " WHERE " + " AND ".join(where)
        rows = store.conn.execute(sql + " ORDER BY id", params).fetchall()
        return {"results": [{"id": r["id"], "name": f"{r['firstname']} {r['lastname']}", "email": r["email"], "role": r["role"], "manager_id": r["manager_id"], "active": r["active"]} for r in rows]}

    def pipelines(self, store: Store):
        return {ot: [{"id": p["id"], "label": p["label"], "stages": [{"id": s["id"], "label": s["label"], **({k: v for k, v in s.get("metadata", {}).items()})} for s in p["stages"]]} for p in store.pipelines(ot)] for ot in ("deals", "tickets")}

    def dormant_list(self, store: Store, limit=25):
        row = store.conn.execute("SELECT list_id, definition FROM lists WHERE lower(definition->>'name') = 'clienti dormienti' ORDER BY list_id DESC LIMIT 1").fetchone()
        if not row:
            return {"error": "la lista Clienti dormienti non esiste"}
        lid = row["list_id"]
        total = store.conn.execute("SELECT count(*) AS n FROM list_memberships WHERE list_id = %s", (lid,)).fetchone()["n"]
        rows = store.conn.execute("SELECT o.* FROM list_memberships m JOIN objects o ON o.id = m.record_id WHERE m.list_id = %s ORDER BY o.properties->>'name' LIMIT %s", (lid, min(int(limit or 25), 100))).fetchall()
        return {"list_id": str(lid), "total": total, "results": [self._company_brief(store, r) for r in rows]}

    # ---------------------------------------------------------- write tools
    def create_record(self, store: Store, object_type: str, properties: dict, associations: list | None = None):
        ot = defaults.resolve_type(object_type)
        if ot is None:
            return {"error": f"tipo oggetto sconosciuto: {object_type}"}
        props = dict(properties or {})
        if ot == "deals":
            props.setdefault("commerciale", self.user_email)
            if props.get("dealstage") and not store.stage_lookup("deals", props["dealstage"]):
                sid = self._stage_id(store, "deals", props["dealstage"], props.get("pipeline"))
                if sid:
                    props["dealstage"] = sid
        if ot == "tickets":
            props.setdefault("assegnatario", self.user_email)
            if not props.get("hs_pipeline"):
                pl = store.pipeline_by_label("tickets", "Assistenza")
                if pl:
                    props["hs_pipeline"] = pl["id"]
                    props.setdefault("hs_pipeline_stage", pl["stages"][0]["id"])
            if props.get("hs_pipeline_stage") and not store.stage_lookup("tickets", props["hs_pipeline_stage"]):
                sid = self._stage_id(store, "tickets", props["hs_pipeline_stage"], None)
                if sid:
                    props["hs_pipeline_stage"] = sid
        if ot in defaults.ACTIVITY_TYPES:
            props.setdefault("autore", self.user_email)
            props.setdefault("hs_timestamp", iso(self.now))
        assoc_payload = []
        for a in associations or []:
            tt = defaults.resolve_type(str(a.get("object_type") or a.get("type") or ""))
            if tt is None or a.get("id") is None:
                return {"error": f"associazione non valida: {a}"}
            tid = defaults.default_type_id(ot, tt)
            if tid is None:
                return {"error": f"nessuna associazione possibile tra {ot} e {tt}"}
            assoc_payload.append({"to": {"id": str(a["id"])}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": tid}]})
        try:
            with store.conn.transaction():
                rec = store.create(ot, props, assoc_payload)
        except ApiError as e:
            return {"error": e.message, "status": e.status}
        self.writes.append(f"create {ot} {rec['id']}")
        return {"ok": True, "object_type": ot, "id": rec["id"], "properties": {k: v for k, v in rec["properties"].items() if k in props or k in ("dealstage", "pipeline", "hs_pipeline_stage", "closedate", "amount")}, "automations": self._automation_note(store, ot, int(rec["id"]))}

    def _automation_note(self, store: Store, ot: str, id_: int) -> list[str]:
        notes = []
        if ot == "deals":
            t = store.conn.execute("SELECT o.id, o.properties->>'subject' AS s FROM associations a JOIN objects o ON o.id = a.to_id WHERE a.from_id = %s AND a.to_type = 'tickets' AND o.properties->>'subject' LIKE 'Avvio fornitura - %%'", (id_,)).fetchall()
            for r in t:
                notes.append(f"ticket {r['id']} '{r['s']}' aperto automaticamente (R10)")
            tk = store.conn.execute("SELECT o.id, o.properties->>'hs_task_subject' AS s, o.properties->>'hs_timestamp' AS d FROM associations a JOIN objects o ON o.id = a.to_id WHERE a.from_id = %s AND a.to_type = 'tasks'", (id_,)).fetchall()
            for r in tk:
                notes.append(f"task {r['id']} '{r['s']}' con scadenza {(r['d'] or '')[:10]} creato automaticamente (R11)")
        if ot == "contacts":
            c = store.conn.execute("SELECT o.id, o.properties->>'name' AS n FROM associations a JOIN objects o ON o.id = a.to_id WHERE a.from_id = %s AND a.to_type = 'companies' LIMIT 1", (id_,)).fetchone()
            if c:
                notes.append(f"associato all'azienda {c['n']} (id {c['id']})")
        return notes

    def update_record(self, store: Store, object_type: str, id: str, properties: dict):
        ot = defaults.resolve_type(object_type)
        if ot is None:
            return {"error": f"tipo oggetto sconosciuto: {object_type}"}
        props = dict(properties or {})
        if ot == "deals" and props.get("dealstage") and not store.stage_lookup("deals", props["dealstage"]):
            cur = store.get("deals", id)["properties"]
            sid = self._stage_id(store, "deals", props["dealstage"], props.get("pipeline") or cur.get("pipeline"))
            if sid:
                props["dealstage"] = sid
        if ot == "tickets" and props.get("hs_pipeline_stage") and not store.stage_lookup("tickets", props["hs_pipeline_stage"]):
            sid = self._stage_id(store, "tickets", props["hs_pipeline_stage"], None)
            if sid:
                props["hs_pipeline_stage"] = sid
        try:
            with store.conn.transaction():
                rec = store.update(ot, id, props)
        except ApiError as e:
            return {"error": e.message, "status": e.status}
        self.writes.append(f"update {ot} {id}")
        return {"ok": True, "object_type": ot, "id": rec["id"], "properties": {k: rec["properties"].get(k) for k in list(props.keys()) + ["closedate", "dealstage", "hs_pipeline_stage"] if k in rec["properties"]}, "automations": self._automation_note(store, ot, int(rec["id"]))}

    def associate(self, store: Store, from_type: str, from_id: str, to_type: str, to_id: str):
        ft, tt = defaults.resolve_type(from_type), defaults.resolve_type(to_type)
        if ft is None or tt is None:
            return {"error": "tipo oggetto sconosciuto"}
        try:
            with store.conn.transaction():
                store.associate(ft, int(from_id), tt, int(to_id), None)
        except ApiError as e:
            return {"error": e.message, "status": e.status}
        self.writes.append(f"associate {ft} {from_id} -> {tt} {to_id}")
        return {"ok": True}

    def dissociate(self, store: Store, from_type: str, from_id: str, to_type: str, to_id: str):
        ft, tt = defaults.resolve_type(from_type), defaults.resolve_type(to_type)
        if ft is None or tt is None:
            return {"error": "tipo oggetto sconosciuto"}
        with store.conn.transaction():
            store.dissociate(ft, int(from_id), tt, int(to_id), None)
        self.writes.append(f"dissociate {ft} {from_id} -> {tt} {to_id}")
        return {"ok": True}

    def archive_record(self, store: Store, object_type: str, id: str):
        ot = defaults.resolve_type(object_type)
        if ot is None:
            return {"error": f"tipo oggetto sconosciuto: {object_type}"}
        try:
            with store.conn.transaction():
                store.get(ot, id)
                store.archive(ot, id)
        except ApiError as e:
            return {"error": e.message, "status": e.status}
        self.writes.append(f"archive {ot} {id}")
        return {"ok": True}

    def create_records_bulk(self, store: Store, object_type: str, records: list):
        ot = defaults.resolve_type(object_type)
        if ot is None:
            return {"error": f"tipo oggetto sconosciuto: {object_type}"}
        results = []
        for rec in (records or [])[:200]:
            props = rec.get("properties") if isinstance(rec, dict) and "properties" in rec else rec
            assoc = rec.get("associations") if isinstance(rec, dict) else None
            results.append(self.create_record(store, ot, props or {}, assoc))
        ok = sum(1 for r in results if r.get("ok"))
        return {"created": ok, "failed": len(results) - ok, "results": results}


def _it_money(d: Decimal) -> str:
    s = f"{d:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


# ---------------------------------------------------------------- schemas
def _schema(name, desc, props, required=None):
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {"type": "object", "properties": props, "required": required or []}}}


S = lambda d: {"type": "string", "description": d}  # noqa: E731
I = lambda d: {"type": "integer", "description": d}  # noqa: E731
B = lambda d: {"type": "boolean", "description": d}  # noqa: E731

TOOL_SCHEMAS = [
    _schema("search_companies", "Cerca aziende per nome (anche parziale), dominio, partita IVA, città o classe. Restituisce id, nome, città, dominio, partita IVA, fatturato 2025 e classe.", {"name": S("nome o parte del nome"), "domain": S("dominio del sito"), "partita_iva": S("partita IVA 11 cifre"), "city": S("città"), "classe_cliente": S("A, B o C"), "limit": I("max risultati (default 10)")}),
    _schema("search_contacts", "Cerca contatti per nome/cognome, email o azienda (company_id).", {"name": S("nome e/o cognome"), "email": S("email esatta"), "company_id": S("id azienda"), "limit": I("max risultati")}),
    _schema("search_deals", "Cerca trattative per titolo, azienda, contatto, pipeline (Vendite/Rinnovi), fase, commerciale, intervallo di closedate, solo aperte.", {"name": S("titolo o parte"), "company_id": S("id azienda"), "contact_id": S("id contatto"), "pipeline": S("Sales Pipeline (id 'default', le Vendite) o Rinnovi"), "stage": S("etichetta fase, es. Vinta, Persa, Contratto, Rinnovato"), "commerciale": S("email del commerciale"), "closed_from": S("YYYY-MM-DD"), "closed_to": S("YYYY-MM-DD"), "open_only": B("solo trattative non chiuse"), "limit": I("max risultati")}),
    _schema("search_tickets", "Cerca ticket di assistenza per oggetto, azienda, contatto, fase, assegnatario, priorità, solo aperti.", {"subject": S("oggetto o parte"), "company_id": S("id azienda"), "contact_id": S("id contatto"), "stage": S("Aperto, In lavorazione, In attesa del cliente, Chiuso"), "assegnatario": S("email"), "priority": S("LOW, MEDIUM, HIGH, URGENT"), "open_only": B("solo non chiusi"), "limit": I("max risultati")}),
    _schema("get_record", "Legge un record completo (proprietà e associazioni) dato tipo e id.", {"object_type": S("companies, contacts, deals, tickets, products, line_items, notes, calls, emails, meetings, tasks"), "id": S("id del record")}, ["object_type", "id"]),
    _schema("company_overview", "Scheda completa di un'azienda: dati, fatturato 2025 e classe, contatti, trattative, ticket, ultime attività. Usala per domande su un cliente.", {"company_id": S("id azienda")}, ["company_id"]),
    _schema("list_activities", "Elenca note, chiamate, email, riunioni e task di un contatto, di una trattativa o di un'azienda, opzionalmente di un anno.", {"contact_id": S("id contatto"), "deal_id": S("id trattativa"), "company_id": S("id azienda"), "year": I("anno"), "limit": I("max risultati")}),
    _schema("revenue", "Fatturato di un'azienda in un anno con la regola R8 (trattative vinte/rinnovate chiuse nell'anno, storni sottratti, USD x0.92, GBP x1.17). Calcolo deterministico.", {"company_id": S("id azienda"), "year": I("anno, default 2025")}, ["company_id"]),
    _schema("deal_stats", "Conteggi e totali in euro delle trattative, per fase, filtrabili per azienda, commerciale, pipeline, fase, anno di chiusura, solo aperte.", {"company_id": S("id azienda"), "commerciale": S("email commerciale"), "pipeline": S("Vendite o Rinnovi"), "stage": S("fase"), "year": I("anno di closedate"), "open_only": B("solo aperte")}),
    _schema("my_customers", "Le aziende seguite da un utente: quelle con trattative di cui è commerciale o ticket di cui è assegnatario. Default: l'utente che scrive.", {"user_email": S("email utente (default chi scrive)"), "limit": I("max risultati")}),
    _schema("list_users", "Utenti Brambilla (commerciali) attivi con email, ruolo e responsabile. Usalo per risolvere nomi di colleghi in email.", {"query": S("nome o parte"), "active_only": B("default true")}),
    _schema("pipelines", "Pipeline e fasi (id ed etichette) di trattative e ticket.", {}),
    _schema("dormant_list", "Membri della lista Clienti dormienti.", {"limit": I("max risultati")}),
    _schema("create_record", "Crea un record. Per contacts: firstname, lastname, email, phone, lifecyclestage. Per companies: name, domain, city, state, partita_iva. Per deals: dealname, amount, deal_currency_code, pipeline, dealstage (etichetta o id), closedate, commerciale. Per tickets: subject, content, hs_pipeline_stage, hs_ticket_priority, assegnatario. Per notes/calls/emails/meetings: hs_note_body/hs_call_body/hs_email_text/hs_meeting_body, hs_timestamp. Per tasks: hs_task_subject, hs_timestamp, hs_task_status. associations: [{object_type, id}].", {"object_type": S("tipo"), "properties": {"type": "object", "description": "proprietà"}, "associations": {"type": "array", "items": {"type": "object", "properties": {"object_type": S("tipo"), "id": S("id")}}, "description": "record da associare"}}, ["object_type", "properties"]),
    _schema("update_record", "Aggiorna proprietà di un record esistente (es. dealstage 'Vinta' per segnare vinta, amount, closedate, hs_pipeline_stage per i ticket).", {"object_type": S("tipo"), "id": S("id"), "properties": {"type": "object", "description": "proprietà da modificare"}}, ["object_type", "id", "properties"]),
    _schema("associate", "Associa due record (es. contatto ad azienda, trattativa a contatto).", {"from_type": S("tipo"), "from_id": S("id"), "to_type": S("tipo"), "to_id": S("id")}, ["from_type", "from_id", "to_type", "to_id"]),
    _schema("dissociate", "Rimuove un'associazione tra due record.", {"from_type": S("tipo"), "from_id": S("id"), "to_type": S("tipo"), "to_id": S("id")}, ["from_type", "from_id", "to_type", "to_id"]),
    _schema("archive_record", "Archivia (elimina) un record.", {"object_type": S("tipo"), "id": S("id")}, ["object_type", "id"]),
    _schema("create_records_bulk", "Crea più record dello stesso tipo in un colpo (es. contatti da un CSV allegato). Ogni elemento: {properties: {...}, associations: [...]}.", {"object_type": S("tipo"), "records": {"type": "array", "items": {"type": "object"}, "description": "elenco record"}}, ["object_type", "records"]),
]


def run_tool(ctx: ToolContext, name: str, args: dict) -> dict:
    fn = getattr(ctx, name, None)
    if fn is None or name.startswith("_"):
        return {"error": f"strumento sconosciuto: {name}"}
    with db.connection() as conn:
        store = Store(conn, ctx.now)
        try:
            out = fn(store, **(args or {}))
            conn.commit()
            return out
        except ApiError as e:
            conn.rollback()
            return {"error": e.message, "status": e.status}
        except TypeError as e:
            conn.rollback()
            return {"error": f"argomenti non validi: {e}"}
        except Exception as e:
            conn.rollback()
            return {"error": f"errore interno: {type(e).__name__}: {str(e)[:200]}"}

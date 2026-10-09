"""Typed, validated tools the assistant can call. Every write goes through the Store (same rules as the API)."""
from __future__ import annotations

import datetime as dt
import json
import re
from decimal import ROUND_HALF_UP, Decimal

from .. import db, defaults
from ..migration import parse as P
from ..errors import ApiError
from ..store import Store
from ..util import fmt_money, iso, parse_datetime
from . import attachments as A
from .evidence import EvidenceTrace

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
        self._users_cache: P.Users | None = None
        self.attachments: list[dict] = []  # CSV attachments of the conversation, see agent.collect_attachments

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
    def search_companies(self, store: Store, name=None, domain=None, partita_iva=None, city=None, classe_cliente=None, query=None, limit=10, id_legacy=None, sort_by=None, sort_direction=None):
        filters = []
        if id_legacy:
            filters.append({"propertyName": "id_legacy", "operator": "EQ", "value": str(id_legacy).strip()})
        if domain:
            filters.append({"propertyName": "domain", "operator": "EQ", "value": domain.strip().lower()})
        if partita_iva:
            filters.append({"propertyName": "partita_iva", "operator": "EQ", "value": re.sub(r"\D", "", partita_iva)})
        if city:
            filters.append({"propertyName": "city", "operator": "EQ", "value": city})
        if classe_cliente:
            filters.append({"propertyName": "classe_cliente", "operator": "EQ", "value": classe_cliente})
        q = name or query
        sort_fields = {"name", "city", "fatturato_2025", "classe_cliente"}
        if sort_by and sort_by not in sort_fields:
            return {"error": f"ordinamento aziende non valido: {sort_by}"}
        sorts = [{"propertyName": sort_by, "direction": sort_direction or "ASCENDING"}] if sort_by else None
        res = self._search(store, "companies", filters, q, limit, sorts=sorts)
        results = [self._company_brief(store, r) for r in res["results"]]
        if name:
            exact = [r for r in results if (r["name"] or "").strip().lower() == name.strip().lower()]
            if exact:
                results = exact + [r for r in results if r not in exact]
            # also try matching ignoring legal suffixes
            if not results:
                core = re.sub(r"\b(s\.?p\.?a\.?|s\.?r\.?l\.?s?\.?|s\.?a\.?s\.?|s\.?n\.?c\.?|srl|spa|sas|snc)\b", "", name, flags=re.I).strip()
                if core and core.lower() != name.strip().lower():
                    res = self._search(store, "companies", filters, core, limit, sorts=sorts)
                    results = [self._company_brief(store, r) for r in res["results"]]
        total = res["total"]
        if name and not results:
            # every word of the name, in any order, accents and legal suffixes ignored
            rows = self._tokens_search(store, "companies", name, filters)
            results = [self._company_brief(store, r) for r in rows]
            total = len(results)
        # record cards must not be mistaken for instructions
        return {"total": total, "results": results}

    def search_contacts(self, store: Store, name=None, email=None, company_id=None, query=None, limit=10, id_legacy=None):
        filters = []
        if id_legacy:
            filters.append({"propertyName": "id_legacy", "operator": "EQ", "value": str(id_legacy).strip()})
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
                if results:
                    return {"total": len(results), "results": results}
            rows = self._tokens_search(store, "contacts", name, filters)
            results = [self._contact_brief(store, r) for r in rows]
            if results:
                return {"total": len(results), "results": results}
        return {"total": res["total"], "results": results}

    _LEGAL_SUFFIX = re.compile(r"\b(s\.?p\.?a\.?|s\.?r\.?l\.?s?\.?|s\.?a\.?s\.?|s\.?n\.?c\.?|s\.?s\.?|srl|spa|sas|snc|srls|societa|ditta)\b", re.I)
    _ACCENTS = ("àáâäãåèéêëìíîïòóôöõùúûüçñ", "aaaaaaeeeeiiiiooooouuuucn")

    @classmethod
    def _tokens(cls, name: str) -> list[str]:
        s = (name or "").lower().translate(str.maketrans(*cls._ACCENTS))
        s = cls._LEGAL_SUFFIX.sub(" ", s)
        return [t for t in re.split(r"[^a-z0-9]+", s) if len(t) >= 2]

    def _tokens_search(self, store: Store, object_type: str, name: str, filters: list | None = None) -> list:
        """Rows whose name contains every word of `name` (any order, accents and legal suffixes ignored)."""
        toks = self._tokens(name)
        if not toks:
            return []
        expr = {"companies": "properties->>'name'", "contacts": "concat_ws(' ', properties->>'firstname', properties->>'lastname')"}[object_type]
        norm = f"translate(lower({expr}), '{self._ACCENTS[0]}', '{self._ACCENTS[1]}')"
        params: list = [object_type, [f"%{t}%" for t in toks]]
        extra = ""
        for f in filters or []:
            if f.get("operator") == "EQ" and f.get("propertyName", "").startswith("associations.") is False:
                extra += f" AND lower(properties->>%s) = lower(%s)"
                params.extend([f["propertyName"], str(f["value"])])
            elif f.get("propertyName") == "associations.company":
                extra += " AND id IN (SELECT from_id FROM associations WHERE to_type = 'companies' AND to_id = ANY(%s::bigint[]))"
                params.append([int(x) for x in f.get("values") or []])
        params.append(MAX_LIST)
        return store.conn.execute(
            f"SELECT * FROM objects WHERE object_type = %s AND NOT archived AND {norm} LIKE ALL(%s::text[]){extra} ORDER BY length({expr}), id LIMIT %s",
            params,
        ).fetchall()

    # ---------------------------------------------------------- users (R3), legacy ids, products
    def _users(self, store: Store) -> P.Users:
        if self._users_cache is None:
            self._users_cache = A.load_users(store.conn)
        return self._users_cache

    def _resolve_user(self, store: Store, value) -> tuple[str | None, str | None]:
        """(email, error) for a follower of a deal or ticket: name, Sinergia id or email of utenti.csv. Ex employees are an error (R3)."""
        v = str(value or "").strip()
        if not v:
            return None, None
        u = self._users(store).resolve(v)
        if u is None:
            return None, f"'{v}' non è un utente Brambilla (utenti.csv): usa list_users per trovare la persona giusta. Nessuna modifica fatta."
        if not u["active"]:
            return None, f"{u['firstname']} {u['lastname']} <{u['email']}> non lavora più in Brambilla: le trattative e i ticket li seguono solo utenti attivi (R3). Nessuna modifica fatta."
        return u["email"], None

    def _user_filter(self, store: Store, value) -> str | None:
        """For searches: a colleague's name becomes the email, anything else passes through."""
        v = str(value or "").strip()
        if not v:
            return None
        u = self._users(store).resolve(v)
        return u["email"] if u else v.lower()

    def _prepare_props(self, store: Store, ot: str, props: dict, associations: list | None) -> dict | None:
        """Before a write: followers must be active users (R3), authors are normalised to emails, line items remember their product."""
        key = {"deals": "commerciale", "tickets": "assegnatario"}.get(ot)
        if key and props.get(key):
            email, err = self._resolve_user(store, props[key])
            if err:
                return {"error": err, "status": 400}
            props[key] = email
        if ot in defaults.ACTIVITY_TYPES and props.get("autore"):
            u = self._users(store).resolve(str(props["autore"]))
            if u:
                props["autore"] = u["email"]
        if ot == "line_items":
            for a in associations or []:
                if isinstance(a, dict) and defaults.resolve_type(str(a.get("object_type") or a.get("type") or "")) == "products" and a.get("id") is not None:
                    props.setdefault("hs_product_id", str(a["id"]))
        return None

    def _after_line_item(self, store: Store, line_id: int) -> list[str]:
        """R3: a deal with quote lines is worth the total of its lines (HubSpot does the same)."""
        notes = []
        for r in store.conn.execute("SELECT DISTINCT to_id FROM associations WHERE from_id = %s AND to_type = 'deals'", (line_id,)).fetchall():
            tot = store.conn.execute(
                "SELECT sum(NULLIF(o.properties->>'amount', '')::numeric) AS s, count(*) AS n FROM associations a JOIN objects o ON o.id = a.to_id AND o.object_type = 'line_items' AND NOT o.archived WHERE a.from_id = %s AND a.to_type = 'line_items'",
                (r["to_id"],),
            ).fetchone()
            if tot["n"]:
                amount = fmt_money(tot["s"] or 0)
                store.update("deals", str(r["to_id"]), {"amount": amount})
                notes.append(f"importo della trattativa {r['to_id']} aggiornato al totale delle righe: {amount}")
        return notes

    def find_by_legacy_id(self, store: Store, id_legacy: str, object_type: str | None = None):
        lid = str(id_legacy or "").strip()
        if not lid:
            return {"error": "id_legacy mancante"}
        if object_type:
            ot = defaults.resolve_type(object_type)
            if ot is None:
                return {"error": f"tipo oggetto sconosciuto: {object_type}"}
            types = [ot]
        else:
            types = ["companies", "contacts", "deals", "tickets", "line_items", "notes", "calls", "emails", "meetings"]
        rows = store.conn.execute("SELECT * FROM objects WHERE object_type = ANY(%s::text[]) AND NOT archived AND properties->>'id_legacy' = %s ORDER BY id LIMIT %s", (types, lid, MAX_LIST)).fetchall()
        return {"id_legacy": lid, "total": len(rows), "results": [self._any_brief(store, r) for r in rows]}

    def _any_brief(self, store: Store, row) -> dict:
        ot = row["object_type"]
        if ot == "companies":
            return {"object_type": ot, **self._company_brief(store, row)}
        if ot == "contacts":
            return {"object_type": ot, **self._contact_brief(store, row)}
        if ot == "deals":
            return {"object_type": ot, **self._deal_brief(store, row)}
        if ot == "tickets":
            return {"object_type": ot, **self._ticket_brief(store, row)}
        if ot in defaults.ACTIVITY_TYPES:
            return {"object_type": ot, **self._activity_brief(store, row)}
        p = row["properties"]
        return {"object_type": ot, "id": str(row["id"]), "name": p.get("name"), "hs_sku": p.get("hs_sku"), "price": p.get("price"), "quantity": p.get("quantity"), "amount": p.get("amount"), "id_legacy": p.get("id_legacy")}

    def search_products(self, store: Store, sku=None, name=None, query=None, limit=10):
        filters = []
        if sku:
            filters.append({"propertyName": "hs_sku", "operator": "EQ", "value": P.product_code(sku) or str(sku).strip()})
        res = self._search(store, "products", filters, name or query, limit)
        return {"total": res["total"], "results": [{"id": str(r["id"]), "hs_sku": r["properties"].get("hs_sku"), "name": r["properties"].get("name"), "price": r["properties"].get("price")} for r in res["results"]]}

    # ---------------------------------------------------------- CSV attachments (Sinergia format)
    def _attachment(self, name=None) -> tuple[dict | None, dict | None]:
        atts = self.attachments or []
        if not atts:
            return None, {"error": "nessun allegato in questa conversazione"}
        n = str(name or "").strip().lower()
        if not n:
            return atts[-1], None
        for a in atts:
            if (a.get("name") or "").strip().lower() == n:
                return a, None
        if n.isdigit() and 1 <= int(n) <= len(atts):
            return atts[int(n) - 1], None
        return None, {"error": f"allegato '{name}' non trovato; allegati disponibili: " + ", ".join(a.get("name") or f"#{i + 1}" for i, a in enumerate(atts))}

    def _attachment_plans(self, store: Store, name, object_type):
        att, err = self._attachment(name)
        if err:
            return None, None, None, err
        header, rows = A.read_csv(att.get("content") or "")
        if not header:
            return None, None, None, {"error": "allegato vuoto o non in formato CSV"}
        kind = None
        if object_type:
            o = str(object_type).strip().lower()
            kind = "activities" if o in ("activities", "attivita", "attività", "activity") else defaults.resolve_type(o)
            if kind in defaults.ACTIVITY_TYPES:
                kind = "activities"
            if kind is None or kind not in A.COLUMNS:
                return None, None, None, {"error": f"tipo oggetto sconosciuto: {object_type}"}
        kind = kind or A.detect_kind(header)
        if kind is None:
            return None, None, None, {"error": "non riconosco il tipo di file dall'intestazione: indica object_type (contacts, companies, deals, tickets, products, line_items, activities)", "columns": header, "rows": len(rows)}
        if kind == "users":
            return None, None, None, {"error": "il file è un elenco di utenti Brambilla (utenti.csv): gli utenti non si importano dall'assistente", "columns": header, "rows": len(rows)}
        return att, kind, A.plan_rows(store, kind, header, rows, writer_email=self.user_email), None

    def preview_attachment(self, store: Store, name=None, object_type=None, limit=25):
        att, kind, plans, err = self._attachment_plans(store, name, object_type)
        if err:
            return err
        lim = min(max(int(limit or 25), 1), 50)
        out = {"attachment": att.get("name"), "object_type": kind, "object_label": A.KIND_LABEL[kind], "summary": A.summarize(plans), "rows": [p.out() for p in plans[:lim]], "truncated": len(plans) > lim}
        if any("R3" in w for p in plans for w in p.warnings):
            out["guidance"] = "Righe con un commerciale/assegnatario che non lavora più: si importano comunque, con il campo vuoto (R3, come nella migrazione). Non è un motivo per rifiutare l'import: importa e riferisci quali righe hanno il campo vuoto."
        return out

    def import_attachment(self, store: Store, name=None, object_type=None, update_existing=None, skip_lines=None):
        att, kind, plans, err = self._attachment_plans(store, name, object_type)
        if err:
            return err
        if update_existing is None:
            update_existing = kind == "products"  # R4: same code, republished at a new price
        try:
            skip = {int(x) for x in (skip_lines or [])}
        except (TypeError, ValueError):
            return {"error": "skip_lines deve essere una lista di numeri di riga"}
        created, updated, skipped, failed = [], [], [], []
        for p in plans:
            if p.line in skip:
                skipped.append({"line": p.line, "reason": "esclusa su richiesta"})
                continue
            if p.skip:
                skipped.append({"line": p.line, "reason": p.skip})
                continue
            props = {k: v for k, v in p.properties.items() if v is not None}
            assoc = [{"object_type": a["object_type"], "id": a["id"]} for a in p.associations]
            if p.existing:
                ex = p.existing
                if not update_existing:
                    skipped.append({"line": p.line, "reason": f"esiste già: {ex['object_type']} {ex['id']} '{ex['label']}' (stesso {ex['match']})", "id": ex["id"]})
                    continue
                r = self.update_record(store, ex["object_type"], ex["id"], {k: v for k, v in props.items() if k != "id_legacy" and v != ""})
                if r.get("ok"):
                    for a in assoc:
                        self.associate(store, ex["object_type"], ex["id"], a["object_type"], a["id"])
                    updated.append({"line": p.line, "id": ex["id"], "object_type": ex["object_type"], "label": ex["label"]})
                else:
                    failed.append({"line": p.line, "error": r.get("error")})
                continue
            r = self.create_record(store, p.object_type, props, assoc)
            if r.get("ok"):
                created.append({"line": p.line, "id": r["id"], "object_type": p.object_type, "label": self._plan_label(p), "associations": [f"{a['object_type']} {a['id']} ({a['label']})" for a in p.associations], "automations": r.get("automations") or []})
            else:
                failed.append({"line": p.line, "label": self._plan_label(p), "error": r.get("error")})
        return {
            "attachment": att.get("name"), "object_type": kind, "object_label": A.KIND_LABEL[kind],
            "summary": {"rows": len(plans), "created": len(created), "updated": len(updated), "skipped": len(skipped), "failed": len(failed)},
            "created": created[:60], "updated": updated[:60], "skipped": skipped[:60], "failed": failed[:60],
            "warnings": [{"line": p.line, "warnings": p.warnings} for p in plans if p.warnings][:40],
        }

    @staticmethod
    def _plan_label(p) -> str:
        pr = p.properties
        return (pr.get("name") or pr.get("dealname") or pr.get("subject") or " ".join(x for x in (pr.get("firstname"), pr.get("lastname")) if x) or pr.get("email") or pr.get("hs_sku") or pr.get("hs_note_body") or pr.get("hs_call_body") or pr.get("hs_email_text") or pr.get("hs_meeting_body") or "")[:80]

    def _pipeline(self, store: Store, object_type: str, pipeline: str) -> dict | None:
        value = str(pipeline).strip()
        if object_type == "deals" and value.lower() == "vendite":
            value = "default"
        return store.pipeline_by_label(object_type, value) or next((p for p in store.pipelines(object_type) if p["id"] == value), None)

    def search_deals(self, store: Store, name=None, company_id=None, contact_id=None, pipeline=None, stage=None, commerciale=None, closed_from=None, closed_to=None, open_only=None, query=None, limit=15, id_legacy=None, sort_by="closedate", sort_direction="DESCENDING"):
        filters = []
        commerciale = self._user_filter(store, commerciale)
        if id_legacy:
            filters.append({"propertyName": "id_legacy", "operator": "EQ", "value": str(id_legacy).strip()})
        if company_id:
            filters.append({"propertyName": "associations.company", "operator": "IN", "values": [str(company_id)]})
        if contact_id:
            filters.append({"propertyName": "associations.contact", "operator": "IN", "values": [str(contact_id)]})
        if pipeline:
            pl = self._pipeline(store, "deals", pipeline)
            if pl is None:
                return {"error": f"pipeline sconosciuta: {pipeline}"}
            pipeline = pl["id"]
            filters.append({"propertyName": "pipeline", "operator": "EQ", "value": pipeline})
        if stage:
            sid = self._stage_id(store, "deals", stage, pipeline)
            if sid is None:
                return {"error": f"fase sconosciuta: {stage}"}
            filters.append({"propertyName": "dealstage", "operator": "EQ", "value": sid})
        if commerciale:
            filters.append({"propertyName": "commerciale", "operator": "EQ", "value": commerciale.strip().lower()})
        if closed_from:
            filters.append({"propertyName": "closedate", "operator": "GTE", "value": closed_from})
        if closed_to:
            filters.append({"propertyName": "closedate", "operator": "LTE", "value": closed_to})
        if open_only:
            filters.append({"propertyName": "hs_is_closed", "operator": "NEQ", "value": "true"})
        sort_fields = {"closedate", "amount", "dealname"}
        if sort_by not in sort_fields:
            return {"error": f"ordinamento trattative non valido: {sort_by}"}
        res = self._search(store, "deals", filters, name or query, limit, sorts=[{"propertyName": sort_by, "direction": sort_direction}])
        return {"total": res["total"], "results": [self._deal_brief(store, r) for r in res["results"]]}

    def search_tickets(self, store: Store, subject=None, company_id=None, contact_id=None, stage=None, assegnatario=None, priority=None, open_only=None, created_from=None, created_to=None, query=None, limit=15, id_legacy=None, sort_by="createdate", sort_direction="DESCENDING", include_stats=None):
        filters = []
        assegnatario = self._user_filter(store, assegnatario)
        if id_legacy:
            filters.append({"propertyName": "id_legacy", "operator": "EQ", "value": str(id_legacy).strip()})
        if company_id:
            filters.append({"propertyName": "associations.company", "operator": "IN", "values": [str(company_id)]})
        if contact_id:
            filters.append({"propertyName": "associations.contact", "operator": "IN", "values": [str(contact_id)]})
        if stage:
            sid = self._stage_id(store, "tickets", stage, None)
            if sid is None:
                return {"error": f"fase sconosciuta: {stage}"}
            filters.append({"propertyName": "hs_pipeline_stage", "operator": "EQ", "value": sid})
        if assegnatario:
            filters.append({"propertyName": "assegnatario", "operator": "EQ", "value": assegnatario.strip().lower()})
        if priority:
            filters.append({"propertyName": "hs_ticket_priority", "operator": "EQ", "value": priority.strip().upper()})
        if created_from:
            filters.append({"propertyName": "createdate", "operator": "GTE", "value": created_from})
        if created_to:
            filters.append({"propertyName": "createdate", "operator": "LTE", "value": created_to})
        if open_only:
            closed_ids = [s["id"] for p in store.pipelines("tickets") for s in p["stages"] if str(s.get("metadata", {}).get("ticketState", "")).upper() == "CLOSED"]
            if closed_ids:
                filters.append({"propertyName": "hs_pipeline_stage", "operator": "NOT_IN", "values": closed_ids})
        sort_fields = {"createdate", "priority", "subject"}
        sort_property = {"priority": "hs_ticket_priority"}.get(sort_by, sort_by)
        if sort_by not in sort_fields:
            return {"error": f"ordinamento ticket non valido: {sort_by}"}
        res = self._search(store, "tickets", filters, subject or query, limit, sorts=[{"propertyName": sort_property, "direction": sort_direction}])
        out = {"total": res["total"], "results": [self._ticket_brief(store, r) for r in res["results"]]}
        if include_stats and not priority:
            out["by_priority"] = {
                p: self._search(store, "tickets", filters + [{"propertyName": "hs_ticket_priority", "operator": "EQ", "value": p}], subject or query, 1)["total"]
                for p in ("LOW", "MEDIUM", "HIGH", "URGENT")
            }
            known = sum(out["by_priority"].values())
            out["by_priority"]["SENZA PRIORITÀ"] = max(out["total"] - known, 0)
        return out

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

    def list_deal_line_items(self, store: Store, deal_id: str, limit: int = 25, after: str | None = None):
        """Return a bounded, pageable view of a deal's line items and products."""
        deal = store.get("deals", deal_id)
        did = int(deal["id"])
        page_limit = min(max(int(limit or MAX_LIST), 1), MAX_LIST)

        params: list = [did]
        after_sql = ""
        if after not in (None, ""):
            try:
                after_id = int(str(after))
            except ValueError:
                return {"error": f"cursore di paginazione non valido: {after}"}
            after_sql = " AND a.to_id > %s"
            params.append(after_id)
        params.append(page_limit + 1)

        rows = store.conn.execute(
            f"""
            WITH page AS (
                SELECT DISTINCT a.to_id AS line_item_id
                FROM associations a
                JOIN objects line_item
                  ON line_item.id = a.to_id
                 AND line_item.object_type = 'line_items'
                 AND NOT line_item.archived
                WHERE a.from_id = %s
                  AND a.from_type = 'deals'
                  AND a.to_type = 'line_items'
                  {after_sql}
                ORDER BY a.to_id
                LIMIT %s
            )
            SELECT line_item.*,
                   product.id AS product_id,
                   product.properties AS product_properties
            FROM page
            JOIN objects line_item ON line_item.id = page.line_item_id
            LEFT JOIN LATERAL (
                SELECT p.id, p.properties
                FROM associations product_assoc
                JOIN objects p
                  ON p.id = product_assoc.to_id
                 AND p.object_type = 'products'
                 AND NOT p.archived
                WHERE product_assoc.from_id = line_item.id
                  AND product_assoc.from_type = 'line_items'
                  AND product_assoc.to_type = 'products'
                ORDER BY p.id
                LIMIT 1
            ) product ON TRUE
            ORDER BY line_item.id
            """,
            params,
        ).fetchall()

        truncated = len(rows) > page_limit
        rows = rows[:page_limit]
        results = []
        for row in rows:
            props = row["properties"]
            product_props = row["product_properties"] or {}
            product = None
            if row["product_id"] is not None:
                product = {
                    "id": str(row["product_id"]),
                    "name": product_props.get("name"),
                    "sku": product_props.get("hs_sku"),
                    "unit_price": product_props.get("price"),
                }
            results.append({
                "id": str(row["id"]),
                "id_legacy": props.get("id_legacy"),
                "name": props.get("name"),
                "sku": props.get("hs_sku"),
                "quantity": props.get("quantity"),
                "unit_price": props.get("price"),
                "discount": {
                    "percentage": props.get("hs_discount_percentage"),
                    "unit_amount": props.get("discount"),
                    "total_amount": props.get("hs_total_discount"),
                },
                "amount": props.get("amount"),
                "currency": props.get("hs_line_item_currency_code"),
                "product": product,
            })

        total = store.conn.execute(
            """
            SELECT count(DISTINCT a.to_id) AS n
            FROM associations a
            JOIN objects line_item
              ON line_item.id = a.to_id
             AND line_item.object_type = 'line_items'
             AND NOT line_item.archived
            WHERE a.from_id = %s
              AND a.from_type = 'deals'
              AND a.to_type = 'line_items'
            """,
            (did,),
        ).fetchone()["n"]
        next_page = {"after": str(rows[-1]["id"])} if truncated and rows else None
        return {
            "deal_id": str(did),
            "total": total,
            "returned": len(results),
            "limit": page_limit,
            "truncated": truncated,
            "paging": {"next": next_page},
            "results": results,
        }

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

    def deal_stats(self, store: Store, company_id=None, commerciale=None, pipeline=None, stage=None, year=None, closed_from=None, closed_to=None, open_only=None, won_only=None):
        where = ["object_type = 'deals'", "NOT archived"]
        params: list = []
        commerciale = self._user_filter(store, commerciale)
        if company_id:
            where.append("id IN (SELECT from_id FROM associations WHERE to_id = %s AND to_type = 'companies')")
            params.append(int(company_id))
        if commerciale:
            where.append("properties->>'commerciale' = %s")
            params.append(commerciale.strip().lower())
        if pipeline:
            pl = self._pipeline(store, "deals", pipeline)
            if pl is None:
                return {"error": f"pipeline sconosciuta: {pipeline}"}
            pipeline = pl["id"]
            where.append("properties->>'pipeline' = %s")
            params.append(pipeline)
        if stage:
            sid = self._stage_id(store, "deals", stage, pipeline)
            if sid is None:
                return {"error": f"fase sconosciuta: {stage}"}
            where.append("properties->>'dealstage' = %s")
            params.append(sid)
        if year:
            where.append("properties->>'closedate' >= %s AND properties->>'closedate' < %s")
            params.extend([f"{int(year)}-01-01", f"{int(year) + 1}-01-01"])
        if closed_from:
            where.append("properties->>'closedate' >= %s")
            params.append(closed_from)
        if closed_to:
            where.append("properties->>'closedate' <= %s")
            params.append(closed_to)
        if open_only:
            where.append("COALESCE(properties->>'hs_is_closed', 'false') <> 'true'")
        if won_only:
            where.append("properties->>'hs_is_closed_won' = 'true'")
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

    def my_customers(self, store: Store, user_email: str | None = None, limit=25, classe_cliente=None, sort_by="name", sort_direction="ASCENDING"):
        email = (self._user_filter(store, user_email) or self.user_email or "").strip().lower()
        if not email:
            return {"error": "utente non indicato"}
        sort_fields = {
            "name": "c.properties->>'name'",
            "fatturato_2025": "NULLIF(c.properties->>'fatturato_2025','')::numeric",
            "deals": "deals",
            "tickets": "tickets",
        }
        if sort_by not in sort_fields:
            return {"error": f"ordinamento clienti non valido: {sort_by}"}
        direction = "DESC" if str(sort_direction).upper().startswith("DESC") else "ASC"
        class_sql = ""
        class_params: list = []
        if classe_cliente:
            class_sql = " AND c.properties->>'classe_cliente' = %s"
            class_params.append(str(classe_cliente).strip().upper())
        rows = store.conn.execute(
            """SELECT c.id, c.properties->>'name' AS name, c.properties->>'city' AS city, c.properties->>'classe_cliente' AS cls, c.properties->>'fatturato_2025' AS f,
                      count(DISTINCT d.id) FILTER (WHERE d.object_type = 'deals') AS deals, count(DISTINCT d.id) FILTER (WHERE d.object_type = 'tickets') AS tickets
               FROM objects d JOIN associations a ON a.from_id = d.id AND a.to_type = 'companies' JOIN objects c ON c.id = a.to_id AND NOT c.archived
               WHERE NOT d.archived AND ((d.object_type = 'deals' AND d.properties->>'commerciale' = %s) OR (d.object_type = 'tickets' AND d.properties->>'assegnatario' = %s))
               """ + class_sql + f" GROUP BY c.id ORDER BY {sort_fields[sort_by]} {direction} NULLS LAST, c.id LIMIT %s",
            [email, email] + class_params + [min(int(limit or 25), 100)],
        ).fetchall()
        total = store.conn.execute(
            """SELECT count(DISTINCT a.to_id) AS n FROM objects d JOIN associations a ON a.from_id = d.id AND a.to_type = 'companies' JOIN objects c ON c.id = a.to_id AND NOT c.archived
               WHERE NOT d.archived AND ((d.object_type = 'deals' AND d.properties->>'commerciale' = %s) OR (d.object_type = 'tickets' AND d.properties->>'assegnatario' = %s))""" + class_sql,
            [email, email] + class_params,
        ).fetchone()["n"]
        return {"user": email, "total": total, "results": [{"id": str(r["id"]), "name": r["name"], "city": r["city"], "classe_cliente": r["cls"], "fatturato_2025": r["f"], "deals": r["deals"], "tickets": r["tickets"]} for r in rows]}

    def company_stats(self, store: Store, classe_cliente=None, user_email=None, mine=None):
        """Exact company counts and stored R8 revenue, optionally by customer class and follower."""
        where = ["c.object_type = 'companies'", "NOT c.archived"]
        params: list = []
        if classe_cliente:
            where.append("c.properties->>'classe_cliente' = %s")
            params.append(str(classe_cliente).strip().upper())
        email = None
        if user_email or mine:
            email = (self._user_filter(store, user_email) or self.user_email or "").strip().lower() if user_email else (self.user_email or "").strip().lower()
            if not email:
                return {"error": "utente non indicato"}
            where.append("""c.id IN (SELECT a.to_id FROM objects d JOIN associations a ON a.from_id = d.id AND a.to_type = 'companies'
                WHERE NOT d.archived AND ((d.object_type = 'deals' AND d.properties->>'commerciale' = %s) OR (d.object_type = 'tickets' AND d.properties->>'assegnatario' = %s)))""")
            params.extend([email, email])
        rows = store.conn.execute(
            f"""SELECT COALESCE(c.properties->>'classe_cliente', '') AS class, count(*) AS n,
                       COALESCE(sum(COALESCE(NULLIF(c.properties->>'fatturato_2025','')::numeric, 0)), 0) AS revenue
                  FROM objects c WHERE {' AND '.join(where)} GROUP BY 1 ORDER BY 1""",
            params,
        ).fetchall()
        total = sum(r["n"] for r in rows)
        revenue = sum((r["revenue"] for r in rows), Decimal(0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        out = {
            "count": total,
            "total_fatturato_2025_eur": str(revenue),
            "total_fatturato_2025_eur_it": _it_money(revenue),
            "by_class": {(r["class"] or "SENZA CLASSE"): {"count": r["n"], "fatturato_2025_eur": str(r["revenue"].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))} for r in rows},
        }
        if email:
            out["user"] = email
        return out

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

    def dormant_list(self, store: Store, limit=25, user_email=None, mine=None):
        row = store.conn.execute("SELECT list_id, definition FROM lists WHERE lower(definition->>'name') = 'clienti dormienti' ORDER BY list_id DESC LIMIT 1").fetchone()
        if not row:
            return {"error": "la lista Clienti dormienti non esiste"}
        lid = row["list_id"]
        email = None
        if user_email or mine:
            email = (self._user_filter(store, user_email) or self.user_email or "").strip().lower() if user_email else (self.user_email or "").strip().lower()
            if not email:
                return {"error": "utente non indicato"}
        won = [s["id"] for p in store.pipelines("deals") for s in p["stages"]
               if str((s.get("metadata") or {}).get("isClosed")).lower() == "true" and float((s.get("metadata") or {}).get("probability") or 0) >= 1.0]
        mine_sql = ""
        params: list = [lid]
        if email:
            mine_sql = """ AND m.record_id IN (SELECT a.to_id FROM objects d JOIN associations a ON a.from_id = d.id AND a.to_type = 'companies'
                WHERE NOT d.archived AND ((d.object_type = 'deals' AND d.properties->>'commerciale' = %s) OR (d.object_type = 'tickets' AND d.properties->>'assegnatario' = %s)))"""
            params += [email, email]
        total = store.conn.execute("SELECT count(*) AS n FROM list_memberships m WHERE m.list_id = %s" + mine_sql, params).fetchone()["n"]
        rows = store.conn.execute(
            "SELECT o.* FROM list_memberships m JOIN objects o ON o.id = m.record_id WHERE m.list_id = %s" + mine_sql + " ORDER BY o.properties->>'name' LIMIT %s",
            params + [min(int(limit or 25), 100)]).fetchall()
        results = []
        for r in rows:
            item = self._company_brief(store, r)
            last = store.conn.execute(
                """SELECT d.id, d.properties->>'dealname' AS name, d.properties->>'amount' AS amount, d.properties->>'deal_currency_code' AS cur,
                          d.properties->>'closedate' AS closedate, d.properties->>'commerciale' AS commerciale
                   FROM associations a JOIN objects d ON d.id = a.to_id AND d.object_type = 'deals' AND NOT d.archived
                   WHERE a.from_id = %s AND a.to_type = 'deals' AND d.properties->>'dealstage' = ANY(%s)
                   ORDER BY d.properties->>'closedate' DESC NULLS LAST LIMIT 1""", (r["id"], won)).fetchone() if won else None
            if last:
                item["ultima_trattativa_vinta"] = {"id": str(last["id"]), "dealname": last["name"], "amount": last["amount"], "currency": last["cur"] or "EUR",
                                                   "closedate": (last["closedate"] or "")[:10], "commerciale": last["commerciale"]}
            results.append(item)
        out = {"list_id": str(lid), "total": total, "results": results}
        if email:
            out["user"] = email
        return out

    # ---------------------------------------------------------- write tools
    def create_record(self, store: Store, object_type: str, properties: dict, associations: list | None = None):
        ot = defaults.resolve_type(object_type)
        if ot is None:
            return {"error": f"tipo oggetto sconosciuto: {object_type}"}
        props = dict(properties or {})
        if ot == "deals":
            if props.get("pipeline"):
                pl = self._pipeline(store, "deals", props["pipeline"])
                if pl is None:
                    return {"error": f"pipeline sconosciuta: {props['pipeline']}"}
                props["pipeline"] = pl["id"]
            props.setdefault("commerciale", self.user_email)
            if props.get("dealstage") and not store.stage_lookup("deals", props["dealstage"]):
                sid = self._stage_id(store, "deals", props["dealstage"], props.get("pipeline"))
                if sid:
                    props["dealstage"] = sid
        if ot == "tickets":
            props.setdefault("assegnatario", self.user_email)
            if not props.get("hs_pipeline"):
                from .. import rules
                pl = rules.ensure_ticket_pipeline(store)
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
        bad = self._prepare_props(store, ot, props, associations)
        if bad:
            return bad
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
        extra_notes = self._after_line_item(store, int(rec["id"])) if ot == "line_items" else []
        return {"ok": True, "object_type": ot, "id": rec["id"], "properties": {k: v for k, v in rec["properties"].items() if k in props or k in ("dealstage", "pipeline", "hs_pipeline_stage", "closedate", "amount")}, "automations": self._automation_note(store, ot, int(rec["id"])) + extra_notes}

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
        if ot == "deals" and props.get("pipeline"):
            pl = self._pipeline(store, "deals", props["pipeline"])
            if pl is None:
                return {"error": f"pipeline sconosciuta: {props['pipeline']}"}
            props["pipeline"] = pl["id"]
        if ot == "deals" and props.get("dealstage") and not store.stage_lookup("deals", props["dealstage"]):
            cur = store.get("deals", id)["properties"]
            sid = self._stage_id(store, "deals", props["dealstage"], props.get("pipeline") or cur.get("pipeline"))
            if sid:
                props["dealstage"] = sid
        if ot == "tickets" and props.get("hs_pipeline_stage") and not store.stage_lookup("tickets", props["hs_pipeline_stage"]):
            sid = self._stage_id(store, "tickets", props["hs_pipeline_stage"], None)
            if sid:
                props["hs_pipeline_stage"] = sid
        bad = self._prepare_props(store, ot, props, None)
        if bad:
            return bad
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

    def archive_record(self, store: Store, object_type: str, id: str, confirmed: bool = False):
        ot = defaults.resolve_type(object_type)
        if ot is None:
            return {"error": f"tipo oggetto sconosciuto: {object_type}"}
        if ot == "companies" and not confirmed:
            try:
                cid = int(str(id).strip())
            except ValueError:
                cid = None
            if cid is not None:
                n = store.conn.execute(
                    "SELECT count(DISTINCT o.id) AS n FROM associations a JOIN objects o ON o.id = a.to_id AND o.object_type = 'deals' AND NOT o.archived WHERE a.from_id = %s AND a.to_type = 'deals' AND COALESCE(o.properties->>'hs_is_closed', 'false') <> 'true'",
                    (cid,),
                ).fetchone()["n"]
                if n:
                    return {"error": f"l'azienda ha {n} trattative aperte: archiviarla le lascia senza cliente. Non archiviata. Chiedi conferma all'utente; solo se conferma esplicitamente richiama archive_record con confirmed=true.", "status": 409, "requires_confirmation": True, "open_deals": n}
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
        records = records or []
        if not isinstance(records, list):
            return {"error": "records deve essere una lista", "status": 400}
        if len(records) > 200:
            return {"error": "massimo 200 record per chiamata; suddividi l'elenco in più chiamate", "status": 400}
        results = []
        for rec in records:
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
    _schema("search_companies", "Cerca aziende per nome (anche parziale), dominio, partita IVA, città o classe. Restituisce id, nome, città, dominio, partita IVA, fatturato 2025 e classe. Per classifiche usa sort_by='fatturato_2025' e sort_direction='DESCENDING': l'ordinamento avviene prima del limite.", {"name": S("nome o parte del nome"), "domain": S("dominio del sito"), "partita_iva": S("partita IVA 11 cifre"), "city": S("città"), "classe_cliente": S("A, B o C"), "sort_by": S("name, city, fatturato_2025 o classe_cliente"), "sort_direction": S("ASCENDING o DESCENDING"), "limit": I("max risultati (default 10, max 25)")}),
    _schema("search_contacts", "Cerca contatti per nome/cognome, email o azienda (company_id).", {"name": S("nome e/o cognome"), "email": S("email esatta"), "company_id": S("id azienda"), "limit": I("max risultati")}),
    _schema("search_deals", "Cerca trattative per titolo, azienda, contatto, pipeline (Vendite/Rinnovi), fase, commerciale, intervallo di closedate, solo aperte. Per classifiche usa sort_by='amount' e sort_direction='DESCENDING': l'ordinamento avviene prima del limite.", {"name": S("titolo o parte"), "company_id": S("id azienda"), "contact_id": S("id contatto"), "pipeline": S("Sales Pipeline (id 'default', le Vendite) o Rinnovi"), "stage": S("etichetta fase, es. Vinta, Persa, Contratto, Rinnovato"), "commerciale": S("email del commerciale"), "closed_from": S("YYYY-MM-DD"), "closed_to": S("YYYY-MM-DD"), "open_only": B("solo trattative non chiuse"), "sort_by": S("closedate, amount o dealname"), "sort_direction": S("ASCENDING o DESCENDING"), "limit": I("max risultati (max 25)")}),
    _schema("search_tickets", "Cerca ticket per oggetto, azienda, contatto, fase, assegnatario, priorità, intervallo di apertura e stato aperto. Per conteggi esatti per priorità usa include_stats=true. Per il più vecchio usa sort_by='createdate', sort_direction='ASCENDING', limit=1.", {"subject": S("oggetto o parte"), "company_id": S("id azienda"), "contact_id": S("id contatto"), "stage": S("Aperto, In lavorazione, In attesa del cliente, Chiuso"), "assegnatario": S("email"), "priority": S("LOW, MEDIUM, HIGH, URGENT"), "open_only": B("solo non chiusi"), "created_from": S("data apertura minima YYYY-MM-DD"), "created_to": S("data apertura massima YYYY-MM-DD"), "sort_by": S("createdate, priority o subject"), "sort_direction": S("ASCENDING o DESCENDING"), "include_stats": B("aggiunge conteggi esatti by_priority"), "limit": I("max risultati (max 25)")}),
    _schema("get_record", "Legge un record completo (proprietà e associazioni) dato tipo e id.", {"object_type": S("companies, contacts, deals, tickets, products, line_items, notes, calls, emails, meetings, tasks"), "id": S("id del record")}, ["object_type", "id"]),
    _schema("company_overview", "Scheda completa di un'azienda: dati, fatturato 2025 e classe, contatti, trattative, ticket, ultime attività. Usala per domande su un cliente.", {"company_id": S("id azienda")}, ["company_id"]),
    _schema("list_deal_line_items", "Elenca le righe di una trattativa con id corrente e legacy, nome, SKU, quantità, prezzo unitario, sconto, importo e prodotto associato. Restituisce totale, troncamento e cursore per la pagina successiva.", {"deal_id": S("id trattativa"), "limit": {"type": "integer", "minimum": 1, "maximum": 25, "description": "max risultati (default 25)"}, "after": S("cursore restituito da paging.next.after")}, ["deal_id"]),
    _schema("list_activities", "Elenca note, chiamate, email, riunioni e task di un contatto, di una trattativa o di un'azienda, opzionalmente di un anno.", {"contact_id": S("id contatto"), "deal_id": S("id trattativa"), "company_id": S("id azienda"), "year": I("anno"), "limit": I("max risultati")}),
    _schema("revenue", "Fatturato di un'azienda in un anno con la regola R8 (trattative vinte/rinnovate chiuse nell'anno, storni sottratti, USD x0.92, GBP x1.17). Calcolo deterministico.", {"company_id": S("id azienda"), "year": I("anno, default 2025")}, ["company_id"]),
    _schema("deal_stats", "Conteggi e totali in euro delle trattative, per fase, filtrabili per azienda, commerciale, pipeline, fase, anno o intervallo di chiusura, solo aperte o solo vinte. Usalo per totali esatti senza sommare a mano elenchi troncati.", {"company_id": S("id azienda"), "commerciale": S("email commerciale"), "pipeline": S("Vendite o Rinnovi"), "stage": S("fase"), "year": I("anno di closedate"), "closed_from": S("YYYY-MM-DD"), "closed_to": S("YYYY-MM-DD"), "open_only": B("solo aperte"), "won_only": B("solo vinte/rinnovate")}),
    _schema("my_customers", "Le aziende seguite da un utente: quelle con trattative di cui è commerciale o ticket di cui è assegnatario. Default: chi scrive. Può filtrare la classe e ordinare per fatturato prima del limite; total resta esatto.", {"user_email": S("email o nome utente (default chi scrive)"), "classe_cliente": S("A, B o C"), "sort_by": S("name, fatturato_2025, deals o tickets"), "sort_direction": S("ASCENDING o DESCENDING"), "limit": I("max risultati (max 100)")}),
    _schema("company_stats", "Conteggio e fatturato 2025 esatti delle aziende, complessivi e per classe, senza elenchi troncati né somme manuali. Filtra per classe; per 'i miei clienti' usa mine=true, per un collega user_email.", {"classe_cliente": S("A, B o C"), "mine": B("solo clienti seguiti da chi scrive"), "user_email": S("email o nome del collega")}),
    _schema("list_users", "Utenti Brambilla (commerciali) attivi con email, ruolo e responsabile. Usalo per risolvere nomi di colleghi in email.", {"query": S("nome o parte"), "active_only": B("default true")}),
    _schema("pipelines", "Pipeline e fasi (id ed etichette) di trattative e ticket.", {}),
    _schema("dormant_list", "Membri della lista Clienti dormienti, ciascuno con la sua ultima trattativa vinta. Per 'i miei clienti dormienti' usa mine=true (clienti seguiti da chi scrive: sue trattative o suoi ticket) oppure user_email per un collega. total = numero esatto di membri del filtro.", {"limit": I("max risultati (max 100)"), "mine": {"type": "boolean", "description": "solo i clienti di chi scrive"}, "user_email": S("email o nome del collega")}),
    _schema("create_record", "Crea un record. Per contacts: firstname, lastname, email, phone, lifecyclestage. Per companies: name, domain, city, state, partita_iva. Per deals: dealname, amount, deal_currency_code, pipeline, dealstage (etichetta o id), closedate, commerciale. Per tickets: subject, content, hs_pipeline_stage, hs_ticket_priority, assegnatario. Per notes/calls/emails/meetings: hs_note_body/hs_call_body/hs_email_text/hs_meeting_body, hs_timestamp. Per tasks: hs_task_subject, hs_timestamp, hs_task_status. associations: [{object_type, id}].", {"object_type": S("tipo"), "properties": {"type": "object", "description": "proprietà"}, "associations": {"type": "array", "items": {"type": "object", "properties": {"object_type": S("tipo"), "id": S("id")}}, "description": "record da associare"}}, ["object_type", "properties"]),
    _schema("update_record", "Aggiorna proprietà di un record esistente (es. dealstage 'Vinta' per segnare vinta, amount, closedate, hs_pipeline_stage per i ticket).", {"object_type": S("tipo"), "id": S("id"), "properties": {"type": "object", "description": "proprietà da modificare"}}, ["object_type", "id", "properties"]),
    _schema("associate", "Associa due record (es. contatto ad azienda, trattativa a contatto).", {"from_type": S("tipo"), "from_id": S("id"), "to_type": S("tipo"), "to_id": S("id")}, ["from_type", "from_id", "to_type", "to_id"]),
    _schema("dissociate", "Rimuove un'associazione tra due record.", {"from_type": S("tipo"), "from_id": S("id"), "to_type": S("tipo"), "to_id": S("id")}, ["from_type", "from_id", "to_type", "to_id"]),
    _schema("archive_record", "Archivia (elimina) un record. Un'azienda con trattative aperte non si archivia senza conferma esplicita dell'utente (confirmed=true solo dopo la sua conferma).", {"object_type": S("tipo"), "id": S("id"), "confirmed": B("true solo se l'utente ha confermato esplicitamente dopo averlo avvisato")}, ["object_type", "id"]),
    _schema("create_records_bulk", "Crea più record dello stesso tipo in un colpo (es. contatti da un CSV allegato). Ogni elemento: {properties: {...}, associations: [...]}.", {"object_type": S("tipo"), "records": {"type": "array", "items": {"type": "object"}, "description": "elenco record"}}, ["object_type", "records"]),
    _schema("find_by_legacy_id", "Trova un record dal suo codice Sinergia (id_legacy: es. 'ticket 595833', 'azienda 264566', 'trattativa 28595675'). Cerca in tutti i tipi se object_type manca.", {"id_legacy": S("codice Sinergia"), "object_type": S("companies, contacts, deals, tickets, line_items, notes, calls, emails, meetings (opzionale)")}, ["id_legacy"]),
    _schema("search_products", "Cerca articoli del listino per codice (hs_sku, es. BF-12288 o 12288) o descrizione. Restituisce id, codice, descrizione e prezzo in euro.", {"sku": S("codice articolo"), "name": S("descrizione o parte"), "limit": I("max risultati")}),
    _schema("preview_attachment", "Legge un CSV allegato (formato Sinergia, separatore ';') SENZA scrivere: riconosce il tipo (contatti, aziende, trattative, ticket, listino, righe d'offerta, attività), mappa ogni riga nelle proprietà del CRM, risolve id_azienda/id_contatto/id_opportunita/codice_articolo/id_utente nei record del CRM e segnala le righe che esistono già. Usalo per rispondere a domande sull'allegato o per controllare prima di importare.", {"name": S("nome dell'allegato (default: l'ultimo)"), "object_type": S("tipo, solo se l'intestazione non basta"), "limit": I("righe mostrate (default 25)")}),
    _schema("import_attachment", "Importa nel CRM le righe di un CSV allegato (stessa logica di preview_attachment), creando i record con le associazioni risolte. Le righe già esistenti (stessa email, partita IVA, codice Sinergia o codice articolo) non vengono duplicate: saltate, oppure aggiornate con update_existing=true (default true solo per il listino, R4). Usalo solo quando l'utente chiede di importare/aggiungere i dati dell'allegato. Risponde con creati, aggiornati, saltati e falliti riga per riga.", {"name": S("nome dell'allegato (default: l'ultimo)"), "object_type": S("tipo, solo se l'intestazione non basta"), "update_existing": B("aggiorna i record già esistenti invece di saltarli"), "skip_lines": {"type": "array", "items": {"type": "integer"}, "description": "numeri di riga da non importare"}}),
]
for _s in TOOL_SCHEMAS:
    if _s["function"]["name"] in ("search_companies", "search_contacts", "search_deals", "search_tickets"):
        _s["function"]["parameters"]["properties"]["id_legacy"] = S("codice Sinergia del record (id_legacy)")
    if _s["function"]["name"] == "search_deals":
        _s["function"]["parameters"]["properties"]["commerciale"] = S("email o nome del commerciale")
    if _s["function"]["name"] == "search_tickets":
        _s["function"]["parameters"]["properties"]["assegnatario"] = S("email o nome dell'assegnatario")


def run_tool(ctx: ToolContext, name: str, args: dict, observer: EvidenceTrace | None = None) -> dict:
    call_id = observer.begin(name, args) if observer else None
    fn = getattr(ctx, name, None)
    if fn is None or name.startswith("_"):
        if observer:
            observer.failed(call_id)
        return {"error": f"strumento sconosciuto: {name}"}
    with db.connection() as conn:
        store = Store(conn, ctx.now)
        write_start = len(ctx.writes)
        try:
            out = fn(store, **(args or {}))
            if observer:
                observer.returned(call_id, out)
            conn.commit()
            if observer:
                observer.transaction_finished(call_id, "committed")
            return out
        except ApiError as e:
            del ctx.writes[write_start:]
            outcome = "rolled_back"
            try:
                conn.rollback()
            except Exception:
                outcome = "unknown"
            if observer:
                observer.failed(call_id, outcome=outcome)
            return {"error": e.message, "status": e.status}
        except TypeError as e:
            del ctx.writes[write_start:]
            outcome = "rolled_back"
            try:
                conn.rollback()
            except Exception:
                outcome = "unknown"
            if observer:
                observer.failed(call_id, outcome=outcome)
            return {"error": f"argomenti non validi: {e}"}
        except Exception as e:
            del ctx.writes[write_start:]
            outcome = "rolled_back"
            try:
                conn.rollback()
            except Exception:
                outcome = "unknown"
            if observer:
                observer.failed(call_id, outcome=outcome)
            return {"error": f"errore interno: {type(e).__name__}: {str(e)[:200]}"}

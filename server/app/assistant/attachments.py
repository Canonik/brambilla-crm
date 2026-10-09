"""CSV attachments in the Sinergia export format: detect the file kind, map every row to CRM
properties with the same normalisers the migration uses, and resolve Sinergia references
(id_azienda, id_contatto, id_opportunita, codice_articolo, id_utente) to CRM records.

Nothing here writes: the tool layer decides what to create from a plan."""
from __future__ import annotations

import csv
import io
import re

from .. import defaults, rules
from ..migration import parse as P
from ..util import iso

ACTIVITY_BODY = {"notes": "hs_note_body", "calls": "hs_call_body", "emails": "hs_email_text", "meetings": "hs_meeting_body"}

COLUMNS: dict[str, list[str]] = {
    "companies": ["id_azienda", "ragione_sociale", "sito_web", "note", "citta", "provincia", "cancellato", "ultima_modifica"],
    "contacts": ["id_contatto", "nome", "cognome", "email", "telefono", "id_azienda", "tipo", "cancellato", "ultima_modifica"],
    "deals": ["id_opportunita", "titolo", "id_azienda", "contatti", "importo", "valuta", "pipeline", "fase", "data_chiusura", "id_commerciale", "cancellato", "ultima_modifica"],
    "line_items": ["id_riga", "id_opportunita", "codice_articolo", "descrizione", "quantita", "prezzo_unitario", "sconto"],
    "products": ["codice_articolo", "descrizione", "unita", "prezzo_listino", "cancellato", "ultima_modifica"],
    "tickets": ["id_ticket", "oggetto", "descrizione", "stato", "priorita", "id_contatto", "id_azienda", "aperto_il", "chiuso_il", "id_utente", "cancellato", "ultima_modifica"],
    "activities": ["id_attivita", "tipo", "data", "testo", "id_contatto", "id_opportunita", "id_utente", "cancellato"],
    "users": ["id_utente", "nome", "cognome", "email", "ruolo", "responsabile", "attivo"],
}
# columns that only one kind of file has: they break ties (contacts vs users, products vs line items)
DISTINCTIVE: dict[str, set[str]] = {
    "companies": {"ragione_sociale", "sito_web", "citta", "provincia"},
    "contacts": {"id_contatto", "cognome", "telefono", "tipo"},
    "deals": {"id_opportunita", "titolo", "importo", "fase", "data_chiusura", "id_commerciale"},
    "line_items": {"id_riga", "quantita", "prezzo_unitario", "sconto"},
    "products": {"prezzo_listino", "unita"},
    "tickets": {"id_ticket", "oggetto", "stato", "priorita", "aperto_il", "chiuso_il"},
    "activities": {"id_attivita", "testo", "data"},
    "users": {"ruolo", "responsabile", "attivo"},
}
# HubSpot-style headers are accepted too (a colleague may export from the new CRM)
HUBSPOT_HINTS = {"contacts": {"firstname", "lastname"}, "companies": {"domain", "partita_iva"}, "deals": {"dealname", "dealstage"}, "tickets": {"subject", "hs_pipeline_stage"}, "products": {"hs_sku"}, "line_items": {"hs_discount_percentage"}}

KIND_LABEL = {"companies": "aziende", "contacts": "contatti", "deals": "trattative", "line_items": "righe d'offerta", "products": "listino", "tickets": "ticket", "activities": "attività", "users": "utenti"}


def _header_key(k: str | None) -> str:
    k = (k or "").strip().strip('"').strip().lower()
    return k.lstrip("﻿")


def read_csv(text: str) -> tuple[list[str], list[dict]]:
    """Header (lower-cased) and rows as dicts. Separator is `;` as in Sinergia, `,` tolerated."""
    if not isinstance(text, str):
        text = str(text)
    text = P.fix_text(text)
    if text.startswith("﻿"):
        text = text[1:]
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    if not text.strip():
        return [], []
    sample = text[:4096]
    delimiter = ";" if sample.count(";") >= sample.count(",") else ","
    if sample.count(";") == 0 and sample.count(",") == 0 and sample.count("\t") > 0:
        delimiter = "\t"
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    rows = list(reader)
    if not rows:
        return [], []
    header = [_header_key(h) for h in rows[0]]
    out = []
    for i, raw in enumerate(rows[1:], start=2):
        if not any((c or "").strip() for c in raw):
            continue
        d = {h: (raw[j] if j < len(raw) else "") for j, h in enumerate(header) if h}
        d["_line"] = i
        out.append(d)
    return [h for h in header if h], out


def detect_kind(header: list[str]) -> str | None:
    hs = set(header)
    best, best_score = None, 0
    for kind, cols in COLUMNS.items():
        score = sum(1 for c in cols if c in hs) + sum(1 for c in DISTINCTIVE[kind] if c in hs)
        if score > best_score:
            best, best_score = kind, score
        elif score == best_score and score > 0:
            best = None if best != kind else best
    if best is not None and best_score >= 2:
        return best
    for kind, hints in HUBSPOT_HINTS.items():
        if hints & hs:
            return kind
    return None


def _get(row: dict, *names: str) -> str:
    for n in names:
        v = row.get(n)
        if v is not None and str(v).strip() != "":
            return str(v)
    return ""


class Resolver:
    """Finds CRM records for Sinergia references. Read-only, cached per plan."""

    def __init__(self, store, users: P.Users | None = None):
        self.store = store
        self.conn = store.conn
        self.users = users or load_users(store.conn)
        self._cache: dict = {}

    def by_legacy(self, object_type: str, legacy_id: str | None) -> dict | None:
        lid = P.clean(legacy_id)
        if not lid:
            return None
        key = ("legacy", object_type, lid)
        if key not in self._cache:
            row = self.conn.execute(
                "SELECT id, properties FROM objects WHERE object_type = %s AND NOT archived AND properties->>'id_legacy' = %s ORDER BY id LIMIT 1",
                (object_type, lid),
            ).fetchone()
            self._cache[key] = dict(row) if row else None
        return self._cache[key]

    def by_prop(self, object_type: str, prop: str, value: str | None) -> dict | None:
        v = (value or "").strip()
        if not v:
            return None
        key = ("prop", object_type, prop, v.lower())
        if key not in self._cache:
            row = self.conn.execute(
                "SELECT id, properties FROM objects WHERE object_type = %s AND NOT archived AND lower(properties->>%s) = lower(%s) ORDER BY id LIMIT 1",
                (object_type, prop, v),
            ).fetchone()
            self._cache[key] = dict(row) if row else None
        return self._cache[key]

    def company_by_name(self, name: str | None) -> tuple[dict | None, int]:
        n = P.clean(name)
        if not n:
            return None, 0
        rows = self.conn.execute(
            "SELECT id, properties FROM objects WHERE object_type = 'companies' AND NOT archived AND lower(properties->>'name') = lower(%s) ORDER BY id LIMIT 3",
            (n,),
        ).fetchall()
        if len(rows) == 1:
            return dict(rows[0]), 1
        return None, len(rows)

    def product_by_code(self, code: str | None) -> dict | None:
        sku = P.product_code(code)
        if not sku:
            return None
        return self.by_prop("products", "hs_sku", sku)

    def user(self, raw: str | None) -> dict | None:
        return self.users.resolve(raw)


def load_users(conn) -> P.Users:
    rows = conn.execute("SELECT id, firstname, lastname, email, role, manager_id, active FROM crm_users").fetchall()
    return P.Users([
        {"id_utente": r["id"], "nome": r["firstname"], "cognome": r["lastname"], "email": r["email"], "ruolo": r["role"], "responsabile": r["manager_id"], "attivo": "s" if r["active"] else "n"}
        for r in rows
    ])


def _label(object_type: str, rec: dict) -> str:
    p = rec.get("properties") or {}
    if object_type == "companies":
        return p.get("name") or ""
    if object_type == "contacts":
        return (" ".join(x for x in (p.get("firstname"), p.get("lastname")) if x) or p.get("email") or "")
    if object_type == "deals":
        return p.get("dealname") or ""
    if object_type == "products":
        return f"{p.get('hs_sku') or ''} {p.get('name') or ''}".strip()
    if object_type == "tickets":
        return p.get("subject") or ""
    return ""


class RowPlan:
    __slots__ = ("line", "object_type", "properties", "associations", "warnings", "existing", "skip", "source")

    def __init__(self, line: int, object_type: str):
        self.line = line
        self.object_type = object_type
        self.properties: dict = {}
        self.associations: list[dict] = []
        self.warnings: list[str] = []
        self.existing: dict | None = None
        self.skip: str | None = None
        self.source: dict = {}

    def assoc(self, object_type: str, rec: dict | None, via: str, raw: str | None) -> None:
        raw = P.clean(raw)
        if not raw:
            return
        if rec is None:
            self.warnings.append(f"{via}={raw}: nessun record nel CRM (riferimento ignorato)")
            return
        if any(a["object_type"] == object_type and a["id"] == str(rec["id"]) for a in self.associations):
            return
        self.associations.append({"object_type": object_type, "id": str(rec["id"]), "label": _label(object_type, rec), "via": f"{via}={raw}"})

    def found(self, object_type: str, rec: dict | None, match: str) -> None:
        if rec is not None and self.existing is None:
            self.existing = {"object_type": object_type, "id": str(rec["id"]), "label": _label(object_type, rec), "match": match}

    def out(self) -> dict:
        d = {"line": self.line, "properties": {k: v for k, v in self.properties.items() if v not in (None, "")}}
        if self.associations:
            d["associations"] = self.associations
        if self.existing:
            d["existing"] = self.existing
        if self.skip:
            d["skip"] = self.skip
        if self.warnings:
            d["warnings"] = self.warnings
        return d


def plan_rows(store, kind: str, header: list[str], rows: list[dict], *, writer_email: str | None, resolver: Resolver | None = None) -> list[RowPlan]:
    """One RowPlan per CSV row: CRM properties, resolved associations, existing-record match."""
    r = resolver or Resolver(store)
    sinergia = any(c in COLUMNS.get(kind, []) for c in header)
    out = []
    for row in rows:
        rp = RowPlan(row.get("_line", 0), kind)
        if P.is_deleted(row.get("cancellato")):
            rp.skip = "cancellato in Sinergia"
            out.append(rp)
            continue
        if sinergia:
            _map_sinergia(store, kind, row, rp, r, writer_email)
        _passthrough(store, kind, row, rp)
        out.append(rp)
    return out


def _passthrough(store, kind: str, row: dict, rp: RowPlan) -> None:
    """Columns named like CRM properties are taken as they are (HubSpot-style CSVs)."""
    ot = kind if kind != "activities" else rp.object_type
    if ot not in defaults.OBJECT_TYPES:
        return
    defs = store.prop_defs(ot)
    for k, v in row.items():
        if k.startswith("_") or k in rp.properties or k not in defs or k in defaults.READ_ONLY_PROPERTIES:
            continue
        if k in COLUMNS.get(kind, []):
            continue
        sv = P.clean(v)
        if sv:
            rp.properties[k] = sv


def _map_sinergia(store, kind: str, row: dict, rp: RowPlan, r: Resolver, writer_email: str | None) -> None:
    if kind == "contacts":
        emails, phone_like = P.parse_emails(_get(row, "email"))
        rp.properties = {
            "firstname": P.clean(_get(row, "nome")),
            "lastname": P.clean(_get(row, "cognome")),
            "email": emails[0] if emails else None,
            "phone": P.clean(_get(row, "telefono")) or (phone_like or None),
            "id_legacy": P.clean(_get(row, "id_contatto")) or None,
        }
        if len(emails) > 1:
            rp.properties["hs_additional_emails"] = ";".join(emails[1:])
        tipo = P.clean(_get(row, "tipo"))
        if tipo:
            ls = P.lifecycle_stage(tipo)
            if ls:
                rp.properties["lifecyclestage"] = ls
            else:
                rp.warnings.append(f"tipo '{tipo}' non riconosciuto (lead/prospect/cliente/ex cliente)")
        raw_email = _get(row, "email")
        if raw_email.strip() and not emails and not phone_like:
            rp.warnings.append(f"email '{raw_email.strip()}' non valida: contatto senza email")
        rp.found("contacts", r.by_legacy("contacts", _get(row, "id_contatto")), "id_legacy")
        if emails:
            rp.found("contacts", r.by_prop("contacts", "email", emails[0]), "email")
        comp = r.by_legacy("companies", _get(row, "id_azienda"))
        rp.assoc("companies", comp, "id_azienda", _get(row, "id_azienda"))
        if comp is None and not _get(row, "id_azienda"):
            cname = _get(row, "azienda", "ragione_sociale", "company")
            if cname:
                c, n = r.company_by_name(cname)
                if c:
                    rp.assoc("companies", c, "azienda", cname)
                elif n > 1:
                    rp.warnings.append(f"azienda '{cname.strip()}': {n} aziende con questo nome, associazione non fatta")
                else:
                    rp.warnings.append(f"azienda '{cname.strip()}' non trovata nel CRM")
        return

    if kind == "companies":
        note = P.clean(_get(row, "note"))
        rp.properties = {
            "name": P.clean(_get(row, "ragione_sociale")),
            "domain": P.domain_of(_get(row, "sito_web")),
            "city": P.clean(_get(row, "citta")) or None,
            "state": P.clean(_get(row, "provincia")).upper() or None,
            "partita_iva": P.extract_vat(note) or P.normalize_vat(_get(row, "partita_iva", "piva", "p_iva")),
            "description": note or None,
            "id_legacy": P.clean(_get(row, "id_azienda")) or None,
        }
        rp.found("companies", r.by_legacy("companies", _get(row, "id_azienda")), "id_legacy")
        if rp.properties["partita_iva"]:
            rp.found("companies", r.by_prop("companies", "partita_iva", rp.properties["partita_iva"]), "partita_iva")
        if rp.properties["domain"]:
            rp.found("companies", r.by_prop("companies", "domain", rp.properties["domain"]), "domain")
        return

    if kind == "deals":
        importo = _get(row, "importo")
        amount = P.parse_amount(importo)
        cur = P.parse_currency(importo, _get(row, "valuta")) if amount is not None else None
        fam = P.pipeline_family(_get(row, "pipeline"))
        st = P.deal_stage(_get(row, "fase"), _get(row, "pipeline"))
        if st is not None and fam is None:
            fam = st[0]
        fam = fam or "sales"
        pipeline_id, stage_id = "default", None
        if fam == "renewal":
            pl = rules.ensure_deal_pipeline(store)
            if pl:
                pipeline_id = pl["id"]
                if st is not None and st[0] == "renewal" and st[1] < len(pl["stages"]):
                    stage_id = pl["stages"][st[1]]["id"]
        else:
            if st is not None and st[0] == "sales":
                stage_id = P.SALES_STAGES[st[1]]
        fase = P.clean(_get(row, "fase"))
        if fase and stage_id is None:
            rp.warnings.append(f"fase '{fase}' non riconosciuta: usata la prima fase della pipeline")
        closed = P.parse_dt(_get(row, "data_chiusura"))
        rp.properties = {
            "dealname": P.clean(_get(row, "titolo")),
            "amount": str(amount) if amount is not None else None,
            "deal_currency_code": (cur or "EUR") if amount is not None else None,
            "pipeline": pipeline_id,
            "dealstage": stage_id,
            "closedate": iso(closed) if closed else None,
            "id_legacy": P.clean(_get(row, "id_opportunita")) or None,
        }
        if importo.strip() and amount is None:
            rp.warnings.append(f"importo '{importo.strip()}' non interpretabile: trattativa senza importo")
        raw_user = _get(row, "id_commerciale", "commerciale")
        if raw_user.strip():
            u = r.user(raw_user)
            if u is None:
                rp.warnings.append(f"commerciale '{raw_user.strip()}' non è un utente Brambilla: campo lasciato vuoto")
                rp.properties["commerciale"] = ""
            elif not u["active"]:
                rp.warnings.append(f"commerciale {u['firstname']} {u['lastname']} non lavora più in Brambilla (R3): campo lasciato vuoto")
                rp.properties["commerciale"] = ""
            else:
                rp.properties["commerciale"] = u["email"]
        rp.found("deals", r.by_legacy("deals", _get(row, "id_opportunita")), "id_legacy")
        rp.assoc("companies", r.by_legacy("companies", _get(row, "id_azienda")), "id_azienda", _get(row, "id_azienda"))
        for cid in P.split_ids(_get(row, "contatti")):
            rp.assoc("contacts", r.by_legacy("contacts", cid), "contatti", cid)
        return

    if kind == "tickets":
        pl = rules.ensure_ticket_pipeline(store)
        idx = P.ticket_stage(_get(row, "stato"))
        opened = P.parse_dt(_get(row, "aperto_il"))
        closed = P.parse_dt(_get(row, "chiuso_il"))
        rp.properties = {
            "subject": P.clean(_get(row, "oggetto")),
            "content": P.clean(_get(row, "descrizione")) or None,
            "hs_pipeline": pl["id"] if pl else None,
            "hs_pipeline_stage": (pl["stages"][idx]["id"] if pl and idx < len(pl["stages"]) else None),
            "hs_ticket_priority": P.ticket_priority(_get(row, "priorita")),
            "createdate": iso(opened) if opened else None,
            "closed_date": iso(closed) if closed else None,
            "id_legacy": P.clean(_get(row, "id_ticket")) or None,
        }
        raw_user = _get(row, "id_utente", "assegnatario")
        if raw_user.strip():
            u = r.user(raw_user)
            if u is None:
                rp.warnings.append(f"assegnatario '{raw_user.strip()}' non è un utente Brambilla: campo lasciato vuoto")
                rp.properties["assegnatario"] = ""
            elif not u["active"]:
                rp.warnings.append(f"assegnatario {u['firstname']} {u['lastname']} non lavora più in Brambilla (R3): campo lasciato vuoto")
                rp.properties["assegnatario"] = ""
            else:
                rp.properties["assegnatario"] = u["email"]
        rp.found("tickets", r.by_legacy("tickets", _get(row, "id_ticket")), "id_legacy")
        contact = r.by_legacy("contacts", _get(row, "id_contatto"))
        if contact is None and not _get(row, "id_contatto"):
            m = re.match(r"^\s*Da:\s*<?([^\s<>]+@[^\s<>]+)>?", rp.properties.get("content") or "", re.I)
            if m:
                contact = r.by_prop("contacts", "email", m.group(1).lower())
                if contact:
                    rp.assoc("contacts", contact, "Da:", m.group(1).lower())
        rp.assoc("contacts", contact, "id_contatto", _get(row, "id_contatto"))
        rp.assoc("companies", r.by_legacy("companies", _get(row, "id_azienda")), "id_azienda", _get(row, "id_azienda"))
        return

    if kind == "activities":
        t = P.activity_type(_get(row, "tipo")) or "notes"
        rp.object_type = t
        when = P.parse_dt(_get(row, "data"))
        rp.properties = {
            ACTIVITY_BODY[t]: P.clean(_get(row, "testo")),
            "hs_timestamp": iso(when) if when else None,
            "id_legacy": P.clean(_get(row, "id_attivita")) or None,
        }
        raw_user = _get(row, "id_utente", "autore")
        u = r.user(raw_user) if raw_user.strip() else None
        rp.properties["autore"] = u["email"] if u else (writer_email or None)
        if raw_user.strip() and u is None:
            rp.warnings.append(f"autore '{raw_user.strip()}' non è un utente Brambilla: usato chi scrive")
        rp.found(t, r.by_legacy(t, _get(row, "id_attivita")), "id_legacy")
        rp.assoc("contacts", r.by_legacy("contacts", _get(row, "id_contatto")), "id_contatto", _get(row, "id_contatto"))
        rp.assoc("deals", r.by_legacy("deals", _get(row, "id_opportunita")), "id_opportunita", _get(row, "id_opportunita"))
        return

    if kind == "products":
        price = P.parse_number(_get(row, "prezzo_listino", "prezzo", "price"))
        sku = P.product_code(_get(row, "codice_articolo", "codice", "sku", "hs_sku"))
        rp.properties = {"hs_sku": sku, "name": P.clean(_get(row, "descrizione", "name")), "price": str(price) if price is not None else None}
        if not sku:
            rp.warnings.append("codice articolo mancante o non valido")
        rp.found("products", r.product_by_code(sku), "hs_sku")
        return

    if kind == "line_items":
        prod = r.product_by_code(_get(row, "codice_articolo"))
        deal = r.by_legacy("deals", _get(row, "id_opportunita"))
        qty = P.parse_number(_get(row, "quantita"))
        price = P.parse_number(_get(row, "prezzo_unitario"))
        pp = (prod or {}).get("properties") or {}
        if price is None and pp.get("price"):
            price = P.parse_number(pp.get("price"))
        rp.properties = {
            "name": P.clean(_get(row, "descrizione")) or pp.get("name"),
            "hs_sku": P.product_code(_get(row, "codice_articolo")) or pp.get("hs_sku"),
            "quantity": str(qty) if qty is not None else "1",
            "price": str(price) if price is not None else None,
            "hs_discount_percentage": str(P.parse_percent(_get(row, "sconto"))),
            "hs_product_id": str(prod["id"]) if prod else None,
            "id_legacy": P.clean(_get(row, "id_riga")) or None,
        }
        if qty is None and _get(row, "quantita").strip():
            rp.warnings.append(f"quantità '{_get(row, 'quantita').strip()}' non interpretabile: usato 1")
        if price is None:
            rp.warnings.append("prezzo unitario mancante e articolo non in listino")
        rp.found("line_items", r.by_legacy("line_items", _get(row, "id_riga")), "id_legacy")
        rp.assoc("deals", deal, "id_opportunita", _get(row, "id_opportunita"))
        if deal is None:
            rp.warnings.append("riga senza trattativa nel CRM: non importabile")
            rp.skip = "trattativa non trovata"
        rp.assoc("products", prod, "codice_articolo", _get(row, "codice_articolo"))
        return


def summarize(plans: list[RowPlan]) -> dict:
    return {
        "rows": len(plans),
        "new": sum(1 for p in plans if not p.skip and not p.existing),
        "existing": sum(1 for p in plans if not p.skip and p.existing),
        "skipped": sum(1 for p in plans if p.skip),
        "with_warnings": sum(1 for p in plans if p.warnings),
    }

"""Sinergia 4 -> CRM migration. One transaction, bulk COPY, deterministic."""
from __future__ import annotations

import csv
import datetime as dt
import io
import logging
import os
import re
import time
import zipfile
from collections import defaultdict
from decimal import Decimal

import httpx
from psycopg.types.json import Jsonb

from .. import brambilla, db, defaults, rules
from ..errors import ApiError
from ..routers.lists import create_list
from ..store import Store, invalidate_caches
from ..util import UTC, iso, utcnow
from . import parse as P

log = logging.getLogger("crm.migration")

FILES = ["aziende", "contatti", "opportunita", "righe_offerta", "listino", "ticket", "attivita", "utenti", "storico_fasi"]
FX = {"EUR": Decimal("1"), "USD": Decimal("0.92"), "GBP": Decimal("1.17")}
DORMANT_LIST_NAME = "Clienti dormienti"
REVENUE_YEAR = 2025
ACTIVITY_BODY = {"notes": "hs_note_body", "calls": "hs_call_body", "emails": "hs_email_text", "meetings": "hs_meeting_body"}


OBJECT_INDEXES = ["objects_type_id_idx", "objects_id_legacy_idx", "objects_contact_email_uq", "objects_company_piva_uq", "objects_company_domain_idx", "objects_sku_idx", "objects_name_lower_idx", "objects_dealname_lower_idx"]
ASSOC_INDEXES = ["associations_from_totype_idx", "associations_to_idx"]


def _index_ddl() -> list[str]:
    here = os.path.join(os.path.dirname(__file__), "..", "schema.sql")
    with open(here, encoding="utf-8") as fh:
        stmts = [s.strip() for s in fh.read().split(";") if s.strip()]
    return [s for s in stmts if s.upper().startswith("CREATE INDEX") or s.upper().startswith("CREATE UNIQUE INDEX")]


INDEX_DDL = _index_ddl()


def resume_pending():
    return None


# ------------------------------------------------------------------ input
def download(url: str) -> bytes:
    if url.startswith("file://"):
        with open(url[7:], "rb") as fh:
            return fh.read()
    if os.path.exists(url):
        with open(url, "rb") as fh:
            return fh.read()
    with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(180.0, connect=30.0)) as client:
        r = client.get(url)
        r.raise_for_status()
        return r.content


def read_export(data: bytes) -> dict[str, list[dict]]:
    zf = zipfile.ZipFile(io.BytesIO(data))
    out: dict[str, list[dict]] = {}
    for info in zf.infolist():
        if info.is_dir():
            continue
        base = os.path.basename(info.filename).lower()
        stem = re.sub(r"\.csv$", "", base)
        if stem not in FILES:
            continue
        raw = zf.read(info)
        text = raw.decode("cp1252", "surrogateescape")
        if text.startswith("﻿"):
            text = text[1:]
        # Sinergia specifies semicolons; punctuation in text cannot select a dialect.
        reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=";")
        rows = []
        for i, r in enumerate(reader):
            d = {(k or "").strip().lower(): (v if isinstance(v, str) else "") for k, v in r.items() if k is not None}
            d["_row_idx"] = i
            rows.append(d)
        out[stem] = rows
    missing = [f for f in FILES if f not in out]
    if missing:
        raise ApiError(400, f"export archive is missing files: {', '.join(missing)}", "VALIDATION_ERROR")
    return out


# ------------------------------------------------------------------ helpers
class Rec:
    __slots__ = ("id", "type", "props", "created", "updated", "legacy_ids")

    def __init__(self, type_: str, props: dict, created: dt.datetime, updated: dt.datetime, legacy_ids=None):
        self.id = None
        self.type = type_
        self.props = props
        self.created = created
        self.updated = updated
        self.legacy_ids = legacy_ids or []


class UnionFind:
    def __init__(self):
        self.parent: dict = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def _mod(row: dict) -> dt.datetime:
    return P.parse_dt(row.get("ultima_modifica")) or dt.datetime(1970, 1, 1, tzinfo=UTC)


def _mod_key(row: dict):
    """Most recent ultima_modifica wins; on a tie the later file row wins."""
    return (_mod(row), row.get("_row_idx", 0))


def _norm_text(s: str | None) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", P.fix_text(s) or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", t.strip().lower())


def _merge_field(rows_desc: list[dict], getter) -> str | None:
    """rows_desc sorted most recent first; first non-empty value wins."""
    for r in rows_desc:
        v = getter(r)
        if v not in (None, ""):
            return v
    return None


# ------------------------------------------------------------------ builders
class Migration:
    def __init__(self, files: dict[str, list[dict]], now: dt.datetime):
        self.files = files
        self.now = now
        self.users = P.Users(files["utenti"])
        self.stats: dict[str, int | str] = {}
        self.records: list[Rec] = []
        self.assocs: list[tuple[Rec, Rec, int]] = []  # (from, to, type_id) - inverse added automatically
        self.company_by_legacy: dict[str, Rec] = {}
        self.contact_by_legacy: dict[str, Rec] = {}
        self.deal_by_legacy: dict[str, Rec] = {}
        self.product_by_code: dict[str, Rec] = {}
        self.companies: list[Rec] = []
        self.contacts: list[Rec] = []
        self.deals: list[Rec] = []
        self.deal_company: dict[int, Rec] = {}  # index of deal rec -> company rec
        self.deal_contacts: dict[int, list[Rec]] = {}
        self.contact_company: dict[int, Rec] = {}
        self.activity_links: list[tuple[Rec, Rec | None, Rec | None]] = []  # (activity, contact, deal)

    # ---------------------------------------------------------- companies
    def build_companies(self):
        rows = [r for r in self.files["aziende"] if not P.is_deleted(r.get("cancellato"))]
        self.stats["aziende_rows"] = len(self.files["aziende"])
        self.stats["aziende_deleted"] = len(self.files["aziende"]) - len(rows)
        uf = UnionFind()
        info = {}
        for r in rows:
            lid = P.clean(r.get("id_azienda"))
            if not lid:
                continue
            dom = P.domain_of(r.get("sito_web"))
            vat = P.extract_vat(P.fix_text(r.get("note")))
            info[lid] = (r, dom, vat)
            uf.find(("id", lid))
            if dom:
                uf.union(("id", lid), ("dom", dom))
            if vat:
                uf.union(("id", lid), ("vat", vat))
        groups: dict = defaultdict(list)
        for lid, (r, dom, vat) in info.items():
            groups[uf.find(("id", lid))].append(lid)
        merged = 0
        for members in groups.values():
            rs = sorted((info[m][0] for m in members), key=_mod_key, reverse=True)
            newest = rs[0]
            if len(rs) > 1:
                merged += len(rs) - 1
            name = _merge_field(rs, lambda r: P.clean(r.get("ragione_sociale")))
            domain = _merge_field(rs, lambda r: P.domain_of(r.get("sito_web")))
            city = _merge_field(rs, lambda r: P.clean(r.get("citta")))
            state = _merge_field(rs, lambda r: P.clean(r.get("provincia")).upper())
            vat = _merge_field(rs, lambda r: P.extract_vat(P.fix_text(r.get("note"))))
            note = _merge_field(rs, lambda r: P.clean(r.get("note")))
            extra = []
            for r in rs:
                d = P.domain_of(r.get("sito_web"))
                if d and d != domain and d not in extra:
                    extra.append(d)
            props = {"name": name, "domain": domain, "city": city, "state": state, "partita_iva": vat, "description": note, "id_legacy": P.clean(newest.get("id_azienda"))}
            if extra:
                props["hs_additional_domains"] = ";".join(extra)
            if domain:
                props["website"] = domain
            rec = Rec("companies", {k: v for k, v in props.items() if v not in (None, "")}, self.now, _mod(newest), [P.clean(r.get("id_azienda")) for r in rs])
            self.records.append(rec)
            self.companies.append(rec)
            for r in rs:
                self.company_by_legacy[P.clean(r.get("id_azienda"))] = rec
        self.stats["companies"] = len(self.companies)
        self.stats["companies_merged_rows"] = merged

    # ---------------------------------------------------------- contacts
    def build_contacts(self):
        rows = [r for r in self.files["contatti"] if not P.is_deleted(r.get("cancellato"))]
        self.stats["contatti_rows"] = len(self.files["contatti"])
        self.stats["contatti_deleted"] = len(self.files["contatti"]) - len(rows)
        parsed = []  # per row: dict with emails, phone, company, name key
        uf = UnionFind()
        for i, r in enumerate(rows):
            emails, phone_like = P.parse_emails(r.get("email"))
            comp = self.company_by_legacy.get(P.clean(r.get("id_azienda")))
            parsed.append({
                "row": r, "emails": emails, "phone": P.clean(r.get("telefono")) or (phone_like or ""), "company": comp,
                "name": _norm_text(r.get("nome")) + "|" + _norm_text(r.get("cognome")),
            })
            uf.find(i)
            for e in emails:
                uf.union(i, ("email", e))
        # DECISIONS 2.2: same name inside the same company joins the same person, unless that would
        # join two different valid emails (sequential, first row of the (name, company) key is the anchor)
        comp_emails: dict = defaultdict(set)
        for i, p in enumerate(parsed):
            comp_emails[uf.find(i)].update(p["emails"])
        anchor: dict[tuple, int] = {}
        name_merges = 0
        for i, p in enumerate(parsed):
            if p["company"] is None or p["name"] == "|":
                continue
            key = (p["name"], id(p["company"]))
            if key not in anchor:
                anchor[key] = i
                continue
            ra, rb = uf.find(anchor[key]), uf.find(i)
            if ra == rb:
                continue
            ea, eb = comp_emails[ra], comp_emails[rb]
            if ea and eb and not (ea & eb):
                continue
            uf.union(ra, rb)
            comp_emails[uf.find(ra)] = ea | eb
            name_merges += 1
        groups: dict = defaultdict(list)
        for i in range(len(parsed)):
            groups[uf.find(i)].append(i)
        merged = 0
        for idxs in groups.values():
            ps = sorted((parsed[i] for i in idxs), key=lambda p: _mod_key(p["row"]), reverse=True)
            rs = [p["row"] for p in ps]
            newest = rs[0]
            if len(rs) > 1:
                merged += len(rs) - 1
            email = _merge_field(ps, lambda p: p["emails"][0] if p["emails"] else None)
            all_emails: list[str] = []
            for p in ps:
                for e in p["emails"]:
                    if e not in all_emails:
                        all_emails.append(e)
            extra_emails = [e for e in all_emails if e != email]
            tipo = _merge_field(rs, lambda r: P.clean(r.get("tipo")))
            props = {
                "firstname": _merge_field(rs, lambda r: P.clean(r.get("nome"))),
                "lastname": _merge_field(rs, lambda r: P.clean(r.get("cognome"))),
                "email": email,
                "phone": _merge_field(ps, lambda p: p["phone"]),
                "lifecyclestage": P.lifecycle_stage(tipo) if tipo else None,
                "id_legacy": P.clean(newest.get("id_contatto")),
            }
            if extra_emails:
                props["hs_additional_emails"] = ";".join(extra_emails)
            if email:
                props["hs_email_domain"] = email.rsplit("@", 1)[1]
            comp = _merge_field(ps, lambda p: p["company"])
            rec = Rec("contacts", {k: v for k, v in props.items() if v not in (None, "")}, self.now, _mod(newest), [P.clean(r.get("id_contatto")) for r in rs])
            self.records.append(rec)
            self.contacts.append(rec)
            for r in rs:
                self.contact_by_legacy[P.clean(r.get("id_contatto"))] = rec
            if comp is not None:
                self.contact_company[id(rec)] = comp
        self.stats["contacts"] = len(self.contacts)
        self.stats["contacts_merged_rows"] = merged
        self.stats["contacts_merged_by_name_company"] = name_merges

    def apply_r12(self):
        """Contacts without a company: match the email domain against company domains (primary first)."""
        primary: dict[str, Rec] = {}
        additional: dict[str, Rec] = {}
        for c in self.companies:
            d = c.props.get("domain")
            if d and d not in primary:
                primary[d] = c
            for extra in (c.props.get("hs_additional_domains") or "").split(";"):
                if extra and extra not in additional:
                    additional[extra] = c
        n = 0
        for rec in self.contacts:
            if id(rec) in self.contact_company:
                continue
            e = rec.props.get("email")
            if not e:
                continue
            dom = e.rsplit("@", 1)[1]
            comp = primary.get(dom) or additional.get(dom)
            if comp is not None:
                self.contact_company[id(rec)] = comp
                n += 1
        self.stats["contacts_auto_associated_r12"] = n
        for rec in self.contacts:
            comp = self.contact_company.get(id(rec))
            if comp is not None:
                self.assocs.append((rec, comp, 279))
                self.assocs.append((rec, comp, 1))

    # ---------------------------------------------------------- products
    def build_products(self):
        rows = [r for r in self.files["listino"] if not P.is_deleted(r.get("cancellato"))]
        self.stats["listino_rows"] = len(self.files["listino"])
        groups: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            code = P.product_code(r.get("codice_articolo"))
            if code:
                groups[code].append(r)
        for code, rs in groups.items():
            rs = sorted(rs, key=_mod_key, reverse=True)
            newest = rs[0]
            price = _merge_field(rs, lambda r: P.parse_number(r.get("prezzo_listino")))
            props = {
                "name": _merge_field(rs, lambda r: P.clean(r.get("descrizione"))),
                "hs_sku": code,
                "price": P.num_str(price) if price is not None else None,
                "hs_unit": _merge_field(rs, lambda r: P.clean(r.get("unita"))),
            }
            rec = Rec("products", {k: v for k, v in props.items() if v not in (None, "")}, self.now, _mod(newest))
            self.records.append(rec)
            self.product_by_code[code] = rec
        self.stats["products"] = len(self.product_by_code)

    # ---------------------------------------------------------- deals + line items
    def build_deals(self, sales_pl: dict, renewal_pl: dict):
        rows = [r for r in self.files["opportunita"] if not P.is_deleted(r.get("cancellato"))]
        self.stats["opportunita_rows"] = len(self.files["opportunita"])
        self.stats["opportunita_deleted"] = len(self.files["opportunita"]) - len(rows)
        hist: dict[str, list[tuple[dt.datetime, tuple | None, dict]]] = defaultdict(list)
        for h in self.files["storico_fasi"]:
            lid = P.clean(h.get("id_opportunita"))
            d = P.parse_dt(h.get("data_cambio"))
            if lid and d:
                hist[lid].append((d, P.deal_stage(h.get("fase_nuova"), None), h))
        for v in hist.values():
            v.sort(key=lambda x: x[0])
        lines: dict[str, list[dict]] = defaultdict(list)
        for r in self.files["righe_offerta"]:
            lines[P.clean(r.get("id_opportunita"))].append(r)
        sales_stage_ids = [s["id"] for s in sales_pl["stages"]]
        renewal_stage_ids = [s["id"] for s in renewal_pl["stages"]]
        unknown_stage = 0
        owner_unresolved = 0
        line_count = 0
        amount_from_lines = 0
        lines_price_fallback = 0
        lines_no_product = 0
        closedate_from_history = 0
        amount_unparsed = 0
        for r in rows:
            lid = P.clean(r.get("id_opportunita"))
            if not lid:
                continue
            fam = P.pipeline_family(r.get("pipeline"))
            st = P.deal_stage(r.get("fase"), r.get("pipeline"))
            if st is not None:
                fam = st[0]
                idx = st[1]
            else:
                unknown_stage += 1
                fam = fam or "sales"
                idx = 0
            if fam == "renewal":
                pipeline_id, stage_id = renewal_pl["id"], renewal_stage_ids[idx]
                won, lost = idx == 2, idx == 3
            else:
                pipeline_id, stage_id = sales_pl["id"], sales_stage_ids[idx]
                won, lost = idx == 5, idx == 6
            amount = P.parse_amount(r.get("importo"))
            if amount is None and P.clean(r.get("importo")):
                amount_unparsed += 1
            currency = P.parse_currency(r.get("importo"), r.get("valuta"))
            if amount is not None and not currency:
                currency = "EUR"
            # line items
            deal_lines = lines.get(lid, [])
            line_recs = []
            if deal_lines:
                total = Decimal(0)
                any_total = False
                for lr in deal_lines:
                    code = P.product_code(lr.get("codice_articolo"))
                    prod = self.product_by_code.get(code) if code else None
                    qty = P.parse_number(lr.get("quantita"))
                    if qty is None:
                        qty = Decimal(0)
                    price = P.parse_number(lr.get("prezzo_unitario"))
                    if price is None and prod is not None and prod.props.get("price") is not None:
                        price = Decimal(prod.props["price"])
                        lines_price_fallback += 1
                    if price is None:
                        price = Decimal(0)
                    if prod is None:
                        lines_no_product += 1
                    disc = P.parse_percent(lr.get("sconto"))
                    name = P.clean(lr.get("descrizione")) or (prod.props.get("name") if prod else None)
                    props = {
                        "name": name,
                        "quantity": P.num_str(qty) if qty is not None else None,
                        "price": P.num_str(price) if price is not None else None,
                        "hs_discount_percentage": P.num_str(disc),
                        "hs_sku": code,
                        "hs_line_item_currency_code": "EUR",
                        "id_legacy": P.clean(lr.get("id_riga")),
                    }
                    if qty is not None and price is not None:
                        line_total = P.money(qty * price * (Decimal(1) - disc / Decimal(100)))
                        props["amount"] = P.num_str(line_total)
                        props["hs_total_discount"] = P.num_str(P.money(qty * price * disc / Decimal(100)))
                        total += line_total
                        any_total = True
                    if prod is not None:
                        props["hs_product_id"] = None  # filled after ids are assigned
                    lrec = Rec("line_items", {k: v for k, v in props.items() if v not in (None, "")}, self.now, self.now)
                    lrec.legacy_ids = [prod]  # stash product rec for later
                    line_recs.append(lrec)
                if any_total:
                    amount = total
                    currency = P.parse_currency(r.get("importo"), r.get("valuta")) or "EUR"
                    amount_from_lines += 1
            # close date
            closedate = P.parse_dt(r.get("data_chiusura"))
            h = hist.get(lid, [])
            if closedate is None and (won or lost):
                target = ("renewal", 2 if won else 3) if fam == "renewal" else ("sales", 5 if won else 6)
                entries = [d for d, s, _ in h if s == target]
                if entries:
                    closedate = max(entries)
                    closedate_from_history += 1
            hint_ids = {P.clean(x.get("id_utente")).upper() for _, _, x in h if P.clean(x.get("id_utente"))}
            resolved = self.users.resolve(r.get("id_commerciale"), hint_ids)
            owner = self.users.effective(resolved)
            if P.clean(r.get("id_commerciale")) and resolved is None:
                owner_unresolved += 1
            created = h[0][0] if h else _mod(r)
            props = {
                "dealname": P.clean(r.get("titolo")),
                "amount": P.num_str(P.money(amount)) if amount is not None else None,
                "deal_currency_code": currency if amount is not None else None,
                "pipeline": pipeline_id,
                "dealstage": stage_id,
                "closedate": iso(closedate) if closedate else None,
                "commerciale": owner["email"] if owner else None,
                "id_legacy": lid,
                "hs_is_closed": "true" if (won or lost) else "false",
                "hs_is_closed_won": "true" if won else "false",
                "hs_is_closed_lost": "true" if lost else "false",
            }
            stage_meta = next(s for s in (renewal_pl if fam == "renewal" else sales_pl)["stages"] if s["id"] == stage_id)["metadata"]
            props["hs_deal_stage_probability"] = stage_meta.get("probability")
            if won and amount is not None:
                props["hs_closed_amount"] = props["amount"]
                props["hs_closed_won_date"] = props["closedate"]
            if lost:
                props["hs_closed_lost_date"] = props["closedate"]
            rec = Rec("deals", {k: v for k, v in props.items() if v not in (None, "")}, created, _mod(r), [lid])
            self.records.append(rec)
            self.deals.append(rec)
            self.deal_by_legacy[lid] = rec
            comp = self.company_by_legacy.get(P.clean(r.get("id_azienda")))
            if comp is not None:
                self.deal_company[id(rec)] = comp
                self.assocs.append((rec, comp, 341))
                self.assocs.append((rec, comp, 5))
            contacts = []
            for cid in P.split_ids(r.get("contatti")):
                c = self.contact_by_legacy.get(cid)
                if c is not None and c not in contacts:
                    contacts.append(c)
            self.deal_contacts[id(rec)] = contacts
            for c in contacts:
                self.assocs.append((rec, c, 3))
            for lrec in line_recs:
                self.records.append(lrec)
                self.assocs.append((lrec, rec, 20))
                prod = lrec.legacy_ids[0]
                lrec.legacy_ids = []
                if prod is not None:
                    self.assocs.append((lrec, prod, 901))
                    lrec.props["__product"] = prod
                line_count += 1
            if contacts:
                rec.props["num_associated_contacts"] = str(len(contacts))
        self.stats["deals"] = len(self.deals)
        self.stats["line_items"] = line_count
        self.stats["deals_amount_from_lines"] = amount_from_lines
        self.stats["lines_price_from_listino"] = lines_price_fallback
        self.stats["lines_without_product"] = lines_no_product
        self.stats["deals_closedate_from_history"] = closedate_from_history
        self.stats["deals_unknown_stage"] = unknown_stage
        self.stats["deals_owner_unresolved"] = owner_unresolved
        self.stats["deals_amount_unparsed"] = amount_unparsed
        self.stats["righe_rows"] = len(self.files["righe_offerta"])

    # ---------------------------------------------------------- tickets
    def build_tickets(self, ticket_pl: dict):
        rows = [r for r in self.files["ticket"] if not P.is_deleted(r.get("cancellato"))]
        self.stats["ticket_rows"] = len(self.files["ticket"])
        self.stats["ticket_deleted"] = len(self.files["ticket"]) - len(rows)
        stage_ids = [s["id"] for s in ticket_pl["stages"]]
        contact_by_email = {}
        for c in self.contacts:
            e = c.props.get("email")
            if e and e not in contact_by_email:
                contact_by_email[e] = c
        from_da = 0
        n = 0
        for r in rows:
            lid = P.clean(r.get("id_ticket"))
            if not lid:
                continue
            idx = P.ticket_stage(r.get("stato"))
            opened_raw = P.parse_dt(r.get("aperto_il"))
            opened = opened_raw or _mod(r)
            closed = P.parse_dt(r.get("chiuso_il"))
            owner = self.users.effective(self.users.resolve(r.get("id_utente")))
            content = P.clean(r.get("descrizione"))
            props = {
                "subject": P.clean(r.get("oggetto")),
                "content": content,
                "hs_pipeline": ticket_pl["id"],
                "hs_pipeline_stage": stage_ids[idx],
                "hs_ticket_priority": P.ticket_priority(r.get("priorita")),
                "createdate": iso(opened_raw) if opened_raw else None,
                "closed_date": iso(closed) if closed else None,
                "assegnatario": owner["email"] if owner else None,
                "id_legacy": lid,
            }
            rec = Rec("tickets", {k: v for k, v in props.items() if v not in (None, "")}, opened, _mod(r), [lid])
            self.records.append(rec)
            n += 1
            contact = self.contact_by_legacy.get(P.clean(r.get("id_contatto")))
            if contact is None:
                m = re.match(r"^\s*Da:\s*<?([^\s<>]+@[^\s<>]+)>?", content, re.I)
                if m:
                    contact = contact_by_email.get(m.group(1).lower())
                    if contact is not None:
                        from_da += 1
            if contact is not None:
                self.assocs.append((rec, contact, 16))
                rec.props["hs_num_associated_contacts"] = "1"
            comp = self.company_by_legacy.get(P.clean(r.get("id_azienda")))
            if comp is not None:
                self.assocs.append((rec, comp, 339))
                self.assocs.append((rec, comp, 26))
        self.stats["tickets"] = n
        self.stats["tickets_contact_from_da_line"] = from_da

    # ---------------------------------------------------------- activities
    def build_activities(self):
        rows = self.files["attivita"]
        self.stats["attivita_rows"] = len(rows)
        counts = defaultdict(int)
        deleted = 0
        unknown = 0
        for r in rows:
            if P.is_deleted(r.get("cancellato")):
                deleted += 1
                continue
            t = P.activity_type(r.get("tipo"))
            if t is None:
                unknown += 1
                t = "notes"
            when = P.parse_dt(r.get("data")) or self.now
            user = self.users.resolve(r.get("id_utente"))
            props = {
                ACTIVITY_BODY[t]: P.clean(r.get("testo")),
                "hs_timestamp": iso(when),
                "autore": user["email"] if user else None,
                "id_legacy": P.clean(r.get("id_attivita")),
            }
            if t == "calls":
                props["hs_call_status"] = "COMPLETED"
            rec = Rec(t, {k: v for k, v in props.items() if v not in (None, "")}, when, when)
            self.records.append(rec)
            counts[t] += 1
            contact = self.contact_by_legacy.get(P.clean(r.get("id_contatto")))
            deal = self.deal_by_legacy.get(P.clean(r.get("id_opportunita")))
            fwd = {"notes": (202, 214), "calls": (194, 206), "emails": (198, 210), "meetings": (200, 212)}[t]
            if contact is not None:
                self.assocs.append((rec, contact, fwd[0]))
            if deal is not None:
                self.assocs.append((rec, deal, fwd[1]))
            self.activity_links.append((rec, contact, deal))
        for k, v in counts.items():
            self.stats[k] = v
        self.stats["attivita_deleted"] = deleted
        self.stats["attivita_unknown_type"] = unknown

    # ---------------------------------------------------------- R8 / R9
    def compute_revenue(self):
        per_company: dict[int, Decimal] = defaultdict(Decimal)
        won_companies: set[int] = set()
        for d in self.deals:
            comp = self.deal_company.get(id(d))
            if comp is None:
                continue
            if d.props.get("hs_is_closed_won") != "true":
                continue
            won_companies.add(id(comp))
            cd = d.props.get("closedate")
            if not cd or not cd.startswith(str(REVENUE_YEAR)):
                continue
            amt = d.props.get("amount")
            if amt is None:
                continue
            rate = FX.get(d.props.get("deal_currency_code") or "EUR", Decimal(1))
            per_company[id(comp)] += Decimal(amt) * rate
        classes = defaultdict(int)
        for c in self.companies:
            total = P.money(per_company.get(id(c), Decimal(0)))
            c.props["fatturato_2025"] = format(total, "f")
            if total >= 100000:
                cls = "A"
            elif total >= 20000:
                cls = "B"
            elif total > 0:
                cls = "C"
            else:
                cls = None
            if cls:
                c.props["classe_cliente"] = cls
            classes[cls or "-"] += 1
        self.stats["classes"] = dict(classes)
        # R9 dormant: won deal ever, no activity in REVENUE_YEAR via its contacts or its deals
        company_contacts: dict[int, set[int]] = defaultdict(set)
        for c in self.contacts:
            comp = self.contact_company.get(id(c))
            if comp is not None:
                company_contacts[id(comp)].add(id(c))
        contact_company_id = {}
        for comp_id, cs in company_contacts.items():
            for cid in cs:
                contact_company_id.setdefault(cid, set()).add(comp_id)
        active_companies: set[int] = set()
        prefix = str(REVENUE_YEAR) + "-"
        for act, contact, deal in self.activity_links:
            if not act.props["hs_timestamp"].startswith(prefix):
                continue
            if contact is not None:
                for comp_id in contact_company_id.get(id(contact), ()):
                    active_companies.add(comp_id)
            if deal is not None:
                comp = self.deal_company.get(id(deal))
                if comp is not None:
                    active_companies.add(id(comp))
        self.dormant = [c for c in self.companies if id(c) in won_companies and id(c) not in active_companies]
        self.stats["dormant_companies"] = len(self.dormant)


# ------------------------------------------------------------------ writing
def _copy_objects(conn, records: list[Rec]):
    with conn.cursor() as cur:
        with cur.copy("COPY objects (id, object_type, properties, created_at, updated_at, archived) FROM STDIN") as copy:
            copy.set_types(["int8", "text", "jsonb", "timestamptz", "timestamptz", "bool"])
            for r in records:
                copy.write_row((r.id, r.type, Jsonb(r.props), r.created, r.updated, False))


def _copy_assocs(conn, rows):
    with conn.cursor() as cur:
        with cur.copy("COPY associations (from_id, to_id, type_id, from_type, to_type, category) FROM STDIN") as copy:
            copy.set_types(["int8", "int8", "int4", "text", "text", "text"])
            for row in rows:
                copy.write_row(row)


def run_migration(url: str) -> dict:
    t0 = time.time()
    data = download(url)
    t_dl = time.time() - t0
    files = read_export(data)
    t_parse = time.time() - t0
    log.info("export downloaded (%d bytes, %.1fs) and parsed (%.1fs)", len(data), t_dl, t_parse)
    with db.connection() as conn:
        prev = conn.execute("SELECT 1 FROM meta WHERE key = 'migration'").fetchone()
        if prev:
            conn.rollback()
            from ..routers.admin import reset_database
            reset_database()
    with db.connection() as conn:
        now = utcnow()
        store = Store(conn, now)
        brambilla.ensure_all(conn)
        invalidate_caches()
        sales_pl = next(p for p in store.pipelines("deals") if p["id"] == "default")
        renewal_pl = rules.ensure_deal_pipeline(store)
        ticket_pl = rules.ensure_ticket_pipeline(store)
        m = Migration(files, now)
        m.build_companies()
        m.build_contacts()
        m.apply_r12()
        m.build_products()
        m.build_deals(sales_pl, renewal_pl)
        m.build_tickets(ticket_pl)
        m.build_activities()
        m.compute_revenue()
        files.clear()  # Release raw CSV rows before ID/association/COPY allocation.
        t_build = time.time() - t0
        # ids
        start = int(conn.execute("SELECT nextval('objects_id_seq') AS v").fetchone()["v"])
        next_id = start
        for r in m.records:
            r.id = next_id
            next_id += 1
            r.props["hs_object_id"] = str(r.id)
            ot = defaults.OBJECT_TYPES[r.type]
            r.props.setdefault(ot["created"], iso(r.created))
            r.props[ot["modified"]] = iso(r.updated)
            if r.type == "tickets":
                r.props["hs_ticket_id"] = str(r.id)
            if r.type == "contacts":
                r.props["hs_full_name_or_email"] = " ".join(x for x in (r.props.get("firstname"), r.props.get("lastname")) if x) or r.props.get("email", "")
        conn.execute("SELECT setval('objects_id_seq', %s)", (next_id,))
        for r in m.records:
            if r.type == "line_items" and "__product" in r.props:
                prod = r.props.pop("__product")
                r.props["hs_product_id"] = str(prod.id)
            if r.type == "contacts":
                comp = m.contact_company.get(id(r))
                if comp is not None:
                    r.props["associatedcompanyid"] = str(comp.id)
        # association rows (both directions)
        assoc_rows = set()
        for f, t, tid in m.assocs:
            lab = defaults.ASSOC_BY_ID[tid]
            cat = "USER_DEFINED" if tid in (901, 902) else "HUBSPOT_DEFINED"
            assoc_rows.add((f.id, t.id, tid, f.type, t.type, cat))
            inv = lab[5]
            if inv is not None:
                assoc_rows.add((t.id, f.id, inv, t.type, f.type, cat))
        # company contact counts
        cc = defaultdict(int)
        for c in m.contacts:
            comp = m.contact_company.get(id(c))
            if comp is not None:
                cc[comp.id] += 1
        for c in m.companies:
            if cc.get(c.id):
                c.props["num_associated_contacts"] = str(cc[c.id])
        # write: drop secondary indexes, bulk COPY, rebuild
        conn.execute("SET LOCAL synchronous_commit = off")
        conn.execute("SET LOCAL maintenance_work_mem = '256MB'")
        for idx in OBJECT_INDEXES + ASSOC_INDEXES:
            conn.execute(f"DROP INDEX IF EXISTS {idx}")
        conn.execute("ALTER TABLE associations DROP CONSTRAINT IF EXISTS associations_pkey")
        t_w0 = time.time()
        _copy_objects(conn, m.records)
        t_w1 = time.time()
        _copy_assocs(conn, assoc_rows)
        t_w2 = time.time()
        dom_rows = set()
        for c in m.companies:
            if c.props.get("domain"):
                dom_rows.add((c.props["domain"], c.id))
            for extra in (c.props.get("hs_additional_domains") or "").split(";"):
                if extra:
                    dom_rows.add((extra, c.id))
        with conn.cursor() as cur:
            with cur.copy("COPY company_domains (domain, company_id) FROM STDIN") as copy:
                for row in sorted(dom_rows):
                    copy.write_row(row)
            cur.executemany(
                "INSERT INTO crm_users (id, firstname, lastname, email, role, manager_id, active) VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO UPDATE SET firstname = EXCLUDED.firstname, lastname = EXCLUDED.lastname, email = EXCLUDED.email, role = EXCLUDED.role, manager_id = EXCLUDED.manager_id, active = EXCLUDED.active",
                [(u["id"], u["firstname"], u["lastname"], u["email"], u["role"], u["manager"], u["active"]) for u in m.users.by_id.values()],
            )
        lst = create_list(conn, DORMANT_LIST_NAME, "0-2", "MANUAL")
        with conn.cursor() as cur:
            with cur.copy("COPY list_memberships (list_id, record_id, added_at) FROM STDIN") as copy:
                copy.set_types(["int8", "int8", "timestamptz"])
                for c in m.dormant:
                    copy.write_row((int(lst["listId"]), c.id, now))
        conn.execute("ALTER TABLE associations ADD PRIMARY KEY (from_id, to_id, type_id)")
        for ddl in INDEX_DDL:
            conn.execute(ddl)
        t_w3 = time.time()
        t_write = time.time() - t0
        m.stats.update({"records": len(m.records), "associations": len(assoc_rows), "seconds_download": round(t_dl, 1), "seconds_build": round(t_build, 1), "seconds_copy_objects": round(t_w1 - t_w0, 1), "seconds_copy_assocs": round(t_w2 - t_w1, 1), "seconds_indexes": round(t_w3 - t_w2, 1), "seconds_total": round(t_write, 1), "migrated_at": iso(now), "source": url[:200]})
        conn.execute("INSERT INTO meta (key, value) VALUES ('migration', %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", (Jsonb(m.stats),))
        conn.commit()
    invalidate_caches()
    try:
        with db.connection() as conn:
            conn.execute("ANALYZE objects")
            conn.execute("ANALYZE associations")
            conn.commit()
    except Exception:  # pragma: no cover
        pass
    log.info("migration done in %.1fs: %s", time.time() - t0, m.stats)
    return m.stats

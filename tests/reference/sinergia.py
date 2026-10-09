"""Independent reference implementation of the Sinergia migration (R1-R9, R12 on import).

Pure Python over the nine CSVs, written from `DECISIONS.md` without looking at the server
code, so that the acceptance tests compare two independent readings of the same rules.

    from tests.reference import sinergia
    expected = sinergia.migrate(sinergia.load_export("legacy/export.zip"))

`expected` has one dict per object type (`companies`, `contacts`, `deals`, `products`,
`line_items`, `tickets`, `notes`, `calls`, `emails`, `meetings`), keyed by the value of the
property named in `KEY_PROPERTY` (`id_legacy` everywhere, `hs_sku` for products). Values are
the expected HubSpot properties as strings; `None` means the property must be empty; keys that
start with `_` are informative (labels of generated pipeline stages, sets) and not compared.
Datetimes are `YYYY-MM-DDTHH:MM:SSZ`. Also: `merged_into[type][old] = survivor`,
`associations` = set of `(from_type, from_key, to_type, to_key)`, `dormant` = set of company
keys, `users` = list of user dicts, `stats` = counters worth printing.

CLI: `python -m tests.reference.sinergia legacy/export.zip [--json out.json]`.
"""
from __future__ import annotations

import csv
import io
import json
import re
import sys
import time
import unicodedata
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from pathlib import Path

FILES = ["utenti", "aziende", "contatti", "opportunita", "storico_fasi", "listino", "righe_offerta", "ticket", "attivita"]
KEY_PROPERTY = {"products": "hs_sku"}
OBJECT_TYPES = ["companies", "contacts", "deals", "products", "line_items", "tickets", "notes", "calls", "emails", "meetings"]

TRUE_SET = {"1", "s", "si", "sì", "true", "y", "yes"}
CENT = Decimal("0.01")
RATES = {"EUR": Decimal("1"), "USD": Decimal("0.92"), "GBP": Decimal("1.17")}
EXCEL_EPOCH = datetime(1899, 12, 30)

SALES_STAGES = {"01": "appointmentscheduled", "02": "qualifiedtobuy", "03": "presentationscheduled",
                "04": "decisionmakerboughtin", "05": "contractsent", "06": "closedwon", "07": "closedlost"}
SALES_NAMES = {"contatto": "01", "qualifica": "02", "presentazione": "03", "decisione": "04",
               "contratto": "05", "vinta": "06", "persa": "07"}
RENEWAL_LABELS = {"r1": "Da rinnovare", "r2": "In trattativa", "r3": "Rinnovato", "r4": "Non rinnovato"}
RENEWAL_NAMES = [("non rinnovato", "r4"), ("da rinnovare", "r1"), ("in trattativa", "r2"), ("rinnovato", "r3")]
CLOSED_CODES = {("sales", "06"), ("sales", "07"), ("renewals", "r3"), ("renewals", "r4")}
WON_CODES = {("sales", "06"), ("renewals", "r3")}

LIFECYCLE = {"lead": "lead", "prospect": "opportunity", "cliente": "customer", "ex cliente": "other", "ex-cliente": "other", "excliente": "other"}
TICKET_STAGES = [("in lavorazione", "In lavorazione"), ("lavorazione", "In lavorazione"), ("in attesa", "In attesa del cliente"),
                 ("attesa", "In attesa del cliente"), ("chiuso", "Chiuso"), ("risolto", "Chiuso"), ("aperto", "Aperto"), ("nuovo", "Aperto")]
PRIORITIES = [("bassa", "LOW"), ("media", "MEDIUM"), ("normale", "MEDIUM"), ("alta", "HIGH"), ("urgente", "URGENT")]
ACTIVITY_TYPES = {"nota": "notes", "appunto": "notes", "chiamata": "calls", "telefonata": "calls", "tel.": "calls", "tel": "calls",
                  "email": "emails", "e-mail": "emails", "mail": "emails", "incontro": "meetings", "meeting": "meetings",
                  "riunione": "meetings", "visita": "meetings"}
BODY_PROP = {"notes": "hs_note_body", "calls": "hs_call_body", "emails": "hs_email_text", "meetings": "hs_meeting_body"}
EMAIL_RE = re.compile(r"^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$")


# ----------------------------------------------------------------------------- helpers

def truthy(v: str) -> bool:
    return (v or "").strip().lower() in TRUE_SET


MOJIBAKE_RE = re.compile(r"[\u00c2\u00c3][\u0080-\u00bf\u20ac\u2018-\u201e\u2020-\u2022\u2026\u02dc\u2122\u0160\u0161\u017d\u017e\u0152\u0153\u0178\u0192\u02c6\u2030\u2039\u203a\u00a0-\u00bf]")


def fix_encoding(v: str) -> str:
    """The files are cp1252, but about 4,600 rows (companies, contacts, tickets) are UTF-8: once read as
    cp1252 they show `SocietÃ ` for `Società`. Re-encode and decode those fields; leave everything else."""
    if not v or not MOJIBAKE_RE.search(v):
        return v
    try:
        return v.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return v


def norm_text(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s.strip().lower())


def parse_dt(s: str) -> datetime | None:
    s = (s or "").strip()
    if not s:
        return None
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?", s)
    if m:
        y, mo, d, h, mi, se = m.groups()
    else:
        m = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?", s)
        if m:
            d, mo, y, h, mi, se = m.groups()
        else:
            m = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{2})", s)
            if m:
                d, mo, y = m.groups()
                y = "20" + y
                h = mi = se = None
            elif re.fullmatch(r"\d{5}", s):
                return EXCEL_EPOCH + timedelta(days=int(s))
            else:
                return None
    try:
        return datetime(int(y), int(mo), int(d), int(h or 0), int(mi or 0), int(se or 0))
    except ValueError:
        return None


def iso(dt: datetime | None) -> str | None:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


def parse_money(s: str) -> Decimal | None:
    t = (s or "").strip()
    if not t:
        return None
    neg = False
    if t.startswith("(") and t.endswith(")"):
        neg, t = True, t[1:-1]
    t = re.sub(r"(?i)\b(eur|usd|gbp)\b|[€$£]", " ", t)
    monthly = bool(re.search(r"(?i)mensil|/\s*mese|al\s+mese", t))
    t = re.sub(r"(?i)mensil\w*|/\s*mese|al\s+mese", " ", t)
    mult = Decimal(1)
    t = t.strip()
    m = re.search(r"(?i)(mln|milion[ei]|mila|k)\s*$", t)
    if m:
        word = m.group(1).lower()
        mult = Decimal(1_000_000) if word.startswith("m") and word != "mila" else Decimal(1000)
        t = t[: m.start()].strip()
    if t.endswith("-"):
        neg, t = True, t[:-1]
    t = t.strip()
    if t.startswith("-"):
        neg, t = True, t[1:]
    t = t.replace(" ", "")
    if "," in t and "." in t:
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(",", "")
    elif t.count(",") > 1:
        t = t.replace(",", "")
    elif t.count(".") > 1:
        t = t.replace(".", "")
    elif "," in t:
        t = t.replace(",", ".")
    try:
        val = Decimal(t) * mult
    except InvalidOperation:
        return None
    if monthly:
        val *= 12
    if neg:
        val = -val
    return val.quantize(CENT, ROUND_HALF_UP)


def money_str(d: Decimal | None) -> str | None:
    return None if d is None else str(d.quantize(CENT, ROUND_HALF_UP))


def num_str(d: Decimal) -> str:
    """Shortest plain form: 10, 2.5, 0.03 (never exponent notation)."""
    q = d.quantize(CENT, ROUND_HALF_UP)
    if q == q.to_integral():
        return str(q.quantize(Decimal(1)))
    return str(q).rstrip("0")


def parse_currency(valuta: str, importo: str) -> str:
    v = (valuta or "").strip().lower()
    if v in ("eur", "euro", "€"):
        return "EUR"
    if v in ("usd", "$"):
        return "USD"
    if v in ("gbp", "£"):
        return "GBP"
    s = (importo or "").lower()
    if "usd" in s or "$" in s:
        return "USD"
    if "gbp" in s or "£" in s:
        return "GBP"
    return "EUR"


def parse_stage(fase: str) -> tuple[str, str] | None:
    f = (fase or "").strip().lower()
    if not f:
        return None
    m = re.match(r"^(0[1-7]|r[1-4])(?![0-9a-z])", f)
    if m:
        code = m.group(1)
        return ("renewals", code) if code.startswith("r") else ("sales", code)
    for name, code in RENEWAL_NAMES:
        if name in f:
            return ("renewals", code)
    for name, code in SALES_NAMES.items():
        if name in f:
            return ("sales", code)
    return None


def parse_pipeline(pipeline: str, stage: tuple[str, str] | None) -> str:
    p = (pipeline or "").strip().lower()
    if p.startswith("rinnov"):
        return "renewals"
    if p.startswith("vendit"):
        return "sales"
    return stage[0] if stage else "sales"


def norm_domain(url: str) -> str:
    d = (url or "").strip().lower()
    d = re.sub(r"^[a-z]+://", "", d)
    d = d.split("/")[0].split("?")[0]
    d = re.sub(r"^www\.", "", d)
    return d.strip()


VAT_RE = re.compile(r"(?i)(?:p\.?\s*iva|partita\s*iva|\bpi\b)\s*[:\s]*(?:it\s*)?((?:\d\s*){11})(?!\d)")


def extract_vat(note: str) -> str | None:
    for m in VAT_RE.finditer(note or ""):
        digits = re.sub(r"\D", "", m.group(1))
        if len(digits) == 11:
            return digits
    return None


def norm_email(s: str) -> str | None:
    """A single address: trimmed and lower-cased, valid or absent. No repairs (`(at)`, inner spaces stay invalid)."""
    e = (s or "").strip().lower()
    return e if EMAIL_RE.match(e) else None


PHONE_LIKE_RE = re.compile(r"[\d\s+/().-]{6,}")


def parse_email_field(s: str) -> tuple[str | None, list[str], str | None]:
    """The raw `email` column: (email, additional valid emails, phone number found instead of an email)."""
    raw = (s or "").strip()
    if not raw:
        return None, [], None
    if PHONE_LIKE_RE.fullmatch(raw) and re.search(r"\d{6}", re.sub(r"\D", "", raw)):
        return None, [], raw
    tokens = [t for t in re.split(r"\s+e\s+|/|;|,", raw.lower()) if t.strip()]
    valid = []
    for t in tokens:
        e = norm_email(t)
        if e and e not in valid:
            valid.append(e)
    if not valid:
        return None, [], None
    return valid[0], valid[1:], None


def norm_sku(code: str) -> str | None:
    digits = re.sub(r"\D", "", code or "")
    if not digits or len(digits) > 5:
        return None
    return "BF-" + digits.zfill(5)


def parse_quantity(s: str) -> Decimal | None:
    m = re.match(r"\s*(-?[\d.,]+)", s or "")
    if not m:
        return None
    return parse_money(m.group(1))


def parse_discount(s: str) -> Decimal:
    t = (s or "").strip().replace("%", "").strip()
    if not t:
        return Decimal(0)
    has_sep = "," in t or "." in t
    v = parse_money(t)
    if v is None:
        return Decimal(0)
    if has_sep and v < 1:
        v = v * 100
    return v.quantize(CENT, ROUND_HALF_UP)


class UnionFind:
    def __init__(self):
        self.p: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def pick(rows_desc: list[dict], col: str, valid=lambda v: bool(v.strip())) -> str:
    """Value of `col` from the most recent row (rows sorted by ultima_modifica desc) that has a valid one."""
    for r in rows_desc:
        v = r.get(col, "")
        if v is not None and valid(v):
            return v.strip()
    return ""


# ----------------------------------------------------------------------------- loading

def load_export(path: str | Path) -> dict[str, list[dict]]:
    path = Path(path)
    out: dict[str, list[dict]] = {}
    if path.is_dir():
        for name in FILES:
            with open(path / f"{name}.csv", encoding="cp1252", newline="") as f:
                out[name] = list(csv.DictReader(f, delimiter=";"))
        return _normalize(out)
    with zipfile.ZipFile(path) as zf:
        names = {Path(n).name.lower(): n for n in zf.namelist() if n.lower().endswith(".csv")}
        for name in FILES:
            member = names.get(f"{name}.csv")
            if member is None:
                raise FileNotFoundError(f"{name}.csv not in archive")
            with zf.open(member) as raw:
                text = io.TextIOWrapper(raw, encoding="cp1252", newline="")
                out[name] = list(csv.DictReader(text, delimiter=";"))
    return _normalize(out)


def _normalize(out: dict[str, list[dict]]) -> dict[str, list[dict]]:
    for rows in out.values():
        for r in rows:
            for k, v in list(r.items()):
                r[k] = fix_encoding(v or "").strip()
    return out


# ----------------------------------------------------------------------------- result

@dataclass
class Expected:
    companies: dict = field(default_factory=dict)
    contacts: dict = field(default_factory=dict)
    deals: dict = field(default_factory=dict)
    products: dict = field(default_factory=dict)
    line_items: dict = field(default_factory=dict)
    tickets: dict = field(default_factory=dict)
    notes: dict = field(default_factory=dict)
    calls: dict = field(default_factory=dict)
    emails: dict = field(default_factory=dict)
    meetings: dict = field(default_factory=dict)
    merged_into: dict = field(default_factory=lambda: {"companies": {}, "contacts": {}})
    associations: set = field(default_factory=set)
    dormant: set = field(default_factory=set)
    users: list = field(default_factory=list)
    stats: Counter = field(default_factory=Counter)


# ----------------------------------------------------------------------------- users

class Users:
    def __init__(self, rows: list[dict]):
        self.by_id: dict[str, dict] = {}
        self.full: dict[frozenset, list[dict]] = defaultdict(list)
        self.initial: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for r in rows:
            u = {"id": r["id_utente"], "email": r["email"].strip().lower(), "first": r["nome"], "last": r["cognome"],
                 "active": truthy(r["attivo"]), "manager": r["responsabile"], "role": r["ruolo"]}
            self.by_id[u["id"]] = u
            ft, lt = norm_text(u["first"]).split(), norm_text(u["last"]).split()
            self.full[frozenset(ft + lt)].append(u)
            self.initial[(ft[0][0], " ".join(lt))].append(u)

    def resolve(self, ref: str, history_users: set[str] | None = None) -> dict | None:
        ref = (ref or "").strip()
        if not ref:
            return None
        if re.fullmatch(r"(?i)u\d+", ref):
            return self.by_id.get(ref.upper())
        tokens = norm_text(ref).split()
        cands = list(self.full.get(frozenset(tokens), []))
        if not cands and len(tokens) >= 2:
            dotted = [t for t in tokens if t.endswith(".")]
            if len(dotted) == 1:
                ini = dotted[0][0]
                rest = " ".join(t for t in tokens if not t.endswith("."))
                cands = list(self.initial.get((ini, rest), []))
        if len(cands) > 1 and history_users:
            narrowed = [u for u in cands if u["id"] in history_users]
            if narrowed:
                cands = narrowed
        if len(cands) > 1:
            active = [u for u in cands if u["active"]]
            if active:
                cands = active
        return cands[0] if cands else None


# ----------------------------------------------------------------------------- migration

def migrate(data: dict[str, list[dict]]) -> Expected:
    t0 = time.time()
    ex = Expected()
    st = ex.stats
    for rows in data.values():
        for r in rows:
            for k, v in r.items():
                if isinstance(v, str):
                    r[k] = fix_encoding(v).strip()
    users = Users(data["utenti"])
    ex.users = list(users.by_id.values())

    # ---- companies
    live_co = [r for r in data["aziende"] if not truthy(r["cancellato"])]
    st["companies_deleted"] = len(data["aziende"]) - len(live_co)
    for r in live_co:
        r["_domain"] = norm_domain(r["sito_web"])
        r["_vat"] = extract_vat(r["note"]) or ""
        r["_mod"] = parse_dt(r["ultima_modifica"]) or datetime.min
    uf = UnionFind()
    by_domain: dict[str, str] = {}
    by_vat: dict[str, str] = {}
    for r in live_co:
        cid = r["id_azienda"]
        uf.find(cid)
        if r["_domain"]:
            if r["_domain"] in by_domain:
                uf.union(by_domain[r["_domain"]], cid)
            else:
                by_domain[r["_domain"]] = cid
        if r["_vat"]:
            if r["_vat"] in by_vat:
                uf.union(by_vat[r["_vat"]], cid)
            else:
                by_vat[r["_vat"]] = cid
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in live_co:
        groups[uf.find(r["id_azienda"])].append(r)
    co_survivor: dict[str, str] = {}
    domain_to_company: dict[str, str] = {}
    for rows in groups.values():
        rows.sort(key=lambda r: r["_mod"], reverse=True)
        surv = rows[0]["id_azienda"]
        for r in rows:
            co_survivor[r["id_azienda"]] = surv
            ex.merged_into["companies"][r["id_azienda"]] = surv
        domain = pick(rows, "_domain")
        others = []
        for r in rows:
            if r["_domain"] and r["_domain"] != domain and r["_domain"] not in others:
                others.append(r["_domain"])
        props = {
            "id_legacy": surv,
            "name": pick(rows, "ragione_sociale"),
            "domain": domain or None,
            "city": pick(rows, "citta") or None,
            "state": pick(rows, "provincia").upper() or None,
            "partita_iva": pick(rows, "_vat") or None,
            "_rows": [r["id_azienda"] for r in rows],
            "_additional_domains": set(others),
        }
        if len(others) == 1:
            props["hs_additional_domains"] = others[0]
        elif not others:
            props["hs_additional_domains"] = None
        for d in [domain] + others:
            if d:
                domain_to_company[d] = surv
        ex.companies[surv] = props
        if len(rows) > 1:
            st["companies_merged_groups"] += 1
            st["companies_merged_rows"] += len(rows) - 1

    # ---- contacts
    live_ct = [r for r in data["contatti"] if not truthy(r["cancellato"])]
    st["contacts_deleted"] = len(data["contatti"]) - len(live_ct)
    for r in live_ct:
        email, extra, phone_like = parse_email_field(r["email"])
        r["_email"] = email or ""
        r["_emails"] = ([email] if email else []) + extra
        r["_phone"] = r["telefono"] or (phone_like or "")
        r["_mod"] = parse_dt(r["ultima_modifica"]) or datetime.min
        r["_company"] = co_survivor.get(r["id_azienda"], "")
        r["_name"] = norm_text(r["nome"]) + "|" + norm_text(r["cognome"])
        if r["email"] and not r["_email"]:
            st["contacts_invalid_email"] += 1
        if extra:
            st["contacts_two_addresses"] += 1
        if phone_like:
            st["contacts_phone_in_email"] += 1
        if r["id_azienda"] and not r["_company"]:
            st["contacts_dangling_company"] += 1
    uf = UnionFind()
    by_email: dict[str, str] = {}
    for r in live_ct:
        cid = r["id_contatto"]
        uf.find(cid)
        for e in r["_emails"]:
            if e in by_email:
                uf.union(by_email[e], cid)
            else:
                by_email[e] = cid
    # same name inside the same company joins the same person, unless that would join two different valid emails
    comp_emails: dict[str, set[str]] = defaultdict(set)
    for r in live_ct:
        comp_emails[uf.find(r["id_contatto"])].update(r["_emails"])
    by_name_company: dict[tuple[str, str], str] = {}
    for r in live_ct:
        if not r["_company"] or r["_name"] == "|":
            continue
        key = (r["_name"], r["_company"])
        cid = r["id_contatto"]
        if key not in by_name_company:
            by_name_company[key] = cid
            continue
        ra, rb = uf.find(by_name_company[key]), uf.find(cid)
        if ra == rb:
            continue
        ea, eb = comp_emails[ra], comp_emails[rb]
        if ea and eb and not (ea & eb):
            st["contacts_name_merge_blocked_by_emails"] += 1
            continue
        uf.union(ra, rb)
        root = uf.find(ra)
        comp_emails[root] = ea | eb
        st["contacts_name_company_merges"] += 1
    cgroups: dict[str, list[dict]] = defaultdict(list)
    for r in live_ct:
        cgroups[uf.find(r["id_contatto"])].append(r)
    ct_survivor: dict[str, str] = {}
    contact_company: dict[str, str] = {}
    email_to_contact: dict[str, str] = {}
    for rows in cgroups.values():
        rows.sort(key=lambda r: r["_mod"], reverse=True)
        surv = rows[0]["id_contatto"]
        for r in rows:
            ct_survivor[r["id_contatto"]] = surv
            ex.merged_into["contacts"][r["id_contatto"]] = surv
        email = pick(rows, "_email") or None
        all_emails: list[str] = []
        for r in rows:
            for e in r["_emails"]:
                if e not in all_emails:
                    all_emails.append(e)
        extra_emails = [e for e in all_emails if e != email]
        company = pick(rows, "_company")
        tipo = norm_text(pick(rows, "tipo"))
        lifecycle = LIFECYCLE.get(tipo) or LIFECYCLE.get(tipo.replace("-", " ")) or None
        if not company and email:
            dom = email.split("@", 1)[1]
            if dom in domain_to_company:
                company = domain_to_company[dom]
                st["contacts_r12_associated"] += 1
        props = {
            "id_legacy": surv,
            "firstname": pick(rows, "nome") or None,
            "lastname": pick(rows, "cognome") or None,
            "email": email,
            "phone": pick(rows, "_phone") or None,
            "lifecyclestage": lifecycle,
            "_rows": [r["id_contatto"] for r in rows],
            "_company": company or None,
            "_additional_emails": set(extra_emails),
        }
        if len(extra_emails) == 1:
            props["hs_additional_emails"] = extra_emails[0]
        elif not extra_emails:
            props["hs_additional_emails"] = None
        ex.contacts[surv] = props
        for e in all_emails:
            email_to_contact.setdefault(e, surv)
        if company:
            contact_company[surv] = company
            ex.associations.add(("contacts", surv, "companies", company))
        if len(rows) > 1:
            st["contacts_merged_groups"] += 1
            st["contacts_merged_rows"] += len(rows) - 1

    # ---- stage history (for close dates and ambiguous user names)
    history: dict[str, list[dict]] = defaultdict(list)
    for r in data["storico_fasi"]:
        history[r["id_opportunita"]].append(r)

    # ---- products
    live_li = [r for r in data["listino"] if not truthy(r["cancellato"])]
    prod_rows: dict[str, list[dict]] = defaultdict(list)
    for r in live_li:
        sku = norm_sku(r["codice_articolo"])
        if sku:
            r["_mod"] = parse_dt(r["ultima_modifica"]) or datetime.min
            prod_rows[sku].append(r)
    for sku, rows in prod_rows.items():
        rows.sort(key=lambda r: r["_mod"], reverse=True)
        ex.products[sku] = {"hs_sku": sku, "name": pick(rows, "descrizione") or None, "price": money_str(parse_money(pick(rows, "prezzo_listino")))}
        if len(rows) > 1:
            st["products_republished"] += 1

    # ---- deals (first pass: which are live)
    live_op = [r for r in data["opportunita"] if not truthy(r["cancellato"])]
    st["deals_deleted"] = len(data["opportunita"]) - len(live_op)
    live_deal_ids = {r["id_opportunita"] for r in live_op}

    # ---- line items
    line_totals: dict[str, Decimal] = defaultdict(Decimal)
    for r in data["righe_offerta"]:
        if r["id_opportunita"] not in live_deal_ids:
            st["line_items_dropped_deal"] += 1
            continue
        sku = norm_sku(r["codice_articolo"])
        prod = ex.products.get(sku) if sku else None
        if prod is None:
            st["line_items_without_product"] += 1
        qty = parse_quantity(r["quantita"]) or Decimal(0)
        price = parse_money(r["prezzo_unitario"])
        if price is None and prod is not None and prod["price"] is not None:
            price = Decimal(prod["price"])
            st["line_items_price_from_product"] += 1
        if price is None:
            price = Decimal(0)
        disc = parse_discount(r["sconto"])
        name = r["descrizione"] or (prod["name"] if prod else None)
        amount = (qty * price * (1 - disc / 100)).quantize(CENT, ROUND_HALF_UP)
        line_totals[r["id_opportunita"]] += amount
        props = {
            "id_legacy": r["id_riga"],
            "name": name,
            "quantity": num_str(qty),
            "price": money_str(price),
            "hs_discount_percentage": num_str(disc),
            "amount": money_str(amount),
            "_product": sku if prod else None,
        }
        ex.line_items[r["id_riga"]] = props
        ex.associations.add(("line_items", r["id_riga"], "deals", r["id_opportunita"]))
        if prod is not None:
            ex.associations.add(("line_items", r["id_riga"], "products", sku))

    # ---- deals
    deal_company: dict[str, str] = {}
    deal_contacts: dict[str, set[str]] = defaultdict(set)
    for r in live_op:
        did = r["id_opportunita"]
        stage = parse_stage(r["fase"])
        pipe = parse_pipeline(r["pipeline"], stage)
        if stage is None:
            st["deals_stage_unparsed"] += 1
        elif stage[0] != pipe:
            st["deals_stage_pipeline_conflict"] += 1
            pipe = stage[0]
        code = stage[1] if stage else None
        is_closed = (pipe, code) in CLOSED_CODES
        closedate = parse_dt(r["data_chiusura"])
        if r["data_chiusura"] and closedate is None:
            st["deals_closedate_unparsed"] += 1
        if closedate is None and is_closed:
            cands = []
            for h in history.get(did, []):
                hs = parse_stage(h["fase_nuova"])
                if hs and hs[1] == code:
                    hd = parse_dt(h["data_cambio"])
                    if hd:
                        cands.append(hd)
            if cands:
                closedate = max(cands)
                st["deals_closedate_from_history"] += 1
            else:
                st["deals_closed_without_date"] += 1
        if did in line_totals:
            amount = line_totals[did].quantize(CENT, ROUND_HALF_UP)
            currency = parse_currency(r["valuta"], r["importo"])
            st["deals_amount_from_lines"] += 1
        else:
            amount = parse_money(r["importo"])
            if r["importo"] and amount is None:
                st["deals_amount_unparsed"] += 1
            currency = parse_currency(r["valuta"], r["importo"]) if amount is not None else None
        hist_users = {h["id_utente"] for h in history.get(did, []) if h["id_utente"]}
        user = users.resolve(r["id_commerciale"], hist_users)
        if r["id_commerciale"] and user is None:
            st["deals_user_unresolved"] += 1
        commerciale = user["email"] if user and user["active"] else None
        if user and not user["active"]:
            st["deals_inactive_user"] += 1
        company = co_survivor.get(r["id_azienda"], "")
        if r["id_azienda"] and not company:
            st["deals_dangling_company"] += 1
        contacts = set()
        for c in re.split(r"[;,]", r["contatti"]):
            c = c.strip()
            if not c:
                continue
            s = ct_survivor.get(c)
            if s:
                contacts.add(s)
            else:
                st["deals_dangling_contact_refs"] += 1
        props = {
            "id_legacy": did,
            "dealname": r["titolo"] or None,
            "amount": money_str(amount),
            "deal_currency_code": currency,
            "closedate": iso(closedate),
            "commerciale": commerciale,
            "_pipeline": pipe,
            "_stage_code": code,
            "_won": (pipe, code) in WON_CODES,
            "_company": company or None,
            "_contacts": sorted(contacts),
        }
        if pipe == "sales":
            props["pipeline"] = "default"
            props["dealstage"] = SALES_STAGES.get(code) if code else None
        else:
            props["_pipeline_label"] = "Rinnovi"
            props["_dealstage_label"] = RENEWAL_LABELS.get(code) if code else None
        ex.deals[did] = props
        if company:
            deal_company[did] = company
            ex.associations.add(("deals", did, "companies", company))
        for c in contacts:
            deal_contacts[did].add(c)
            ex.associations.add(("deals", did, "contacts", c))

    # ---- tickets
    for r in data["ticket"]:
        if truthy(r["cancellato"]):
            st["tickets_deleted"] += 1
            continue
        tid = r["id_ticket"]
        stato = norm_text(r["stato"])
        stage = next((label for key, label in TICKET_STAGES if key in stato), None)
        if stage is None:
            st["tickets_stage_unparsed"] += 1
        pr = norm_text(r["priorita"])
        priority = next((p for key, p in PRIORITIES if key in pr), None) if pr else None
        if pr and priority is None:
            st["tickets_priority_unparsed"] += 1
        user = users.resolve(r["id_utente"])
        assegnatario = user["email"] if user and user["active"] else None
        contact = ct_survivor.get(r["id_contatto"], "")
        if not contact:
            m = re.match(r"Da:\s*([^\s;,]+)", r["descrizione"])
            if m:
                e = norm_email(m.group(1))
                if e and e in email_to_contact:
                    contact = email_to_contact[e]
                    st["tickets_contact_from_header"] += 1
        company = co_survivor.get(r["id_azienda"], "")
        props = {
            "id_legacy": tid,
            "subject": r["oggetto"] or None,
            "content": r["descrizione"] or None,
            "hs_ticket_priority": priority,
            "createdate": iso(parse_dt(r["aperto_il"])),
            "closed_date": iso(parse_dt(r["chiuso_il"])),
            "assegnatario": assegnatario,
            "_pipeline_label": "Assistenza",
            "_stage_label": stage,
            "_contact": contact or None,
            "_company": company or None,
        }
        ex.tickets[tid] = props
        if contact:
            ex.associations.add(("tickets", tid, "contacts", contact))
        if company:
            ex.associations.add(("tickets", tid, "companies", company))

    # ---- activities
    activities_2025_contacts: set[str] = set()
    activities_2025_deals: set[str] = set()
    for r in data["attivita"]:
        if truthy(r["cancellato"]):
            st["activities_deleted"] += 1
            continue
        kind = ACTIVITY_TYPES.get(norm_text(r["tipo"]))
        if kind is None:
            st["activities_type_unparsed"] += 1
            continue
        aid = r["id_attivita"]
        when = parse_dt(r["data"])
        if when is None:
            st["activities_date_unparsed"] += 1
        user = users.resolve(r["id_utente"])
        contact = ct_survivor.get(r["id_contatto"], "")
        deal = r["id_opportunita"] if r["id_opportunita"] in live_deal_ids else ""
        props = {
            "id_legacy": aid,
            "hs_timestamp": iso(when),
            BODY_PROP[kind]: r["testo"] or None,
            "autore": user["email"] if user else None,
            "_contact": contact or None,
            "_deal": deal or None,
        }
        getattr(ex, kind)[aid] = props
        if contact:
            ex.associations.add((kind, aid, "contacts", contact))
        if deal:
            ex.associations.add((kind, aid, "deals", deal))
        if when and when.year == 2025:
            if contact:
                activities_2025_contacts.add(contact)
            if deal:
                activities_2025_deals.add(deal)
        if not contact and not deal:
            st["activities_without_links"] += 1

    # ---- R8 revenue and class
    revenue: dict[str, Decimal] = defaultdict(Decimal)
    won_companies: set[str] = set()
    for did, d in ex.deals.items():
        co = d["_company"]
        if not co or not d["_won"]:
            continue
        won_companies.add(co)
        if d["amount"] is None or not d["closedate"] or not d["closedate"].startswith("2025"):
            continue
        revenue[co] += Decimal(d["amount"]) * RATES[d["deal_currency_code"]]
    for co, props in ex.companies.items():
        total = revenue.get(co, Decimal(0)).quantize(CENT, ROUND_HALF_UP)
        props["fatturato_2025"] = str(total)
        if total >= 100000:
            cls = "A"
        elif total >= 20000:
            cls = "B"
        elif total > 0:
            cls = "C"
        else:
            cls = None
        props["classe_cliente"] = cls
        st[f"class_{cls or 'none'}"] += 1

    # ---- R9 dormant
    company_contacts: dict[str, set[str]] = defaultdict(set)
    for c, co in contact_company.items():
        company_contacts[co].add(c)
    company_deals: dict[str, set[str]] = defaultdict(set)
    for did, co in deal_company.items():
        company_deals[co].add(did)
    for co in won_companies:
        if company_contacts[co] & activities_2025_contacts:
            continue
        if company_deals[co] & activities_2025_deals:
            continue
        ex.dormant.add(co)

    for ot in OBJECT_TYPES:
        st[f"count_{ot}"] = len(getattr(ex, ot))
    st["associations"] = len(ex.associations)
    st["dormant"] = len(ex.dormant)
    st["seconds"] = round(time.time() - t0, 1)
    return ex


def summary(ex: Expected) -> str:
    lines = []
    for k in sorted(ex.stats):
        lines.append(f"{k:40s} {ex.stats[k]}")
    return "\n".join(lines)


def to_json(ex: Expected) -> dict:
    def clean(d):
        return {k: (sorted(v) if isinstance(v, set) else v) for k, v in d.items()}
    return {
        **{ot: {k: clean(v) for k, v in getattr(ex, ot).items()} for ot in OBJECT_TYPES},
        "merged_into": ex.merged_into,
        "associations": sorted(ex.associations),
        "dormant": sorted(ex.dormant),
        "stats": dict(ex.stats),
    }


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "legacy/export.zip"
    ex = migrate(load_export(src))
    print(summary(ex))
    if "--json" in sys.argv:
        out = sys.argv[sys.argv.index("--json") + 1]
        Path(out).write_text(json.dumps(to_json(ex), ensure_ascii=False))
        print(f"written {out}")

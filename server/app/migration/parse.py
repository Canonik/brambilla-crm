"""Normalisers for the Sinergia 4 export. Every shape seen in the data is handled here."""
from __future__ import annotations

import datetime as dt
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from ..util import UTC, normalize_domain, valid_email

TRUE_SET = {"s", "si", "sì", "1", "y", "yes", "true", "x", "vero"}


def is_deleted(v: str | None) -> bool:
    return (v or "").strip().lower() in TRUE_SET


def is_true(v: str | None) -> bool:
    return (v or "").strip().lower() in TRUE_SET


def fix_text(s: str | None) -> str:
    """Repair UTF-8 text that was read as cp1252 (e.g. 'SocietÃ\xa0' -> 'Società')."""
    if not s:
        return ""
    if any(ch in s for ch in ("Ã", "â", "Â")) or any(0xDC80 <= ord(c) <= 0xDCFF for c in s):
        try:
            return s.encode("cp1252", "surrogateescape").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    try:
        return s.encode("utf-8", "surrogateescape").decode("utf-8", "replace")
    except Exception:
        return s


def clean(s: str | None) -> str:
    return fix_text(s).strip()


# ------------------------------------------------------------------ dates
_DMY = re.compile(r"^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})(?:[ T](\d{1,2})[:.](\d{2})(?:[:.](\d{2}))?)?$")
_YMD = re.compile(r"^(\d{4})[/.\-](\d{1,2})[/.\-](\d{1,2})(?:[ T](\d{1,2})[:.](\d{2})(?:[:.](\d{2}))?(?:\.\d+)?Z?)?$")
_EXCEL_EPOCH = dt.datetime(1899, 12, 30, tzinfo=UTC)


def parse_dt(s: str | None) -> dt.datetime | None:
    if s is None:
        return None
    s = s.strip()
    if not s:
        return None
    m = _DMY.match(s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000 if y < 70 else 1900
        hh, mm, ss = int(m.group(4) or 0), int(m.group(5) or 0), int(m.group(6) or 0)
        try:
            return dt.datetime(y, mo, d, hh, mm, ss, tzinfo=UTC)
        except ValueError:
            try:  # maybe month/day swapped
                return dt.datetime(y, d, mo, hh, mm, ss, tzinfo=UTC)
            except ValueError:
                return None
    m = _YMD.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        hh, mm, ss = int(m.group(4) or 0), int(m.group(5) or 0), int(m.group(6) or 0)
        try:
            return dt.datetime(y, mo, d, hh, mm, ss, tzinfo=UTC)
        except ValueError:
            return None
    if re.fullmatch(r"\d{4,6}", s):  # excel serial
        n = int(s)
        if 20000 < n < 80000:
            return _EXCEL_EPOCH + dt.timedelta(days=n)
    if re.fullmatch(r"\d{4,6}(\.\d+)?", s):
        n = float(s)
        if 20000 < n < 80000:
            return _EXCEL_EPOCH + dt.timedelta(days=n)
    if re.fullmatch(r"\d{12,13}", s):
        return dt.datetime.fromtimestamp(int(s) / 1000, tz=UTC)
    if re.fullmatch(r"\d{9,10}", s):
        return dt.datetime.fromtimestamp(int(s), tz=UTC)
    from ..util import parse_datetime
    return parse_datetime(s)


# ------------------------------------------------------------------ numbers
_CUR_PREFIX = re.compile(r"^(EUR|USD|GBP|CHF|€|\$|£)\s*", re.I)
_CUR_SUFFIX = re.compile(r"\s*(EUR|USD|GBP|CHF|€|\$|£)$", re.I)
CURRENCY_MAP = {"eur": "EUR", "euro": "EUR", "€": "EUR", "usd": "USD", "$": "USD", "dollari": "USD", "gbp": "GBP", "£": "GBP", "sterline": "GBP", "chf": "CHF"}


def parse_number(s: str | None) -> Decimal | None:
    """Parse '1.234,56', '1,234.56', '1234.56', '1234,56', '€ 1.234,56', '(1.234,56)', '-5.131,24', '20 pz'."""
    if s is None:
        return None
    s = s.strip()
    if not s:
        return None
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1].strip()
    s = _CUR_PREFIX.sub("", s).strip()
    s = _CUR_SUFFIX.sub("", s).strip()
    if s.endswith("-"):
        neg = not neg
        s = s[:-1].strip()
    if s.startswith("-"):
        neg = not neg
        s = s[1:].strip()
    elif s.startswith("+"):
        s = s[1:].strip()
    s = re.sub(r"\s*[A-Za-z%.]+\s*$", lambda m: "" if re.search(r"[A-Za-z%]", m.group(0)) else m.group(0), s).strip()
    s = s.replace(" ", "")
    if not s:
        return None
    if re.fullmatch(r"\d{1,3}(\.\d{3})+,\d+", s) or re.fullmatch(r"\d{1,3}(\.\d{3}){2,}", s):
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(,\d{3})+\.\d+", s) or re.fullmatch(r"\d{1,3}(,\d{3}){2,}", s):
        s = s.replace(",", "")
    elif re.fullmatch(r"\d+,\d+", s):
        s = s.replace(",", ".")
    elif re.fullmatch(r"\d+\.\d+", s):
        pass
    elif re.fullmatch(r"\d+", s):
        pass
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    elif re.fullmatch(r"\d{1,3}(,\d{3})+", s):
        s = s.replace(",", "")
    else:
        return None
    try:
        d = Decimal(s)
    except InvalidOperation:
        return None
    return -d if neg else d


_MULT = re.compile(r"^(.*?)\s*(k|mila|mln|milioni|milione|mio|m)$", re.I)
_MONTHLY = re.compile(r"\s*(/\s*mese|al\s+mese|mensil[ei]|mensile|/\s*m)\s*$", re.I)
_YEARLY = re.compile(r"\s*(/\s*anno|all'anno|annui|annuo|annuale|annuali)\s*$", re.I)


def parse_amount(importo: str | None) -> Decimal | None:
    """Deal amount: everything parse_number does plus '73k', '6.5mila', '1,2 mln', '500,59 /mese' (x12), '4,086.16-'."""
    if importo is None:
        return None
    s = importo.strip()
    if not s:
        return None
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1].strip()
    s = _CUR_PREFIX.sub("", s).strip()
    s = _CUR_SUFFIX.sub("", s).strip()
    monthly = False
    if _MONTHLY.search(s):
        s = _MONTHLY.sub("", s).strip()
        monthly = True
    elif _YEARLY.search(s):
        s = _YEARLY.sub("", s).strip()
    s = _CUR_SUFFIX.sub("", s).strip()
    if s.endswith("-"):
        neg = not neg
        s = s[:-1].strip()
    if s.startswith("-"):
        neg = not neg
        s = s[1:].strip()
    mult = Decimal(1)
    m = _MULT.match(s)
    if m and re.search(r"\d", m.group(1)):
        unit = m.group(2).lower()
        mult = Decimal(1000) if unit in ("k", "mila") else Decimal(1_000_000)
        s = m.group(1).strip()
        core = s.replace(" ", "")
        # with a multiplier a lone separator is always decimal ("4.5 k", "206,5k")
        if re.fullmatch(r"\d+[.,]\d+", core):
            core = core.replace(",", ".")
            v = Decimal(core)
        else:
            v = parse_number(core)
    else:
        v = parse_number(s)
    if v is None:
        return None
    v = v * mult
    if monthly:
        v = v * 12
    return -v if neg else v


def parse_currency(importo: str | None, valuta: str | None) -> str | None:
    v = (valuta or "").strip().lower()
    if v:
        c = CURRENCY_MAP.get(v)
        if c:
            return c
        if len(v) == 3 and v.isalpha():
            return v.upper()
    s = (importo or "").strip().lower()
    if "usd" in s or "$" in s:
        return "USD"
    if "gbp" in s or "£" in s:
        return "GBP"
    if "chf" in s:
        return "CHF"
    if "eur" in s or "€" in s:
        return "EUR"
    return None


def parse_percent(s: str | None) -> Decimal:
    if s is None:
        return Decimal(0)
    s = s.strip()
    if not s:
        return Decimal(0)
    had_pct = "%" in s
    s = s.replace("%", "").strip()
    v = parse_number(s)
    if v is None:
        return Decimal(0)
    if not had_pct and 0 < abs(v) < 1:
        v = v * 100
    return v


def money(d: Decimal) -> Decimal:
    return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def num_str(d: Decimal | None) -> str | None:
    if d is None:
        return None
    d = d.normalize()
    if d == d.to_integral_value():
        return str(int(d))
    return format(d, "f")


# ------------------------------------------------------------------ codes, vat, emails
def product_code(s: str | None) -> str | None:
    if not s:
        return None
    digits = re.sub(r"\D", "", fix_text(s))
    if not digits:
        return None
    digits = digits.lstrip("0") or "0"
    return "BF-" + digits.zfill(5)


_VAT_RE = re.compile(r"(?:p\.?\s*iva|partita\s+iva|p\.?\s*i\.?|piva|vat)\s*[:.]?\s*(?:n\.?\s*)?(?:it\s*)?((?:\d[\s.]?){11})(?!\d)", re.I)
_VAT_LOOSE = re.compile(r"(?<!\d)IT\s?(\d{11})(?!\d)", re.I)


def extract_vat(note: str | None) -> str | None:
    if not note:
        return None
    m = _VAT_RE.search(note)
    if m:
        d = re.sub(r"\D", "", m.group(1))
        if len(d) == 11:
            return d
    m = _VAT_LOOSE.search(note)
    if m:
        return m.group(1)
    return None


def normalize_vat(s: str | None) -> str | None:
    if not s:
        return None
    d = re.sub(r"\D", "", re.sub(r"^\s*IT", "", s.strip(), flags=re.I))
    return d if len(d) == 11 else None


def parse_email(s: str | None) -> str | None:
    emails, _ = parse_emails(s)
    return emails[0] if emails else None


_PHONE_RE = re.compile(r"^\+?[\d\s/().-]{6,}$")
_EMAIL_SIMPLE = re.compile(r"^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$")


def parse_emails(s: str | None) -> tuple[list[str], str | None]:
    """All valid addresses in the field (lower-cased, in order) and a phone number if the field holds one instead."""
    if not s:
        return [], None
    raw = fix_text(s).strip()
    if not raw:
        return [], None
    if "@" not in raw and _PHONE_RE.match(raw) and re.search(r"\d{6}", re.sub(r"\D", "", raw)):
        return [], raw
    tokens = re.split(r"\s+e\s+|/|;|,", raw.lower())
    out = []
    for t in tokens:
        t = t.strip().strip("<>\"'")
        if t and _EMAIL_SIMPLE.match(t) and t not in out:
            out.append(t)
    return out, None


def split_ids(s: str | None) -> list[str]:
    if not s:
        return []
    out = []
    for x in re.split(r"[;,/|\s]+", s):
        x = x.strip()
        if x and x not in out:
            out.append(x)
    return out


# ------------------------------------------------------------------ enumerations
LIFECYCLE = {"cliente": "customer", "clienti": "customer", "customer": "customer", "prospect": "opportunity", "opportunity": "opportunity", "lead": "lead", "ex cliente": "other", "excliente": "other", "ex-cliente": "other", "ex": "other", "other": "other", "altro": "other"}


def lifecycle_stage(s: str | None) -> str | None:
    v = clean(s).lower()
    v = re.sub(r"\s+", " ", v)
    if not v:
        return None
    if v in LIFECYCLE:
        return LIFECYCLE[v]
    v2 = v.replace("-", " ").replace("_", " ")
    if v2 in LIFECYCLE:
        return LIFECYCLE[v2]
    if v2.startswith("ex"):
        return "other"
    for k, val in LIFECYCLE.items():
        if k in v2:
            return val
    return None


SALES_STAGES = ["appointmentscheduled", "qualifiedtobuy", "presentationscheduled", "decisionmakerboughtin", "contractsent", "closedwon", "closedlost"]
SALES_KEYWORDS = [("contatto", 0), ("qualifica", 1), ("presentazione", 2), ("decisione", 3), ("contratto", 4), ("vinta", 5), ("vinto", 5), ("persa", 6), ("perso", 6)]
RENEWAL_KEYWORDS = [("non rinnovato", 3), ("non rinnovata", 3), ("rinnovato", 2), ("rinnovata", 2), ("da rinnovare", 0), ("in trattativa", 1), ("trattativa", 1), ("rinnovare", 0)]


def deal_stage(fase: str | None, pipeline: str | None) -> tuple[str, int] | None:
    """Return ('sales'|'renewal', index) or None."""
    f = clean(fase).lower()
    f = re.sub(r"\s+", " ", f)
    p = clean(pipeline).lower()
    if not f:
        return None
    m = re.match(r"^r\s?([1-4])\b", f)
    if m:
        return ("renewal", int(m.group(1)) - 1)
    m = re.match(r"^0?([1-7])\b", f)
    if m and not re.match(r"^\d{2,}", f.replace("0", "", 1) if f.startswith("0") else f + "x"):
        pass
    m = re.match(r"^(0[1-7]|[1-7])(?:\s*[-:._]?\s*|$)", f)
    if m:
        return ("sales", int(m.group(1)) - 1)
    for kw, idx in RENEWAL_KEYWORDS:
        if kw in f:
            return ("renewal", idx)
    for kw, idx in SALES_KEYWORDS:
        if kw in f:
            return ("sales", idx)
    return None


def pipeline_family(pipeline: str | None) -> str | None:
    p = clean(pipeline).lower()
    if not p:
        return None
    if "rinnov" in p or "renew" in p:
        return "renewal"
    if "vend" in p or "sales" in p or p == "default":
        return "sales"
    return None


TICKET_STAGES = ["Aperto", "In lavorazione", "In attesa del cliente", "Chiuso"]


def ticket_stage(stato: str | None) -> int:
    s = clean(stato).lower()
    if not s:
        return 0
    if "chius" in s or "risol" in s or "closed" in s or "resolved" in s:
        return 3
    if "attesa" in s or "waiting" in s or "pending" in s:
        return 2
    if "lavor" in s or "progress" in s or "corso" in s:
        return 1
    return 0


def ticket_priority(p: str | None) -> str | None:
    s = clean(p).lower()
    if not s:
        return None
    if "urgent" in s or s.startswith("4"):
        return "URGENT"
    if "alta" in s or "high" in s or s.startswith("3"):
        return "HIGH"
    if "bassa" in s or "low" in s or s.startswith("1"):
        return "LOW"
    if "media" in s or "normale" in s or "medium" in s or s.startswith("2"):
        return "MEDIUM"
    return None


ACTIVITY_TYPES = {"nota": "notes", "note": "notes", "appunto": "notes", "chiamata": "calls", "telefonata": "calls", "tel.": "calls", "tel": "calls", "call": "calls", "e-mail": "emails", "email": "emails", "mail": "emails", "incontro": "meetings", "meeting": "meetings", "riunione": "meetings", "visita": "meetings"}


def activity_type(tipo: str | None) -> str | None:
    t = clean(tipo).lower()
    if not t:
        return None
    if t in ACTIVITY_TYPES:
        return ACTIVITY_TYPES[t]
    for k, v in ACTIVITY_TYPES.items():
        if t.startswith(k):
            return v
    if "mail" in t:
        return "emails"
    if "tel" in t or "chiam" in t:
        return "calls"
    if "visit" in t or "incontr" in t or "riun" in t or "meet" in t:
        return "meetings"
    if "not" in t or "app" in t:
        return "notes"
    return None


def domain_of(site: str | None) -> str | None:
    return normalize_domain(clean(site))


# ------------------------------------------------------------------ users
class Users:
    def __init__(self, rows: list[dict]):
        self.by_id: dict[str, dict] = {}
        for r in rows:
            uid = clean(r.get("id_utente")).upper()
            if not uid:
                continue
            self.by_id[uid] = {
                "id": uid,
                "firstname": clean(r.get("nome")),
                "lastname": clean(r.get("cognome")),
                "email": clean(r.get("email")).lower(),
                "role": clean(r.get("ruolo")),
                "manager": clean(r.get("responsabile")).upper() or None,
                "active": is_true(r.get("attivo")),
            }
        self.by_email = {u["email"]: u for u in self.by_id.values() if u["email"]}
        self.by_name: dict[str, list[dict]] = {}
        for u in self.by_id.values():
            fn, ln = u["firstname"].lower(), u["lastname"].lower()
            variants = set()
            if fn and ln:
                variants.update({f"{fn} {ln}", f"{ln} {fn}", f"{fn[0]}. {ln}", f"{ln} {fn[0]}.", f"{fn[0]} {ln}", f"{ln} {fn[0]}", f"{fn}{ln}", f"{ln}{fn}"})
            for v in variants:
                self.by_name.setdefault(v, []).append(u)

    def resolve(self, raw: str | None, hint_ids: set[str] | None = None) -> dict | None:
        s = clean(raw)
        if not s:
            return None
        up = s.upper().replace(" ", "")
        if up in self.by_id:
            return self.by_id[up]
        m = re.fullmatch(r"U?0*(\d+)", up)
        if m:
            cand = "U" + m.group(1).zfill(2)
            if cand in self.by_id:
                return self.by_id[cand]
        if "@" in s:
            return self.by_email.get(s.lower())
        key = re.sub(r"\s+", " ", s.lower()).strip()
        key = re.sub(r"\s*\.\s*", ". ", key).strip()
        key = re.sub(r"\s+", " ", key)
        cands = self.by_name.get(key)
        if cands:
            return self._pick(cands, hint_ids)
        # try without accents
        import unicodedata
        def strip_acc(x):
            return "".join(c for c in unicodedata.normalize("NFD", x) if unicodedata.category(c) != "Mn")
        key2 = strip_acc(key)
        for k, v in self.by_name.items():
            if strip_acc(k) == key2:
                return self._pick(v, hint_ids)
        return None

    @staticmethod
    def _pick(cands: list[dict], hint_ids: set[str] | None) -> dict:
        if len(cands) == 1:
            return cands[0]
        if hint_ids:
            for c in cands:
                if c["id"] in hint_ids:
                    return c
        for c in cands:
            if c["active"]:
                return c
        return cands[0]

    def effective(self, u: dict | None) -> dict | None:
        """The user who follows the record today: only users still active; who left follows nothing."""
        if u is None or not u["active"]:
            return None
        return u

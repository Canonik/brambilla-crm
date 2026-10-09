import datetime as dt
import re
from decimal import Decimal, InvalidOperation

UTC = dt.timezone.utc


def utcnow() -> dt.datetime:
    return dt.datetime.now(UTC)


def iso(d: dt.datetime) -> str:
    if d.tzinfo is None:
        d = d.replace(tzinfo=UTC)
    d = d.astimezone(UTC)
    return d.strftime("%Y-%m-%dT%H:%M:%S.") + f"{d.microsecond // 1000:03d}Z"


def now_iso() -> str:
    return iso(utcnow())


def to_ms(d: dt.datetime) -> int:
    if d.tzinfo is None:
        d = d.replace(tzinfo=UTC)
    return int(d.timestamp() * 1000)


_ISO_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,6}))?)?)?\s*(Z|[+-]\d{2}:?\d{2})?$")


def parse_datetime(value) -> dt.datetime | None:
    """Accept ms epoch (int/str), ISO 8601, or date; return aware UTC datetime."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        if abs(v) < 1e11:  # seconds
            v *= 1000
        return dt.datetime.fromtimestamp(v / 1000, tz=UTC)
    s = str(value).strip()
    if not s:
        return None
    if re.fullmatch(r"-?\d{11,}", s):
        return dt.datetime.fromtimestamp(int(s) / 1000, tz=UTC)
    if re.fullmatch(r"\d{9,10}", s):
        return dt.datetime.fromtimestamp(int(s), tz=UTC)
    m = _ISO_RE.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        hh = int(m.group(4) or 0)
        mm = int(m.group(5) or 0)
        ss = int(m.group(6) or 0)
        frac = m.group(7) or "0"
        us = int((frac + "000000")[:6])
        tz = m.group(8)
        try:
            base = dt.datetime(y, mo, d, hh, mm, ss, us)
        except ValueError:
            return None
        if tz and tz != "Z":
            sign = 1 if tz[0] == "+" else -1
            tz = tz[1:].replace(":", "")
            off = dt.timedelta(hours=int(tz[:2]), minutes=int(tz[2:]))
            base = base.replace(tzinfo=dt.timezone(sign * off))
        else:
            base = base.replace(tzinfo=UTC)
        return base.astimezone(UTC)
    try:
        d2 = dt.datetime.fromisoformat(s)
        if d2.tzinfo is None:
            d2 = d2.replace(tzinfo=UTC)
        return d2.astimezone(UTC)
    except ValueError:
        pass
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return dt.datetime.strptime(s, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def normalize_number(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        d = Decimal(str(value))
    else:
        s = str(value).strip()
        if not s:
            return None
        try:
            d = Decimal(s)
        except InvalidOperation:
            s2 = s.replace(" ", "")
            if re.fullmatch(r"-?\d{1,3}(\.\d{3})+(,\d+)?", s2):
                s2 = s2.replace(".", "").replace(",", ".")
            elif re.fullmatch(r"-?\d+,\d+", s2):
                s2 = s2.replace(",", ".")
            else:
                s2 = s2.replace(",", "")
            try:
                d = Decimal(s2)
            except InvalidOperation:
                return None
    if d == d.to_integral_value():
        return str(int(d))
    s = format(d.normalize(), "f")
    return s


def fmt_money(x: float | Decimal) -> str:
    d = Decimal(str(x)).quantize(Decimal("0.01"))
    s = format(d, "f")
    return s


EMAIL_RE = re.compile(r"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)*\.[A-Za-z]{2,}$")


def valid_email(s: str) -> bool:
    if not s or len(s) > 254:
        return False
    if ".." in s or s.startswith(".") or "@." in s or ".@" in s:
        return False
    return bool(EMAIL_RE.match(s))


def email_domain(email: str) -> str | None:
    if not email or "@" not in email:
        return None
    return email.rsplit("@", 1)[1].lower()


def normalize_domain(s: str | None) -> str | None:
    if not s:
        return None
    s = s.strip().lower()
    s = re.sub(r"^[a-z]+://", "", s)
    s = s.split("/")[0].split("?")[0].split("#")[0]
    s = s.split("@")[-1]
    s = s.split(":")[0]
    s = re.sub(r"^www\.", "", s)
    s = s.strip(". ")
    return s or None

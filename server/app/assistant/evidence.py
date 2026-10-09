"""Bounded, request-local behavioral provenance for the assistant UI.

This module never executes tools, reads the database, or sees model prompts.  It
projects allowlisted metadata from tool dispatch/results.  It is deliberately
not chain-of-thought, model confidence, or proof that a retrieved record caused
the final answer.
"""
from __future__ import annotations

import re
import time
import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any


MAX_EVENTS = 64
MAX_RECORDS = 20
MAX_RELATIONS = 40
MAX_CALLS = 32
MAX_COUNT = 1_000_000
MAX_FACTS = 32
MAX_SEARCHES = 12
MAX_AUTOMATIONS = 12
# Failure categories are a closed set derived from the numeric status a tool
# reported, never from error text.
FAILURES = {400: "validation", 404: "not_found", 409: "conflict", 429: "rate_limited"}
FAILURE_KINDS = frozenset(("validation", "not_found", "conflict", "rate_limited", "rejected", "error"))
LIST_TOOLS = frozenset(
    ("search_companies", "search_contacts", "search_deals", "search_tickets",
     "my_customers", "dormant_list", "list_activities", "list_users",
     "find_by_legacy_id", "search_products", "list_deal_line_items")
)
RECORD_TYPES = frozenset(
    ("companies", "contacts", "deals", "tickets", "products", "line_items",
     "notes", "calls", "emails", "meetings", "tasks")
)
DECISION_WRITE_TOOLS = frozenset(
    ("create_record", "update_record", "associate", "archive_record",
     "import_attachment", "create_records_bulk")
)

# Tool names and labels are application-owned.  No model-supplied label reaches
# the UI.  Input summaries below are also fixed templates with safe ids only.
TOOLS: dict[str, tuple[str, str]] = {
    "search_companies": ("read", "Searched companies"),
    "search_contacts": ("read", "Searched contacts"),
    "search_deals": ("read", "Searched deals"),
    "search_tickets": ("read", "Searched tickets"),
    "get_record": ("read", "Retrieved a CRM record"),
    "company_overview": ("read", "Retrieved company overview"),
    "list_activities": ("read", "Retrieved activities"),
    "revenue": ("read", "Calculated revenue"),
    "deal_stats": ("read", "Calculated deal statistics"),
    "my_customers": ("read", "Retrieved assigned customers"),
    "list_users": ("read", "Retrieved active users"),
    "pipelines": ("read", "Retrieved pipelines"),
    "dormant_list": ("read", "Retrieved dormant customers"),
    "find_by_legacy_id": ("read", "Looked up a Sinergia legacy id"),
    "search_products": ("read", "Searched the price list"),
    "list_deal_line_items": ("read", "Retrieved deal line items"),
    "preview_attachment": ("read", "Previewed a CSV attachment"),
    "create_record": ("write", "Created a CRM record"),
    "update_record": ("write", "Updated a CRM record"),
    "associate": ("write", "Associated CRM records"),
    "dissociate": ("write", "Removed a CRM association"),
    "archive_record": ("write", "Archived a CRM record"),
    "create_records_bulk": ("write", "Created CRM records in bulk"),
    "import_attachment": ("write", "Imported a CSV attachment"),
}


def _canonical_id(value: Any) -> str | None:
    value = str(value) if isinstance(value, int) and value > 0 else value
    return value if isinstance(value, str) and re.fullmatch(r"[1-9][0-9]{0,19}", value) else None


def _object_type(value: Any) -> str | None:
    value = str(value or "").strip().lower().replace("-", "_")
    aliases = {"company": "companies", "contact": "contacts", "deal": "deals", "ticket": "tickets"}
    value = aliases.get(value, value)
    return value if value in RECORD_TYPES else None


def _safe_summary(tool: str, args: dict) -> str:
    ot = _object_type(args.get("object_type") or args.get("type"))
    id_ = _canonical_id(args.get("id"))
    if tool == "revenue":
        cid = _canonical_id(args.get("company_id"))
        year = args.get("year")
        return f"Revenue for company #{cid or 'unknown'} in {year if isinstance(year, int) else 'the requested year'}"
    if tool in ("get_record", "update_record", "archive_record") and ot and id_:
        return f"{ot} #{id_}"
    if tool == "company_overview":
        cid = _canonical_id(args.get("company_id"))
        return f"Company #{cid}" if cid else "Company overview"
    if tool in ("associate", "dissociate"):
        ft, tt = _object_type(args.get("from_type")), _object_type(args.get("to_type"))
        fid, tid = _canonical_id(args.get("from_id")), _canonical_id(args.get("to_id"))
        if ft and tt and fid and tid:
            return f"{ft} #{fid} to {tt} #{tid}"
    if tool == "create_record" and ot:
        return f"New {ot} record"
    if tool == "create_records_bulk" and ot:
        records = args.get("records")
        count = len(records) if isinstance(records, list) else 0
        return f"Up to {min(count, 200)} new {ot} records"
    return TOOLS.get(tool, ("read", "Observed CRM operation"))[1]


def _records(tool: str, args: dict, result: Any) -> tuple[list[dict[str, str]], list[dict[str, dict[str, str]]], bool]:
    """Extract identifiers, and the links between them that the tool itself read,
    only from documented result shapes and safe id args."""
    found: list[dict[str, str]] = []
    relations: list[dict[str, dict[str, str]]] = []
    seen: set[tuple[str, str]] = set()
    linked: set[tuple[str, str, str, str]] = set()
    incomplete = False

    def add(type_value: Any, id_value: Any) -> None:
        nonlocal incomplete
        ot, id_ = _object_type(type_value), _canonical_id(id_value)
        if not ot or not id_:
            return
        key = (ot, id_)
        if key in seen:
            return
        if len(found) >= MAX_RECORDS:
            incomplete = True
            return
        seen.add(key)
        found.append({"type": ot, "id": id_})

    def link(from_type: Any, from_id: Any, to_type: Any, to_id: Any) -> None:
        """A relation is kept only when both ends were already accepted as records."""
        nonlocal incomplete
        ft, fid, tt, tid = _object_type(from_type), _canonical_id(from_id), _object_type(to_type), _canonical_id(to_id)
        if not ft or not fid or not tt or not tid or (ft, fid) == (tt, tid):
            return
        if (ft, fid) not in seen or (tt, tid) not in seen:
            return
        key = (ft, fid, tt, tid)
        if key in linked or (tt, tid, ft, fid) in linked:
            return
        if len(relations) >= MAX_RELATIONS:
            incomplete = True
            return
        linked.add(key)
        relations.append({"from": {"type": ft, "id": fid}, "to": {"type": tt, "id": tid}})

    if not isinstance(result, dict):
        return found, relations, incomplete

    search_types = {
        "search_companies": "companies", "search_contacts": "contacts",
        "search_deals": "deals", "search_tickets": "tickets",
        "my_customers": "companies", "dormant_list": "companies",
    }
    if tool in search_types:
        values = result.get("results")
        if isinstance(values, list):
            for row in values:
                if isinstance(row, dict):
                    add(search_types[tool], row.get("id"))
            # contact/deal/ticket briefs carry the company the store resolved
            # through its stored associations: an observed link, not a guess.
            if search_types[tool] != "companies":
                for row in values:
                    if isinstance(row, dict) and row.get("company_id") is not None:
                        add("companies", row.get("company_id"))
                        link(search_types[tool], row.get("id"), "companies", row.get("company_id"))
    elif tool == "get_record":
        own_type, own_id = result.get("object_type") or args.get("object_type"), result.get("id")
        add(own_type, own_id)
        assoc = result.get("associations")
        if isinstance(assoc, dict):
            for object_type, rows in assoc.items():
                if isinstance(rows, list):
                    for row in rows:
                        if isinstance(row, dict):
                            add(object_type, row.get("id"))
                            link(own_type, own_id, object_type, row.get("id"))
    elif tool == "company_overview":
        company = result.get("company")
        company_id = company.get("id") if isinstance(company, dict) else None
        add("companies", company_id)
        for key, ot in (("contacts", "contacts"), ("deals", "deals"), ("tickets", "tickets"), ("last_activities", None)):
            rows = result.get(key)
            if isinstance(rows, list):
                for row in rows:
                    if isinstance(row, dict):
                        add(ot or row.get("type"), row.get("id"))
                        link("companies", company_id, ot or row.get("type"), row.get("id"))
    elif tool == "list_activities":
        rows = result.get("results")
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    add(row.get("type"), row.get("id"))
    elif tool == "find_by_legacy_id":
        rows = result.get("results")
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    add(row.get("object_type"), row.get("id"))
    elif tool == "search_products":
        rows = result.get("results")
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    add("products", row.get("id"))
    elif tool == "list_deal_line_items":
        deal_id = result.get("deal_id")
        add("deals", deal_id)
        rows = result.get("results")
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    add("line_items", row.get("id"))
                    link("deals", deal_id, "line_items", row.get("id"))
                    product = row.get("product")
                    if isinstance(product, dict):
                        add("products", product.get("id"))
                        link("line_items", row.get("id"), "products", product.get("id"))
    elif tool == "import_attachment":
        # Rows the import created or updated are the only records it vouches for;
        # skipped and failed rows did not change the CRM.
        for key in ("created", "updated"):
            rows = result.get(key)
            if isinstance(rows, list):
                for row in rows:
                    if isinstance(row, dict):
                        add(row.get("object_type"), row.get("id"))
    elif tool == "revenue":
        add("companies", result.get("company_id"))
        rows = result.get("won_deals")
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    add("deals", row.get("id"))
                    link("companies", result.get("company_id"), "deals", row.get("id"))
    elif tool == "update_record":
        add(result.get("object_type") or args.get("object_type"), result.get("id"))
    elif tool == "create_record":
        own_type, own_id = result.get("object_type") or args.get("object_type"), result.get("id")
        add(own_type, own_id)
        targets = args.get("associations")
        if result.get("ok") is True and isinstance(targets, list):
            for target in targets[:MAX_RECORDS]:
                if isinstance(target, dict):
                    add(target.get("object_type") or target.get("type"), target.get("id"))
                    link(own_type, own_id, target.get("object_type") or target.get("type"), target.get("id"))
    elif tool == "create_records_bulk":
        rows = result.get("results")
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict) and row.get("ok") is True:
                    add(row.get("object_type") or args.get("object_type"), row.get("id"))
    elif tool in ("associate", "dissociate") and result.get("ok") is True:
        add(args.get("from_type"), args.get("from_id"))
        add(args.get("to_type"), args.get("to_id"))
        link(args.get("from_type"), args.get("from_id"), args.get("to_type"), args.get("to_id"))
    elif tool == "archive_record" and result.get("ok") is True:
        add(args.get("object_type"), args.get("id"))

    return found, relations, incomplete


def _bounded_count(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 0 <= value <= MAX_COUNT else None


def _counts(tool: str, result: Any) -> tuple[int | None, int | None]:
    """Row counts for list-shaped reads: how many rows came back, and the store total when reported."""
    if tool not in LIST_TOOLS or not isinstance(result, dict):
        return None, None
    rows = result.get("results")
    count = min(len(rows), MAX_COUNT) if isinstance(rows, list) else None
    return count, _bounded_count(result.get("total"))


_MONEY = re.compile(r"-?(?:0|[1-9][0-9]{0,11})\.[0-9]{2}")
_RESULT_MONEY = re.compile(r"-?(?:0|[1-9][0-9]{0,13})\.[0-9]{2}")


def _calculation(tool: str, result: Any) -> tuple[dict | None, bool]:
    if tool != "revenue" or not isinstance(result, dict):
        return None, False
    rows = result.get("won_deals")
    total = result.get("total_eur")
    if not isinstance(rows, list) or not isinstance(total, str) or not _RESULT_MONEY.fullmatch(total):
        return None, True
    if len(rows) > MAX_RECORDS:
        return None, True
    terms = []
    for row in rows:
        if not isinstance(row, dict):
            return None, True
        id_, amount = _canonical_id(row.get("id")), row.get("amount_eur")
        if not id_ or not isinstance(amount, str) or not _MONEY.fullmatch(amount):
            return None, True
        terms.append({"record": {"type": "deals", "id": id_}, "amount": amount})
    return {
        "kind": "sum_money_v1", "policy": "brambilla_revenue_v1", "currency": "EUR",
        "populationComplete": True, "populationCount": len(terms), "terms": terms,
        "result": total, "year": result.get("year") if isinstance(result.get("year"), int) else None,
    }, False


_EMAIL = re.compile(r"(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,63}(?![\w.-])", re.I)
_ITALIAN_MONEY = re.compile(r"(?<![\w])[-+]?(?:[0-9]{1,3}(?:\.[0-9]{3})+|[0-9]+),[0-9]{2}(?![\w])")
_DECIMAL_MONEY = re.compile(r"(?<![\w])[-+]?(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)\.[0-9]{2}(?![\w])")
_ISO_DATE = re.compile(r"(?<![0-9])([12][0-9]{3})-([01][0-9])-([0-3][0-9])(?![0-9])")
_SLASH_DATE = re.compile(r"(?<![0-9])([0-3]?[0-9])[/.-]([01]?[0-9])[/.-]([12][0-9]{3})(?![0-9])")
_ID_IN_REPLY = re.compile(r"(?i)(?:\bid\s*[#:=\-]?\s*|#)([1-9][0-9]{0,19})(?![0-9])")
_QUOTED_NAME = re.compile(r"[\"'“‘]([^\"'”’\n]{2,120})[\"'”’]")
_TITLE_NAME = re.compile(
    r"(?<![\w@])(?:[A-ZÀ-ÖØ-Þ][\wÀ-ÖØ-öø-ÿ&.'-]{1,40})"
    r"(?:\s+(?:[A-ZÀ-ÖØ-Þ][\wÀ-ÖØ-öø-ÿ&.'-]{1,40}|S\.(?:r\.l|p\.A)\.)){1,5}"
)
_MONTHS = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
    "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
    "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
}
_ITALIAN_DATE = re.compile(
    rf"(?i)(?<![0-9])([0-3]?[0-9])\s+({'|'.join(_MONTHS)})\s+([12][0-9]{{3}})(?![0-9])"
)
_NAME_KEYS = frozenset((
    "name", "company_name", "dealname", "subject", "title", "label",
    "hs_task_subject", "hs_call_title", "hs_email_subject", "hs_meeting_title",
))
_AMOUNT_KEYS = frozenset((
    "amount", "amount_eur", "total_eur", "total_eur_it", "price", "unit_price",
    "total_amount", "fatturato_2025",
))


def _clean_text(value: Any, *, limit: int = 120) -> str | None:
    if not isinstance(value, str):
        return None
    clean = " ".join(value.split()).strip()
    if not 1 <= len(clean) <= limit or any(ord(char) < 32 for char in clean):
        return None
    return clean


def _normal_money(value: Any) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        return None
    text = str(value).strip().replace("€", "").replace(" ", "")
    if re.fullmatch(r"[-+]?(?:[0-9]{1,3}(?:\.[0-9]{3})+|[0-9]+),[0-9]{1,2}", text):
        text = text.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"[-+]?(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]{1,2})?", text):
        text = text.replace(",", "")
    else:
        return None
    try:
        amount = Decimal(text).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None
    return format(amount, "f") if abs(amount) <= Decimal("99999999999999.99") else None


def _normal_date(value: str) -> str | None:
    match = _ISO_DATE.search(value)
    if match:
        parts = tuple(int(part) for part in match.groups())
    else:
        match = _SLASH_DATE.search(value)
        if match:
            day, month, year = (int(part) for part in match.groups())
            parts = (year, month, day)
        else:
            match = _ITALIAN_DATE.search(value)
            if not match:
                return None
            parts = (int(match.group(3)), _MONTHS[match.group(2).lower()], int(match.group(1)))
    try:
        return date(*parts).isoformat()
    except ValueError:
        return None


@dataclass(frozen=True)
class _ObservedFact:
    kind: str
    normalized: str
    source: str
    event: int


def _output_facts(result: Any, records: list[dict[str, str]], event: int) -> list[_ObservedFact]:
    """Reduce a result to bounded comparable values; never retain its raw payload."""
    facts: list[_ObservedFact] = []
    seen: set[tuple[str, str]] = set()

    def add(kind: str, normalized: str | None, source: Any) -> None:
        if normalized is None or len(facts) >= 256:
            return
        display = _clean_text(str(source))
        key = (kind, normalized)
        if display is None or key in seen:
            return
        seen.add(key)
        facts.append(_ObservedFact(kind, normalized, display, event))

    for ref in records:
        add("record_id", ref.get("id"), ref.get("id"))

    visited = 0

    def walk(value: Any, key: str = "", depth: int = 0) -> None:
        nonlocal visited
        if depth > 6 or visited >= 512:
            return
        if isinstance(value, dict):
            first = _clean_text(value.get("firstname"))
            last = _clean_text(value.get("lastname"))
            if first and last:
                full = f"{first} {last}"
                add("name", full.casefold(), full)
            for child_key, child in value.items():
                if isinstance(child_key, str):
                    walk(child, child_key.lower(), depth + 1)
            return
        if isinstance(value, list):
            for child in value[:200]:
                walk(child, key, depth + 1)
            return
        visited += 1
        if isinstance(value, str):
            email = _EMAIL.fullmatch(value.strip())
            if email:
                add("email", email.group(0).lower(), email.group(0))
            if key in _NAME_KEYS:
                clean = _clean_text(value)
                if clean:
                    add("name", clean.casefold(), clean)
            if key in _AMOUNT_KEYS:
                add("amount", _normal_money(value), value)
            if "date" in key or "timestamp" in key:
                add("date", _normal_date(value), value[:120])
            if key == "email":
                match = _EMAIL.fullmatch(value.strip())
                if match:
                    add("email", match.group(0).lower(), match.group(0))
            if key == "id" or key.endswith("_id") or key == "id_legacy":
                add("record_id", _canonical_id(value), value)
        elif key in _AMOUNT_KEYS and isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
            add("amount", _normal_money(value), value)
        elif (key == "id" or key.endswith("_id")) and isinstance(value, int) and not isinstance(value, bool):
            add("record_id", _canonical_id(value), value)

    walk(result)
    return facts


def _automations(result: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    def add(rule: str, object_type: str, id_value: Any) -> None:
        id_ = _canonical_id(id_value)
        key = (rule, object_type, id_ or "")
        if id_ and key not in seen and len(found) < MAX_AUTOMATIONS:
            seen.add(key)
            found.append({"rule": rule, "record": {"type": object_type, "id": id_}})

    def walk(value: Any, depth: int = 0) -> None:
        if depth > 5:
            return
        if isinstance(value, dict):
            notes = value.get("automations")
            if isinstance(notes, list):
                for note in notes[:MAX_AUTOMATIONS * 2]:
                    if not isinstance(note, str):
                        continue
                    r10 = re.search(r"(?i)\bticket\s+([1-9][0-9]{0,19})\b.*\(R10\)", note)
                    r11 = re.search(r"(?i)\btask\s+([1-9][0-9]{0,19})\b.*\(R11\)", note)
                    r12 = re.search(r"(?i)associato all['’]azienda\b.*\(id\s+([1-9][0-9]{0,19})\)", note)
                    if r10:
                        add("R10", "tickets", r10.group(1))
                    if r11:
                        add("R11", "tasks", r11.group(1))
                    if r12:
                        add("R12", "companies", r12.group(1))
            for child in value.values():
                if isinstance(child, (dict, list)):
                    walk(child, depth + 1)
        elif isinstance(value, list):
            for child in value[:200]:
                walk(child, depth + 1)

    walk(result)
    return found


def _record_labels(tool: str, args: dict, result: Any) -> dict[tuple[str, str], dict[str, str]]:
    """Names and locations that result rows explicitly attached to record ids."""
    labels: dict[tuple[str, str], dict[str, str]] = {}

    def add(object_type: Any, row: Any) -> None:
        if not isinstance(row, dict):
            return
        ot, id_ = _object_type(object_type), _canonical_id(row.get("id"))
        if not ot or not id_:
            return
        properties = row.get("properties") if isinstance(row.get("properties"), dict) else row
        label = next((_clean_text(properties.get(key), limit=80) for key in ("name", "dealname", "subject", "label") if _clean_text(properties.get(key), limit=80)), None)
        if not label:
            first, last = _clean_text(properties.get("firstname"), limit=40), _clean_text(properties.get("lastname"), limit=40)
            label = _clean_text(" ".join(part for part in (first, last) if part), limit=80)
        city, state = _clean_text(properties.get("city"), limit=40), _clean_text(properties.get("state"), limit=40)
        detail = _clean_text(", ".join(part for part in (city, state) if part), limit=80)
        if label:
            labels[(ot, id_)] = {"label": label, **({"detail": detail} if detail else {})}

    if not isinstance(result, dict):
        return labels
    search_types = {
        "search_companies": "companies", "search_contacts": "contacts", "search_deals": "deals",
        "search_tickets": "tickets", "my_customers": "companies", "dormant_list": "companies",
        "search_products": "products",
    }
    if tool in search_types and isinstance(result.get("results"), list):
        for row in result["results"]:
            add(search_types[tool], row)
    elif tool == "find_by_legacy_id" and isinstance(result.get("results"), list):
        for row in result["results"]:
            add(row.get("object_type") if isinstance(row, dict) else None, row)
    elif tool == "get_record":
        add(result.get("object_type") or args.get("object_type"), result)
    elif tool == "company_overview":
        add("companies", result.get("company"))
        for key, object_type in (("contacts", "contacts"), ("deals", "deals"), ("tickets", "tickets")):
            rows = result.get(key)
            if isinstance(rows, list):
                for row in rows:
                    add(object_type, row)
    elif tool == "revenue":
        rows = result.get("won_deals")
        if isinstance(rows, list):
            for row in rows:
                add("deals", row)
    elif tool == "list_deal_line_items":
        rows = result.get("results")
        if isinstance(rows, list):
            for row in rows:
                add("line_items", row)
                if isinstance(row, dict):
                    add("products", row.get("product"))
    elif tool in ("create_record", "update_record"):
        add(result.get("object_type") or args.get("object_type"), result)
    elif tool == "create_records_bulk":
        rows = result.get("results")
        if isinstance(rows, list):
            for row in rows:
                add(row.get("object_type") if isinstance(row, dict) else args.get("object_type"), row)
    elif tool == "import_attachment":
        for key in ("created", "updated"):
            rows = result.get(key)
            if isinstance(rows, list):
                for row in rows:
                    add(row.get("object_type") if isinstance(row, dict) else None, row)
    return labels


def _write_action(tool: str, args: dict) -> str:
    if tool == "update_record":
        ot = _object_type(args.get("object_type"))
        properties = args.get("properties") if isinstance(args.get("properties"), dict) else {}
        stage = str(properties.get("dealstage") or "").strip().lower()
        if ot == "deals" and stage in ("vinta", "won", "closedwon", "rinnovato"):
            return "Moved the deal to Won"
        if ot == "deals" and stage in ("persa", "lost", "closedlost", "non rinnovato"):
            return "Moved the deal to Lost"
        ticket_stage = str(properties.get("hs_pipeline_stage") or "").strip().lower()
        if ot == "tickets" and ticket_stage in ("chiuso", "closed"):
            return "Closed the ticket"
        return "Updated the record"
    return {
        "create_record": "Created the record",
        "associate": "Linked the records",
        "archive_record": "Archived the record",
        "import_attachment": "Imported the attachment",
        "create_records_bulk": "Created the records",
    }.get(tool, "Changed the CRM")


def _reply_candidates(reply: str, observed: list[_ObservedFact]) -> list[tuple[int, str, str, str]]:
    """Return ordered (offset, display, kind, normalized) candidate facts."""
    candidates: list[tuple[int, str, str, str]] = []

    def add(start: int, text: str, kind: str, normalized: str | None) -> None:
        clean = _clean_text(text)
        if normalized is not None and clean is not None:
            candidates.append((start, clean, kind, normalized))

    for pattern in (_ITALIAN_MONEY, _DECIMAL_MONEY):
        for match in pattern.finditer(reply):
            add(match.start(), match.group(0), "amount", _normal_money(match.group(0)))
    for match in _EMAIL.finditer(reply):
        add(match.start(), match.group(0), "email", match.group(0).lower())
    for pattern in (_ISO_DATE, _SLASH_DATE, _ITALIAN_DATE):
        for match in pattern.finditer(reply):
            add(match.start(), match.group(0), "date", _normal_date(match.group(0)))
    for match in _ID_IN_REPLY.finditer(reply):
        add(match.start(1), match.group(1), "record_id", match.group(1))

    # Tool-returned record names are candidates when they occur verbatim in the
    # reply. This catches casing and punctuation without attempting broad NER.
    for fact in observed:
        if fact.kind != "name":
            continue
        for match in re.finditer(re.escape(fact.source), reply, re.I):
            add(match.start(), match.group(0), "name", fact.normalized)
    for pattern in (_QUOTED_NAME, _TITLE_NAME):
        for match in pattern.finditer(reply):
            text = match.group(1) if pattern is _QUOTED_NAME else match.group(0)
            start = match.start(1) if pattern is _QUOTED_NAME else match.start()
            # A quote around an amount or an id is not a record name.
            if _normal_money(text) is None and not _canonical_id(text):
                add(start, text, "name", " ".join(text.split()).casefold())

    candidates.sort(key=lambda item: (item[0], -len(item[1])))
    out: list[tuple[int, str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    for candidate in candidates:
        key = (candidate[2], candidate[3])
        if key in seen:
            continue
        seen.add(key)
        out.append(candidate)
        if len(out) >= MAX_FACTS:
            break
    return out


def _grounding(reply: Any, observed: list[_ObservedFact], available_events: set[int]) -> dict | None:
    if not isinstance(reply, str):
        return None
    indexed: dict[tuple[str, str], int] = {}
    for fact in observed:
        if fact.event in available_events:
            indexed.setdefault((fact.kind, fact.normalized), fact.event)
    facts = []
    for _, text, kind, normalized in _reply_candidates(reply[:20_000], observed):
        event = indexed.get((kind, normalized))
        facts.append({"text": text, "kind": kind, "status": "grounded" if event is not None else "unverified", "event": event})
    grounded = sum(1 for fact in facts if fact["status"] == "grounded")
    return {"facts": facts, "grounded": grounded, "unverified": len(facts) - grounded}


@dataclass
class _Call:
    id: int
    tool: str
    operation: str
    started: float
    args: dict
    returned: bool = False
    settled: bool = False
    records: list[dict[str, str]] | None = None
    relations: list[dict[str, dict[str, str]]] | None = None
    calculation: dict | None = None
    count: int | None = None
    total: int | None = None
    failure: str | None = None
    fact_event: int | None = None
    facts: list[_ObservedFact] | None = None
    searches: list[int] | None = None
    candidates: int = 0
    chosen: dict[str, str] | None = None
    automations: list[dict[str, Any]] | None = None
    action: str | None = None


class EvidenceTrace:
    """Best-effort observer. Every public method swallows instrumentation errors."""

    def __init__(self, enabled: bool = False):
        self.enabled = enabled is True
        self._calls: dict[int, _Call] = {}
        self._events: list[dict] = []
        self._incomplete = False
        self._labels: dict[tuple[str, str], dict[str, str]] = {}

    def _event(self, call: _Call, status: str, *, final: bool = False) -> None:
        if len(self._events) >= MAX_EVENTS:
            self._incomplete = True
            return
        event: dict[str, Any] = {
            "sequence": len(self._events) + 1, "call": call.id, "tool": call.tool,
            "operation": call.operation, "status": status,
        }
        if final:
            event["durationMs"] = max(0, min(60_000, round((time.perf_counter() - call.started) * 1000)))
            event["inputSummary"] = _safe_summary(call.tool, call.args)
            event["records"] = list(call.records or [])
            if call.relations:
                event["relations"] = list(call.relations)
            if call.count is not None:
                event["count"] = call.count
            if call.total is not None:
                event["total"] = call.total
            if call.calculation is not None:
                event["calculation"] = call.calculation
            if call.failure is not None and status in ("failed", "rolled_back", "unknown"):
                event["failure"] = call.failure
            if call.tool in DECISION_WRITE_TOOLS and call.operation == "write":
                event["decisionPath"] = {
                    "searches": list(call.searches or []),
                    "candidates": call.candidates,
                    "chosen": deepcopy(call.chosen),
                    "automations": deepcopy(call.automations or []),
                    "action": call.action or "Changed the CRM",
                }
        self._events.append(event)

    def begin(self, tool: Any, args: Any) -> int | None:
        if not self.enabled:
            return None
        try:
            config = TOOLS.get(tool) if isinstance(tool, str) else None
            if config is None or len(self._calls) >= MAX_CALLS:
                self._incomplete = True
                return None
            call = _Call(len(self._calls) + 1, tool, config[0], time.perf_counter(), dict(args) if isinstance(args, dict) else {})
            if call.operation == "write" and call.tool in DECISION_WRITE_TOOLS:
                reads = [
                    event for event in self._events
                    if event.get("operation") == "read" and event.get("status") == "completed"
                ][-MAX_SEARCHES:]
                call.searches = [event["sequence"] for event in reads]
                call.candidates = min(MAX_COUNT, sum(
                    event.get("count") if isinstance(event.get("count"), int) else len(event.get("records") or [])
                    for event in reads
                ))
                call.action = _write_action(call.tool, call.args)
            self._calls[call.id] = call
            self._event(call, "attempted")
            return call.id
        except Exception:
            self._incomplete = True
            return None

    def returned(self, call_id: int | None, result: Any) -> None:
        if not self.enabled or call_id is None:
            return
        try:
            call = self._calls.get(call_id)
            if call is None or call.settled or call.returned:
                self._incomplete = True
                return
            call.returned = True
            call.records, call.relations, omitted = _records(call.tool, call.args, result)
            call.calculation, calc_omitted = _calculation(call.tool, result)
            call.count, call.total = _counts(call.tool, result)
            call.fact_event = len(self._events) + 1
            call.facts = _output_facts(result, call.records, call.fact_event)
            # Names used as decision labels come only from preceding reads.
            # Write-return labels remain in memory for grounding and are never
            # copied into the event merely because a write returned them.
            if call.operation == "read":
                self._labels.update(_record_labels(call.tool, call.args, result))
            if call.operation == "write" and call.tool in DECISION_WRITE_TOOLS:
                if call.records:
                    ref = call.records[0]
                    call.chosen = {**ref, **self._labels.get((ref["type"], ref["id"]), {})}
                else:
                    call.chosen = None
                call.automations = _automations(result)
            self._incomplete |= omitted or calc_omitted
            if isinstance(result, dict) and "error" in result:
                status_code = result.get("status")
                call.failure = FAILURES.get(status_code, "rejected") if isinstance(status_code, int) and not isinstance(status_code, bool) else "rejected"
                call.settled = True
                self._event(call, "failed" if call.operation == "read" else "rolled_back", final=True)
            elif call.operation == "read":
                call.settled = True
                self._event(call, "completed", final=True)
            else:
                self._event(call, "awaiting_commit")
        except Exception:
            self._incomplete = True

    def transaction_finished(self, call_id: int | None, outcome: str) -> None:
        if not self.enabled or call_id is None:
            return
        try:
            call = self._calls.get(call_id)
            if call is None or call.operation != "write" or call.settled or outcome not in ("committed", "rolled_back", "unknown"):
                if call is not None and not call.settled:
                    self._incomplete = True
                return
            call.settled = True
            status = outcome if call.returned else "unknown"
            self._incomplete |= status == "unknown"
            self._event(call, status, final=True)
        except Exception:
            self._incomplete = True

    def failed(self, call_id: int | None, *, outcome: str = "rolled_back", reason: str = "error") -> None:
        if not self.enabled or call_id is None:
            return
        try:
            call = self._calls.get(call_id)
            if call is None or call.settled:
                return
            call.settled = True
            call.failure = reason if reason in FAILURE_KINDS else "error"
            status = "failed" if call.operation == "read" else outcome
            if status == "unknown":
                self._incomplete = True
            self._event(call, status, final=True)
        except Exception:
            self._incomplete = True

    def snapshot(self, reply: str | None = None) -> dict | None:
        if not self.enabled:
            return None
        try:
            incomplete = self._incomplete or any(not call.settled for call in self._calls.values())
            value = {"version": 1, "events": deepcopy(self._events), "incomplete": incomplete}
            observed = [fact for call in self._calls.values() for fact in (call.facts or [])]
            grounding = _grounding(reply, observed, {event["sequence"] for event in value["events"]})
            if grounding is not None:
                value["grounding"] = grounding
            while len(json.dumps(value, separators=(",", ":")).encode()) > 32_768 and value["events"]:
                value["events"].pop()
                value["incomplete"] = True
                grounding = _grounding(reply, observed, {event["sequence"] for event in value["events"]})
                if grounding is not None:
                    value["grounding"] = grounding
            return value
        except Exception:
            return None

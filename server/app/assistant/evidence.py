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
from typing import Any


MAX_EVENTS = 64
MAX_RECORDS = 20
MAX_RELATIONS = 40
MAX_CALLS = 32
MAX_COUNT = 1_000_000
# Failure categories are a closed set derived from the numeric status a tool
# reported, never from error text.
FAILURES = {400: "validation", 404: "not_found", 409: "conflict", 429: "rate_limited"}
FAILURE_KINDS = frozenset(("validation", "not_found", "conflict", "rate_limited", "rejected", "error"))
LIST_TOOLS = frozenset(
    ("search_companies", "search_contacts", "search_deals", "search_tickets",
     "my_customers", "dormant_list", "list_activities", "list_users")
)
RECORD_TYPES = frozenset(
    ("companies", "contacts", "deals", "tickets", "products", "line_items",
     "notes", "calls", "emails", "meetings", "tasks")
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
    "create_record": ("write", "Created a CRM record"),
    "update_record": ("write", "Updated a CRM record"),
    "associate": ("write", "Associated CRM records"),
    "dissociate": ("write", "Removed a CRM association"),
    "archive_record": ("write", "Archived a CRM record"),
    "create_records_bulk": ("write", "Created CRM records in bulk"),
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


class EvidenceTrace:
    """Best-effort observer. Every public method swallows instrumentation errors."""

    def __init__(self, enabled: bool = False):
        self.enabled = enabled is True
        self._calls: dict[int, _Call] = {}
        self._events: list[dict] = []
        self._incomplete = False

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

    def snapshot(self) -> dict | None:
        if not self.enabled:
            return None
        try:
            incomplete = self._incomplete or any(not call.settled for call in self._calls.values())
            value = {"version": 1, "events": deepcopy(self._events), "incomplete": incomplete}
            while len(json.dumps(value, separators=(",", ":")).encode()) > 32_768 and value["events"]:
                value["events"].pop()
                value["incomplete"] = True
            return value
        except Exception:
            return None

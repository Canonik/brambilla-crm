"""Record store: validation, CRUD, associations, search. All business rules go through here."""
from __future__ import annotations

import datetime as dt
import json
import re
import threading
from decimal import Decimal

import psycopg
from psycopg.types.json import Jsonb

from . import defaults
from .errors import ApiError, conflict, not_found, validation
from .util import email_domain, fmt_money, iso, normalize_domain, normalize_number, parse_datetime, parse_record_id, utcnow, valid_email

_defs_cache: dict[str, dict[str, dict]] = {}
_pipeline_cache: dict[str, list[dict]] = {}
_cache_lock = threading.Lock()


def invalidate_caches() -> None:
    with _cache_lock:
        _defs_cache.clear()
        _pipeline_cache.clear()


def record_out(row, properties: list[str] | None, object_type: str, *, all_props: bool = False) -> dict:
    props = row["properties"]
    created = row["created_at"]
    updated = row["updated_at"]
    if properties is None or all_props:
        out_props = dict(props)
    else:
        out_props = {p: props.get(p) for p in properties}
        for sysp in ("hs_object_id", defaults.OBJECT_TYPES[object_type]["created"], defaults.OBJECT_TYPES[object_type]["modified"]):
            out_props.setdefault(sysp, props.get(sysp))
    out = {
        "id": str(row["id"]),
        "properties": out_props,
        "createdAt": iso(created),
        "updatedAt": iso(updated),
        "archived": bool(row["archived"]),
    }
    if row.get("archived_at"):
        out["archivedAt"] = iso(row["archived_at"])
    return out


class Store:
    def __init__(self, conn: psycopg.Connection, now: dt.datetime | None = None):
        self.conn = conn
        self.now = now or utcnow()

    # ------------------------------------------------------------ definitions
    def prop_defs(self, object_type: str) -> dict[str, dict]:
        with _cache_lock:
            d = _defs_cache.get(object_type)
        if d is not None:
            return d
        rows = self.conn.execute("SELECT name, definition FROM properties WHERE object_type = %s", (object_type,)).fetchall()
        d = {r["name"]: r["definition"] for r in rows}
        with _cache_lock:
            _defs_cache[object_type] = d
        return d

    def readable_properties(self, object_type: str, properties: list[str] | None) -> list[str] | None:
        """Ignore undefined requested properties, matching HubSpot read semantics."""
        if properties is None:
            return None
        definitions = self.prop_defs(object_type)
        return [name for name in properties if name in definitions]

    def pipelines(self, object_type: str) -> list[dict]:
        with _cache_lock:
            p = _pipeline_cache.get(object_type)
        if p is not None:
            return p
        rows = self.conn.execute("SELECT definition FROM pipelines WHERE object_type = %s ORDER BY (definition->>'displayOrder')::int, id", (object_type,)).fetchall()
        p = [r["definition"] for r in rows]
        with _cache_lock:
            _pipeline_cache[object_type] = p
        return p

    def pipeline_by_label(self, object_type: str, label: str) -> dict | None:
        for p in self.pipelines(object_type):
            if p["label"].strip().lower() == label.strip().lower():
                return p
        return None

    def stage_lookup(self, object_type: str, stage_id: str) -> tuple[dict, dict] | None:
        for p in self.pipelines(object_type):
            for s in p["stages"]:
                if s["id"] == stage_id:
                    return p, s
        return None

    # ------------------------------------------------------------ validation
    def normalize_properties(self, object_type: str, props: dict, *, existing: dict | None = None) -> dict:
        if not isinstance(props, dict):
            raise validation("properties must be an object")
        defs = self.prop_defs(object_type)
        out: dict[str, str | None] = {}
        errors = []
        for name, value in props.items():
            name = str(name)
            d = defs.get(name)
            if d is None:
                from . import brambilla
                spec = brambilla.custom_property(object_type, name)
                if spec is not None:
                    from .routers.properties import ensure_property
                    d = ensure_property(self.conn, object_type, spec)
                    invalidate_caches()
                    defs = self.prop_defs(object_type)
                else:
                    errors.append({"isValid": False, "message": f'Property "{name}" does not exist', "error": "PROPERTY_DOESNT_EXIST", "name": name})
                    continue
            if name in defaults.READ_ONLY_PROPERTIES:
                continue
            if value is None or (isinstance(value, str) and value.strip() == ""):
                out[name] = None
                continue
            t = d.get("type")
            if t == "number":
                v = normalize_number(value)
                if v is None:
                    errors.append({"isValid": False, "message": f"{value!r} was not a valid number for property {name}", "error": "INVALID_NUMBER", "name": name})
                    continue
                if name in ("price", "amount", "fatturato_2025") and object_type != "deals":
                    pass
                out[name] = v
            elif t == "datetime":
                dv = parse_datetime(value)
                if dv is None:
                    errors.append({"isValid": False, "message": f"{value!r} was not a valid datetime for property {name}", "error": "INVALID_DATE", "name": name})
                    continue
                out[name] = iso(dv)
            elif t == "date":
                dv = parse_datetime(value)
                if dv is None:
                    errors.append({"isValid": False, "message": f"{value!r} was not a valid date for property {name}", "error": "INVALID_DATE", "name": name})
                    continue
                out[name] = dv.strftime("%Y-%m-%d")
            elif t == "bool":
                if isinstance(value, bool):
                    out[name] = "true" if value else "false"
                else:
                    sv = str(value).strip().lower()
                    out[name] = "true" if sv in ("true", "1", "yes", "y", "si", "sì") else "false"
            elif t == "enumeration":
                if isinstance(value, list):
                    out[name] = ";".join(str(x) for x in value)
                else:
                    out[name] = str(value).strip()
            else:
                if isinstance(value, (dict, list)):
                    out[name] = json.dumps(value)
                else:
                    out[name] = str(value)
        # object specific normalisation
        if object_type == "contacts" and "email" in out and out["email"]:
            e = out["email"].strip().lower()
            if not valid_email(e):
                errors.append({"isValid": False, "message": f"Email address {out['email']} is invalid", "error": "INVALID_EMAIL", "name": "email"})
            else:
                out["email"] = e
                out["hs_email_domain"] = email_domain(e)
        if object_type == "contacts" and "email" in out and out["email"] is None:
            out["hs_email_domain"] = None
        if object_type == "companies":
            if "domain" in out and out["domain"]:
                d = out["domain"].strip().lower()
                d = re.sub(r"^[a-z]+://", "", d).split("/")[0]
                out["domain"] = d
            if "partita_iva" in out and out["partita_iva"]:
                piva = re.sub(r"[^0-9]", "", re.sub(r"^\s*IT", "", out["partita_iva"].strip(), flags=re.I))
                if len(piva) != 11:
                    errors.append({"isValid": False, "message": f"partita_iva {out['partita_iva']!r} is not an 11-digit Italian VAT number", "error": "INVALID_OPTION", "name": "partita_iva"})
                else:
                    out["partita_iva"] = piva
            if "classe_cliente" in out and out["classe_cliente"]:
                out["classe_cliente"] = out["classe_cliente"].strip().upper()
        if object_type == "deals":
            self._normalize_deal(out, existing)
        if object_type == "tickets":
            self._normalize_ticket(out, existing)
        if object_type == "line_items":
            self._normalize_line_item(out, existing)
        if object_type in defaults.ACTIVITY_TYPES and existing is None and not out.get("hs_timestamp"):
            out["hs_timestamp"] = iso(self.now)
        if errors:
            raise validation("Property values were not valid: " + json.dumps(errors, ensure_ascii=False), errors)
        return out

    def _normalize_deal(self, out: dict, existing: dict | None) -> None:
        merged = dict(existing or {})
        merged.update({k: v for k, v in out.items()})
        pipeline = merged.get("pipeline")
        stage = merged.get("dealstage")
        pls = self.pipelines("deals")
        if pipeline is not None and pipeline != "":
            pl = next((p for p in pls if p["id"] == pipeline), None)
            if pl is None:
                pl = self.pipeline_by_label("deals", pipeline)
                if pl is None:
                    raise validation(f"Pipeline {pipeline!r} does not exist", [{"isValid": False, "message": f"Pipeline {pipeline!r} does not exist", "error": "INVALID_OPTION", "name": "pipeline"}])
                out["pipeline"] = pl["id"]
                pipeline = pl["id"]
        if stage:
            found = None
            for p in pls:
                for s in p["stages"]:
                    if s["id"] == stage or s["label"].strip().lower() == str(stage).strip().lower():
                        if pipeline is None or pipeline == "" or p["id"] == pipeline:
                            found = (p, s)
                            break
                        if found is None:
                            found = (p, s)
                if found and (pipeline is None or pipeline == "" or found[0]["id"] == pipeline):
                    break
            if found is None or (pipeline and found[0]["id"] != pipeline):
                raise validation(f"Deal stage {stage!r} does not exist in pipeline {pipeline or 'default'!r}", [{"isValid": False, "message": f"{stage!r} was not one of the allowed options", "error": "INVALID_OPTION", "name": "dealstage"}])
            out["dealstage"] = found[1]["id"]
            out["pipeline"] = found[0]["id"]
            pipeline = found[0]["id"]
            stage = found[1]["id"]
        if existing is None:
            if not pipeline:
                out["pipeline"] = pipeline = pls[0]["id"] if pls else "default"
            if not stage:
                pl = next((p for p in pls if p["id"] == pipeline), pls[0] if pls else None)
                if pl and pl["stages"]:
                    out["dealstage"] = stage = pl["stages"][0]["id"]
        if "deal_currency_code" in out and out["deal_currency_code"]:
            out["deal_currency_code"] = out["deal_currency_code"].strip().upper()
        # derived fields
        look = self.stage_lookup("deals", stage) if stage else None
        if look:
            meta = look[1].get("metadata", {})
            closed = str(meta.get("isClosed", "false")).lower() == "true"
            prob = meta.get("probability")
            out["hs_deal_stage_probability"] = str(prob) if prob is not None else None
            won = closed and prob is not None and float(prob) >= 1.0
            lost = closed and not won
            out["hs_is_closed"] = "true" if closed else "false"
            out["hs_is_closed_won"] = "true" if won else "false"
            out["hs_is_closed_lost"] = "true" if lost else "false"
            amount = merged.get("amount") if "amount" not in out else out.get("amount")
            out["hs_closed_amount"] = amount if won and amount else "0"

    def _normalize_ticket(self, out: dict, existing: dict | None) -> None:
        merged = dict(existing or {})
        merged.update(out)
        pls = self.pipelines("tickets")
        pipeline = merged.get("hs_pipeline")
        stage = merged.get("hs_pipeline_stage")
        if pipeline:
            pl = next((p for p in pls if p["id"] == pipeline), None) or self.pipeline_by_label("tickets", pipeline)
            if pl is None:
                raise validation(f"Pipeline {pipeline!r} does not exist", [{"isValid": False, "message": f"Pipeline {pipeline!r} does not exist", "error": "INVALID_OPTION", "name": "hs_pipeline"}])
            out["hs_pipeline"] = pl["id"]
            pipeline = pl["id"]
        if stage:
            found = None
            for p in pls:
                for s in p["stages"]:
                    if s["id"] == stage or s["label"].strip().lower() == str(stage).strip().lower():
                        if not pipeline or p["id"] == pipeline:
                            found = (p, s)
                            break
                if found:
                    break
            if found is None:
                raise validation(f"Ticket stage {stage!r} does not exist in pipeline {pipeline or '0'!r}", [{"isValid": False, "message": f"{stage!r} was not one of the allowed options", "error": "INVALID_OPTION", "name": "hs_pipeline_stage"}])
            out["hs_pipeline_stage"] = found[1]["id"]
            out["hs_pipeline"] = found[0]["id"]
            pipeline = found[0]["id"]
            stage = found[1]["id"]
        if existing is None:
            if not pipeline:
                out["hs_pipeline"] = pipeline = pls[0]["id"] if pls else "0"
            if not stage:
                pl = next((p for p in pls if p["id"] == pipeline), None)
                if pl and pl["stages"]:
                    out["hs_pipeline_stage"] = stage = pl["stages"][0]["id"]
        if "hs_ticket_priority" in out and out["hs_ticket_priority"]:
            v = out["hs_ticket_priority"].strip().upper()
            alias = {"BASSA": "LOW", "MEDIA": "MEDIUM", "NORMALE": "MEDIUM", "ALTA": "HIGH", "URGENTE": "URGENT"}
            out["hs_ticket_priority"] = alias.get(v, v)
        look = self.stage_lookup("tickets", stage) if stage else None
        if look and str(look[1].get("metadata", {}).get("ticketState", "OPEN")).upper() == "CLOSED":
            if "closed_date" not in out and not merged.get("closed_date"):
                out["closed_date"] = iso(self.now)

    def _normalize_line_item(self, out: dict, existing: dict | None) -> None:
        if existing is None and "quantity" not in out:
            out["quantity"] = "1"
        merged = dict(existing or {})
        merged.update(out)
        q = merged.get("quantity")
        p = merged.get("price")
        disc_pct = merged.get("hs_discount_percentage")
        disc = merged.get("discount")
        if q is not None and p is not None:
            try:
                qd = Decimal(q)
                pd = Decimal(p)
                gross = qd * pd
                if disc_pct not in (None, ""):
                    total_disc = gross * Decimal(disc_pct) / Decimal(100)
                elif disc not in (None, ""):
                    total_disc = Decimal(disc) * qd
                else:
                    total_disc = Decimal(0)
                out["amount"] = fmt_money(gross - total_disc)
                out["hs_total_discount"] = fmt_money(total_disc)
            except Exception:
                pass
        if existing is None and not merged.get("quantity"):
            out.setdefault("quantity", "1")
        if existing is None and not merged.get("hs_discount_percentage") and not merged.get("discount"):
            out.setdefault("hs_discount_percentage", "0")

    # ------------------------------------------------------------ CRUD
    def _row(self, object_type: str, id_: int, *, lock: bool = False, include_archived: bool = False):
        sql = "SELECT * FROM objects WHERE id = %s AND object_type = %s"
        if not include_archived:
            sql += " AND NOT archived"
        if lock:
            sql += " FOR UPDATE"
        return self.conn.execute(sql, (id_, object_type)).fetchone()

    def resolve_id(self, object_type: str, id_value: str, id_property: str | None) -> int:
        if id_property and id_property not in ("hs_object_id", "id"):
            defs = self.prop_defs(object_type)
            if id_property not in defs:
                raise validation(f'Property "{id_property}" does not exist')
            val = str(id_value)
            if object_type == "contacts" and id_property == "email":
                val = val.strip().lower()
            if object_type == "companies" and id_property == "partita_iva":
                val = re.sub(r"[^0-9]", "", re.sub(r"^\s*IT", "", val, flags=re.I))
            row = self.conn.execute(
                "SELECT id FROM objects WHERE object_type = %s AND NOT archived AND properties->>%s = %s ORDER BY id LIMIT 1",
                (object_type, id_property, val),
            ).fetchone()
            if not row:
                raise not_found(f"No {defaults.OBJECT_TYPES[object_type]['singular']} with {id_property} '{id_value}' exists")
            return int(row["id"])
        rid = parse_record_id(id_value)
        if rid is None:
            raise not_found(f"resource not found: {id_value}")
        return rid

    def get(self, object_type: str, id_value, properties: list[str] | None = None, associations: list[str] | None = None, id_property: str | None = None, *, include_archived: bool = False) -> dict:
        id_ = self.resolve_id(object_type, id_value, id_property)
        row = self._row(object_type, id_, include_archived=include_archived)
        if row is None:
            raise not_found(f"No {defaults.OBJECT_TYPES[object_type]['singular']} with ID {id_value} exists")
        out = record_out(row, self.readable_properties(object_type, properties), object_type)
        if associations:
            out["associations"] = self.associations_block(id_, associations)
        return out

    def new_id(self) -> int:
        return int(self.conn.execute("SELECT nextval('objects_id_seq') AS id").fetchone()["id"])

    def create(self, object_type: str, properties: dict, associations: list | None = None, *, run_rules: bool = True) -> dict:
        if associations is not None and not isinstance(associations, list):
            raise validation("associations must be an array")
        props = self.normalize_properties(object_type, properties or {})
        props = {k: v for k, v in props.items() if v is not None}
        ot = defaults.OBJECT_TYPES[object_type]
        id_ = self.new_id()
        now = self.now
        props["hs_object_id"] = str(id_)
        props[ot["created"]] = iso(now)
        props[ot["modified"]] = iso(now)
        if object_type == "tickets":
            props["hs_ticket_id"] = str(id_)
        if object_type == "contacts":
            props["hs_full_name_or_email"] = (" ".join(x for x in (props.get("firstname"), props.get("lastname")) if x) or props.get("email") or "")
        try:
            with self.conn.transaction():
                self.conn.execute(
                    "INSERT INTO objects (id, object_type, properties, created_at, updated_at) VALUES (%s, %s, %s, %s, %s)",
                    (id_, object_type, Jsonb(props), now, now),
                )
        except psycopg.errors.UniqueViolation as e:
            raise self._unique_conflict(object_type, props, e)
        if object_type == "companies":
            self._sync_company_domains(id_, props)
        if object_type == "deals":
            self._deal_stage_dates(id_, None, props.get("dealstage"), props)
        for a in associations or []:
            self._apply_association_payload(object_type, id_, a)
        if run_rules:
            from . import rules
            rules.after_create(self, object_type, id_, props)
        row = self._row(object_type, id_)
        return record_out(row, None, object_type)

    def _unique_conflict(self, object_type: str, props: dict, e: Exception) -> ApiError:
        msg = str(e)
        if "objects_contact_email_uq" in msg:
            ex = self.conn.execute("SELECT id FROM objects WHERE object_type='contacts' AND NOT archived AND properties->>'email' = %s", (props.get("email"),)).fetchone()
            return conflict(f"Contact already exists. Existing ID: {ex['id'] if ex else 'unknown'}")
        if "objects_company_piva_uq" in msg:
            ex = self.conn.execute("SELECT id FROM objects WHERE object_type='companies' AND NOT archived AND properties->>'partita_iva' = %s", (props.get("partita_iva"),)).fetchone()
            return conflict(f"Company with partita_iva {props.get('partita_iva')} already exists. Existing ID: {ex['id'] if ex else 'unknown'}")
        if "objects_uq_" in msg:
            return conflict("A record with the same value for a unique property already exists")
        return conflict("Record already exists")

    def update(self, object_type: str, id_value, properties: dict, id_property: str | None = None, *, run_rules: bool = True) -> dict:
        id_ = self.resolve_id(object_type, id_value, id_property)
        row = self._row(object_type, id_, lock=True)
        if row is None:
            raise not_found(f"No {defaults.OBJECT_TYPES[object_type]['singular']} with ID {id_value} exists")
        old = row["properties"]
        props = self.normalize_properties(object_type, properties or {}, existing=old)
        ot = defaults.OBJECT_TYPES[object_type]
        now = self.now
        new = dict(old)
        for k, v in props.items():
            if v is None:
                new.pop(k, None)
            else:
                new[k] = v
        new[ot["modified"]] = iso(now)
        if object_type == "contacts":
            new["hs_full_name_or_email"] = (" ".join(x for x in (new.get("firstname"), new.get("lastname")) if x) or new.get("email") or "")
        if object_type == "deals" and old.get("dealstage") != new.get("dealstage"):
            self._deal_stage_dates(id_, old.get("dealstage"), new.get("dealstage"), new)
        try:
            with self.conn.transaction():
                self.conn.execute("UPDATE objects SET properties = %s, updated_at = %s WHERE id = %s", (Jsonb(new), now, id_))
        except psycopg.errors.UniqueViolation as e:
            raise self._unique_conflict(object_type, new, e)
        if object_type == "companies":
            self._sync_company_domains(id_, new)
        if run_rules:
            from . import rules
            rules.after_update(self, object_type, id_, old, new)
        row = self._row(object_type, id_)
        return record_out(row, None, object_type)

    def _deal_stage_dates(self, id_: int, old_stage, new_stage, props: dict) -> None:
        look = self.stage_lookup("deals", new_stage) if new_stage else None
        if not look:
            return
        meta = look[1].get("metadata", {})
        closed = str(meta.get("isClosed", "false")).lower() == "true"
        if not closed:
            return
        won = float(meta.get("probability") or 0) >= 1.0
        if not props.get("closedate"):
            props["closedate"] = iso(self.now)
        if won:
            props["hs_closed_won_date"] = iso(self.now)
        else:
            props["hs_closed_lost_date"] = iso(self.now)

    def archive(self, object_type: str, id_value, id_property: str | None = None) -> None:
        id_ = self.resolve_id(object_type, id_value, id_property)
        row = self._row(object_type, id_, lock=True)
        if row is None:
            return  # HubSpot: archiving a missing/archived record is a 204 no-op
        now = self.now
        self.conn.execute("UPDATE objects SET archived = true, archived_at = %s, updated_at = %s WHERE id = %s", (now, now, id_))
        if object_type == "companies":
            self.conn.execute("DELETE FROM company_domains WHERE company_id = %s", (id_,))
        self.conn.execute("DELETE FROM list_memberships WHERE record_id = %s", (id_,))

    def delete_permanently(self, object_type: str, id_: int) -> None:
        self.conn.execute("DELETE FROM associations WHERE from_id = %s OR to_id = %s", (id_, id_))
        self.conn.execute("DELETE FROM list_memberships WHERE record_id = %s", (id_,))
        self.conn.execute("DELETE FROM company_domains WHERE company_id = %s", (id_,))
        self.conn.execute("DELETE FROM objects WHERE id = %s AND object_type = %s", (id_, object_type))

    def upsert(self, object_type: str, id_property: str, id_value: str, properties: dict) -> tuple[dict, bool]:
        props = dict(properties or {})
        props[id_property] = id_value
        for attempt in range(3):
            try:
                with self.conn.transaction():
                    try:
                        existing = self.resolve_id(object_type, id_value, id_property)
                    except ApiError as e:
                        if e.status != 404:
                            raise
                        existing = None
                    if existing is not None:
                        return self.update(object_type, existing, props), False
                    return self.create(object_type, props), True
            except ApiError as e:
                if e.status == 409 and attempt < 2:
                    continue
                raise
        raise conflict("upsert failed")

    def _sync_company_domains(self, id_: int, props: dict) -> None:
        doms = set()
        d = normalize_domain(props.get("domain"))
        if d:
            doms.add(d)
        for extra in (props.get("hs_additional_domains") or "").split(";"):
            nd = normalize_domain(extra)
            if nd:
                doms.add(nd)
        self.conn.execute("DELETE FROM company_domains WHERE company_id = %s", (id_,))
        if doms:
            self.conn.cursor().executemany("INSERT INTO company_domains (domain, company_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", [(x, id_) for x in doms])

    def merge(self, object_type: str, primary_id: int, merge_id: int) -> dict:
        prow = self._row(object_type, primary_id, lock=True)
        mrow = self._row(object_type, merge_id, lock=True)
        if prow is None or mrow is None:
            raise not_found("resource not found")
        ot = defaults.OBJECT_TYPES[object_type]
        new = dict(mrow["properties"])
        new.update({k: v for k, v in prow["properties"].items() if v not in (None, "")})
        new["hs_object_id"] = str(primary_id)
        new[ot["created"]] = prow["properties"].get(ot["created"])
        new[ot["modified"]] = iso(self.now)
        if object_type == "companies":
            doms = []
            for d in [prow["properties"].get("domain"), mrow["properties"].get("domain")] + (prow["properties"].get("hs_additional_domains") or "").split(";") + (mrow["properties"].get("hs_additional_domains") or "").split(";"):
                nd = normalize_domain(d)
                if nd and nd not in doms:
                    doms.append(nd)
            if doms:
                new["domain"] = prow["properties"].get("domain") or doms[0]
                extra = [d for d in doms if d != normalize_domain(new["domain"])]
                if extra:
                    new["hs_additional_domains"] = ";".join(extra)
        # archive secondary first so unique indexes free up
        self.conn.execute("UPDATE objects SET archived = true, archived_at = %s, updated_at = %s WHERE id = %s", (self.now, self.now, merge_id))
        self.conn.execute("UPDATE objects SET properties = %s, updated_at = %s WHERE id = %s", (Jsonb(new), self.now, primary_id))
        # move associations
        rows = self.conn.execute("SELECT * FROM associations WHERE from_id = %s OR to_id = %s", (merge_id, merge_id)).fetchall()
        for r in rows:
            f = primary_id if r["from_id"] == merge_id else r["from_id"]
            t = primary_id if r["to_id"] == merge_id else r["to_id"]
            if f == t:
                continue
            self.conn.execute(
                "INSERT INTO associations (from_id, to_id, type_id, from_type, to_type, category) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (f, t, r["type_id"], r["from_type"], r["to_type"], r["category"]),
            )
        self.conn.execute("DELETE FROM associations WHERE from_id = %s OR to_id = %s", (merge_id, merge_id))
        self.conn.execute("UPDATE list_memberships SET record_id = %s WHERE record_id = %s AND NOT EXISTS (SELECT 1 FROM list_memberships l2 WHERE l2.list_id = list_memberships.list_id AND l2.record_id = %s)", (primary_id, merge_id, primary_id))
        self.conn.execute("DELETE FROM list_memberships WHERE record_id = %s", (merge_id,))
        if object_type == "companies":
            self.conn.execute("DELETE FROM company_domains WHERE company_id = %s", (merge_id,))
            self._sync_company_domains(primary_id, new)
        return record_out(self._row(object_type, primary_id), None, object_type)

    # ------------------------------------------------------------ associations
    def _apply_association_payload(self, object_type: str, id_: int, a: dict) -> None:
        if not isinstance(a, dict):
            raise validation("associations must be objects")
        to = a.get("to") or {}
        raw_to = to.get("id") if isinstance(to, dict) else to
        if raw_to is None:
            raise validation("association target id missing")
        to_id = parse_record_id(raw_to)
        if to_id is None:
            raise validation(f"Invalid association target id: {raw_to!r}")
        types = a.get("types") or []
        if not isinstance(types, list) or not all(isinstance(t, dict) for t in types):
            raise validation("association types must be an array of objects")
        type_ids = []
        to_type = None
        for t in types:
            tid = t.get("associationTypeId")
            if tid is None:
                continue
            tid = parse_record_id(tid)
            if tid is None:
                raise validation(f"Invalid associationTypeId: {t.get('associationTypeId')!r}")
            lab = self.assoc_label(tid)
            if lab is None:
                raise validation(f"Association type {tid} does not exist")
            to_type = lab["to_type"]
            type_ids.append(tid)
        if to_type is None:
            to_type_name = defaults.resolve_type(str(to.get("objectType") or a.get("toObjectType") or ""))
            if to_type_name is None:
                # infer from the target record
                r = self.conn.execute("SELECT object_type FROM objects WHERE id = %s", (to_id,)).fetchone()
                if r is None:
                    raise not_found(f"No object with ID {to_id} exists")
                to_type_name = r["object_type"]
            to_type = to_type_name
        self.associate(object_type, id_, to_type, to_id, type_ids or None)

    def assoc_label(self, type_id: int) -> dict | None:
        return self.conn.execute("SELECT * FROM association_labels WHERE type_id = %s", (type_id,)).fetchone()

    def associate(self, from_type: str, from_id: int, to_type: str, to_id: int, type_ids: list[int] | None = None, *, check: bool = True) -> list[dict]:
        if check:
            if self._row(from_type, from_id) is None:
                raise not_found(f"No {from_type} with ID {from_id} exists")
            if self._row(to_type, to_id) is None:
                raise not_found(f"No {to_type} with ID {to_id} exists")
        if not type_ids:
            default = defaults.default_type_id(from_type, to_type)
            if default is None:
                lab = self.conn.execute("SELECT type_id FROM association_labels WHERE from_type = %s AND to_type = %s ORDER BY type_id LIMIT 1", (from_type, to_type)).fetchone()
                if lab is None:
                    raise validation(f"No association type between {from_type} and {to_type}")
                default = lab["type_id"]
            type_ids = [default]
            primary = defaults.PRIMARY_ASSOC.get((from_type, to_type))
            if primary is not None:
                has_primary = self.conn.execute("SELECT 1 FROM associations WHERE from_id = %s AND type_id = %s LIMIT 1", (from_id, primary)).fetchone()
                if not has_primary:
                    type_ids.append(primary)
        labels = []
        for tid in type_ids:
            lab = self.assoc_label(tid)
            if lab is None:
                raise validation(f"Association type {tid} does not exist")
            if lab["from_type"] != from_type or lab["to_type"] != to_type:
                raise validation(f"Association type {tid} is not valid between {from_type} and {to_type}")
            inv = lab["inverse_type_id"]
            self.conn.execute(
                "INSERT INTO associations (from_id, to_id, type_id, from_type, to_type, category) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (from_id, to_id, tid, from_type, to_type, lab["category"]),
            )
            if inv is not None:
                self.conn.execute(
                    "INSERT INTO associations (from_id, to_id, type_id, from_type, to_type, category) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                    (to_id, from_id, inv, to_type, from_type, lab["category"]),
                )
            labels.append(lab)
        self._after_association(from_type, from_id, to_type, to_id)
        return labels

    def _after_association(self, from_type, from_id, to_type, to_id) -> None:
        pairs = [(from_type, from_id, to_type, to_id), (to_type, to_id, from_type, from_id)]
        for a_type, a_id, b_type, b_id in pairs:
            if a_type == "contacts" and b_type == "companies":
                self._set_prop(a_id, "associatedcompanyid", str(b_id), only_if_missing=True)
            if a_type in ("companies", "deals") and b_type == "contacts":
                n = self.conn.execute("SELECT count(DISTINCT to_id) AS n FROM associations WHERE from_id = %s AND to_type = 'contacts'", (a_id,)).fetchone()["n"]
                self._set_prop(a_id, "num_associated_contacts", str(n))

    def _set_prop(self, id_: int, name: str, value: str | None, *, only_if_missing: bool = False) -> None:
        if only_if_missing:
            self.conn.execute("UPDATE objects SET properties = properties || %s WHERE id = %s AND NOT (properties ? %s)", (Jsonb({name: value}), id_, name))
        else:
            self.conn.execute("UPDATE objects SET properties = properties || %s WHERE id = %s", (Jsonb({name: value}), id_))

    def dissociate(self, from_type: str, from_id: int, to_type: str, to_id: int, type_ids: list[int] | None = None) -> None:
        if type_ids:
            for tid in type_ids:
                lab = self.assoc_label(tid)
                self.conn.execute("DELETE FROM associations WHERE from_id = %s AND to_id = %s AND type_id = %s", (from_id, to_id, tid))
                if lab and lab["inverse_type_id"] is not None:
                    self.conn.execute("DELETE FROM associations WHERE from_id = %s AND to_id = %s AND type_id = %s", (to_id, from_id, lab["inverse_type_id"]))
        else:
            self.conn.execute("DELETE FROM associations WHERE (from_id = %s AND to_id = %s) OR (from_id = %s AND to_id = %s)", (from_id, to_id, to_id, from_id))
        if from_type == "contacts" and to_type == "companies" or from_type == "companies" and to_type == "contacts":
            cid = from_id if from_type == "contacts" else to_id
            comp = to_id if from_type == "contacts" else from_id
            self.conn.execute("UPDATE objects SET properties = properties - 'associatedcompanyid' WHERE id = %s AND properties->>'associatedcompanyid' = %s", (cid, str(comp)))
            nxt = self.conn.execute("SELECT to_id FROM associations WHERE from_id = %s AND to_type = 'companies' ORDER BY type_id LIMIT 1", (cid,)).fetchone()
            if nxt:
                self._set_prop(cid, "associatedcompanyid", str(nxt["to_id"]))

    def associations_block(self, id_: int, to_types: list[str]) -> dict:
        out = {}
        for t in to_types:
            tt = defaults.resolve_type(t)
            if tt is None:
                continue
            rows = self.conn.execute(
                "SELECT a.to_id, a.type_id, l.name, l.label, l.category FROM associations a JOIN association_labels l ON l.type_id = a.type_id JOIN objects o ON o.id = a.to_id AND NOT o.archived WHERE a.from_id = %s AND a.to_type = %s ORDER BY a.to_id, a.type_id",
                (id_, tt),
            ).fetchall()
            if rows:
                out[tt] = {"results": [{"id": str(r["to_id"]), "type": (r["name"] or r["label"] or str(r["type_id"]))} for r in rows]}
        return out

    def associations_v4(self, from_type: str, from_id: int, to_type: str, limit: int = 500, after: str | None = None) -> tuple[list[dict], str | None]:
        sql = "SELECT a.to_id, a.type_id, l.label, l.category FROM associations a JOIN association_labels l ON l.type_id = a.type_id JOIN objects o ON o.id = a.to_id AND NOT o.archived WHERE a.from_id = %s AND a.to_type = %s"
        params: list = [from_id, to_type]
        if after:
            sql += " AND a.to_id > %s"
            params.append(int(after))
        sql += " ORDER BY a.to_id, a.type_id"
        rows = self.conn.execute(sql, params).fetchall()
        grouped: dict[int, list] = {}
        for r in rows:
            grouped.setdefault(r["to_id"], []).append({"category": r["category"], "typeId": r["type_id"], "label": r["label"]})
        ids = list(grouped.keys())
        page = ids[:limit]
        results = [{"toObjectId": i, "associationTypes": grouped[i]} for i in page]
        next_after = str(page[-1]) if len(ids) > limit else None
        return results, next_after

    def associated_ids(self, from_id: int, to_type: str) -> list[int]:
        rows = self.conn.execute("SELECT DISTINCT a.to_id FROM associations a JOIN objects o ON o.id = a.to_id AND NOT o.archived WHERE a.from_id = %s AND a.to_type = %s ORDER BY a.to_id", (from_id, to_type)).fetchall()
        return [int(r["to_id"]) for r in rows]

    # ------------------------------------------------------------ listing & search
    def list(self, object_type: str, limit: int = 10, after: str | None = None, properties: list[str] | None = None, associations: list[str] | None = None, archived: bool = False) -> tuple[list[dict], str | None]:
        sql = "SELECT * FROM objects WHERE object_type = %s AND archived = %s"
        params: list = [object_type, archived]
        if after:
            try:
                params.append(int(after))
            except ValueError:
                raise validation(f"Invalid paging cursor: {after}")
            sql += " AND id > %s"
        sql += " ORDER BY id LIMIT %s"
        params.append(limit + 1)
        rows = self.conn.execute(sql, params).fetchall()
        more = len(rows) > limit
        rows = rows[:limit]
        readable = self.readable_properties(object_type, properties)
        results = [record_out(r, readable, object_type) for r in rows]
        if associations:
            for r, row in zip(results, rows):
                r["associations"] = self.associations_block(row["id"], associations)
        return results, (str(rows[-1]["id"]) if more and rows else None)

    def search(self, object_type: str, body: dict) -> dict:
        from .search import build_search
        return build_search(self, object_type, body)

"""Full oracle-vs-server reconciliation of a migrated CRM.

Reads every record of every object type through the list endpoint (cursor pagination, no 10k
search cap), compares with `tests.reference.sinergia`, and prints a markdown report: per-type
counts, missing and extra records, mismatches per field with examples, association coverage on
a sample, R8 revenue/class, R9 dormant list.

    BASE_URL=http://127.0.0.1:8010 CRM_TOKEN=dev-token python -m tests.reference.reconcile \
        --export legacy/export.zip --types companies,deals --out /tmp/report.md

Assumes the server has already migrated that export (it does not call /__reset or /__migrate).
"""
from __future__ import annotations

import argparse
import os
import random
import sys
import time
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation

import httpx

from tests.reference import sinergia as S

NUMERIC = {"amount", "price", "quantity", "hs_discount_percentage", "fatturato_2025"}
DATES = {"closedate", "createdate", "closed_date", "hs_timestamp"}
ASSOC_PAIRS = [("contacts", "companies"), ("deals", "companies"), ("deals", "contacts"), ("line_items", "deals"),
               ("tickets", "contacts"), ("tickets", "companies"), ("notes", "contacts"), ("notes", "deals"),
               ("calls", "contacts"), ("calls", "deals"), ("emails", "contacts"), ("emails", "deals"),
               ("meetings", "contacts"), ("meetings", "deals")]


def same(field: str, exp, got) -> bool:
    if exp in (None, ""):
        return got in (None, "")
    if got in (None, ""):
        return False
    if field in NUMERIC:
        try:
            return Decimal(str(got)) == Decimal(str(exp))
        except InvalidOperation:
            return False
    if field in DATES:
        return str(got)[:19].replace(".000", "") == str(exp)[:19] or str(got)[:10] == str(exp)[:10]
    return str(got) == str(exp)


def fetch_all(client: httpx.Client, ot: str, props: list[str], assoc: list[str], limit: int = 100) -> dict[str, dict]:
    out: dict[str, dict] = {}
    after = None
    while True:
        params = {"limit": limit, "properties": ",".join(props)}
        if assoc:
            params["associations"] = ",".join(assoc)
        if after:
            params["after"] = after
        r = client.get(f"/crm/v3/objects/{ot}", params=params)
        if r.status_code != 200:
            raise RuntimeError(f"list {ot}: {r.status_code} {r.text[:300]}")
        body = r.json()
        for rec in body["results"]:
            out[rec["id"]] = rec
        after = body.get("paging", {}).get("next", {}).get("after")
        if not after:
            return out


def search_total(client: httpx.Client, ot: str, filters=None) -> int | None:
    body = {"limit": 1}
    if filters:
        body["filterGroups"] = [{"filters": filters}]
    r = client.post(f"/crm/v3/objects/{ot}/search", json=body)
    return r.json().get("total") if r.status_code == 200 else None


def reconcile(base_url: str, token: str, export: str, types: list[str], sample_assoc: int, out) -> int:
    t0 = time.time()
    ex = S.migrate(S.load_export(export))
    client = httpx.Client(base_url=base_url, headers={"Authorization": f"Bearer {token}"}, timeout=60)
    lines = [f"# Oracle vs server reconciliation", f"", f"- server: `{base_url}`", f"- export: `{export}`",
             f"- oracle: {len(ex.companies)} companies, {len(ex.contacts)} contacts, {len(ex.deals)} deals, {len(ex.tickets)} tickets, "
             f"{sum(len(getattr(ex, k)) for k in ('notes', 'calls', 'emails', 'meetings'))} activities, {len(ex.dormant)} dormant", ""]
    problems = 0
    crm_ids: dict[str, dict[str, str]] = {}     # type -> key -> crm id
    crm_recs: dict[str, dict[str, dict]] = {}   # type -> crm id -> record
    assoc_by_type = {ot: sorted({to for (f, to) in ASSOC_PAIRS if f == ot}) for ot in S.OBJECT_TYPES}
    for ot in types:
        exp = getattr(ex, ot)
        key = S.KEY_PROPERTY.get(ot, "id_legacy")
        fields = sorted({k for v in exp.values() for k in v if not k.startswith("_")})
        try:
            recs = fetch_all(client, ot, fields, assoc_by_type.get(ot, []))
        except Exception as e:  # noqa: BLE001
            lines += [f"## {ot}", "", f"**cannot list: {e}**", ""]
            problems += 1
            continue
        crm_recs[ot] = recs
        by_key: dict[str, list[str]] = defaultdict(list)
        for cid, rec in recs.items():
            k = (rec.get("properties") or {}).get(key)
            if k not in (None, ""):
                by_key[str(k)].append(cid)
        crm_ids[ot] = {k: v[0] for k, v in by_key.items()}
        dup_keys = [k for k, v in by_key.items() if len(v) > 1]
        missing = [k for k in exp if k not in by_key]
        extra = [cid for cid, rec in recs.items() if str((rec.get("properties") or {}).get(key) or "") not in exp]
        total = search_total(client, ot)
        mism: Counter = Counter()
        examples: dict[str, list] = defaultdict(list)
        compared = 0
        for k, props in exp.items():
            cid = crm_ids[ot].get(k)
            if cid is None:
                continue
            compared += 1
            got = recs[cid].get("properties") or {}
            for f, v in props.items():
                if f.startswith("_") or f == key:
                    continue
                if not same(f, v, got.get(f)):
                    mism[f] += 1
                    if len(examples[f]) < 3:
                        examples[f].append((k, v, got.get(f)))
        lines += [f"## {ot}", "",
                  f"| | count |", f"|---|---|",
                  f"| expected | {len(exp)} |", f"| listed through pagination | {len(recs)} |",
                  f"| search total | {total} |", f"| missing (expected key not in CRM) | {len(missing)} |",
                  f"| extra (CRM key not expected) | {len(extra)} |", f"| duplicate keys in CRM | {len(dup_keys)} |", ""]
        if missing:
            lines.append(f"- missing examples: {missing[:8]}")
        if extra:
            lines.append(f"- extra examples (crm ids): {extra[:8]}")
        if dup_keys:
            lines.append(f"- duplicate key examples: {dup_keys[:8]}")
        if missing or extra or dup_keys or total != len(exp):
            problems += 1
        if mism:
            problems += 1
            lines += ["", "| field | mismatches | examples (key: expected -> got) |", "|---|---|---|"]
            for f, n in mism.most_common():
                exs = "; ".join(f"`{k}`: `{e}` -> `{g}`" for k, e, g in examples[f])
                lines.append(f"| {f} | {n} | {exs} |")
        elif compared:
            lines.append(f"- all fields match on the {compared} records compared")
        else:
            lines.append("- nothing to compare")
        lines.append("")
        print(f"{ot}: expected {len(exp)} listed {len(recs)} total {total} missing {len(missing)} extra {len(extra)} mismatched fields {dict(mism)}", file=sys.stderr)

    # associations: full check for pairs where the list endpoint returned associations, sample otherwise
    lines += ["## associations", "", "| from -> to | expected | checked | missing | stray | note |", "|---|---|---|---|---|---|"]
    rng = random.Random(11)
    for frm, to in ASSOC_PAIRS:
        if frm not in crm_recs or to not in crm_ids:
            continue
        exp_pairs: dict[str, set[str]] = defaultdict(set)
        for (f, fk, t, tk) in ex.associations:
            if f == frm and t == to:
                exp_pairs[fk].add(tk)
        keys = list(crm_ids[frm])
        checked = missing_n = stray_n = 0
        note = "from list `associations=`"
        have_inline = any("associations" in rec for rec in list(crm_recs[frm].values())[:50])
        if not have_inline:
            keys = rng.sample(keys, min(sample_assoc, len(keys)))
            note = f"sample of {len(keys)} via v4 GET"
        to_key_by_id = {v: k for k, v in crm_ids[to].items()}
        examples = []
        for fk in keys:
            cid = crm_ids[frm][fk]
            if have_inline:
                res = ((crm_recs[frm][cid].get("associations") or {}).get(to) or {}).get("results") or []
                got_ids = {str(x.get("id") or x.get("toObjectId")) for x in res}
            else:
                r = client.get(f"/crm/v4/objects/{frm}/{cid}/associations/{to}", params={"limit": 500})
                got_ids = {str(x["toObjectId"]) for x in r.json().get("results", [])} if r.status_code == 200 else set()
            got_keys = {to_key_by_id.get(i, f"?{i}") for i in got_ids}
            want = exp_pairs.get(fk, set())
            checked += 1
            if want - got_keys:
                missing_n += 1
                if len(examples) < 3:
                    examples.append(f"`{fk}` wants {sorted(want - got_keys)[:3]}")
            if got_keys - want:
                stray_n += 1
                if len(examples) < 3:
                    examples.append(f"`{fk}` has extra {sorted(got_keys - want)[:3]}")
        if missing_n or stray_n:
            problems += 1
        lines.append(f"| {frm} -> {to} | {sum(len(v) for v in exp_pairs.values())} | {checked} | {missing_n} | {stray_n} | {note}; {'; '.join(examples)} |")
    lines.append("")

    # R8 class totals and R9 dormant list
    if "companies" in crm_ids:
        lines += ["## R8 classes", "", "| class | expected | search total |", "|---|---|---|"]
        for cls in ("A", "B", "C"):
            exp_n = sum(1 for v in ex.companies.values() if v.get("classe_cliente") == cls)
            got_n = search_total(client, "companies", [{"propertyName": "classe_cliente", "operator": "EQ", "value": cls}])
            if got_n != exp_n:
                problems += 1
            lines.append(f"| {cls} | {exp_n} | {got_n} |")
        lines.append("")
        r = client.get("/crm/v3/lists/object-type-id/0-2/name/Clienti dormienti")
        if r.status_code != 200:
            lines += ["## R9 dormant", "", f"**list not found: {r.status_code} {r.text[:200]}**", ""]
            problems += 1
        else:
            lid = r.json()["list"]["listId"]
            members: set[str] = set()
            after = None
            while True:
                params = {"limit": 250}
                if after:
                    params["after"] = after
                res = client.get(f"/crm/v3/lists/{lid}/memberships", params=params).json()
                members |= {str(x["recordId"]) for x in res.get("results", [])}
                after = res.get("paging", {}).get("next", {}).get("after")
                if not after:
                    break
            exp_ids = {crm_ids["companies"][k] for k in ex.dormant if k in crm_ids["companies"]}
            id_to_key = {v: k for k, v in crm_ids["companies"].items()}
            only_exp = sorted(id_to_key.get(i, i) for i in exp_ids - members)[:10]
            only_got = sorted(id_to_key.get(i, i) for i in members - exp_ids)[:10]
            if members != exp_ids:
                problems += 1
            lines += ["## R9 dormant", "", f"- expected {len(ex.dormant)}, list has {len(members)}, missing {len(exp_ids - members)}, unexpected {len(members - exp_ids)}",
                      f"- missing examples (id_legacy): {only_exp}", f"- unexpected examples (id_legacy): {only_got}", ""]
    lines.append(f"_{problems} problem groups, {time.time() - t0:.0f} s_")
    out.write("\n".join(lines) + "\n")
    return problems


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=os.environ.get("BASE_URL", "http://127.0.0.1:8010"))
    ap.add_argument("--token", default=os.environ.get("CRM_TOKEN", "dev-token"))
    ap.add_argument("--export", default=os.environ.get("EXPORT_ZIP", "legacy/export.zip"))
    ap.add_argument("--types", default=",".join(S.OBJECT_TYPES))
    ap.add_argument("--sample-assoc", type=int, default=300)
    ap.add_argument("--out", default="-")
    a = ap.parse_args()
    types = [t for t in a.types.split(",") if t]
    out = sys.stdout if a.out == "-" else open(a.out, "w")
    problems = reconcile(a.base_url, a.token, a.export, types, a.sample_assoc, out)
    if out is not sys.stdout:
        out.close()
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()

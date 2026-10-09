"""R1-R9 on the sample export: compare the migrated CRM with the independent reference
implementation in tests/reference (pure Python over the CSVs)."""
import random
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.acceptance.conftest import EXPORT_ZIP, assoc_ids, by_legacy, search  # noqa: E402

pytestmark = pytest.mark.migration

SAMPLE = 40
OBJECTS = ["companies", "contacts", "deals", "products", "line_items", "tickets", "notes", "calls", "emails", "meetings"]


@pytest.fixture(scope="module")
def expected():
    from tests.reference import sinergia

    if not EXPORT_ZIP.exists():
        pytest.skip("no export zip")
    return sinergia.migrate(sinergia.load_export(EXPORT_ZIP))


class Resolver:
    """id_legacy (or hs_sku for products) -> CRM id, resolved lazily in batches of IN searches."""

    def __init__(self, client):
        self.client = client
        self.cache = {ot: {} for ot in OBJECTS}

    def key_prop(self, ot):
        return "hs_sku" if ot == "products" else "id_legacy"

    def resolve(self, ot, keys):
        keys = [str(k) for k in keys]
        missing = [k for k in keys if k not in self.cache[ot]]
        for i in range(0, len(missing), 100):
            chunk = missing[i:i + 100]
            res = search(self.client, ot, [{"propertyName": self.key_prop(ot), "operator": "IN", "values": chunk}], [self.key_prop(ot)], limit=200)
            assert res["total"] <= len(chunk), f"{ot}: duplicate keys in CRM for {chunk[:5]}"
            for x in res["results"]:
                self.cache[ot][x["properties"][self.key_prop(ot)]] = x["id"]
            for k in chunk:
                self.cache[ot].setdefault(k, None)
        return {k: self.cache[ot][k] for k in keys}

    def one(self, ot, key):
        return self.resolve(ot, [key])[str(key)]

    def all_pairs(self, ot, limit=100):
        """Walk the whole list endpoint: (id, key) for every record, exactly once."""
        after = None
        seen = {}
        while True:
            params = {"limit": limit, "properties": self.key_prop(ot)}
            if after:
                params["after"] = after
            r = self.client.get(f"/crm/v3/objects/{ot}", params=params)
            assert r.status_code == 200, r.text[:200]
            body = r.json()
            for x in body["results"]:
                assert x["id"] not in seen, f"{ot}: id {x['id']} returned twice while paging"
                seen[x["id"]] = x["properties"].get(self.key_prop(ot))
            after = body.get("paging", {}).get("next", {}).get("after")
            if not after:
                break
        return seen


@pytest.fixture(scope="module")
def ids(client, migrated):
    return Resolver(client)


def test_migration_time(migrated):
    print(f"\nmigration took {migrated:.1f}s")
    assert migrated < 150, "too close to the 5 minute Railway limit (2x slower there)"


@pytest.mark.parametrize("ot", OBJECTS)
def test_counts(client, expected, ot):
    total = search(client, ot, limit=1)["total"]
    exp = len(getattr(expected, ot))
    assert total == exp, f"{ot}: CRM has {total}, reference expects {exp}"


def _check_props(crm_props, exp_props, label):
    for k, v in exp_props.items():
        if k.startswith("_"):
            continue
        got = crm_props.get(k)
        if v in (None, ""):
            assert got in (None, ""), f"{label}: {k} should be empty, got {got!r}"
            continue
        if k in ("amount", "price", "quantity", "hs_discount_percentage", "fatturato_2025"):
            assert got not in (None, ""), f"{label}: {k} missing"
            assert Decimal(got) == Decimal(v), f"{label}: {k} {got!r} != {v!r}"
        elif k in ("closedate", "createdate", "closed_date", "hs_timestamp"):
            assert got and got[:10] == v[:10], f"{label}: {k} {got!r} != {v!r}"
        else:
            assert got == v, f"{label}: {k} {got!r} != {v!r}"


@pytest.mark.parametrize("ot", OBJECTS)
def test_sample_records_fields(client, expected, ids, ot):
    exp = getattr(expected, ot)
    rng = random.Random(42)
    keys = rng.sample(sorted(exp), min(SAMPLE, len(exp)))
    found = ids.resolve(ot, keys)
    missing = [k for k in keys if not found[k]]
    assert not missing, f"{ot}: key missing in CRM: {missing[:10]}"
    for k in keys:
        rec = client.get(f"/crm/v3/objects/{ot}/{found[k]}").json()
        _check_props(rec["properties"], exp[k], f"{ot} {k}")


def test_merged_rows_are_gone(client, expected, ids):
    for ot in ("companies", "contacts"):
        merged = getattr(expected, "merged_into")[ot]
        olds = [old for old in list(merged)[:300] if old != merged[old]]
        found = ids.resolve(ot, olds)
        gone = [old for old in olds if found[old]]
        assert not gone, f"{ot}: merged rows still present: {gone[:10]}"


def test_associations_sample(client, expected, ids):
    rng = random.Random(7)
    assocs = sorted(expected.associations)
    picked = rng.sample(assocs, min(300, len(assocs)))
    bad = []
    for ot in OBJECTS:
        ids.resolve(ot, [fl for (f, fl, t, tl) in picked if f == ot] + [tl for (f, fl, t, tl) in picked if t == ot])
    for from_ot, from_legacy, to_ot, to_legacy in picked:
        fid = ids.one(from_ot, from_legacy)
        tid = ids.one(to_ot, to_legacy)
        if fid is None or tid is None:
            bad.append(("missing record", from_ot, from_legacy, to_ot, to_legacy))
            continue
        if tid not in assoc_ids(client, from_ot, fid, to_ot):
            bad.append(("missing", from_ot, from_legacy, to_ot, to_legacy))
    assert not bad, bad[:15]
    # deals: contacts associated exactly once and no stray associations
    for legacy in rng.sample(sorted(expected.deals), 30):
        exp_contacts = {t for (f, fl, tt, t) in assocs if f == "deals" and fl == legacy and tt == "contacts"}
        got = assoc_ids(client, "deals", ids.one("deals", legacy), "contacts")
        want = set(ids.resolve("contacts", exp_contacts).values())
        assert got == want, f"deal {legacy} contacts: got {got} want {want}"


def test_r8_revenue_and_class(client, expected, ids):
    rng = random.Random(3)
    comps = expected.companies
    with_rev = [k for k, v in comps.items() if Decimal(v.get("fatturato_2025", "0") or "0") != 0]
    zero = [k for k, v in comps.items() if Decimal(v.get("fatturato_2025", "0") or "0") == 0]
    sample = rng.sample(with_rev, min(len(with_rev), 200)) + rng.sample(zero, min(20, len(zero)))
    found = ids.resolve("companies", sample)
    for k in sample:
        assert found[k], f"company {k} missing"
        p = client.get(f"/crm/v3/objects/companies/{found[k]}", params={"properties": "fatturato_2025,classe_cliente,name"}).json()["properties"]
        assert Decimal(p.get("fatturato_2025") or "0") == Decimal(comps[k]["fatturato_2025"]), f"{k} {p}"
        assert (p.get("classe_cliente") or "") == (comps[k].get("classe_cliente") or ""), f"{k} {p}"
    for cls in ("A", "B", "C"):
        exp = sum(1 for v in comps.values() if v.get("classe_cliente") == cls)
        got = search(client, "companies", [{"propertyName": "classe_cliente", "operator": "EQ", "value": cls}], limit=1)["total"]
        assert got == exp, f"class {cls}: {got} != {exp}"


def test_r9_dormant_list(client, expected, ids):
    r = client.get("/crm/v3/lists/object-type-id/0-2/name/Clienti dormienti")
    assert r.status_code == 200, r.text
    lid = r.json()["list"]["listId"]
    members = set()
    after = None
    while True:
        params = {"limit": 250}
        if after:
            params["after"] = after
        res = client.get(f"/crm/v3/lists/{lid}/memberships", params=params).json()
        members |= {str(x["recordId"]) for x in res["results"]}
        after = res.get("paging", {}).get("next", {}).get("after")
        if not after:
            break
    found = ids.resolve("companies", sorted(expected.dormant))
    exp = {v for v in found.values() if v}
    assert len(members) == len(expected.dormant), f"dormant: {len(members)} != {len(expected.dormant)}"
    extra = members - exp
    missing = exp - members
    assert not extra and not missing, f"dormant extra {sorted(extra)[:10]} missing {sorted(missing)[:10]}"


def test_custom_properties_and_pipelines(client, migrated):
    for ot, names in {"companies": ["id_legacy", "partita_iva", "fatturato_2025", "classe_cliente"], "deals": ["id_legacy", "commerciale"], "tickets": ["id_legacy", "assegnatario"], "notes": ["id_legacy", "autore"], "calls": ["id_legacy", "autore"], "emails": ["id_legacy", "autore"], "meetings": ["id_legacy", "autore"], "contacts": ["id_legacy"], "line_items": ["id_legacy"]}.items():
        props = {p["name"]: p for p in client.get(f"/crm/v3/properties/{ot}").json()["results"]}
        for n in names:
            assert n in props, f"{ot} misses property {n}"
    assert client.get("/crm/v3/properties/companies/partita_iva").json()["hasUniqueValue"] is True
    assert client.get("/crm/v3/properties/companies/fatturato_2025").json()["type"] == "number"
    pipes = {p["label"]: p for p in client.get("/crm/v3/pipelines/deals").json()["results"]}
    assert "Rinnovi" in pipes
    st = pipes["Rinnovi"]["stages"]
    assert [s["label"] for s in st] == ["Da rinnovare", "In trattativa", "Rinnovato", "Non rinnovato"]
    assert [s["metadata"].get("probability") for s in st] == ["0.2", "0.6", "1.0", "0.0"]
    tp = {p["label"]: p for p in client.get("/crm/v3/pipelines/tickets").json()["results"]}
    assert "Assistenza" in tp
    assert [s["label"] for s in tp["Assistenza"]["stages"]] == ["Aperto", "In lavorazione", "In attesa del cliente", "Chiuso"]
    assert [s["metadata"].get("ticketState") for s in tp["Assistenza"]["stages"]] == ["OPEN", "OPEN", "OPEN", "CLOSED"]


def test_reads_fast_under_load(client, ids, base_url, token):
    import concurrent.futures
    import time

    import httpx

    pairs = ids.all_pairs("contacts", limit=100)
    total = search(client, "contacts", limit=1)["total"]
    assert len(pairs) == total, f"paged {len(pairs)} contacts, search total {total}"
    sample = random.Random(1).sample(list(pairs), 100)

    def read(i):
        with httpx.Client(base_url=base_url, headers={"Authorization": f"Bearer {token}"}, timeout=30) as c:
            t0 = time.time()
            r = c.get(f"/crm/v3/objects/contacts/{i}")
            return r.status_code, time.time() - t0

    with concurrent.futures.ThreadPoolExecutor(20) as ex:
        res = list(ex.map(read, sample * 2))
    codes = [c for c, _ in res]
    lat = sorted(t for _, t in res)
    assert all(c < 500 for c in codes)
    p95 = lat[int(len(lat) * 0.95)]
    print(f"\np95 read latency {p95*1000:.0f} ms")
    assert p95 < 1.0

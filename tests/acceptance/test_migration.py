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


@pytest.fixture(scope="module")
def ids(client, migrated, expected):
    """id_legacy -> CRM id maps per object type, read through search pagination (every record once)."""
    from tests.reference.sinergia import KEY_PROPERTY

    out = {}
    for ot in OBJECTS:
        key = KEY_PROPERTY.get(ot, "id_legacy")
        m = {}
        after = None
        total = None
        while True:
            res = search(client, ot, properties=[key], limit=200, after=after, sorts=[{"propertyName": "hs_object_id", "direction": "ASCENDING"}])
            total = res["total"]
            for x in res["results"]:
                m[x["properties"].get(key)] = x["id"]
            after = res.get("paging", {}).get("next", {}).get("after")
            if not after:
                break
            if len(m) > 10000:
                break
        if len(m) <= 10000:
            assert total == len(m), f"{ot}: total {total} but {len(m)} distinct records paged"
        out[ot] = m
    return out


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
    missing = [k for k in keys if k not in ids[ot]]
    assert not missing, f"{ot}: id_legacy missing in CRM: {missing[:10]}"
    for k in keys:
        rec = client.get(f"/crm/v3/objects/{ot}/{ids[ot][k]}").json()
        _check_props(rec["properties"], exp[k], f"{ot} {k}")


def test_merged_rows_are_gone(client, expected, ids):
    for ot in ("companies", "contacts"):
        merged = getattr(expected, "merged_into")[ot]
        gone = [old for old in list(merged)[:200] if old != merged[old] and old in ids[ot]]
        assert not gone, f"{ot}: merged rows still present: {gone[:10]}"


def test_associations_sample(client, expected, ids):
    rng = random.Random(7)
    assocs = sorted(expected.associations)
    picked = rng.sample(assocs, min(300, len(assocs)))
    bad = []
    for from_ot, from_legacy, to_ot, to_legacy in picked:
        fid = ids[from_ot].get(from_legacy)
        tid = ids[to_ot].get(to_legacy)
        if fid is None or tid is None:
            bad.append(("missing record", from_ot, from_legacy, to_ot, to_legacy))
            continue
        if tid not in assoc_ids(client, from_ot, fid, to_ot):
            bad.append(("missing", from_ot, from_legacy, to_ot, to_legacy))
    assert not bad, bad[:15]
    # deals: contacts associated exactly once and no stray associations
    for legacy in rng.sample(sorted(expected.deals), 30):
        exp_contacts = {t for (f, fl, tt, t) in assocs if f == "deals" and fl == legacy and tt == "contacts"}
        got = assoc_ids(client, "deals", ids["deals"][legacy], "contacts")
        assert got == {ids["contacts"][c] for c in exp_contacts}, f"deal {legacy} contacts"


def test_r8_revenue_and_class(client, expected, ids):
    rng = random.Random(3)
    comps = expected.companies
    with_rev = [k for k, v in comps.items() if Decimal(v.get("fatturato_2025", "0") or "0") != 0]
    zero = [k for k, v in comps.items() if Decimal(v.get("fatturato_2025", "0") or "0") == 0]
    for k in rng.sample(with_rev, min(40, len(with_rev))) + rng.sample(zero, min(10, len(zero))):
        p = client.get(f"/crm/v3/objects/companies/{ids['companies'][k]}", params={"properties": "fatturato_2025,classe_cliente,name"}).json()["properties"]
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
    exp = {ids["companies"][k] for k in expected.dormant if k in ids["companies"]}
    assert len(members) == len(expected.dormant), f"dormant: {len(members)} != {len(expected.dormant)}"
    assert members == exp


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

    sample = random.Random(1).sample(list(ids["contacts"].values()), 100)

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

"""R13 scenarios on the migrated sample export. Each test costs model calls: run with
`-m assistant` deliberately, never in a loop. Checks are on CRM state and on facts in the reply,
as the organizers score them."""
import re
import uuid

import pytest

from tests.acceptance.conftest import assoc_ids, search

pytestmark = [pytest.mark.migration, pytest.mark.assistant]

NOW = "2026-12-02T10:00:00+01:00"


def ask(client, user, *turns, prior=None):
    messages = list(prior or [])
    for t in turns:
        messages.append({"role": "user", "content": t} if isinstance(t, str) else t)
    r = client.post("/__agente", json={"context": {"now": NOW, "user": user}, "messages": messages}, timeout=65)
    assert r.status_code == 200, r.text[:300]
    reply = r.json()["reply"]
    assert isinstance(reply, str) and reply.strip()
    messages.append({"role": "assistant", "content": reply})
    return reply, messages


def numbers_in(text):
    out = set()
    for m in re.finditer(r"\d[\d.,]*", text):
        s = m.group(0)
        it = s.replace(".", "").replace(",", ".") if re.search(r",\d{1,2}$", s) else s.replace(",", "")
        try:
            out.add(round(float(it), 2))
        except ValueError:
            pass
    return out


def company_by_name(client, name):
    res = search(client, "companies", [{"propertyName": "name", "operator": "CONTAINS_TOKEN", "value": name.split()[0]}], ["name", "fatturato_2025", "classe_cliente"], limit=50)
    hits = [x for x in res["results"] if name.lower() in x["properties"]["name"].lower()]
    return hits


def test_example_2_revenue_question(client, migrated):
    hits = company_by_name(client, "Nuova Tessile Spinelli")
    if not hits:
        pytest.skip("company not in this export")
    expected = {round(float(h["properties"].get("fatturato_2025") or 0), 2) for h in hits}
    reply, _ = ask(client, "mattia.vigano@brambillaforniture.it", "Quanto abbiamo fatturato con Nuova Tessile Spinelli nel 2025?")
    print("\nREPLY:", reply)
    assert expected & numbers_in(reply), f"reply lacks the revenue {expected}: {reply}"


def test_example_1_mark_deal_won(client, migrated):
    hits = company_by_name(client, "Nuova Serramenti Mazza")
    if not hits:
        pytest.skip("company not in this export")
    # find open deals of that company
    open_deals = []
    for h in hits:
        for did in assoc_ids(client, "companies", h["id"], "deals"):
            d = client.get(f"/crm/v3/objects/deals/{did}", params={"properties": "dealname,dealstage,pipeline"}).json()
            if d["properties"]["dealstage"] not in ("closedwon", "closedlost") and d["properties"]["pipeline"] == "default":
                open_deals.append(d)
    if len(open_deals) != 1:
        pytest.skip(f"example needs exactly one open deal, found {len(open_deals)}")
    before = client.post("/crm/v3/objects/deals/search", json={"limit": 1}).json()["total"]
    reply, msgs = ask(client, "elena.silvestri@brambillaforniture.it", "Segna come vinta la trattativa di Nuova Serramenti Mazza, è arrivato l'ordine firmato.")
    print("\nREPLY:", reply)
    d = client.get(f"/crm/v3/objects/deals/{open_deals[0]['id']}", params={"properties": "dealstage"}).json()
    assert d["properties"]["dealstage"] == "closedwon", reply
    assert client.post("/crm/v3/objects/deals/search", json={"limit": 1}).json()["total"] == before, "no deals created"
    # R10 fired through the assistant too
    assert assoc_ids(client, "deals", open_deals[0]["id"], "tickets")


def test_create_contact_with_r12(client, migrated):
    dom = f"assist-{uuid.uuid4().hex[:5]}.example"
    co = client.post("/crm/v3/objects/companies", json={"properties": {"name": "Assistente Test Srl", "domain": dom}}).json()["id"]
    reply, _ = ask(client, "anna.sala@brambillaforniture.it", f"Aggiungi il contatto Marco Verdi, email marco.verdi@{dom}, telefono 02 1234567, dell'azienda Assistente Test Srl")
    print("\nREPLY:", reply)
    res = search(client, "contacts", [{"propertyName": "email", "operator": "EQ", "value": f"marco.verdi@{dom}"}], ["firstname", "lastname", "phone"])
    assert res["total"] == 1, reply
    p = res["results"][0]["properties"]
    assert p["firstname"] == "Marco" and p["lastname"] == "Verdi"
    assert co in assoc_ids(client, "contacts", res["results"][0]["id"], "companies")


def test_refuses_duplicate_vat(client, migrated):
    piva = "%011d" % (uuid.uuid4().int % 10**11)
    client.post("/crm/v3/objects/companies", json={"properties": {"name": "Esistente Spa", "partita_iva": piva}})
    before = client.post("/crm/v3/objects/companies/search", json={"limit": 1}).json()["total"]
    reply, _ = ask(client, "anna.sala@brambillaforniture.it", f"Crea l'azienda Nuova Ditta Srl con partita IVA {piva}")
    print("\nREPLY:", reply)
    assert client.post("/crm/v3/objects/companies/search", json={"limit": 1}).json()["total"] == before, "must not create a company with an existing VAT"
    assert re.search(r"iva|esist|già", reply, re.I)


def test_asks_when_ambiguous(client, migrated):
    for i in range(2):
        client.post("/crm/v3/objects/deals", json={"properties": {"dealname": f"Fornitura Ambigua {i}", "dealstage": "qualifiedtobuy", "commerciale": "anna.sala@brambillaforniture.it"}})
    reply, msgs = ask(client, "anna.sala@brambillaforniture.it", "Metti in fase contratto la trattativa Fornitura Ambigua")
    print("\nREPLY:", reply)
    res = search(client, "deals", [{"propertyName": "dealname", "operator": "CONTAINS_TOKEN", "value": "Ambigua"}], ["dealname", "dealstage"])
    assert all(x["properties"]["dealstage"] == "qualifiedtobuy" for x in res["results"]), "ambiguous request must not move anything"
    assert "?" in reply
    reply2, _ = ask(client, "anna.sala@brambillaforniture.it", "Quella che finisce con 1", prior=msgs)
    print("\nREPLY2:", reply2)
    res = search(client, "deals", [{"propertyName": "dealname", "operator": "EQ", "value": "Fornitura Ambigua 1"}], ["dealstage"])
    assert res["results"][0]["properties"]["dealstage"] == "contractsent"


def test_my_customers_question(client, migrated):
    user = "anna.sala@brambillaforniture.it"
    res = search(client, "deals", [{"propertyName": "commerciale", "operator": "EQ", "value": user}], ["dealname"], limit=1)
    if res["total"] == 0:
        pytest.skip("user has no deals in this export")
    reply, _ = ask(client, user, "Quante trattative aperte ho in questo momento?")
    print("\nREPLY:", reply)
    open_total = client.post("/crm/v3/objects/deals/search", json={"filterGroups": [{"filters": [{"propertyName": "commerciale", "operator": "EQ", "value": user}, {"propertyName": "hs_is_closed", "operator": "NEQ", "value": "true"}]}], "limit": 1}).json()["total"]
    assert float(open_total) in numbers_in(reply) or str(open_total) in reply, f"expected {open_total} in reply"


def test_csv_attachment_creates_contacts(client, migrated):
    dom = f"csv-{uuid.uuid4().hex[:5]}.example"
    csv = "nome;cognome;email;telefono\nLaura;Bianchi;laura.bianchi@" + dom + ";02 111\nPaolo;Neri;paolo.neri@" + dom + ";02 222\n"
    msg = {"role": "user", "content": "Importa questi contatti dal file allegato", "attachments": [{"name": "contatti.csv", "content_type": "text/csv", "content": csv}]}
    reply, _ = ask(client, "anna.sala@brambillaforniture.it", msg)
    print("\nREPLY:", reply)
    for e in (f"laura.bianchi@{dom}", f"paolo.neri@{dom}"):
        assert search(client, "contacts", [{"propertyName": "email", "operator": "EQ", "value": e}])["total"] == 1, e

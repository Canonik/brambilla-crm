"""Data access and retrieval tools of the assistant, driven by a scripted model (no network, no key):
Sinergia CSV attachments, legacy ids, name matching, active-user checks (R3), line items (R3/R4)."""
import datetime as dt
import json

from app import db
from app.assistant import agent
from app.assistant.tools import ToolContext, run_tool

from .conftest import H

CTX = {"now": "2026-12-02T10:00:00+01:00", "user": "anna.sala@brambillaforniture.it"}
NOW = dt.datetime(2026, 12, 2, 9, 0, tzinfo=dt.timezone.utc)


class Script:
    def __init__(self, steps):
        self.steps = list(steps)
        self.seen = []

    def __call__(self, messages, tools, **kw):
        self.seen.append(messages[-1])
        step = self.steps.pop(0)
        if isinstance(step, str):
            return {"content": step}
        return {"content": None, "tool_calls": [{"id": f"c{i}", "type": "function", "function": {"name": n, "arguments": json.dumps(a)}} for i, (n, a) in enumerate(step)]}


def tool_results(script):
    return [json.loads(m["content"]) for m in script.seen if m.get("role") == "tool"]


def seed_users():
    with db.connection() as conn:
        conn.execute("DELETE FROM crm_users")
        conn.cursor().executemany(
            "INSERT INTO crm_users (id, firstname, lastname, email, role, manager_id, active) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            [
                ("U01", "Anna", "Sala", "anna.sala@brambillaforniture.it", "Commerciale", None, True),
                ("U29", "Marco", "Costa", "marco.costa@brambillaforniture.it", "Commerciale", "U01", False),
                ("U81", "Marco", "Costa", "m.costa@brambillaforniture.it", "Commerciale", "U01", True),
                ("U47", "Luca", "Santoro", "luca.santoro@brambillaforniture.it", "Commerciale", "U01", False),
            ],
        )
        conn.commit()


def tool(name, args, user=CTX["user"], attachments=None):
    ctx = ToolContext(NOW, user)
    ctx.attachments = attachments or []
    return run_tool(ctx, name, args)


def ask(api, monkeypatch, script, text, attachments=None, prior=None):
    monkeypatch.setattr(agent, "MODEL_CLIENT", script)
    msg = {"role": "user", "content": text}
    if attachments:
        msg["attachments"] = attachments
    r = api.post("/__agente", headers=H, json={"context": CTX, "messages": list(prior or []) + [msg]})
    assert r.status_code == 200
    return r.json()["reply"]


def company(api, name, legacy, domain=None, **props):
    p = {"name": name, "id_legacy": legacy, **props}
    if domain:
        p["domain"] = domain
    return api.post("/crm/v3/objects/companies", headers=H, json={"properties": p}).json()


def get(api, ot, id_):
    return api.get(f"/crm/v3/objects/{ot}/{id_}", headers=H).json()["properties"]


CONTACTS_CSV = (
    "id_contatto;nome;cognome;email;telefono;id_azienda;tipo;cancellato;ultima_modifica\n"
    "5175588;Elisa;Bellini;e.bellini@libero.it;;;CLIENTE;NO;27/07/2022 08:00:00\n"
    "5175589; Giulia ;Ferri;g.ferri@nuovaserramentimazza.it;+39 02 1234567;264566;Prospect;NO;01/03/2024 10:00:00\n"
    "5175590;Paolo;Riva;p.riva(at)gmail.com;3331234567;999999;Lead;NO;01/03/2024 10:00:00\n"
    "5175591;Mario;Cancellato;m.cancellato@example.com;;264566;CLIENTE;SI;01/03/2024 10:00:00\n"
    "5175592;Sara;Conti;s.conti@nuovaserramentimazza.it;;;Ex cliente;NO;01/03/2024 10:00:00\n"
)


def test_contacts_csv_preview_then_import_resolves_legacy_company_and_never_duplicates(api, monkeypatch):
    seed_users()
    comp = company(api, "Nuova Serramenti Mazza S.r.l.", "264566", "nuovaserramentimazza.it", city="Lecco")
    before_company = get(api, "companies", comp["id"])
    existing = api.post("/crm/v3/objects/contacts", headers=H, json={"properties": {"firstname": "Elisa", "lastname": "Bellini", "email": "e.bellini@libero.it", "phone": "0341 000"}}).json()
    before_existing = get(api, "contacts", existing["id"])
    att = [{"name": "contatti.csv", "content_type": "text/csv", "content": CONTACTS_CSV}]
    script = Script([
        [("preview_attachment", {})],
        [("import_attachment", {"name": "contatti.csv"})],
        "Importati 3 contatti, 1 esisteva già, 1 era cancellato.",
    ])
    ask(api, monkeypatch, script, "Importa i contatti dell'allegato", attachments=att)
    preview, imported = tool_results(script)
    assert preview["object_type"] == "contacts" and preview["summary"] == {"rows": 5, "new": 3, "existing": 1, "skipped": 1, "with_warnings": 1}
    giulia = preview["rows"][1]
    assert giulia["properties"]["firstname"] == "Giulia" and giulia["properties"]["lifecyclestage"] == "opportunity" and giulia["properties"]["phone"] == "+39 02 1234567"
    assert giulia["associations"][0]["id"] == comp["id"] and giulia["associations"][0]["via"] == "id_azienda=264566"
    assert preview["rows"][0]["existing"]["id"] == existing["id"] and preview["rows"][0]["existing"]["match"] == "email"
    riva_warnings = " | ".join(preview["rows"][2]["warnings"])
    assert "id_azienda=999999" in riva_warnings and "non valida" in riva_warnings
    assert preview["rows"][3]["skip"] == "cancellato in Sinergia"
    assert imported["summary"] == {"rows": 5, "created": 3, "updated": 0, "skipped": 2, "failed": 0}
    # CRM state: the new contacts, their company (legacy id or R12 by email domain), the untouched ones
    g = api.post("/crm/v3/objects/contacts/search", headers=H, json={"filters": [{"propertyName": "email", "operator": "EQ", "value": "g.ferri@nuovaserramentimazza.it"}]}).json()
    assert g["total"] == 1 and g["results"][0]["properties"]["lifecyclestage"] == "opportunity" and g["results"][0]["properties"]["id_legacy"] == "5175589"
    assert g["results"][0]["properties"]["associatedcompanyid"] == comp["id"]
    s = api.post("/crm/v3/objects/contacts/search", headers=H, json={"filters": [{"propertyName": "email", "operator": "EQ", "value": "s.conti@nuovaserramentimazza.it"}]}).json()
    assert s["results"][0]["properties"]["associatedcompanyid"] == comp["id"] and s["results"][0]["properties"]["lifecyclestage"] == "other"
    p = api.post("/crm/v3/objects/contacts/search", headers=H, json={"query": "Riva"}).json()
    assert p["total"] == 1 and "email" not in p["results"][0]["properties"] and p["results"][0]["properties"]["phone"] == "3331234567"
    assert api.post("/crm/v3/objects/contacts/search", headers=H, json={"query": "e.bellini"}).json()["total"] == 1
    assert api.post("/crm/v3/objects/contacts/search", headers=H, json={"query": "Cancellato"}).json()["total"] == 0
    assert get(api, "contacts", existing["id"]) == before_existing
    after_company = get(api, "companies", comp["id"])
    assert {k: v for k, v in after_company.items() if k not in ("num_associated_contacts", "hs_lastmodifieddate")} == {k: v for k, v in before_company.items() if k not in ("num_associated_contacts", "hs_lastmodifieddate")}


def test_preview_answers_questions_without_writing(api, monkeypatch):
    seed_users()
    att = [{"name": "nuovi.csv", "content_type": "text/csv", "content": CONTACTS_CSV}]
    before = api.post("/crm/v3/objects/contacts/search", headers=H, json={"limit": 1}).json()["total"]
    script = Script([[("preview_attachment", {"name": "nuovi.csv"})], "Nell'allegato ci sono 5 contatti, uno è cancellato."])
    ask(api, monkeypatch, script, "Quanti contatti ci sono nell'allegato?", attachments=att)
    assert tool_results(script)[0]["summary"]["rows"] == 5
    assert api.post("/crm/v3/objects/contacts/search", headers=H, json={"limit": 1}).json()["total"] == before


def test_attachment_from_an_earlier_turn_is_still_readable(api, monkeypatch):
    seed_users()
    prior = [
        {"role": "user", "content": "Ti mando i contatti", "attachments": [{"name": "c.csv", "content_type": "text/csv", "content": "nome;cognome;email\nAda;Verdi;ada.verdi@example.com"}]},
        {"role": "assistant", "content": "Ricevuto: 1 contatto. Lo importo?"},
    ]
    script = Script([[("import_attachment", {})], "Fatto."])
    ask(api, monkeypatch, script, "Sì, importalo", prior=prior)
    assert tool_results(script)[0]["summary"]["created"] == 1
    assert api.post("/crm/v3/objects/contacts/search", headers=H, json={"query": "ada.verdi"}).json()["total"] == 1


def test_no_attachment_is_an_explicit_error(api):
    assert "nessun allegato" in tool("preview_attachment", {})["error"]
    att = [{"name": "a.csv", "content": "nome;cognome\nA;B"}]
    assert "non trovato" in tool("preview_attachment", {"name": "b.csv"}, attachments=att)["error"]
    assert "utenti" in tool("preview_attachment", {}, attachments=[{"name": "u.csv", "content": "id_utente;nome;cognome;email;ruolo;responsabile;attivo\nU01;A;B;a@b.it;x;;s"}])["error"]


DEALS_CSV = (
    "id_opportunita;titolo;id_azienda;contatti;importo;valuta;pipeline;fase;data_chiusura;id_commerciale;cancellato;ultima_modifica\n"
    "90000001;Fornitura guanti Mazza;264566;5175588;€ 1.234,56;;VENDITE;06 - Vinta;15/11/2026;U29;NO;01/12/2026 10:00:00\n"
    "90000002;Offerta pallet Mazza;264566;;4,086.16-;Euro;VENDITE;Persa;;U01;NO;01/12/2026 10:00:00\n"
    "90000003;Rinnovo canone Mazza;264566;;12.000,00;USD;RINNOVI;R3;10/01/2026;Anna Sala;NO;01/12/2026 10:00:00\n"
    "90000004;Senza importo;264566;;;;VENDITE;02 - Qualifica;;U47;NO;01/12/2026 10:00:00\n"
)


def test_deals_csv_maps_stages_amounts_currency_and_active_commerciale(api, monkeypatch):
    seed_users()
    comp = company(api, "Nuova Serramenti Mazza S.r.l.", "264566", "nuovaserramentimazza.it")
    contact = api.post("/crm/v3/objects/contacts", headers=H, json={"properties": {"firstname": "Elisa", "lastname": "Bellini", "email": "e.bellini@libero.it", "id_legacy": "5175588"}}).json()
    res = tool("import_attachment", {}, attachments=[{"name": "opportunita.csv", "content": DEALS_CSV}])
    assert res["summary"] == {"rows": 4, "created": 4, "updated": 0, "skipped": 0, "failed": 0}, res
    deals = {d["label"]: d for d in res["created"]}
    won = get(api, "deals", deals["Fornitura guanti Mazza"]["id"])
    assert won["amount"] == "1234.56" and won["deal_currency_code"] == "EUR" and won["dealstage"] == "closedwon" and won["pipeline"] == "default"
    assert won["closedate"].startswith("2026-11-15") and won["id_legacy"] == "90000001" and "commerciale" not in won  # U29 left the company (R3)
    assert any("R3" in w for row in res["warnings"] for w in row["warnings"] if row["line"] == 2)
    assert any("Avvio fornitura" in a for a in deals["Fornitura guanti Mazza"]["automations"])  # R10 fired through the same store
    assoc = api.get(f"/crm/v4/objects/deals/{won['hs_object_id']}/associations/contacts", headers=H).json()["results"]
    assert [str(a["toObjectId"]) for a in assoc] == [contact["id"]]
    lost = get(api, "deals", deals["Offerta pallet Mazza"]["id"])
    assert lost["amount"] == "-4086.16" and lost["dealstage"] == "closedlost" and lost["commerciale"] == "anna.sala@brambillaforniture.it"
    assert any("Richiamare" in a for a in deals["Offerta pallet Mazza"]["automations"])  # R11
    ren = get(api, "deals", deals["Rinnovo canone Mazza"]["id"])
    assert ren["pipeline"] != "default" and ren["hs_is_closed_won"] == "true" and ren["amount"] == "12000" and ren["deal_currency_code"] == "USD" and ren["commerciale"] == "anna.sala@brambillaforniture.it"
    empty = get(api, "deals", deals["Senza importo"]["id"])
    assert "amount" not in empty and "deal_currency_code" not in empty and empty["dealstage"] == "qualifiedtobuy" and "commerciale" not in empty
    assert api.get(f"/crm/v4/objects/companies/{comp['id']}/associations/deals", headers=H).json()["results"].__len__() == 4


def test_products_csv_republishes_price_of_existing_sku(api):
    seed_users()
    old = api.post("/crm/v3/objects/products", headers=H, json={"properties": {"name": "Guanti in nitrile taglia L", "hs_sku": "BF-62989", "price": "100"}}).json()
    csv_text = "codice_articolo;descrizione;unita;prezzo_listino;cancellato;ultima_modifica\nBF-62989;Guanti in nitrile taglia L;conf;112,98;0;16/06/2012 20:53:00\n62990;Guanti in nitrile taglia XL;conf;115,00;0;16/06/2012 20:53:00\n"
    res = tool("import_attachment", {}, attachments=[{"name": "listino.csv", "content": csv_text}])
    assert res["summary"]["updated"] == 1 and res["summary"]["created"] == 1
    assert get(api, "products", old["id"])["price"] == "112.98"
    new = tool("search_products", {"sku": "62990"})
    assert new["total"] == 1 and new["results"][0]["hs_sku"] == "BF-62990" and new["results"][0]["price"] == "115"
    assert tool("search_products", {"sku": "bf-62989"})["results"][0]["id"] == old["id"]


def test_line_items_csv_links_deal_and_product_and_sets_deal_amount(api):
    seed_users()
    comp = company(api, "Nuova Serramenti Mazza S.r.l.", "264566")
    prod = api.post("/crm/v3/objects/products", headers=H, json={"properties": {"name": "Pallet in legno EPAL 1200x800", "hs_sku": "BF-12288", "price": "15.17"}}).json()
    deal = api.post("/crm/v3/objects/deals", headers=H, json={"properties": {"dealname": "Pallet Mazza", "amount": "999", "id_legacy": "44135407", "dealstage": "contractsent"}, "associations": [{"to": {"id": comp["id"]}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 341}]}]}).json()
    csv_text = (
        "id_riga;id_opportunita;codice_articolo;descrizione;quantita;prezzo_unitario;sconto\n"
        "2550270213;44135407;BF-12288;Pallet in legno EPAL 1200x800;1 pz;15,17;15,0\n"
        "2550270214;44135407;12288;;10;;\n"
        "2550270215;77777777;BF-12288;Riga orfana;1;15,17;\n"
    )
    res = tool("import_attachment", {}, attachments=[{"name": "righe.csv", "content": csv_text}])
    assert res["summary"]["created"] == 2 and res["summary"]["skipped"] == 1, res
    first = get(api, "line_items", res["created"][0]["id"])
    assert first["amount"] == "12.89" and first["hs_discount_percentage"] == "15" and first["hs_product_id"] == prod["id"] and first["quantity"] == "1"
    second = get(api, "line_items", res["created"][1]["id"])
    assert second["name"] == "Pallet in legno EPAL 1200x800" and second["price"] == "15.17" and second["amount"] == "151.70"
    assert get(api, "deals", deal["id"])["amount"] == "164.59"  # 12.89 + 151.70: a deal with lines is worth its lines (R3)
    assert any("164.59" in a for a in res["created"][1]["automations"])
    items = api.get(f"/crm/v4/objects/deals/{deal['id']}/associations/line_items", headers=H).json()["results"]
    assert len(items) == 2
    assert api.get(f"/crm/v4/objects/line_items/{first['hs_object_id']}/associations/products", headers=H).json()["results"][0]["toObjectId"] == int(prod["id"])


def test_tickets_csv_uses_assistenza_pipeline_and_da_header(api):
    seed_users()
    comp = company(api, "Corti Metalli", "100", "cortimetalli.com")
    contact = api.post("/crm/v3/objects/contacts", headers=H, json={"properties": {"firstname": "M", "lastname": "Leone", "email": "m.leone@cortimetalli.com"}}).json()
    csv_text = (
        "id_ticket;oggetto;descrizione;stato;priorita;id_contatto;id_azienda;aperto_il;chiuso_il;id_utente;cancellato;ultima_modifica\n"
        '595833;Problema con l\'ordine;"Da: m.leone@cortimetalli.com\nArrivato il materiale sbagliato";In lavorazione;Alta;;100;03/10/2020 11:46:50;;U01;NO;19/10/2020 18:44:50\n'
    )
    res = tool("import_attachment", {}, attachments=[{"name": "ticket.csv", "content": csv_text}])
    assert res["summary"]["created"] == 1, res
    t = get(api, "tickets", res["created"][0]["id"])
    assert t["hs_ticket_priority"] == "HIGH" and t["assegnatario"] == "anna.sala@brambillaforniture.it" and t["id_legacy"] == "595833"
    stage = tool("pipelines", {})["tickets"]
    assist = next(p for p in stage if p["label"] == "Assistenza")
    assert t["hs_pipeline"] == assist["id"] and t["hs_pipeline_stage"] == assist["stages"][1]["id"]
    assert str(api.get(f"/crm/v4/objects/tickets/{t['hs_object_id']}/associations/contacts", headers=H).json()["results"][0]["toObjectId"]) == contact["id"]
    assert str(api.get(f"/crm/v4/objects/tickets/{t['hs_object_id']}/associations/companies", headers=H).json()["results"][0]["toObjectId"]) == comp["id"]


def test_activities_csv_becomes_notes_calls_with_author_and_links(api):
    seed_users()
    contact = api.post("/crm/v3/objects/contacts", headers=H, json={"properties": {"firstname": "Valentina", "lastname": "Riva", "email": "v.riva@example.com", "id_legacy": "7001"}}).json()
    csv_text = (
        "id_attivita;tipo;data;testo;id_contatto;id_opportunita;id_utente;cancellato\n"
        "607999807;Appunto;13/01/2018 17:02;Promemoria su Valentina per campionatura.;7001;;U47;\n"
        "607999808;Telefonata;14/01/2018 09:00;Richiamata;7001;;;\n"
    )
    res = tool("import_attachment", {}, attachments=[{"name": "attivita.csv", "content": csv_text}])
    assert res["summary"]["created"] == 2, res
    note = get(api, "notes", res["created"][0]["id"])
    assert note["hs_note_body"].startswith("Promemoria") and note["hs_timestamp"].startswith("2018-01-13T17:02") and note["autore"] == "luca.santoro@brambillaforniture.it"
    call = get(api, "calls", res["created"][1]["id"])
    assert call["hs_call_body"] == "Richiamata" and call["autore"] == CTX["user"]
    acts = tool("list_activities", {"contact_id": contact["id"]})
    assert acts["total"] == 2 and {a["type"] for a in acts["results"]} == {"notes", "calls"}


def test_find_by_legacy_id_and_search_filters(api):
    seed_users()
    comp = company(api, "Nuova Impianti Benedetti S.p.A.", "264566", "nuovaimpiantibenedetti.eu")
    ticket = api.post("/crm/v3/objects/tickets", headers=H, json={"properties": {"subject": "Reso materiale", "id_legacy": "824011"}}).json()
    found = tool("find_by_legacy_id", {"id_legacy": "264566"})
    assert found["total"] == 1 and found["results"][0]["object_type"] == "companies" and found["results"][0]["id"] == comp["id"]
    found = tool("find_by_legacy_id", {"id_legacy": "824011"})
    assert found["results"][0]["object_type"] == "tickets" and found["results"][0]["id"] == ticket["id"]
    assert tool("find_by_legacy_id", {"id_legacy": "0000"})["total"] == 0
    assert tool("search_companies", {"id_legacy": "264566"})["results"][0]["id"] == comp["id"]
    assert tool("search_tickets", {"id_legacy": "824011"})["results"][0]["id"] == ticket["id"]


def test_company_search_matches_words_in_any_order_without_accents(api):
    seed_users()
    a = company(api, "Officine Meccaniche Brambilla S.r.l.", "1")
    b = company(api, "Società Agricola Nicolò", "2")
    c = company(api, "Nuova Serramenti Mazza S.r.l.", "3", city="Lecco")
    d = company(api, "Nuova Serramenti Mazza S.r.l.", "4", city="Como")
    assert [r["id"] for r in tool("search_companies", {"name": "brambilla officine"})["results"]] == [a["id"]]
    assert [r["id"] for r in tool("search_companies", {"name": "nicolo agricola"})["results"]] == [b["id"]]
    assert tool("search_companies", {"name": "Mazza Serramenti srl"})["total"] == 2  # ambiguity stays visible
    assert [r["id"] for r in tool("search_companies", {"name": "Mazza Serramenti", "city": "Como"})["results"]] == [d["id"]]
    assert tool("search_companies", {"name": "Nuova Serramenti Mazza"})["results"][0]["id"] == c["id"]  # substring path untouched
    assert tool("search_companies", {"name": "Zzz Non Esiste"})["total"] == 0


def test_contact_search_by_full_name_in_any_order(api):
    seed_users()
    comp = company(api, "Acme", "9")
    x = api.post("/crm/v3/objects/contacts", headers=H, json={"properties": {"firstname": "Maria Grazia", "lastname": "De Luca", "email": "mg@example.com"}, "associations": [{"to": {"id": comp["id"]}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 279}]}]}).json()
    api.post("/crm/v3/objects/contacts", headers=H, json={"properties": {"firstname": "Luca", "lastname": "De Santis", "email": "ls@example.com"}}).json()
    assert [r["id"] for r in tool("search_contacts", {"name": "De Luca Maria"})["results"]] == [x["id"]]
    assert [r["id"] for r in tool("search_contacts", {"name": "grazia de luca", "company_id": comp["id"]})["results"]] == [x["id"]]
    assert tool("search_contacts", {"name": "Maria Grazia De Luca"})["results"][0]["id"] == x["id"]


def test_writes_refuse_ex_employees_and_accept_colleague_names(api):
    seed_users()
    comp = company(api, "Acme", "9")
    deal = api.post("/crm/v3/objects/deals", headers=H, json={"properties": {"dealname": "Acme fornitura", "dealstage": "qualifiedtobuy", "commerciale": "anna.sala@brambillaforniture.it"}}).json()
    before = get(api, "deals", deal["id"])
    r = tool("update_record", {"object_type": "deals", "id": deal["id"], "properties": {"commerciale": "luca.santoro@brambillaforniture.it"}})
    assert r["status"] == 400 and "non lavora più" in r["error"] and get(api, "deals", deal["id"]) == before
    r = tool("update_record", {"object_type": "deals", "id": deal["id"], "properties": {"commerciale": "Pippo Franco"}})
    assert r["status"] == 400 and "non è un utente" in r["error"] and get(api, "deals", deal["id"]) == before
    # the same name, one active and one inactive user: the active one is meant (DECISIONS 3)
    r = tool("update_record", {"object_type": "deals", "id": deal["id"], "properties": {"commerciale": "Marco Costa"}})
    assert r["ok"] and get(api, "deals", deal["id"])["commerciale"] == "m.costa@brambillaforniture.it"
    t = tool("create_record", {"object_type": "tickets", "properties": {"subject": "Verifica", "assegnatario": "U81"}, "associations": [{"object_type": "companies", "id": comp["id"]}]})
    assert t["ok"] and get(api, "tickets", t["id"])["assegnatario"] == "m.costa@brambillaforniture.it"
    t = tool("create_record", {"object_type": "tickets", "properties": {"subject": "Verifica 2", "assegnatario": "Luca Santoro"}})
    assert t["status"] == 400 and api.post("/crm/v3/objects/tickets/search", headers=H, json={"query": "Verifica 2"}).json()["total"] == 0
    assert tool("search_deals", {"commerciale": "Marco Costa"})["results"][0]["id"] == deal["id"]
    assert tool("search_tickets", {"assegnatario": "m. costa"})["total"] == 1
    assert tool("my_customers", {"user_email": "Marco Costa"})["user"] == "m.costa@brambillaforniture.it"
    assert tool("deal_stats", {"commerciale": "Marco Costa"})["count"] == 1


def test_choice_level_model_error_is_a_model_failure(monkeypatch):
    """OpenRouter can answer 200 with the error inside choices[0]: that is not a reply."""
    import httpx
    import pytest
    from app import config

    class FakeResponse:
        status_code = 200
        text = ""

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    class FakeClient:
        payload = None

        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            return FakeResponse(FakeClient.payload)

    monkeypatch.setattr(httpx, "Client", FakeClient)
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "test-key")
    FakeClient.payload = {"choices": [{"error": {"message": "upstream overloaded"}, "message": {"content": ""}}]}
    with pytest.raises(RuntimeError, match="upstream overloaded"):
        agent.openrouter_chat([{"role": "user", "content": "ciao"}], [])
    FakeClient.payload = {"choices": [{"finish_reason": "content_filter", "message": {"content": "x"}}]}
    with pytest.raises(RuntimeError, match="content_filter"):
        agent.openrouter_chat([{"role": "user", "content": "ciao"}], [])
    FakeClient.payload = {"choices": [{"finish_reason": "stop", "message": {"content": "Ciao!"}}]}
    assert agent.openrouter_chat([{"role": "user", "content": "ciao"}], [])["content"] == "Ciao!"


def test_failure_after_a_write_reports_the_write(api, monkeypatch):
    seed_users()
    deal = api.post("/crm/v3/objects/deals", headers=H, json={"properties": {"dealname": "Acme fornitura", "dealstage": "qualifiedtobuy"}}).json()
    calls = {"n": 0}

    def model(messages, tools, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"content": None, "tool_calls": [{"id": "c0", "type": "function", "function": {"name": "update_record", "arguments": json.dumps({"object_type": "deals", "id": deal["id"], "properties": {"amount": "500"}})}}]}
        raise RuntimeError("model down")

    monkeypatch.setattr(agent, "MODEL_CLIENT", model)
    monkeypatch.setattr(agent, "TURN_BUDGET_S", 3.0)
    r = api.post("/__agente", headers=H, json={"context": CTX, "messages": [{"role": "user", "content": "Metti 500 sulla trattativa Acme"}]})
    reply = r.json()["reply"]
    assert f"update deals {deal['id']}" in reply and "Non ho modificato" not in reply
    assert get(api, "deals", deal["id"])["amount"] == "500"


def test_preview_says_ex_employee_rows_are_still_imported(api):
    seed_users()
    company(api, "Nuova Serramenti Mazza S.r.l.", "264566")
    pre = tool("preview_attachment", {}, attachments=[{"name": "o.csv", "content": DEALS_CSV}])
    assert "Non è un motivo per rifiutare" in pre["guidance"]
    res = tool("import_attachment", {}, attachments=[{"name": "o.csv", "content": DEALS_CSV}])
    assert res["summary"]["created"] == 4  # the U29 and U47 rows are imported with an empty commerciale


def test_archiving_a_company_with_open_deals_needs_confirmation(api):
    seed_users()
    comp = company(api, "Acme Archivio", "7")
    api.post("/crm/v3/objects/deals", headers=H, json={"properties": {"dealname": "Aperta", "dealstage": "qualifiedtobuy"}, "associations": [{"to": {"id": comp["id"]}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 341}]}]})
    r = tool("archive_record", {"object_type": "companies", "id": comp["id"]})
    assert r["status"] == 409 and r["open_deals"] == 1 and api.get(f"/crm/v3/objects/companies/{comp['id']}", headers=H).status_code == 200
    assert tool("archive_record", {"object_type": "companies", "id": comp["id"], "confirmed": True})["ok"]
    empty = company(api, "Acme Senza Deal", "8")
    assert tool("archive_record", {"object_type": "companies", "id": empty["id"]})["ok"]


def test_system_prompt_carries_the_questions_and_reply_rules():
    text = agent.system_prompt(NOW, None, CTX["user"])
    assert "UN solo record corrispondente agisci subito" in text and "UNA domanda precisa che li nomina" in text
    assert "Non chiedere mai ciò che è già scritto" in text
    assert "riscrivi lo stato finale" in text and "due decimali" in text
    assert "Non rinnovato" in text and "Rinnovato" in text

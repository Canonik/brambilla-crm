"""Assistant tool layer driven by a scripted fake model (no network, no key)."""
import json

from app.assistant import agent

from .conftest import H

CTX = {"now": "2026-12-02T10:00:00+01:00", "user": "anna.sala@brambillaforniture.it"}


class Script:
    """Each step: either a list of tool calls [(name, args)] or a final text."""

    def __init__(self, steps):
        self.steps = list(steps)
        self.seen = []

    def __call__(self, messages, tools, **kw):
        self.seen.append(messages[-1])
        step = self.steps.pop(0)
        if isinstance(step, str):
            return {"content": step}
        return {"content": None, "tool_calls": [{"id": f"c{i}", "type": "function", "function": {"name": n, "arguments": json.dumps(a)}} for i, (n, a) in enumerate(step)]}


def _setup(api):
    comp = api.post("/crm/v3/objects/companies", headers=H, json={"properties": {"name": "Nuova Serramenti Mazza S.r.l.", "domain": "nuovaserramentimazza.it", "partita_iva": "01234567890", "city": "Lecco"}}).json()
    deal = api.post("/crm/v3/objects/deals", headers=H, json={"properties": {"dealname": "Fornitura serramenti Mazza", "amount": "12500", "deal_currency_code": "EUR", "dealstage": "contractsent", "commerciale": "anna.sala@brambillaforniture.it"}, "associations": [{"to": {"id": comp["id"]}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 341}]}]}).json()
    return comp, deal


def test_mark_deal_won_runs_r10_and_reports(api, monkeypatch):
    comp, deal = _setup(api)
    script = Script([
        [("search_companies", {"name": "Nuova Serramenti Mazza"})],
        [("search_deals", {"company_id": comp["id"], "open_only": True})],
        [("update_record", {"object_type": "deals", "id": deal["id"], "properties": {"dealstage": "Vinta"}})],
        "Fatto: la trattativa 'Fornitura serramenti Mazza' è segnata come Vinta.",
    ])
    monkeypatch.setattr(agent, "MODEL_CLIENT", script)
    r = api.post("/__agente", headers=H, json={"context": CTX, "messages": [{"role": "user", "content": "Segna come vinta la trattativa di Nuova Serramenti Mazza"}]})
    assert r.status_code == 200 and "Vinta" in r.json()["reply"]
    # the tool results the model saw
    results = [json.loads(m["content"]) for m in script.seen if m.get("role") == "tool"]
    assert results[0]["results"][0]["id"] == comp["id"]
    assert results[1]["results"][0]["id"] == deal["id"] and results[1]["results"][0]["stage"] == "Contract Sent"
    assert results[2]["ok"] and results[2]["properties"]["dealstage"] == "closedwon"
    assert results[2]["properties"]["closedate"].startswith("2026-12-02")  # context.now, not server clock
    assert any("Avvio fornitura" in a for a in results[2]["automations"])
    d = api.get(f"/crm/v3/objects/deals/{deal['id']}", headers=H).json()["properties"]
    assert d["dealstage"] == "closedwon"
    t = api.post("/crm/v3/objects/tickets/search", headers=H, json={"query": "Avvio fornitura"}).json()
    assert t["total"] == 1 and t["results"][0]["properties"]["assegnatario"] == "anna.sala@brambillaforniture.it"


def test_revenue_question_uses_deterministic_tool(api, monkeypatch):
    comp, deal = _setup(api)
    api.patch(f"/crm/v3/objects/deals/{deal['id']}", headers=H, json={"properties": {"dealstage": "closedwon", "closedate": "2025-03-10"}})
    api.post("/crm/v3/objects/deals", headers=H, json={"properties": {"dealname": "Storno", "amount": "-500", "dealstage": "closedwon", "closedate": "2025-06-01"}, "associations": [{"to": {"id": comp["id"]}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 341}]}]})
    api.post("/crm/v3/objects/deals", headers=H, json={"properties": {"dealname": "USD deal", "amount": "1000", "deal_currency_code": "USD", "dealstage": "closedwon", "closedate": "2025-07-01"}, "associations": [{"to": {"id": comp["id"]}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 341}]}]})
    script = Script([[("search_companies", {"name": "Nuova Serramenti Mazza"})], [("revenue", {"company_id": comp["id"], "year": 2025})], "Nel 2025 con Nuova Serramenti Mazza abbiamo fatturato 12.920,00 €."])
    monkeypatch.setattr(agent, "MODEL_CLIENT", script)
    r = api.post("/__agente", headers=H, json={"context": CTX, "messages": [{"role": "user", "content": "Quanto abbiamo fatturato con Nuova Serramenti Mazza nel 2025?"}]})
    assert r.status_code == 200
    results = [json.loads(m["content"]) for m in script.seen if m.get("role") == "tool"]
    assert results[1]["total_eur"] == "12920.00" and results[1]["total_eur_it"] == "12.920,00"


def test_duplicate_vat_is_refused_by_tool(api, monkeypatch):
    comp, _ = _setup(api)
    script = Script([[("create_record", {"object_type": "companies", "properties": {"name": "Mazza Bis", "partita_iva": "IT 01234567890"}})], "Non posso crearla: la partita IVA 01234567890 è già di Nuova Serramenti Mazza S.r.l."])
    monkeypatch.setattr(agent, "MODEL_CLIENT", script)
    r = api.post("/__agente", headers=H, json={"context": CTX, "messages": [{"role": "user", "content": "Crea l'azienda Mazza Bis con partita iva 01234567890"}]})
    assert r.status_code == 200
    results = [json.loads(m["content"]) for m in script.seen if m.get("role") == "tool"]
    assert results[0]["status"] == 409 and "already exists" in results[0]["error"]
    assert api.post("/crm/v3/objects/companies/search", headers=H, json={"query": "Mazza Bis"}).json()["total"] == 0


def test_create_contact_r12_and_bulk_csv(api, monkeypatch):
    comp, _ = _setup(api)
    script = Script([
        [("create_record", {"object_type": "contacts", "properties": {"firstname": "Luca", "lastname": "Bianchi", "email": "l.bianchi@nuovaserramentimazza.it"}})],
        [("create_records_bulk", {"object_type": "contacts", "records": [{"properties": {"firstname": "A", "lastname": "B", "email": "a.b@example.com"}}, {"properties": {"firstname": "C", "lastname": "D", "email": "not-valid"}}]})],
        "Creati 2 contatti su 3; uno scartato per email non valida.",
    ])
    monkeypatch.setattr(agent, "MODEL_CLIENT", script)
    r = api.post("/__agente", headers=H, json={"context": CTX, "messages": [{"role": "user", "content": "Aggiungi Luca Bianchi e importa l'allegato", "attachments": [{"name": "c.csv", "content_type": "text/csv", "content": "nome;cognome;email\nA;B;a.b@example.com\nC;D;not-valid"}]}]})
    assert r.status_code == 200
    results = [json.loads(m["content"]) for m in script.seen if m.get("role") == "tool"]
    assert results[0]["ok"] and any("associato all'azienda" in a for a in results[0]["automations"])
    assert results[1]["created"] == 1 and results[1]["failed"] == 1
    # attachment reached the model
    assert "a.b@example.com" in script.seen[0]["content"]


def test_model_failure_never_claims_success(api, monkeypatch):
    def boom(messages, tools, **kw):
        raise RuntimeError("down")
    monkeypatch.setattr(agent, "MODEL_CLIENT", boom)
    monkeypatch.setattr(agent, "TURN_BUDGET_S", 2.0)
    r = api.post("/__agente", headers=H, json={"context": CTX, "messages": [{"role": "user", "content": "ciao"}]})
    assert r.status_code == 200 and "Non ho modificato" in r.json()["reply"]

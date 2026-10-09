"""Capped live smoke of the assistant against a deploy. NOT collected by pytest (no test_ prefix).

Four conversations, each on its own freshly created records, about a dozen model calls in all.
Run only with Coordinator approval (shared model budget):

    BASE_URL=https://<deploy> CRM_TOKEN=<token> python server/tests/live_smoke_assistant.py

Prints every reply, checks the CRM state through the API, archives what it created, exits 1 on
any failed check. Needs a migrated CRM only for scenario 3 (revenue of a migrated company)."""
import json
import os
import re
import sys
import uuid

import httpx

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
TOKEN = os.environ.get("CRM_TOKEN", "dev-token")
USER = os.environ.get("SMOKE_USER", "elena.silvestri@brambillaforniture.it")
NOW = "2026-12-02T10:00:00+01:00"
H = {"Authorization": f"Bearer {TOKEN}"}
client = httpx.Client(base_url=BASE, headers=H, timeout=70)
created: list[tuple[str, str]] = []
failures: list[str] = []


def api(method, path, **kw):
    r = client.request(method, path, **kw)
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {path} -> {r.status_code} {r.text[:200]}")
    return r.json() if r.content else None


def make(ot, props, associations=None):
    body = {"properties": props}
    if associations:
        body["associations"] = associations
    rec = api("POST", f"/crm/v3/objects/{ot}", json=body)
    created.append((ot, rec["id"]))
    return rec


def ask(text, attachments=None, prior=None):
    msgs = list(prior or [])
    m = {"role": "user", "content": text}
    if attachments:
        m["attachments"] = attachments
    msgs.append(m)
    reply = api("POST", "/__agente", json={"context": {"now": NOW, "user": USER}, "messages": msgs})["reply"]
    print(f"\n> {text}\n< {reply}")
    msgs.append({"role": "assistant", "content": reply})
    return reply, msgs


def check(cond, what):
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        failures.append(what)


def search(ot, filters=None, query=None, limit=10):
    body = {"limit": limit}
    if filters:
        body["filterGroups"] = [{"filters": filters}]
    if query:
        body["query"] = query
    return api("POST", f"/crm/v3/objects/{ot}/search", json=body)


tag = uuid.uuid4().hex[:5]

# 1. CSV import of contacts in Sinergia format, company referenced by legacy id
print("\n=== 1. CSV attachment (contacts) ===")
comp = make("companies", {"name": f"Smoke Serramenti {tag} S.r.l.", "domain": f"smoke-{tag}.example", "id_legacy": f"9{tag}", "city": "Lecco"})
csv_text = (
    "id_contatto;nome;cognome;email;telefono;id_azienda;tipo;cancellato;ultima_modifica\n"
    f"1{tag};Giulia;Ferri;giulia.ferri@smoke-{tag}.example;+39 02 1234567;9{tag};CLIENTE;NO;01/03/2024 10:00:00\n"
    f"2{tag};Paolo;Riva;paolo.riva@smoke-{tag}.example;;9{tag};Prospect;NO;01/03/2024 10:00:00\n"
    f"3{tag};Mario;Cancellato;mario.c@smoke-{tag}.example;;9{tag};CLIENTE;SI;01/03/2024 10:00:00\n"
)
reply, _ = ask("Importa nel CRM i contatti dell'allegato.", attachments=[{"name": "contatti.csv", "content_type": "text/csv", "content": csv_text}])
g = search("contacts", [{"propertyName": "email", "operator": "EQ", "value": f"giulia.ferri@smoke-{tag}.example"}])
p = search("contacts", [{"propertyName": "email", "operator": "EQ", "value": f"paolo.riva@smoke-{tag}.example"}])
m = search("contacts", [{"propertyName": "email", "operator": "EQ", "value": f"mario.c@smoke-{tag}.example"}])
for res in (g, p):
    for r in res["results"]:
        created.append(("contacts", r["id"]))
check(g["total"] == 1 and g["results"][0]["properties"].get("lifecyclestage") == "customer" and g["results"][0]["properties"].get("phone") == "+39 02 1234567", "Giulia created as customer with phone")
check(g["total"] == 1 and g["results"][0]["properties"].get("associatedcompanyid") == comp["id"], "Giulia associated to the company by id_azienda")
check(p["total"] == 1 and p["results"][0]["properties"].get("lifecyclestage") == "opportunity", "Paolo created as prospect")
check(m["total"] == 0, "deleted row not imported")
check(bool(re.search(r"\b2\b", reply)) and "giulia" in reply.lower(), "reply names the two contacts created")

# 2. ambiguous company name: must ask, must not write
print("\n=== 2. ambiguous company ===")
a = make("companies", {"name": f"Officine Smoke {tag}", "city": "Como"})
b = make("companies", {"name": f"Officine Smoke {tag}", "city": "Varese"})
da = make("deals", {"dealname": f"Fornitura Officine Smoke {tag} Como", "amount": "1000", "dealstage": "contractsent", "commerciale": USER}, [{"to": {"id": a["id"]}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 341}]}])
db = make("deals", {"dealname": f"Fornitura Officine Smoke {tag} Varese", "amount": "2000", "dealstage": "contractsent", "commerciale": USER}, [{"to": {"id": b["id"]}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 341}]}])
reply, msgs = ask(f"Segna come vinta la trattativa di Officine Smoke {tag}, è arrivato l'ordine firmato.")
sa = api("GET", f"/crm/v3/objects/deals/{da['id']}")["properties"]["dealstage"]
sb = api("GET", f"/crm/v3/objects/deals/{db['id']}")["properties"]["dealstage"]
check(sa == "contractsent" and sb == "contractsent", "no deal changed on the ambiguous turn")
check("como" in reply.lower() and "varese" in reply.lower(), "reply lists both candidates by city")
reply, msgs = ask("Quella di Varese.", prior=msgs)
sa = api("GET", f"/crm/v3/objects/deals/{da['id']}")["properties"]["dealstage"]
sb = api("GET", f"/crm/v3/objects/deals/{db['id']}")["properties"]["dealstage"]
check(sb == "closedwon" and sa == "contractsent", "only the Varese deal is won after clarification")
tk = api("GET", f"/crm/v4/objects/deals/{db['id']}/associations/tickets")["results"]
check(len(tk) == 1, "R10 ticket opened once")
for t in tk:
    created.append(("tickets", str(t["toObjectId"])))

# 3. example 2: revenue of a migrated company (skipped when not migrated)
print("\n=== 3. revenue question (migrated data) ===")
hits = search("companies", [{"propertyName": "name", "operator": "CONTAINS_TOKEN", "value": "Spinelli"}], limit=50)
target = [h for h in hits["results"] if "nuova tessile spinelli" in h["properties"]["name"].lower()]
if target:
    expected = {round(float(h["properties"].get("fatturato_2025") or 0), 2) for h in target}
    reply, _ = ask("Quanto abbiamo fatturato con Nuova Tessile Spinelli nel 2025?")
    nums = set()
    for mm in re.finditer(r"\d[\d.,]*", reply):
        s = mm.group(0)
        it = s.replace(".", "").replace(",", ".") if re.search(r",\d{1,2}$", s) else s.replace(",", "")
        try:
            nums.add(round(float(it), 2))
        except ValueError:
            pass
    check(bool(expected & nums), f"reply contains fatturato_2025 {expected}")
else:
    print("  skip: Nuova Tessile Spinelli not in this CRM (not migrated?)")

# 4. a request against the rules: duplicate partita IVA must be refused, nothing created
print("\n=== 4. refusal (duplicate partita IVA) ===")
piva = "0" + str(int(uuid.uuid4().int % 10**10)).zfill(10)
make("companies", {"name": f"Piva Holder {tag}", "partita_iva": piva})
before = search("companies", query=f"Piva Clone {tag}")["total"]
reply, _ = ask(f"Crea l'azienda Piva Clone {tag} con partita IVA {piva}.")
after = search("companies", query=f"Piva Clone {tag}")["total"]
check(after == before == 0, "no company created with a duplicate partita IVA")
check("partita iva" in reply.lower() or "p.iva" in reply.lower() or piva in reply, "reply explains the partita IVA conflict")

# cleanup: archive what we created (R10 tickets included)
for ot, id_ in reversed(created):
    try:
        client.delete(f"/crm/v3/objects/{ot}/{id_}")
    except Exception:
        pass
print(f"\n{len(failures)} failed checks" + (": " + "; ".join(failures) if failures else ""))
sys.exit(1 if failures else 0)

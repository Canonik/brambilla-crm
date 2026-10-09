"""Third capped live smoke: 8 scenarios in Brambilla's voice, each on records it creates (and archives) itself, plus
read-only scenarios on migrated data. NOT collected by pytest. Coordinator approval needed (model budget).

    BASE_URL=https://<deploy> CRM_TOKEN=<token> python server/tests/live_smoke_assistant_3.py

Runs scenarios 4 at a time (the evaluation sends 4 conversations at once) and reports pass/fail per
scenario and the slowest turn. Exit 1 on any failed check."""
import datetime as dt
import os
import re
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import httpx

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
H = {"Authorization": f"Bearer {os.environ.get('CRM_TOKEN', 'dev-token')}"}
NOW = "2026-12-02T10:00:00+01:00"
DEAL_CO = {"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 341}
TICKET_CO = {"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 339}
CONTACT_CO = {"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 279}
client = httpx.Client(base_url=BASE, headers=H, timeout=75, limits=httpx.Limits(max_connections=8))
lock = threading.Lock()
RESULTS: dict[str, list[tuple[bool, str]]] = {}
TURNS: list[float] = []
tag = uuid.uuid4().hex[:5]


def api(method, path, **kw):
    r = client.request(method, path, **kw)
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {path} -> {r.status_code} {r.text[:200]}")
    return r.json() if r.content else None


class Ctx:
    def __init__(self, name):
        self.name, self.created, self.log = name, [], []
        RESULTS[name] = []

    def make(self, ot, props, assoc=None):
        rec = api("POST", f"/crm/v3/objects/{ot}", json={"properties": props, **({"associations": assoc} if assoc else {})})
        self.created.append((ot, rec["id"]))
        return rec

    def track(self, ot, id_):
        self.created.append((ot, str(id_)))

    def ask(self, user, text, attachments=None, prior=None):
        msgs = list(prior or []) + [{"role": "user", "content": text, **({"attachments": attachments} if attachments else {})}]
        t = time.time()
        reply = api("POST", "/__agente", json={"context": {"now": NOW, "user": user}, "messages": msgs})["reply"]
        dt_s = time.time() - t
        with lock:
            TURNS.append(dt_s)
        self.log.append(f"> [{user}] {text}\n< ({dt_s:.1f}s) {reply}")
        return reply, msgs + [{"role": "assistant", "content": reply}]

    def check(self, cond, what):
        RESULTS[self.name].append((bool(cond), what))

    def cleanup(self):
        for ot, id_ in reversed(self.created):
            try:
                client.delete(f"/crm/v3/objects/{ot}/{id_}")
            except Exception:
                pass


def props(ot, id_):
    return api("GET", f"/crm/v3/objects/{ot}/{id_}")["properties"]


def search(ot, filters=None, query=None, limit=10, assoc=None):
    body = {"limit": limit, **({"filterGroups": [{"filters": filters}]} if filters else {}), **({"query": query} if query else {}), **({"associations": assoc} if assoc else {})}
    return api("POST", f"/crm/v3/objects/{ot}/search", json=body)


def linked(ot, id_, to):
    return [str(a["toObjectId"]) for a in api("GET", f"/crm/v4/objects/{ot}/{id_}/associations/{to}")["results"]]


def numbers(text):
    out = set()
    for m in re.finditer(r"\d[\d.,]*", text):
        s = m.group(0)
        it = s.replace(".", "").replace(",", ".") if re.search(r",\d{1,2}$", s) else s.replace(",", "")
        try:
            out.add(round(float(it), 2))
        except ValueError:
            pass
    return out


owners = api("GET", "/crm/v3/owners")["results"]
inactive = api("GET", "/crm/v3/owners?archived=true")["results"]
active = [o for o in owners if o["active"]]
USER, COLL = active[0]["email"], active[1]



pipes = {p["label"]: p for p in api("GET", "/crm/v3/pipelines/deals")["results"]}
REN = pipes["Rinnovi"]
REN_STAGE = {s["label"]: s["id"] for s in REN["stages"]}
CONTACT_NOTE = {"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 202}
DEAL_NOTE = {"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 214}
digits = int(tag, 16) % 9000 + 1000
SKU_A, SKU_B = f"BF-9{digits % 100:02d}{digits // 100:02d}", f"BF-8{digits % 100:02d}{digits // 100:02d}"


def renewal(c, name):
    co = c.make("companies", {"name": name})
    d = c.make("deals", {"dealname": f"Rinnovo {name}", "amount": "3000", "pipeline": REN["id"], "dealstage": REN_STAGE["In trattativa"], "commerciale": USER}, [{"to": {"id": co["id"]}, "types": [DEAL_CO]}])
    return co, d


def s_renewal_won(c):
    co, d = renewal(c, f"Smoke Rinnovo {tag} S.r.l.")
    c.ask(USER, f"Il rinnovo di Smoke Rinnovo {tag} è andato a buon fine, segnalo come rinnovato.")
    p = props("deals", d["id"])
    c.check(p.get("dealstage") == REN_STAGE["Rinnovato"], "deal is Rinnovato")
    c.check(p.get("closedate", "").startswith("2026-12-02"), "closedate = context.now")
    c.check(not linked("deals", d["id"], "tickets") and not linked("deals", d["id"], "tasks"), "no R10 ticket and no R11 task (not the sales pipeline)")


def s_renewal_lost(c):
    co, d = renewal(c, f"Smoke Nonrinnovo {tag} S.r.l.")
    reply, _ = c.ask(USER, f"Il rinnovo di Smoke Nonrinnovo {tag} non va avanti, sposta in Persa.")
    p = props("deals", d["id"])
    c.check(p.get("dealstage") in (REN_STAGE["Non rinnovato"], REN_STAGE["In trattativa"]), "Non rinnovato, or unchanged with a question")
    if p.get("dealstage") == REN_STAGE["In trattativa"]:
        c.check("?" in reply, "unchanged only because it asked")
    c.check(not linked("deals", d["id"], "tasks") and not linked("deals", d["id"], "tickets"), "no R10 ticket and no R11 task")


def s_quote(c):
    pa = c.make("products", {"name": f"Guanti Smoke {tag}", "hs_sku": SKU_A, "price": "100"})
    pb = c.make("products", {"name": f"Casco Smoke {tag}", "hs_sku": SKU_B, "price": "50"})
    co = c.make("companies", {"name": f"Smoke Preventivo {tag} S.r.l."})
    dn = f"Offerta Smoke Preventivo {tag}"
    d = c.make("deals", {"dealname": dn, "dealstage": "qualifiedtobuy", "commerciale": USER}, [{"to": {"id": co["id"]}, "types": [DEAL_CO]}])
    reply, _ = c.ask(USER, f"Prepara l'offerta '{dn}': 10 pezzi di {SKU_A} con sconto del 10% e 4 pezzi di {SKU_B}.")
    items = linked("deals", d["id"], "line_items")
    for i in items:
        c.track("line_items", i)
    c.check(len(items) == 2, "two line items on the deal")
    amounts = sorted(float(props("line_items", i).get("amount") or 0) for i in items)
    c.check(amounts == [200.0, 900.0], f"line amounts 200 and 900 (got {amounts})")
    c.check(float(props("deals", d["id"]).get("amount") or 0) == 1100.0, "deal amount = total of the lines (1100)")
    c.check(1100.0 in numbers(reply), "reply states 1.100,00")


def s_history(c):
    co = c.make("companies", {"name": f"Smoke Storia {tag} S.r.l."})
    ct = c.make("contacts", {"firstname": "Ida", "lastname": f"Storia{tag}", "email": f"ida.{tag}@smoke-storia.example"}, [{"to": {"id": co["id"]}, "types": [CONTACT_CO]}])
    d = c.make("deals", {"dealname": f"Fornitura Smoke Storia {tag}", "amount": "2000", "dealstage": "presentationscheduled", "commerciale": USER}, [{"to": {"id": co["id"]}, "types": [DEAL_CO]}])
    for body, when, to in (("sopralluogo in cantiere", "2026-10-20T09:00:00Z", CONTACT_NOTE), ("campionatura consegnata", "2026-08-12T09:00:00Z", DEAL_NOTE), ("reclamo su una bolla", "2026-07-03T09:00:00Z", CONTACT_NOTE), ("vecchiaoffertaduemilaventicinque", "2025-02-01T09:00:00Z", CONTACT_NOTE)):
        c.make("notes", {"hs_note_body": body, "hs_timestamp": when, "autore": USER}, [{"to": {"id": (ct if to is CONTACT_NOTE else d)["id"]}, "types": [to]}])
    reply, _ = c.ask(USER, f"Cosa è successo con Smoke Storia {tag} negli ultimi sei mesi?")
    low = reply.lower()
    c.check(all(k in low for k in ("sopralluogo", "campionatura", "reclamo")), "the three recent activities are listed")
    c.check("vecchiaoffertaduemilaventicinque" not in low, "the 2025 activity is left out")
    c.check("ottobre" in low and "agosto" in low and "luglio" in low, "dates given in readable form")


def s_update_contact(c):
    co = c.make("companies", {"name": f"Smoke Contatto {tag} S.r.l."})
    em = f"franco.{tag}@smoke-contatto.example"
    ct = c.make("contacts", {"firstname": "Franco", "lastname": f"Neri{tag}", "email": em, "phone": "0341 111111", "lifecyclestage": "lead"}, [{"to": {"id": co["id"]}, "types": [CONTACT_CO]}])
    c.ask(USER, f"Aggiorna il contatto {em}: nuovo telefono 02 9876543 e adesso è un cliente.")
    p = props("contacts", ct["id"])
    c.check(p.get("phone") == "02 9876543" and p.get("lifecyclestage") == "customer", "phone and lifecyclestage updated")
    c.check(p.get("firstname") == "Franco" and p.get("email") == em, "other fields untouched")


def s_missing_record(c):
    reply, _ = c.ask(USER, f"Segna come vinta la trattativa 'Fornitura Inesistente {tag}', è arrivato l'ordine.")
    low = reply.lower()
    c.check(search("deals", query=f"Inesistente {tag}")["total"] == 0, "no deal created")
    c.check(any(k in low for k in ("non ho trovato", "non trovo", "nessuna", "non esiste", "non risulta", "non ho riscontro")), "reply says the record was not found")
    c.check(not re.search(r"(?<!non )\b(segnata|ho segnato|aggiornata) come vinta", low), "reply does not claim a win")


def s_ticket_csv(c):
    co = c.make("companies", {"name": f"Smoke Assistenza {tag} S.r.l.", "id_legacy": f"6{tag}"})
    u = active[1]
    csv_text = ("id_ticket;oggetto;descrizione;stato;priorita;id_contatto;id_azienda;aperto_il;chiuso_il;id_utente;cancellato;ultima_modifica\n"
                f"5{tag}1;Merce danneggiata {tag};Il bancale è arrivato rotto;Aperto;Alta;;6{tag};01/12/2026 09:00:00;;{u['id']};NO;01/12/2026 09:00:00\n")
    reply, _ = c.ask(USER, "Carica i ticket dell'allegato.", attachments=[{"name": "ticket.csv", "content_type": "text/csv", "content": csv_text}])
    t = search("tickets", [{"propertyName": "subject", "operator": "EQ", "value": f"Merce danneggiata {tag}"}])
    c.check(t["total"] == 1, "ticket created once")
    if t["total"] == 1:
        c.track("tickets", t["results"][0]["id"])
        tp = t["results"][0]["properties"]
        c.check(tp.get("hs_ticket_priority") == "HIGH" and tp.get("assegnatario") == u["email"], "priority HIGH and assegnatario from id_utente")
        c.check(co["id"] in linked("tickets", t["results"][0]["id"], "companies"), "associated to the company by id_azienda")
        c.check(tp.get("id_legacy") == f"5{tag}1", "id_legacy kept")


def s_homonyms(c):
    a = c.make("companies", {"name": f"Smoke Omonimo {tag} S.r.l.", "city": "Bergamo"})
    b = c.make("companies", {"name": f"Smoke Omonimo {tag} S.r.l.", "city": "Cremona"})
    for co, city in ((a, "Bergamo"), (b, "Cremona")):
        c.make("deals", {"dealname": f"Fornitura {city} {tag}", "amount": "1200", "dealstage": "contractsent", "commerciale": USER}, [{"to": {"id": co["id"]}, "types": [DEAL_CO]}])
    reply, msgs = c.ask(USER, f"Alza a 5000 euro l'importo della trattativa di Smoke Omonimo {tag}.")
    c.check(all(props("deals", i).get("amount") == "1200" for i in [x for ot, x in c.created if ot == "deals"]), "no deal changed before the user picks one")
    c.check("bergamo" in reply.lower() and "cremona" in reply.lower(), "one question naming both candidates by city")
    reply2, _ = c.ask(USER, "Quella di Cremona.", prior=msgs)
    deals = {props("deals", x)["dealname"]: x for ot, x in c.created if ot == "deals"}
    c.check(props("deals", deals[f"Fornitura Cremona {tag}"]).get("amount") == "5000" and props("deals", deals[f"Fornitura Bergamo {tag}"]).get("amount") == "1200", "only the Cremona deal updated")
    c.check("5.000,00" in reply2 and "cremona" in reply2.lower(), "final reply restates amount and city")


SCENARIOS = [s_renewal_won, s_renewal_lost, s_quote, s_history, s_update_contact, s_missing_record, s_ticket_csv, s_homonyms]


def run(fn):
    c = Ctx(fn.__name__)
    try:
        fn(c)
    except Exception as e:  # noqa: BLE001
        c.check(False, f"scenario crashed: {type(e).__name__}: {str(e)[:160]}")
    finally:
        c.cleanup()
    return c


ONLY = set(sys.argv[1:])
with ThreadPoolExecutor(max_workers=4) as ex:
    ctxs = list(ex.map(run, [f for f in SCENARIOS if not ONLY or f.__name__ in ONLY]))
failed = 0
for c in ctxs:
    print(f"\n=== {c.name} ===")
    for line in c.log:
        print(line)
    for ok, what in RESULTS[c.name]:
        print(("  ok   " if ok else "  FAIL ") + what)
        failed += not ok
print(f"\nturns: {len(TURNS)}, slowest {max(TURNS or [0]):.1f}s (budget 60s); {failed} failed checks")
sys.exit(1 if failed else 0)

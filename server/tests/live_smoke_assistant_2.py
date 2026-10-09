"""Second capped live smoke: 10 scenarios, each on records it creates (and archives) itself, plus
read-only scenarios on migrated data. NOT collected by pytest. Coordinator approval needed (model budget).

    BASE_URL=https://<deploy> CRM_TOKEN=<token> python server/tests/live_smoke_assistant_2.py

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
        s = m.group(0).rstrip(".,")
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


def s_dormant(c):
    lst = api("GET", "/crm/v3/lists/object-type-id/0-2/name/Clienti%20dormienti")["list"]
    page = api("GET", f"/crm/v3/lists/{lst['listId']}/memberships", params={"limit": 60})
    by_user: dict[str, list[str]] = {}
    for r in page["results"]:
        cid = str(r["recordId"])
        for did in linked("companies", cid, "deals")[:3]:
            u = props("deals", did).get("commerciale")
            if u:
                by_user.setdefault(u, []).append(props("companies", cid)["name"])
    if not by_user:
        c.log.append("skip: no dormant customer with a deal owner in the first 60 members")
        return
    user, names = max(by_user.items(), key=lambda kv: len(kv[1]))
    reply, _ = c.ask(user, "Quali sono i miei clienti dormienti?")
    c.check(any(n.lower() in reply.lower() for n in names), f"reply names at least one of {len(names)} known dormant customers")


def s_lineitems(c):
    for d in search("deals", [{"propertyName": "amount", "operator": "GT", "value": "1000"}, {"propertyName": "hs_is_closed", "operator": "EQ", "value": "true"}], limit=60)["results"]:
        items = linked("deals", d["id"], "line_items")
        name = d["properties"]["dealname"]
        if 2 <= len(items) <= 5 and search("deals", query=name)["total"] == 1:
            lines = [props("line_items", i)["name"] for i in items]
            reply, _ = c.ask(USER, f"Cosa c'è nell'offerta '{name}' e quanto vale in tutto?")
            c.check(round(float(d["properties"]["amount"]), 2) in numbers(reply), f"reply has the deal total {d['properties']['amount']}")
            c.check(sum(1 for n in lines if n[:18].lower() in reply.lower()) >= max(1, len(lines) // 2), f"reply lists the line items {lines[:2]}")
            return
    c.log.append("skip: no suitable migrated deal")


def s_company_tickets(c):
    co = c.make("companies", {"name": f"Smoke Ticketone {tag} S.r.l."})
    subs = [f"Consegna in ritardo {tag}", f"Reso pallet {tag}"]
    for s in subs:
        t = c.make("tickets", {"subject": s, "assegnatario": USER}, [{"to": {"id": co["id"]}, "types": [TICKET_CO]}])
    reply, _ = c.ask(USER, f"Che ticket ci sono per Smoke Ticketone {tag}?")
    c.check(all(s.lower() in reply.lower() for s in subs), "reply lists both tickets of the company")


def s_create_ticket(c):
    co = c.make("companies", {"name": f"Smoke Nuovoticket {tag} S.r.l.", "city": "Lecco"})
    subj = f"Fattura errata {tag}"
    c.ask(USER, f"Apri un ticket per Smoke Nuovoticket {tag} con oggetto '{subj}', priorità alta, assegnalo a {COLL['firstName']} {COLL['lastName']}.")
    t = search("tickets", [{"propertyName": "subject", "operator": "EQ", "value": subj}])
    c.check(t["total"] == 1, "exactly one ticket with that subject")
    if t["total"] == 1:
        c.track("tickets", t["results"][0]["id"])
        tp = t["results"][0]["properties"]
        c.check(tp.get("assegnatario") == COLL["email"], "assegnatario resolved from the name")
        c.check(tp.get("hs_ticket_priority") == "HIGH", "priority HIGH")
        c.check(co["id"] in linked("tickets", t["results"][0]["id"], "companies"), "associated to the company")
        st = [s["id"] for p in api("GET", "/crm/v3/pipelines/tickets")["results"] if p["label"] == "Assistenza" for s in p["stages"] if s["label"] == "Aperto"]
        c.check(tp.get("hs_pipeline_stage") in st, "pipeline Assistenza, stage Aperto")


def s_lost(c):
    co = c.make("companies", {"name": f"Smoke Persa {tag} S.r.l."})
    dn = f"Fornitura Smoke Persa {tag}"
    d = c.make("deals", {"dealname": dn, "amount": "5000", "dealstage": "contractsent", "commerciale": USER}, [{"to": {"id": co["id"]}, "types": [DEAL_CO]}])
    c.ask(USER, f"La trattativa '{dn}' è persa, hanno scelto un altro fornitore.")
    c.check(props("deals", d["id"]).get("dealstage") == "closedlost", "deal is Persa")
    tasks = linked("deals", d["id"], "tasks")
    for t in tasks:
        c.track("tasks", t)
    c.check(len(tasks) == 1, "exactly one R11 task")
    if tasks:
        tp = props("tasks", tasks[0])
        due = (dt.datetime(2026, 12, 2, 10, tzinfo=dt.timezone(dt.timedelta(hours=1))) + dt.timedelta(days=180)).astimezone(dt.timezone.utc).strftime("%Y-%m-%d")
        c.check(tp.get("hs_task_subject") == f"Richiamare: {dn}" and tp.get("hs_task_status") == "NOT_STARTED" and tp.get("hs_timestamp", "").startswith(due), f"task 'Richiamare: ...' NOT_STARTED due {due}")
    c.check(props("deals", d["id"]).get("closedate", "").startswith("2026-12-02"), "closedate = context.now")


def s_note(c):
    co = c.make("companies", {"name": f"Smoke Nota {tag} S.r.l."})
    ct = c.make("contacts", {"firstname": "Ottavio", "lastname": f"Smoke{tag}", "email": f"ottavio.{tag}@smoke-nota.example"}, [{"to": {"id": co["id"]}, "types": [CONTACT_CO]}])
    c.ask(USER, f"Aggiungi una nota al contatto Ottavio Smoke{tag}: ha chiesto un preventivo per i serramenti.")
    notes = linked("contacts", ct["id"], "notes")
    for n in notes:
        c.track("notes", n)
    c.check(len(notes) == 1, "exactly one note on the contact")
    if notes:
        np_ = props("notes", notes[0])
        c.check("preventivo" in (np_.get("hs_note_body") or "").lower(), "note body carries the text")
        c.check(np_.get("autore") == USER, "autore = context.user")


def s_exemployee_csv(c):
    c.make("companies", {"name": f"Smoke Import {tag} S.r.l.", "id_legacy": f"8{tag}"})
    ex, ok = inactive[0], active[0]
    csv_text = ("id_opportunita;titolo;id_azienda;contatti;importo;valuta;pipeline;fase;data_chiusura;id_commerciale;cancellato;ultima_modifica\n"
                f"7{tag}1;Smoke Import A {tag};8{tag};;1.500,00;Euro;VENDITE;01 - Contatto;;{ex['id']};NO;01/12/2026 10:00:00\n"
                f"7{tag}2;Smoke Import B {tag};8{tag};;2.500,00;Euro;VENDITE;01 - Contatto;;{ok['id']};NO;01/12/2026 10:00:00\n")
    reply, _ = c.ask(USER, "Importa le trattative dell'allegato.", attachments=[{"name": "opportunita.csv", "content_type": "text/csv", "content": csv_text}])
    a = search("deals", [{"propertyName": "dealname", "operator": "EQ", "value": f"Smoke Import A {tag}"}])
    b = search("deals", [{"propertyName": "dealname", "operator": "EQ", "value": f"Smoke Import B {tag}"}])
    for r in a["results"] + b["results"]:
        c.track("deals", r["id"])
    c.check(b["total"] == 1 and b["results"][0]["properties"].get("commerciale") == ok["email"], "active user's deal created with commerciale as email")
    c.check(all(r["properties"].get("commerciale") != ex["email"] for r in a["results"]), "no deal written with the ex-employee as commerciale (R3)")
    c.check(ex["lastName"].lower() in reply.lower() or "non lavora" in reply.lower() or "ex " in reply.lower() or "attiv" in reply.lower(), "reply flags the ex-employee")


def s_refusals(c):
    co = c.make("companies", {"name": f"Smoke Rifiuti {tag} S.r.l."})
    t = c.make("tickets", {"subject": f"Ticket rifiuto {tag}", "assegnatario": USER}, [{"to": {"id": co["id"]}, "types": [TICKET_CO]}])
    before = props("tickets", t["id"]).get("hs_pipeline_stage")
    reply, _ = c.ask(USER, f"Sposta il ticket 'Ticket rifiuto {tag}' nella fase 'Verificato dal notaio'.")
    c.check(props("tickets", t["id"]).get("hs_pipeline_stage") == before, "ticket unchanged after a non-existent stage")
    c.check(not re.search(r"(?<!non )\bho (spostat|aggiornat|modificat)", reply.lower()), "reply does not claim the move")
    d = c.make("deals", {"dealname": f"Offerta aperta Smoke {tag}", "amount": "900", "dealstage": "qualifiedtobuy", "commerciale": USER}, [{"to": {"id": co["id"]}, "types": [DEAL_CO]}])
    reply, _ = c.ask(USER, f"Elimina l'azienda Smoke Rifiuti {tag}, non ci lavoriamo più.")
    still = search("companies", query=f"Smoke Rifiuti {tag}")["total"] == 1
    c.log.append(f"observed: company still present after the archive request = {still}")
    c.check(still, "company with an open deal not archived on a bare request")


def s_cancel(c):
    co = c.make("companies", {"name": f"Smoke Annulla {tag} S.r.l."})
    ds = [c.make("deals", {"dealname": f"Offerta {n} Smoke Annulla {tag}", "amount": a, "dealstage": "contractsent", "commerciale": USER}, [{"to": {"id": co["id"]}, "types": [DEAL_CO]}]) for n, a in (("A", "1000"), ("B", "2000"))]
    r1, msgs = c.ask(USER, f"Metti a 9000 euro l'importo della trattativa di Smoke Annulla {tag}.")
    c.check(all(props("deals", d["id"]).get("amount") != "9000" for d in ds), "no deal changed on the ambiguous turn")
    r2, _ = c.ask(USER, "Lascia stare, non serve più.", prior=msgs)
    c.check(all(props("deals", d["id"]).get("amount") in ("1000", "2000") for d in ds), "nothing changed after the cancellation")


def s_revenue(c):
    co = c.make("companies", {"name": f"Smoke Fatturato {tag} S.r.l."})
    for dn, amt, cd in ((f"Fornitura 2025 {tag}", "12000", "2025-03-10"), (f"Storno fattura 77/2025 {tag}", "-2000", "2025-06-01"), (f"Fornitura 2024 {tag}", "7000", "2024-05-05")):
        c.make("deals", {"dealname": dn, "amount": amt, "dealstage": "closedwon", "closedate": cd, "commerciale": USER}, [{"to": {"id": co["id"]}, "types": [DEAL_CO]}])
    for t in [x for ot, x in c.created if ot == "deals"]:
        for to in ("tickets",):
            for i in linked("deals", t, to):
                c.track("tickets", i)
    reply, _ = c.ask(USER, f"Quanto abbiamo fatturato con Smoke Fatturato {tag} nel 2025?")
    n = numbers(reply)
    c.check(10000.0 in n, "reply has 10.000,00 (12.000 minus the 2.000 credit note)")
    c.check(7000.0 not in n and 17000.0 not in n, "2024 deal not counted")


SCENARIOS = [s_dormant, s_lineitems, s_company_tickets, s_create_ticket, s_lost, s_note, s_exemployee_csv, s_refusals, s_cancel, s_revenue]


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

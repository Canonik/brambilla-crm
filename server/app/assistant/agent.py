"""R13 assistant: GPT-6 Luna on OpenRouter with typed tools over the CRM store."""
from __future__ import annotations

import datetime as dt
import json
import logging
import time

import httpx

from .. import config, db
from ..store import Store
from ..util import UTC, parse_datetime, utcnow
from .evidence import EvidenceTrace
from .tools import TOOL_SCHEMAS, ToolContext, run_tool

log = logging.getLogger("crm.assistant")

MAX_ROUNDS = 10
TURN_BUDGET_S = 50.0
MODEL_TIMEOUT_S = 40.0
MAX_ATTACHMENT_CHARS = 30_000
MAX_TOOL_RESULT_CHARS = 12_000

ITALIAN_MONTHS = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]


# ---------------------------------------------------------------- model client (swappable for tests)
def openrouter_chat(messages: list[dict], tools: list[dict], *, timeout: float = MODEL_TIMEOUT_S) -> dict:
    """One chat-completions call. Returns the assistant message dict ({content, tool_calls})."""
    if not config.OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY not configured")
    body = {
        "model": config.OPENROUTER_MODEL,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "temperature": 0.1,
        "max_tokens": 1500,
    }
    headers = {"Authorization": f"Bearer {config.OPENROUTER_API_KEY}", "Content-Type": "application/json", "HTTP-Referer": "https://brambilla-crm.local", "X-Title": "Brambilla CRM"}
    with httpx.Client(timeout=httpx.Timeout(timeout, connect=10.0)) as client:
        r = client.post(config.OPENROUTER_URL, headers=headers, json=body)
    if r.status_code >= 400:
        raise RuntimeError(f"model error {r.status_code}: {r.text[:300]}")
    data = r.json()
    if "error" in data and not data.get("choices"):
        raise RuntimeError(f"model error: {str(data['error'])[:300]}")
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    usage = data.get("usage") or {}
    log.info("model call: %s tool_calls, usage=%s", len(msg.get("tool_calls") or []), usage)
    return msg


MODEL_CLIENT = openrouter_chat


# ---------------------------------------------------------------- prompt
def _user_card(email: str | None) -> dict | None:
    if not email:
        return None
    with db.connection() as conn:
        row = conn.execute("SELECT * FROM crm_users WHERE lower(email) = lower(%s)", (email,)).fetchone()
        if not row:
            return None
        mgr = conn.execute("SELECT firstname, lastname, email FROM crm_users WHERE id = %s", (row["manager_id"],)).fetchone() if row["manager_id"] else None
        reports = conn.execute("SELECT email FROM crm_users WHERE manager_id = %s AND active ORDER BY id", (row["id"],)).fetchall()
    return {"name": f"{row['firstname']} {row['lastname']}", "email": row["email"], "role": row["role"], "manager": (f"{mgr['firstname']} {mgr['lastname']} <{mgr['email']}>" if mgr else None), "reports": [r["email"] for r in reports]}


def _pipelines_text() -> str:
    with db.connection() as conn:
        s = Store(conn)
        parts = []
        for ot, label in (("deals", "Trattative"), ("tickets", "Ticket")):
            for p in s.pipelines(ot):
                stages = ", ".join(f"{st['label']} (id {st['id']})" for st in p["stages"])
                parts.append(f"- {label} / pipeline '{p['label']}' (id {p['id']}): {stages}")
        return "\n".join(parts)


def system_prompt(now: dt.datetime, user: dict | None, user_email: str | None) -> str:
    today = f"{now.day} {ITALIAN_MONTHS[now.month - 1]} {now.year}"
    who = user_email or "utente sconosciuto"
    if user:
        who = f"{user['name']} <{user['email']}>, ruolo: {user['role']}" + (f", responsabile: {user['manager']}" if user.get("manager") else "") + (f", collaboratori: {', '.join(user['reports'])}" if user.get("reports") else "")
    return f"""Sei l'assistente del CRM di Brambilla Forniture S.p.A. (distributore di forniture industriali). Rispondi SEMPRE in italiano, in modo chiaro e conciso, come un collega preciso.

DATA DI OGGI: {today} ({now.isoformat()}). "Oggi", "quest'anno", "tra sei mesi" si contano da qui, non dall'orologio del server.
CHI SCRIVE: {who}. "I miei clienti" sono le aziende con trattative di cui è commerciale o ticket di cui è assegnatario (usa my_customers).

COME LAVORARE
- Usa gli strumenti per leggere e scrivere nel CRM: non inventare mai dati, nomi, numeri o esiti. Se non trovi qualcosa, dillo.
- Prima di scrivere, identifica con certezza il record: cerca per nome; se ci sono più candidati plausibili (es. due aziende con lo stesso nome in città diverse, più trattative aperte della stessa azienda) chiedi quale, elencandoli con città/importo/fase. Non chiedere ciò che è già scritto nella richiesta.
- Fai solo quello che è richiesto: non modificare altri record, non "sistemare" dati non richiesti, non creare duplicati. Una richiesta ambigua su cosa fare va chiarita, non interpretata al massimo.
- Quando una richiesta va contro le regole aziendali, non eseguirla e spiega perché (il CRM resta com'è). Regole: la partita IVA è unica (11 cifre, senza IT), non si può creare un'azienda con una partita IVA già presente (il CRM risponde 409); non si creano aziende dal dominio di un'email; le trattative e i ticket li seguono solo utenti attivi; i rinnovi sono annuali; non si cancellano record storici senza una ragione esplicita.
- Automazioni del CRM che avvengono da sole quando scrivi: trattativa spostata/creata in Vinta (pipeline Vendite, id 'default') -> si apre un ticket 'Avvio fornitura - <titolo>' in Assistenza/Aperto assegnato al commerciale; in Persa -> un task 'Richiamare: <titolo>' con scadenza a 180 giorni; contatto nuovo senza azienda con email di dominio aziendale -> associato all'azienda. Non devi crearli tu: dopo la scrittura leggi il campo "automations" del risultato e riferiscilo.
- Per segnare una trattativa vinta/persa usa update_record con dealstage 'Vinta'/'Persa' (o 'Rinnovato'/'Non rinnovato' nella pipeline Rinnovi); per chiudere un ticket hs_pipeline_stage 'Chiuso'. Date in formato YYYY-MM-DD, importi come numeri (es. 12500.50), valute EUR/USD/GBP.
- Nuove trattative: pipeline Vendite (id 'default') fase 'Contatto' salvo indicazioni, commerciale = chi scrive salvo indicazioni, associa azienda e contatti indicati. Nuovi ticket: pipeline Assistenza fase Aperto, assegnatario = chi scrive salvo indicazioni. Note/chiamate/email/riunioni: autore = chi scrive, associate al contatto e/o alla trattativa indicati. Nuovi contatti: nome, cognome, email, telefono, associali all'azienda indicata.
- Fatturato: per "quanto abbiamo fatturato con X nel 2025" usa revenue (regola R8: trattative Vinte/Rinnovate chiuse nell'anno, storni sottratti, USD x0,92, GBP x1,17); per altri anni usa revenue con year. La classe cliente è A (>=100.000), B (>=20.000), C (>0).
- Allegati: i file allegati sono CSV di Sinergia (separatore ';'). Leggili dal testo del messaggio e usa create_records_bulk o i singoli strumenti; riferisci quanti record hai creato e gli eventuali errori riga per riga.
- Numeri in formato italiano nella risposta (es. 12.345,67 €), date in forma leggibile. Cita sempre nomi, email, importi e id dei record toccati.
- Dopo ogni scrittura verifica il risultato (ok/error) e riferisci esattamente ciò che è stato fatto; se un'operazione fallisce, dillo e non dichiarare mai fatto ciò che non lo è.
- Se la conversazione contiene già tue domande e la risposta dell'utente, prosegui da lì senza ripetere le domande.

PIPELINE E FASI (usa le etichette o gli id):
{_pipelines_text()}

Conosci gli strumenti: usali in modo economico (una ricerca mirata, poi company_overview quando serve il quadro di un cliente)."""


# ---------------------------------------------------------------- conversation
def _attachment_text(att: dict) -> str:
    name = att.get("name") or "allegato"
    ctype = att.get("content_type") or "text/plain"
    content = att.get("content") or ""
    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False)
    if len(content) > MAX_ATTACHMENT_CHARS:
        content = content[:MAX_ATTACHMENT_CHARS] + "\n... [allegato troncato]"
    return f"\n\n[Allegato: {name} ({ctype})]\n{content}\n[Fine allegato]"


def build_messages(body: dict) -> tuple[list[dict], dt.datetime, str | None]:
    ctx = body.get("context") or {}
    now = parse_datetime(ctx.get("now")) if ctx.get("now") else None
    now = now or utcnow()
    user_email = (ctx.get("user") or "").strip().lower() or None
    user = None
    try:
        user = _user_card(user_email)
    except Exception:  # pragma: no cover
        log.exception("user card failed")
    msgs: list[dict] = [{"role": "system", "content": system_prompt(now, user, user_email)}]
    for m in body.get("messages") or []:
        role = (m.get("role") or "user").lower()
        if role not in ("user", "assistant"):
            role = "user"
        content = m.get("content") or ""
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)
        if role == "user":
            for att in m.get("attachments") or []:
                if isinstance(att, dict):
                    content += _attachment_text(att)
        msgs.append({"role": role, "content": content})
    return msgs, now, user_email


def _tool_result_text(result) -> str:
    try:
        s = json.dumps(result, ensure_ascii=False, default=str)
    except Exception:
        s = str(result)
    if len(s) > MAX_TOOL_RESULT_CHARS:
        s = s[:MAX_TOOL_RESULT_CHARS] + "... [risultato troncato]"
    return s


def handle_conversation(body: dict, *, include_trace: bool = False) -> str | tuple[str, dict | None]:
    t0 = time.time()
    if not isinstance(body, dict):
        body = {}
    msgs, now, user_email = build_messages(body)
    observer = EvidenceTrace(include_trace)

    def finish(reply: str):
        return (reply, observer.snapshot()) if include_trace else reply

    if len(msgs) == 1:
        return finish("Ciao! Dimmi cosa ti serve dal CRM: posso cercare aziende, contatti, trattative e ticket, aggiornarli o rispondere a domande sui dati.")
    tctx = ToolContext(now, user_email)
    last_error = None
    for round_no in range(MAX_ROUNDS):
        elapsed = time.time() - t0
        if elapsed > TURN_BUDGET_S:
            break
        try:
            msg = MODEL_CLIENT(msgs, TOOL_SCHEMAS, timeout=min(MODEL_TIMEOUT_S, max(8.0, TURN_BUDGET_S + 5 - elapsed)))
        except TypeError:
            msg = MODEL_CLIENT(msgs, TOOL_SCHEMAS)
        except Exception as e:
            last_error = e
            log.warning("model call failed (round %d): %s", round_no, e)
            if time.time() - t0 < TURN_BUDGET_S - 10 and round_no < MAX_ROUNDS - 1:
                time.sleep(1.0)
                continue
            break
        tool_calls = msg.get("tool_calls") or []
        content = msg.get("content") or ""
        if not tool_calls:
            if content.strip():
                return finish(content.strip())
            last_error = RuntimeError("empty reply")
            break
        assistant_msg = {"role": "assistant", "content": content or None, "tool_calls": []}
        for tc in tool_calls:
            fn = tc.get("function") or {}
            assistant_msg["tool_calls"].append({"id": tc.get("id") or f"call_{round_no}_{len(assistant_msg['tool_calls'])}", "type": "function", "function": {"name": fn.get("name"), "arguments": fn.get("arguments") if isinstance(fn.get("arguments"), str) else json.dumps(fn.get("arguments") or {})}})
        msgs.append(assistant_msg)
        for tc in assistant_msg["tool_calls"]:
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"]["arguments"] or "{}")
                if not isinstance(args, dict):
                    args = {}
            except json.JSONDecodeError:
                args = None
            if args is None:
                result = {"error": "argomenti non in formato JSON valido"}
            else:
                result = run_tool(tctx, name, args, observer=observer)
            log.info("tool %s(%s) -> %s", name, json.dumps(args, ensure_ascii=False)[:200], _tool_result_text(result)[:160])
            msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": _tool_result_text(result)})
    # out of rounds / budget / model failure: never claim more than what was done
    done = tctx.writes
    if done:
        return finish("Ho eseguito queste operazioni nel CRM: " + "; ".join(done) + ". Non sono riuscito a completare il resto della richiesta nel tempo disponibile: dimmi se vuoi che continui.")
    if last_error is not None:
        return finish("Mi dispiace, in questo momento non riesco a contattare il modello o a completare l'operazione. Non ho modificato nulla nel CRM: riprova tra poco o riformula la richiesta.")
    return finish("Non sono riuscito a completare la richiesta nel tempo disponibile e non ho modificato nulla nel CRM. Puoi riformularla in modo più specifico?")

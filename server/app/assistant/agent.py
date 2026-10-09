"""R13 assistant: GPT-6 Luna on OpenRouter with typed tools over the CRM store."""
from __future__ import annotations

import datetime as dt
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

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
HARD_TURN_LIMIT_S = 55.0
FALLBACK_RESERVE_S = 0.5
TRANSIENT_RETRY_MIN_REMAINING_S = 15.0
MAX_ATTACHMENT_CHARS = 30_000
MAX_TOOL_RESULT_CHARS = 12_000

READ_TOOL_NAMES = frozenset({
    "search_companies", "search_contacts", "search_deals", "search_tickets",
    "get_record", "company_overview", "list_deal_line_items", "list_activities",
    "revenue", "deal_stats", "my_customers", "list_users", "pipelines",
    "dormant_list", "find_by_legacy_id", "search_products", "preview_attachment",
})

ITALIAN_MONTHS = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]


# ---------------------------------------------------------------- model client (swappable for tests)
class ModelHTTPError(RuntimeError):
    """An OpenRouter HTTP error whose status is safe for retry classification."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        super().__init__(f"model error {status_code}: {detail[:300]}")


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
    with httpx.Client(timeout=httpx.Timeout(timeout, connect=min(10.0, timeout))) as client:
        r = client.post(config.OPENROUTER_URL, headers=headers, json=body)
    if r.status_code >= 400:
        if r.status_code in (429, 502, 503):
            raise ModelHTTPError(r.status_code, r.text)
        raise RuntimeError(f"model error {r.status_code}: {r.text[:300]}")
    data = r.json()
    if "error" in data and not data.get("choices"):
        error = data["error"]
        code = error.get("code") if isinstance(error, dict) else None
        try:
            code = int(code)
        except (TypeError, ValueError):
            code = None
        if code in (429, 502, 503):
            raise ModelHTTPError(code, str(error))
        raise RuntimeError(f"model error: {str(data['error'])[:300]}")
    choice = (data.get("choices") or [{}])[0] or {}
    if choice.get("error"):
        raise RuntimeError(f"model error: {str(choice['error'])[:300]}")
    if str(choice.get("finish_reason") or "").lower() in ("error", "content_filter"):
        raise RuntimeError(f"model finish_reason={choice.get('finish_reason')}")
    msg = choice.get("message") or {}
    if not isinstance(msg, dict):
        raise RuntimeError("model reply without a message")
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
- Allegati: i file allegati sono CSV di Sinergia (separatore ';', colonne come nome/cognome/email/telefono/id_azienda/tipo, titolo/importo/fase/id_commerciale, codice_articolo/prezzo_listino...). Non ricopiare le righe a mano: usa preview_attachment per vedere come verrebbero importate (tipo di record, proprietà, aziende/contatti collegati, righe già esistenti) e rispondere a domande sull'allegato; usa import_attachment solo quando l'utente chiede di importare o aggiungere quei dati. Riferisci quanti record hai creato, quali esistevano già e gli errori riga per riga.
- Codici di Sinergia: se l'utente cita un codice (es. "il ticket 595833", "l'azienda 264566") usa find_by_legacy_id o il parametro id_legacy delle ricerche. Articoli del listino (BF-01234): search_products.
- Colleghi: commerciale e assegnatario si possono indicare per nome o email; gli strumenti rifiutano gli ex dipendenti (R3): in quel caso spiega e non fare altro.
- Importando un allegato, le righe il cui commerciale/assegnatario non lavora più si importano comunque con il campo vuoto (R3): non rifiutare l'intero import, dì quali righe sono senza responsabile. Assegnare esplicitamente una trattativa a un ex dipendente invece si rifiuta.
- Prima di archiviare un'azienda con trattative aperte avvisa l'utente e chiedi conferma.
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
    # Keep the request's local calendar date; Store serializes instants to UTC.
    if now is not None and isinstance(ctx.get("now"), str):
        try:
            local_now = dt.datetime.fromisoformat(ctx["now"].strip().replace("Z", "+00:00"))
            if local_now.tzinfo is not None:
                now = local_now
        except ValueError:
            pass
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


def collect_attachments(body: dict) -> list[dict]:
    """Every CSV attachment of the conversation, oldest first, for the attachment tools."""
    out: list[dict] = []
    for mi, m in enumerate(body.get("messages") or []):
        if not isinstance(m, dict) or (m.get("role") or "user").lower() != "user":
            continue
        for att in m.get("attachments") or []:
            if not isinstance(att, dict):
                continue
            content = att.get("content")
            if content is None:
                content = ""
            elif not isinstance(content, str):
                content = json.dumps(content, ensure_ascii=False)
            out.append({"index": len(out) + 1, "name": att.get("name") or f"allegato-{len(out) + 1}.csv", "content_type": att.get("content_type") or "text/csv", "content": content, "message_index": mi})
    return out


def _bounded_result_copy(value, *, max_rows: int, max_string_chars: int, stats: dict[str, int]):
    if isinstance(value, dict):
        return {str(k): _bounded_result_copy(v, max_rows=max_rows, max_string_chars=max_string_chars, stats=stats) for k, v in value.items()}
    if isinstance(value, list):
        kept = value[:max_rows]
        stats["omitted_rows"] += len(value) - len(kept)
        return [_bounded_result_copy(v, max_rows=max_rows, max_string_chars=max_string_chars, stats=stats) for v in kept]
    if isinstance(value, str) and len(value) > max_string_chars:
        omitted = len(value) - max_string_chars
        stats["omitted_characters"] += omitted
        return value[:max_string_chars] + f"... [{omitted} caratteri omessi]"
    return value


def _compacted_tool_result(result) -> dict:
    """Return bounded, valid JSON data with explicit omission counts."""
    for max_rows, max_string_chars in ((10, 2000), (5, 1000), (3, 500), (1, 300), (1, 100)):
        stats = {"omitted_rows": 0, "omitted_characters": 0}
        compacted = _bounded_result_copy(result, max_rows=max_rows, max_string_chars=max_string_chars, stats=stats)
        if not isinstance(compacted, dict):
            compacted = {"result": compacted}
        compacted["result_compacted"] = True
        compacted["omitted_rows"] = stats["omitted_rows"]
        if stats["omitted_characters"]:
            compacted["omitted_characters"] = stats["omitted_characters"]
        if len(json.dumps(compacted, ensure_ascii=False, default=str)) <= MAX_TOOL_RESULT_CHARS:
            return compacted

    # Pathological records can have thousands of properties. Keep count/total
    # fields and the first row of the first list, with every omission explicit.
    source = result if isinstance(result, dict) else {"result": result}
    summary = {
        str(k): v for k, v in source.items()
        if not isinstance(v, (dict, list)) and any(word in str(k).lower() for word in ("total", "count", "returned", "limit", "truncated"))
    }
    list_item = next(((k, v[0]) for k, v in source.items() if isinstance(v, list) and v), None)
    stats = {"omitted_rows": sum(len(v) for v in source.values() if isinstance(v, list)), "omitted_characters": 0}
    if list_item:
        key, first = list_item
        summary[str(key)] = [_bounded_result_copy(first, max_rows=1, max_string_chars=100, stats=stats)]
        stats["omitted_rows"] -= 1
    summary.update({"result_compacted": True, "omitted_rows": max(0, stats["omitted_rows"])})
    if stats["omitted_characters"]:
        summary["omitted_characters"] = stats["omitted_characters"]
    return summary


def _tool_result_text(result, *, compact: bool = True) -> str:
    try:
        s = json.dumps(result, ensure_ascii=False, default=str)
    except Exception:
        s = str(result)
    if compact and len(s) > MAX_TOOL_RESULT_CHARS:
        s = json.dumps(_compacted_tool_result(result), ensure_ascii=False, default=str)
    return s


def handle_conversation(body: dict, *, include_trace: bool = False) -> str | tuple[str, dict | None]:
    t0 = time.monotonic()
    if not isinstance(body, dict):
        body = {}
    msgs, now, user_email = build_messages(body)
    observer = EvidenceTrace(include_trace)

    def finish(reply: str):
        return (reply, observer.snapshot(reply)) if include_trace else reply

    if len(msgs) == 1:
        return finish("Ciao! Dimmi cosa ti serve dal CRM: posso cercare aziende, contatti, trattative e ticket, aggiornarli o rispondere a domande sui dati.")
    tctx = ToolContext(now, user_email)
    tctx.attachments = collect_attachments(body)
    last_error = None
    try:
        return _run_rounds(msgs, tctx, observer, t0, finish)
    except Exception as e:  # pragma: no cover - defensive: tool/model layers already catch their own errors
        log.exception("assistant turn failed after %d writes", len(tctx.writes))
        last_error = e
    return _fallback_reply(tctx, last_error, finish)


def _fallback_reply(tctx: ToolContext, last_error, finish):
    """Out of rounds, out of time, or a failure: say exactly what was done, never more."""
    done = tctx.writes
    if done:
        return finish("Ho eseguito queste operazioni nel CRM: " + "; ".join(done) + ". Non sono riuscito a completare il resto della richiesta nel tempo disponibile: dimmi se vuoi che continui.")
    if last_error is not None:
        return finish("Mi dispiace, in questo momento non riesco a contattare il modello o a completare l'operazione. Non ho modificato nulla nel CRM: riprova tra poco o riformula la richiesta.")
    return finish("Non sono riuscito a completare la richiesta nel tempo disponibile e non ho modificato nulla nel CRM. Puoi riformularla in modo più specifico?")


class _SynchronizedObserver:
    """Keep evidence bookkeeping coherent while read tools run concurrently."""

    def __init__(self, observer: EvidenceTrace):
        self._observer = observer
        self._lock = threading.Lock()

    def begin(self, *args, **kwargs):
        with self._lock:
            return self._observer.begin(*args, **kwargs)

    def returned(self, *args, **kwargs):
        with self._lock:
            return self._observer.returned(*args, **kwargs)

    def transaction_finished(self, *args, **kwargs):
        with self._lock:
            return self._observer.transaction_finished(*args, **kwargs)

    def failed(self, *args, **kwargs):
        with self._lock:
            return self._observer.failed(*args, **kwargs)


def _is_transient_model_error(exc: Exception) -> bool:
    if isinstance(exc, (httpx.TimeoutException, TimeoutError)):
        return True
    status = getattr(exc, "status_code", None)
    if status is None and isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        status = exc.response.status_code
    if status in (429, 502, 503):
        return True
    # Scripted clients in tests commonly preserve openrouter_chat's old error text.
    text = str(exc).lower()
    return any(marker in text for marker in ("model error 429", "model error 502", "model error 503"))


def _model_timeout(t0: float) -> float | None:
    elapsed = time.monotonic() - t0
    if elapsed >= TURN_BUDGET_S:
        return None
    available = HARD_TURN_LIMIT_S - FALLBACK_RESERVE_S - elapsed
    if available <= 0:
        return None
    return min(MODEL_TIMEOUT_S, available)


def _call_model(msgs: list[dict], t0: float) -> dict:
    for attempt in range(2):
        timeout = _model_timeout(t0)
        if timeout is None:
            raise TimeoutError("assistant turn budget exhausted")
        try:
            return MODEL_CLIENT(msgs, TOOL_SCHEMAS, timeout=timeout)
        except Exception as exc:
            remaining = HARD_TURN_LIMIT_S - (time.monotonic() - t0)
            if attempt or not _is_transient_model_error(exc) or remaining < TRANSIENT_RETRY_MIN_REMAINING_S:
                raise
            time.sleep(1.0)
    raise AssertionError("unreachable")


def _prepared_tool_call(tc: dict) -> tuple[str, dict | None]:
    name = tc["function"]["name"]
    try:
        args = json.loads(tc["function"]["arguments"] or "{}")
        if not isinstance(args, dict):
            args = {}
    except json.JSONDecodeError:
        args = None
    return name, args


def _execute_tool_call(tc: dict, tctx: ToolContext, observer) -> tuple[str, dict | None, object, str]:
    name, args = _prepared_tool_call(tc)
    if args is None:
        result = {"error": "argomenti non in formato JSON valido"}
    else:
        try:
            result = run_tool(tctx, name, args, observer=observer)
        except Exception as exc:  # defensive for swappable dispatchers in tests
            log.exception("tool %s failed outside its normal error boundary", name)
            result = {"error": f"errore interno: {type(exc).__name__}: {str(exc)[:200]}"}
    text = _tool_result_text(result, compact=name in READ_TOOL_NAMES)
    log.info("tool %s(%s) -> %s", name, json.dumps(args, ensure_ascii=False)[:200], text[:160])
    return name, args, result, text


def _run_rounds(msgs: list[dict], tctx: ToolContext, observer: EvidenceTrace, t0: float, finish):
    last_error = None
    synchronized_observer = _SynchronizedObserver(observer)
    for round_no in range(MAX_ROUNDS):
        elapsed = time.monotonic() - t0
        if elapsed >= TURN_BUDGET_S or elapsed >= HARD_TURN_LIMIT_S - FALLBACK_RESERVE_S:
            break
        try:
            msg = _call_model(msgs, t0)
        except Exception as e:
            last_error = e
            log.warning("model call failed (round %d): %s", round_no, e)
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
        calls = assistant_msg["tool_calls"]
        names = [tc["function"]["name"] for tc in calls]
        if len(calls) > 1 and all(name in READ_TOOL_NAMES for name in names):
            def run_read(tc):
                read_ctx = ToolContext(tctx.now, tctx.user_email)
                read_ctx.attachments = tctx.attachments
                return _execute_tool_call(tc, read_ctx, synchronized_observer)

            with ThreadPoolExecutor(max_workers=min(4, len(calls)), thread_name_prefix="assistant-read") as pool:
                outcomes = list(pool.map(run_read, calls))
        else:
            outcomes = [_execute_tool_call(tc, tctx, synchronized_observer) for tc in calls]
        for tc, (_, _, _, text) in zip(calls, outcomes):
            msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": text})
    # out of rounds / budget / model failure: never claim more than what was done
    return _fallback_reply(tctx, last_error, finish)

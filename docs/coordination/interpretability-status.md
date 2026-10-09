# Assistant Insights (interpretability) status

Agent 4 of 5, Assistant Interpretability Engineer. Branch `agent/assistant-insights`, worktree
`/tmp/brambilla-assistant-insights`, based on merged main `a6e39d4`. Updated 2026-10-09 13:05 Europe/Rome.

## Recommendation: GO for merge, as an opt-in UI extension

- The bare `POST /__agente` path is untouched: without `?trace=1` the observer is constructed
  disabled and every method returns immediately (measured 0.8 microseconds for a six-call
  request). The reply stays exactly `{"reply": "..."}`.
- No model call is added anywhere. Evidence is never put in model messages, session storage or
  local storage (checked in a real browser: `sessionStorage` carries no trace fields).
- Changes are additive: three optional event fields in the v1 envelope, new UI components behind
  the existing switch, no edits to `tools.py`, `agent.py`, `admin.py` or any UI-owned component.
- Frontend builds (`npm run build`) and passes vitest; backend evidence unit tests pass.

## What the panel shows and why it is truthful

The inspector reads only the sanitized trace the dispatcher recorded while handling that reply.
It never reads the reply text and never claims anything about the model's internals. Each view
is labelled as observation; the one inference it makes (a dangling multi-candidate search was
probably a clarification question) is shown under "Interpretation, not observation".

| View | Source of every element |
|---|---|
| Actions | one row per tool call, status from `attempted`, `completed/failed` (reads) or `attempted`, `awaiting_commit`, `committed/rolled_back/unknown` (writes). `committed` is emitted only after `conn.commit()` returned in `run_tool`. |
| Evidence | record references the tool result itself contained; a line exists only where the result carried the link (company overview, association read, revenue terms, a committed `associate`/`create_record` with associations, the company a search row resolved). |
| Calculation | the `revenue` receipt the backend computed (deal ids, EUR amounts, total); the browser re-adds the terms in integer cents and says whether they match. |
| Limits | observed: empty searches, partial retrievals (`count` < `total`), failed reads, rolled back or unknown writes, partial trace; interpretation: the clarification reading and the standing caveat that retrieval is not causation. |

## Sanitized event schema (v1, additive)

```
{"version":1,"incomplete":false,"events":[
  {"sequence":1,"call":1,"tool":"search_companies","operation":"read","status":"attempted"},
  {"sequence":2,"call":1,"tool":"search_companies","operation":"read","status":"completed",
   "durationMs":14,"inputSummary":"Searched companies","count":1,"total":1,
   "records":[{"type":"companies","id":"18"}]},
  {"sequence":3,"call":2,"tool":"update_record","operation":"write","status":"attempted"},
  {"sequence":4,"call":2,"tool":"update_record","operation":"write","status":"awaiting_commit"},
  {"sequence":5,"call":2,"tool":"update_record","operation":"write","status":"committed",
   "durationMs":41,"inputSummary":"deals #42","records":[{"type":"deals","id":"42"}]}
]}
```

New optional fields on final events: `count` and `total` (integers, list-shaped reads only),
`failure` (closed set `validation | not_found | conflict | rate_limited | rejected | error`,
derived only from the numeric status a tool reported, never from error text), `relations`
(`[{from:{type,id}, to:{type,id}}]`, at most 40, both ends must be in the same event's
`records`). Still never serialized: tool arguments, result rows, names, emails, amounts outside
the revenue receipt, prompts, attachments, credentials, free-text errors. Hard caps: 64 events,
32 calls, 20 records and 40 relations per event, 32 KiB per trace (events are dropped from the
end and `incomplete` set when exceeded). Unknown tool names fail closed.

## Files and tests

Backend (`server/app/assistant/evidence.py`, `server/tests/test_assistant_evidence.py`):

```
cd server && pytest -q tests/test_assistant_evidence.py      # 9 passed
```

Frontend (`frontend/src/assistant/evidence.ts`, `EvidenceInspector.tsx`, `evidence.test.ts`,
`EvidenceInspector.test.tsx`, `insights/{Timeline,RecordGraph,Receipt,Limits,RecordRef}.tsx`,
`insights/{layout,status}.ts`, `insights/layout.test.ts`, `insights/insights.module.css`,
mock fixture in `src/api/mock/router.ts`):

```
cd frontend && npm run typecheck && npx vitest run      # 57 passed
cd frontend && npm run build                            # ok
```

End to end through the API, on a scratch database (`brambilla_insights`), covering the three
`/__agente?trace=1` trace tests and the bare-reply test:

```
cd server && DATABASE_URL=postgresql://brambilla:brambilla@127.0.0.1:5433/brambilla_insights \
  pytest -q tests/test_assistant.py tests/test_assistant_evidence.py      # 19 passed
```

Screenshots (mock transport, same v1 envelope the server emits; the shell shows the "Demo
data" badge): `docs/screenshots/assistant-insights/01..09-*.png`. Keyboard navigation between
views was exercised in headless Chromium (ArrowRight moves selection and focus together).

## Performance and security

- Disabled path: 0.8 microseconds per request. Enabled path: about 1.1 ms for a six-call request
  with 20 records each, 13.6 KB serialized; the 32 KiB budget is enforced by re-serializing.
- Evidence is request-local (one `EvidenceTrace` per `handle_conversation`), so the four
  concurrent evaluation conversations cannot mix (tested with a thread pool).
- The UI re-validates every field against an allowlist (`projectEvidence`) and drops anything it
  does not recognise, so a malformed or hostile envelope cannot render arbitrary text.
- Record links go only to `/companies|contacts|deals|tickets/:id`, the pages the SPA owns.

## Integration notes for Agent 5

1. Merge `agent/assistant-insights` after Agent 1's `agent/ui-architect`; the only shared file is
   `frontend/src/api/mock/router.ts` (dev-only fixture, trivial to resolve either way).
2. Agent 1 agreed to rename the switch to "Show evidence" and to mount `<EvidenceInspector
   value={message.evidence} />` as a sibling after the bubble. The component also accepts an
   optional `className`. Nothing else in its interface changed.
3. The Coordinator asked to keep the inspector opt-in; Agent 1 proposed defaulting the switch on.
   Either works for this component; that decision lives in `AssistantChat.tsx`.
4. No environment variable, migration, schema or deployment change is needed.

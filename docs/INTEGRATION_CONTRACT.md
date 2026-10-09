# Integration contract

Owner: Coordinator (`main`). Workers read it with `git show main:docs/INTEGRATION_CONTRACT.md`.
The official files (`BRIEF.md`, `FAQ.md`, `legacy/RICHIESTE.md`) win over anything here.
Business-rule decisions and the data anomalies live in `DECISIONS.md` (same branch): the Core
agent implements the migration from that file, section by section.

## 1. Stack and layout

| Part | Choice | Directory | Owner |
|---|---|---|---|
| Backend + API + assistant | Python 3.12, FastAPI, asyncpg (raw SQL, no ORM), PostgreSQL | `server/` | Core |
| Frontend | Vite + React + TypeScript SPA, built to `frontend/dist` | `frontend/` | UI |
| Deployment | One Railway service built from the root `Dockerfile`; Railway PostgreSQL plugin | root | Coordinator |

Single service, single origin: in production the backend serves `frontend/dist` at `/` with an
SPA fallback for the UI routes listed in section 6. Locally the Vite dev server proxies
`/crm`, `/health`, `/__*`, `/ui` and `/exports` to `http://127.0.0.1:8000`.

### Commands

```
# backend (from repo root)
python -m venv .venv && .venv/bin/pip install -r server/requirements.txt
DATABASE_URL=postgresql://brambilla:brambilla@127.0.0.1:5433/brambilla CRM_TOKEN=dev-token \
  .venv/bin/uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload
# backend tests
.venv/bin/pytest -q server/tests
# frontend
cd frontend && npm ci && npm run dev      # dev server on 5173, proxy to 8000
cd frontend && npm run build              # writes frontend/dist
# acceptance tests against any deploy (coordinator)
BASE_URL=http://127.0.0.1:8000 CRM_TOKEN=dev-token .venv/bin/pytest -q tests/acceptance
```

`server/requirements.txt` pins every package with `==`. `server/main.py` exposes `app`.
Python package layout under `server/` is Core's choice; only `server.main:app` is fixed.

### Environment variables (never commit values)

| Name | Meaning |
|---|---|
| `DATABASE_URL` | PostgreSQL DSN. Railway injects it from the Postgres plugin via a reference variable. |
| `CRM_TOKEN` | The bearer token from the platform's Deploy page. |
| `OPENROUTER_API_KEY` | The model key. Model is always `openai/gpt-6-luna`. |
| `PORT` | Injected by Railway. Bind `0.0.0.0:$PORT`, default 8000. |
| `UI_PASSWORD` | Optional. A second secret accepted only by `POST /ui/login`, so the jury can sign in without the API token. |
| `BASE_URL` | Optional. Public https origin, used to build absolute export links. Relative links are fine per the brief. |

Local Postgres for everyone: `docker run -d --name brambilla-pg -e POSTGRES_PASSWORD=brambilla -e POSTGRES_USER=brambilla -e POSTGRES_DB=brambilla -p 127.0.0.1:5433:5432 postgres:16-alpine`
(it is already running on this machine).

## 2. Authentication

- Every request needs `Authorization: Bearer <CRM_TOKEN>`, except `GET /health`, the export
  download links (`GET /exports/{id}/{file}`), the SPA static files and UI routes, and
  `POST /ui/login`.
- Missing or wrong token: `401` with the HubSpot error envelope, `category: "INVALID_AUTHENTICATION"`.
- UI session: `POST /ui/login` body `{"token": "..."}` accepts `CRM_TOKEN` or `UI_PASSWORD`,
  sets an HttpOnly cookie `crm_session` (opaque, server-side signed value), returns `204`.
  `POST /ui/logout` clears it. `GET /ui/me` returns `200 {"user": "ui"}` or `401`.
  The API middleware accepts either the bearer header or a valid `crm_session` cookie, so the
  SPA calls the very same `/crm/...` endpoints the tests call, with `credentials: "include"`.

## 3. Organizer endpoints (exact contracts in BRIEF.md)

| Endpoint | Behavior |
|---|---|
| `GET /health` | No token. `200 {"status":"ok","version":"2026-09","ui":{...}}`. `ui` keys: `companies`, `contacts`, `deals`, `tickets`, `lists`, `assistant` with the routes of section 6. |
| `POST /__reset` | Token. Truncates all CRM data, reseeds the HubSpot defaults (default properties, `default` deal pipeline, ticket pipeline `0`, association types), zeroes rate-limit counters. `204`. Must stay well under 1 s: TRUNCATE plus a handful of inserts, no DDL. |
| `POST /__migrate` | Token. Body `{"export_url": "..."}`. Downloads the zip (http or https, query string allowed, do not trust the file name), finds the nine CSVs by base name anywhere inside the archive, runs the whole migration, replies `204` only when every record, association, property, pipeline, list and the R8/R9 numbers are readable through the API. One transaction, rollback on failure, `500` with the error envelope on failure. Target under 90 s locally on the sample export (Railway can be 2x slower, limit is 5 min). Use COPY / bulk inserts, never one INSERT per row. |
| `POST /__agente` | Token. Body and reply exactly as BRIEF.md: `{"context":{"now","user"},"messages":[...]}` to `200 {"reply": "<Italian text>"}`. Hard internal deadline 50 s, then reply with what is known. No server-side conversation state. |

## 4. CRM API surface (HubSpot CRM v3/v4 shapes)

Paths are the HubSpot ones, unprefixed. Object type names accepted: `contacts`, `companies`,
`deals`, `tickets`, `products`, `line_items`, `quotes`, `notes`, `calls`, `emails`, `meetings`,
`tasks`, and their numeric ids (`0-1`, `0-2`, `0-3`, `0-5`, `0-7`, `0-8`, `0-14`, `0-46`,
`0-48`, `0-49`, `0-47`, `0-27`).

Objects (`/crm/v3/objects/{objectType}`):
`GET` list (`limit` default 10 max 100, `after` cursor, `properties`, `associations`, `archived`),
`POST` create (`201`), `GET /{id}`, `PATCH /{id}`, `DELETE /{id}` (`204`, archive),
`POST /search` (`filterGroups`, `filters`, `sorts`, `query`, `properties`, `limit` max 200,
`after`; reply `{"total", "results", "paging": {"next": {"after"}}}`),
`POST /batch/read|create|update|upsert|archive` (`{"inputs": [...]}`, reply
`{"status":"COMPLETE","results":[...],"startedAt","completedAt"}`; `archive` replies `204`).
Record shape: `{"id": "123", "properties": {...all values as strings...}, "createdAt",
"updatedAt" (ISO 8601 with milliseconds and Z), "archived": false, "associations"?: {...}}`.
`properties` always includes `hs_object_id`, `createdate`, `lastmodifieddate` (contacts) or
`hs_lastmodifieddate` (other objects). Empty string on write clears a property. Unknown
property on write: `400 VALIDATION_ERROR`. Duplicate contact email or duplicate `partita_iva`
on create: `409`. Numbers are stored as canonical decimal strings, datetimes as ISO 8601 UTC
(input may be ISO or epoch milliseconds), dates as `YYYY-MM-DD`.

Associations v4: `GET /crm/v4/objects/{type}/{id}/associations/{toType}`,
`PUT /crm/v4/objects/{type}/{id}/associations/{toType}/{toId}` body
`[{"associationCategory":"HUBSPOT_DEFINED","associationTypeId":279}]`,
`PUT .../associations/default/{toType}/{toId}`, `DELETE` of the same path,
`POST /crm/v4/associations/{from}/{to}/batch/create|read|archive`,
`GET /crm/v4/associations/{from}/{to}/labels`. Association type ids are HubSpot's
(see `DECISIONS.md` section "Association type ids"). Associations are stored in both
directions; creating one direction makes the inverse readable.

Properties v3: `GET/POST /crm/v3/properties/{objectType}`, `GET/PATCH/DELETE .../{name}`,
`POST .../batch/create|read|archive`, groups under `.../groups`. Shape per HubSpot
(`name, label, type, fieldType, groupName, options, hasUniqueValue, hidden, displayOrder,
createdAt, updatedAt, archived, modificationMetadata`).

Pipelines v3: `GET/POST /crm/v3/pipelines/{objectType}`, `GET/PATCH/DELETE .../{pipelineId}`,
`GET/POST .../{pipelineId}/stages`, `GET/PATCH/DELETE .../stages/{stageId}`. Deal stage
`metadata.probability` as string, ticket stage `metadata.ticketState` `OPEN|CLOSED`, both carry
`metadata.isClosed`.

Lists v3: `POST /crm/v3/lists`, `GET /crm/v3/lists/{listId}`,
`GET /crm/v3/lists/object-type-id/{objectTypeId}/name/{name}`, `POST /crm/v3/lists/search`,
`GET /crm/v3/lists/{listId}/memberships` (`{"results":[{"recordId","membershipTimestamp"}],
"paging","total"}`), `PUT .../memberships/add|remove|add-and-remove`, `DELETE /crm/v3/lists/{listId}`.

Imports and exports v3: `POST /crm/v3/imports` (multipart `importRequest` + `files`),
`GET /crm/v3/imports/{id}`, `POST /crm/v3/exports/export/async` to `{"id"}`,
`GET /crm/v3/exports/export/async/tasks/{id}/status` to `{"status":"COMPLETE","result":"/exports/{id}/file.csv"}`;
the `result` link downloads without a token.

Errors: `{"status":"error","message":"...","correlationId":"<uuid>","category":"..."}` with
`VALIDATION_ERROR` (400), `INVALID_AUTHENTICATION` (401), `OBJECT_NOT_FOUND` (404),
`CONFLICT` (409), `RATE_LIMITS` (429). Rate-limit headers `X-HubSpot-RateLimit-*` are sent on
every authenticated reply; enforcement threshold is generous (env `RATE_LIMIT_PER_10S`,
default 1000) so the organizers' parallel suites never see a 429.

## 5. UI-facing endpoints (implemented by Core, consumed by the SPA)

All under `/ui/api`, token or session cookie, JSON, English-neutral field names. These are
convenience aggregations over the same tables as the CRM API, nothing is computed twice.

| Endpoint | Returns |
|---|---|
| `GET /ui/api/summary` | counts per object type, migration timestamp, dormant count |
| `GET /ui/api/companies?q=&page=&limit=&classe=` | `{items:[{id,name,domain,city,state,partita_iva,fatturato_2025,classe_cliente}],total}` |
| `GET /ui/api/companies/{id}` | company properties plus `contacts[]`, `deals[]` (with pipeline/stage labels), `tickets[]`, `timeline[]` (notes/calls/emails/meetings of its contacts and deals, newest first, max 200) |
| `GET /ui/api/contacts?q=&page=&limit=` | contacts with company name |
| `GET /ui/api/deals/board?pipeline=default` | `{pipeline:{id,label}, stages:[{id,label,probability,isClosed,total_amount,deals:[{id,dealname,amount,deal_currency_code,closedate,commerciale,company:{id,name}}]}]}` |
| `PATCH /ui/api/deals/{id}/stage` | body `{dealstage}`; moves a deal (drag and drop) through the same path as the API so R10/R11 fire |
| `GET /ui/api/tickets?stage=&q=&page=` | tickets with stage label, company, contact |
| `GET /ui/api/dormant` | members of the list `Clienti dormienti` with company fields and last activity date |
| `GET /ui/api/users` | active users from the migration (email, name, role) |
| `POST /ui/api/assistant` | body `{"context":{"now","user"},"messages":[...]}` like `/__agente`; reply `{"reply","trace":[{"step","tool","arguments","result_summary","records":[{"type","id","label"}],"ms"}]}`. Same engine as `/__agente`; `trace` feeds the execution inspector panel. |

Core documents the implemented list in `server/API_FOR_UI.md`; the UI uses one typed client
(`frontend/src/lib/api.ts`) and no production mocks.

## 6. UI routes (SPA) and `/health.ui`

| Module | Route | Page |
|---|---|---|
| companies | `/companies`, `/companies/:id` | list with search; company page with revenue 2025, class, VAT, domains, contacts, deals, tickets, timeline |
| contacts | `/contacts`, `/contacts/:id` | list with search, contact page |
| deals | `/deals`, `/deals/:id` | board by stage, pipeline selector (Sales, Renewals), drag to change stage |
| tickets | `/tickets`, `/tickets/:id` | table by stage, filters |
| lists | `/dormant` | the dormant customers list |
| assistant | `/assistant` | chat, user picker (active users), "now" defaults to the browser clock, execution inspector side panel |

`/health` returns exactly `{"companies":"/companies","contacts":"/contacts","deals":"/deals","tickets":"/tickets","lists":"/dormant","assistant":"/assistant"}` in `ui`. Also `/` redirects to `/companies`.
Interface language is English. The HubSpot name and logo never appear in the UI.

## 7. Assistant engine (Core)

- OpenRouter chat completions, model `openai/gpt-6-luna`, native tool calling, temperature 0,
  at most 8 tool rounds per turn, each tool result truncated to a few KB. Budget is $10 for
  the whole day: keep the system prompt compact, no retries on success paths, no speculative
  calls during development (use the mocked engine in tests).
- Tools read and write through the same service functions as the CRM API, so R7, R10, R11,
  R12 fire exactly as for API calls. Every write tool validates ids exist and belongs to the
  request, and refuses when the target is ambiguous (several matching companies/deals) by
  asking the user, in Italian.
- `context.user` identifies the rep; "my customers" = companies with deals (`commerciale`) or
  tickets (`assegnatario`) followed by that email. `context.now` is the clock for "today".
- Attachments: CSV text with `;` separator, parsed into rows and offered to the model as a
  compact table.
- Reply always in Italian, never claims an action that was not performed.

## 8. Deployment (Coordinator)

Root `Dockerfile` (multi-stage: Node builds `frontend/dist`, Python image runs
`uvicorn server.main:app --host 0.0.0.0 --port $PORT`). `railway.json` sets the Dockerfile
builder and `/health` as the healthcheck. The frontend build failing never breaks the image:
the UI stage falls back to a placeholder page so the API keeps scoring.

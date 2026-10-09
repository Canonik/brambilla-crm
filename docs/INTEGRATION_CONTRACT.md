# Integration contract

Owner: Coordinator (`main`). Workers read it with `git show main:docs/INTEGRATION_CONTRACT.md`.
The official files (`BRIEF.md`, `FAQ.md`, `legacy/RICHIESTE.md`) win over anything here.
Business-rule decisions and the data anomalies live in `DECISIONS.md` (same branch): the Core
agent implements the migration from that file, section by section.

## 1. Stack and layout

| Part | Choice | Directory | Owner |
|---|---|---|---|
| Backend + API + assistant | Python 3.12, FastAPI, psycopg 3 (raw SQL, no ORM), PostgreSQL | `server/` | Core |
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
  download links (`GET /exports/...` as returned in an export's `result`), the SPA static files
  and the UI routes of section 6 (they return HTML, no data).
- Missing or wrong token: `401` with the HubSpot error envelope, `category: "INVALID_AUTHENTICATION"`.
- Browser: the SPA shows a one-time sign-in screen, keeps the token in `localStorage` and sends
  it as `Authorization: Bearer` on every call, so the UI uses the very same endpoints the tests
  call. The token is never baked into the bundle at build time (the repo and the served JS are
  public): no `VITE_CRM_TOKEN` in production builds. No cookie session, no `/ui/login` (decided
  11:25, replaces the earlier cookie scheme).

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

## 5. UI-facing endpoints: none

Decided 11:30: the SPA runs entirely on `/crm/v3`, `/crm/v4`, `/health` and `/__agente`.
Core builds no `/ui/api/*` endpoints and no `/ui/login`. The SPA's typed client is
`frontend/src/api/endpoints.ts`. What the board and lists rely on: exact `total` in search
replies, association filters in search (section 10), `associations` param on GET by id.

Assistant Insights (optional, implemented): `POST /__agente?trace=1` replies with
`{"reply":"...","trace":{"version":1,"events":[...],"incomplete":false}}`. Events contain
only allowlisted tool identifiers, fixed safe input summaries, canonical CRM record references,
duration and observed read/write status. Revenue may include an exact-decimal deterministic
calculation receipt. Raw tool arguments/results, prompts, attachments, credentials and record
properties are never serialized. Without the query parameter the reply remains exactly
`{"reply":"..."}` as the brief requires and the observer is disabled. The SPA requests the
extension only after the user enables **Show reasoning evidence**; evidence is kept out of model
history and browser storage. This is behavioral provenance, not chain-of-thought or model internals.

## 6. UI routes (SPA) and `/health.ui`

| Module (`/health.ui` key) | Route | Page |
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

## 9. Coordinator notes to workers (updated 11:20)

- **Core**: your `server/app` layout is fine. Expose the ASGI app as `server.main:app`
  (a one-line `server/main.py` importing `app.main:app` or similar is enough; keep imports
  relative to the repo root since the Dockerfile copies `server/` into `/app/server/`).
  Default `ui` map must be exactly the section 6 one: `{"companies":"/companies",
  "contacts":"/contacts","deals":"/deals","tickets":"/tickets","lists":"/dormant",
  "assistant":"/assistant"}` (no `products`, the UI has no products page). Never commit
  `server/.venv` (root `.gitignore` already excludes `.venv/`). Serve `frontend/dist` with an
  SPA fallback when the directory exists, otherwise a plain HTML placeholder, for every UI route.
  Acceptance tests you can run against your server: `BASE_URL=http://127.0.0.1:8000
  CRM_TOKEN=dev-token .venv/bin/pytest -q tests/acceptance` from the repo root on `main`
  (`git show main:tests/acceptance/<file>` or merge `main` into `agent/core`).
- **UI**: the dormant customers page lives at `/dormant`. Sign-in screen stores the token in
  `localStorage`, every call carries the bearer header (section 2). Mocks only behind
  `VITE_USE_MOCKS`.
- **Both**: commit on your branch at every working milestone; the coordinator merges `main`
  from the branches, not from worktrees.

## 10. Coordinator notes, 11:25

- Search filters on associations: the UI filters with pseudo-properties
  `associations.contact`, `associations.company`, `associations.deal` and operator `IN`
  (HubSpot search supports them). Core must support these in `POST /crm/v3/objects/{type}/search`.
- `/health.ui` keys stay `companies, contacts, deals, tickets, lists, assistant`; `lists`
  maps to `/dormant`.
- Backend dev port is 8000 (`uvicorn app.main:app --port 8000` from `server/`); set
  `VITE_DEV_PROXY_TARGET=http://127.0.0.1:8000` for the Vite proxy. Production image serves
  `frontend/dist` from `/app/frontend/dist`.

# Frontend handoff

Owner: UI agent, branch `agent/ui`, worktree `~/projects/brambilla-ui`. Everything under `frontend/`.

## Status

| Milestone | Commit | State |
|---|---|---|
| Vite shell, API adapter, all screens, assistant chat | `5ce3208` | done, tests green |
| Visual QA pass and polish | | in progress |
| Wired against the real server | | waiting for `agent/core` to expose a dev server |

## Run, build, test

```sh
cd frontend
npm ci
npm run dev          # http://localhost:5173, proxies API calls to VITE_DEV_PROXY_TARGET (default http://127.0.0.1:8000)
npm run build        # tsc -b && vite build  ->  frontend/dist
npm test             # vitest, 42 tests
npm run typecheck
```

Demo data for development only: `VITE_USE_MOCKS=true npm run dev`. The shell shows a "Demo data" badge whenever it is on. The production build must not set it.

## Serving in production

The backend serves `frontend/dist` as static files with an SPA fallback (every unknown non-API path returns `index.html`). Routes the UI owns:

| Route | Screen |
|---|---|
| `/` | Dashboard |
| `/companies`, `/companies/:id` | Companies list, company page (revenue 2025, class, contacts, deals, tickets, history) |
| `/contacts`, `/contacts/:id` | Contacts |
| `/deals`, `/deals/:id` | Deals board (kanban per pipeline, drag to change stage), deal page |
| `/dormant` | Dormant customers (list `Clienti dormienti`) |
| `/tickets`, `/tickets/:id` | Tickets |
| `/assistant` | Assistant, full page (also available as a side panel on every screen) |

`GET /health` `ui` map, as fixed by the integration contract (the UI does not read it):

```json
{"companies": "/companies", "contacts": "/contacts", "deals": "/deals", "tickets": "/tickets", "lists": "/dormant", "assistant": "/assistant"}
```

## Authentication from the browser

Every call carries `Authorization: Bearer <token>`. The UI shows a one-time sign-in screen and keeps the token in `localStorage`; a `401` clears it and shows the screen again. `GET /health` is called without a token. `VITE_CRM_TOKEN` is honoured only by development builds (`import.meta.env.DEV`) so a production bundle can never carry the token.

## Endpoints the UI calls

All in `frontend/src/api/endpoints.ts`. Shapes follow HubSpot CRM v3.

- `GET /crm/v3/objects/{type}/{id}?properties=a,b&associations=contacts,deals,tickets`
  Types used: `companies`, `contacts`, `deals`, `tickets`, `line_items`, `products`, `notes`, `calls`, `emails`, `meetings`, `tasks`.
  If the response has no `associations`, the UI falls back to `GET /crm/v4/objects/{type}/{id}/associations/{to}` and reads `results[].toObjectId`.
- `POST /crm/v3/objects/{type}/search` with `{ filterGroups, sorts: [{propertyName, direction}], query, properties, limit, after }`. The UI reads `results`, `paging.next.after` and `total`. Operators used: `EQ`, `IN`, `NOT_IN`, `GT`. Filters on `associations.contact`, `associations.deal`, `associations.company`, `associations.ticket` with `IN` are used to load the history (notes, calls, emails, meetings, tasks) of a record and of a company's contacts and deals.
- `POST /crm/v3/objects/{type}/batch/read` with `{ properties, inputs: [{id}] }`, max 100 ids per call.
- `PATCH /crm/v3/objects/deals/{id}` with `{ properties: { dealstage } }` (board drag and deal page).
- `PATCH /crm/v3/objects/tickets/{id}` with `{ properties: { hs_pipeline_stage | hs_ticket_priority | assegnatario } }`.
- `POST /crm/v3/objects/notes` with `{ properties: { hs_timestamp, hs_note_body, autore }, associations: [{ to: {id}, types: [{associationCategory: "HUBSPOT_DEFINED", associationTypeId}] }] }`. Type ids used: contact 202, company 190, deal 214, ticket 228.
- `GET /crm/v3/pipelines/deals`, `GET /crm/v3/pipelines/tickets`: `results[].stages[]` with `id`, `label`, `displayOrder`, `metadata.isClosed`, `metadata.probability`. The sales pipeline must have id `default` with the HubSpot stage ids; the UI translates known Italian labels (Rinnovi, Assistenza and their stages) to English.
- `GET /crm/v3/lists/object-type-id/0-2/name/Clienti%20dormienti` returning `{ list: { listId, name } }`, then `GET /crm/v3/lists/{listId}/memberships?limit=250&after=` returning `{ results: [{recordId}], paging, total }`.
- `GET /health` (no token).
- `POST /__agente` with the brief's body `{ context: { now, user }, messages: [...] }`, reading `reply`. If the response also carries `trace` or `tools` (array of `{tool|name, input|args, output|result, summary}`) the chat shows it as "How this answer was produced". Optional.

Properties requested per object are listed at the top of `endpoints.ts` (`COMPANY_PROPS`, `DEAL_PROPS`, ...). Unknown properties can come back as `null`.

## Known gaps

- Not yet run against the real backend. Expect small fixes in `endpoints.ts` once `server/API_FOR_UI.md` exists.
- Board columns load 40 deals per stage and show "Load more"; stage totals come from `total` in the search response.
- The company history relies on `associations.*` search filters. If the backend does not support them, the fallback is to call the v4 association endpoints per record; say so and I will switch.
- No create forms for companies, contacts or deals: the assistant is the write path the brief scores, and the jury screens are read-plus-stage-changes. Can be added if time allows.

# Frontend audit — Agent 6

Snapshot: 2026-10-09, approximately 11:06 Europe/Rome. Coordinator main `300ea57`;
UI branch `agent/ui` HEAD `1013ba7`, with uncommitted implementation inspected read-only.
Source snapshot copied to `/tmp/brambilla-frontend-qa/snapshot` before running commands.
This is an interim audit of work in progress, not a production readiness certification.

## Immediate handoff to Agents 1 and 3

Production integration is **unverified**, not proven broken: no production URL was provided
or present in deployment documentation. No backend is reachable at localhost:8000
(connection refused with network permission); localhost:5173 also refuses connections;
localhost:3000 times out. Main has neither frontend nor server implementation.
Agent 1 must integrate working milestones and provide the deployment URL for a live audit.
No direct agent messaging channel is available in this session; this file is the shared handoff.
No source fix is approved, and no Agent 3 file was edited. No merge, push or deployment performed.

Read: BRIEF.md, FAQ.md, legacy/RICHIESTE.md, AGENTS.md, docs/INTEGRATION_CONTRACT.md.
No frontend/HANDOFF.md or server/API_FOR_UI.md existed at inspection time.

## Build and test evidence

On the isolated copy of Agent 3's frontend, using its installed dependencies:

- `npm run build`: FAIL. TS5102: `baseUrl` removed; TS5090: non-relative paths
  in tsconfig.app.json (lines 9 and 10). Build stops before Vite.
- `npm test`: 41 passed, 1 failed across 4 files. Failure:
  `src/api/endpoints.test.ts:74`, `adds a note to a company`, expected the created
  `Chiamare lunedì` note in activitiesFor results. These tests use mocks and prove
  no live backend behavior.
- `python tests/frontend-qa/readiness.py --frontend /tmp/brambilla-frontend-qa/snapshot`:
  FAIL, missing src/main.tsx. index.html references that exact entry point.
- Browser screenshots: unavailable; snapshot contains no application entry point or screens.

## Route matrix

| Route | Implementation evidence | Working/broken status |
|---|---|---|
| /companies | Search adapter requests fatturato_2025 and classe_cliente | Blocked: no renderable screen or live response |
| /companies/:id | Adapter fetches company and batches related contacts/deals/tickets | Blocked; relationship error suppression risk below |
| /contacts and /contacts/:id | Search/detail adapters present | Blocked: no renderable screen or live response |
| /deals and /deals/:id | Real pipeline endpoint, stage filter, PATCH dealstage adapter | Blocked; transition and resulting tickets/tasks not exercised |
| /dormant | Named Clienti dormienti lookup and memberships adapter | Blocked; membership accuracy/navigation not exercised |
| /tickets and /tickets/:id | Search/detail/update adapters present | Blocked; linked records and filters not exercised |
| /assistant | POST /__agente adapter present | Blocked; Italian replies, full history, loading/error UX untested |
| All routes | index.html lang=en; no screen components in snapshot | Responsive layout, keyboard use, visible branding and empty states untested |

No workflow is marked passing from mock tests or source inspection alone.

## Five highest-value fixes (Agent 3 approval required)

1. **P0, low risk: unblock compilation and finish the entry point.** Exact files:
   frontend/tsconfig.app.json and frontend/src/main.tsx (missing at snapshot).
   Correct the removed TS configuration and relative aliases using installed compiler diagnostics;
   finish the existing app. Reproduce with npm run build. Agent 1 should check the production
   image contains the app, since Dockerfile masks a build failure with a placeholder.
2. **P1, low risk: align local proxy.** frontend/vite.config.ts defaults to localhost:3000;
   contract uses 127.0.0.1:8000. /ui and /exports are missing from proxy prefixes.
   Start the documented backend on 8000 and load /companies through Vite; observe requests.
   Add the documented prefixes if using session/convenience endpoints.
3. **P1, medium risk: propagate failed relationship/history requests and honor pagination.**
   frontend/src/api/endpoints.ts: associatedIds and activitiesFor catch all failures and
   return empty arrays; associations ignore paging; activities truncate each target type
   to 100 IDs. Reproduce by forcing the association/activity request to return 500 in
   browser devtools: the screen must show a recoverable error, not “no records.” Verify
   with a company containing more than 100 associated contacts and paged associations.
   Existing note test failure needs investigation; its cause is not established here.
4. **P1, medium risk: load active users from migrated data.** frontend/src/api/users.ts
   hardcodes 32 users and DEFAULT_USER. Read /ui/api/users through the existing client,
   once Core confirms implementation. Re-migrate a different export; picker must contain
   current active users, and request context.user must match the selected user.
5. **P1, medium risk: align authentication and production-data policy.**
   frontend/src/auth/token.ts supports embedding VITE_CRM_TOKEN and localStorage;
   contract specifies /ui/login and HttpOnly session. frontend/src/api/transport.ts
   permits VITE_USE_MOCKS=true in production. Coordinate session changes across
   token.ts, client.ts and transport.ts; prohibit production mock mode and avoid
   embedding a credential in the shipped JS. Current default is real requests;
   no automatic mock fallback was observed. Same-origin fetch already sends cookies
   by default, so missing explicit credentials is not itself a same-origin failure.

## Reproducible browser acceptance pass when deployed

Use an already migrated QA environment; never reset the shared production service.
Record deployed commit, URL and selected real record IDs with each result.

1. Open each route directly in a new tab, authenticate, reload and navigate back/forward.
   Confirm JS/CSS load, real API responses, no placeholder/demo badge or visible HubSpot branding.
2. Companies: select a real company; compare visible revenue/class against its CRM API
   properties (including zero/negative revenue with blank class). Follow contacts, deals,
   tickets and timeline. Search an actual name and then a nonexistent string; clear search.
3. Deals: confirm both sales and renewal stages match GET /crm/v3/pipelines/deals.
   Move a designated disposable QA deal by keyboard and pointer; verify persisted stage
   after reload. A won/lost move has business side effects: use only agreed QA records;
   verify resulting ticket/task and do not assume moving back removes those records.
4. Dormant: compare displayed IDs to all pages of Clienti dormienti memberships;
   verify company links and that pagination does not omit or duplicate records.
5. Tickets: compare subject, stage, priority, assignee and associated company/contact
   against API; check filters and navigation. Verify failed reads offer retry.
6. Assistant: select an active migrated user. Send one read-only Italian request about
   a selected company's 2025 revenue. Confirm pending state, a nonempty Italian reply,
   correct figures, context.now/user and full conversation on the next turn. Check
   request failure/offline recovery separately without burning model calls.
7. Repeat at 390px and desktop widths; tab through navigation, filters, dialogs and chat;
   check visible focus, control names, readable errors, no clipped controls and sensible
   loading/empty states. This checklist is pending, not completed evidence.

## Ownership and handoff

Owned paths: tests/frontend-qa/ and this report only. A small standard-library readiness
probe is included; it makes only public GETs and is not a competing API adapter.
Agent 1 can locate this isolated QA commit with:
`git log -1 --format='%h %s' -- docs/reviews/frontend-audit.md`.
Live browser and data checks remain blocked until a renderable app and backend URL exist.

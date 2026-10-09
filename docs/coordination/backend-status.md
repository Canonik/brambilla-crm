# Backend status (Agent 3, backend reliability)

Branch `agent/backend-reliability`, worktree `/tmp/brambilla-backend`. Updated by Agent 3 only.
Local server for evidence: port 8030, database `brambilla_agent3` (nobody else uses it).

## 13:15

All on `agent/backend-reliability`, full backend suite 202 passed (`cd server && DATABASE_URL=...scratch_db CRM_TOKEN=test-token python -m pytest -q tests`).
Acceptance on my migrated server (port 8030): form_check + api_conformity + migration + rules 56 passed.

| Commit | What | Regression test |
|---|---|---|
| 2a9e099 (in main 6257d93) | 141 5xx from malformed bodies and ids now 400/404 | test_malformed_input.py |
| f7d5273 (in main) | every 2026-09 dated URL family | test_dated_routes.py |
| c9b5dcc | rate limit default 50000 per 10 s (20 readers got 429 on 88 percent of reads) | test_rate_limit.py |
| 1bceac5 | exports: 202, filterGroups, sorts, query, status timestamps | test_exports_conformity.py |
| e4776bc | NaN/Infinity 400, HALF_UP money, default quantity amount | test_numbers.py |
| dd1d118 | hasUniqueValue enforced for custom properties (partial unique index) | test_unique_properties.py |
| ce68ed1 | closedate stamped on entering a closed stage; create into closed was never persisted | test_deal_close_date.py |
| next | recordsIdsAdded, mappedObjectTypeIds, import robustness | test_lists_imports_shape.py |

Next: concurrency on one record and upserts, search and pagination on the migrated volume, 20-reader latency with the new limit, restart end to end.

## 13:30 durability evidence (migrated sample, production image `docker build .` of this branch)

| Check | Result |
|---|---|
| 20 parallel readers, 20 s, single-record reads with associations | 21,664 reads, all 200, p50 18 ms, p95 25 ms, max 112 ms |
| Walk every record by GET list (limit 100) | contacts 63,716 / companies 17,392 / deals 33,580, each exactly once, slowest page 119 ms |
| Walk every record by search (limit 200, sorted by id) | same counts and totals, each exactly once, slowest page 123 ms |
| 60 parallel PATCH of one company, 10 different properties | all 200, no property lost |
| 40 parallel creates of one email | one 201, 39 409, one record |
| 48 parallel batch upserts of one email, 8 different fields | all 200, one record, no field lost |
| 200 parallel creates of distinct contacts | 200 x 201, all found by search |
| 20 parallel moves of one deal to closedwon | all 200, exactly one R10 ticket |
| Restart of the production container | counts, 19 custom properties, pipelines, labels, lists, memberships, users, index count and metadata hashes identical; SPA, id_legacy, partita_iva, Assistenza, dormant list, 2026-09 reads all 200 |
| /__reset on 800,000 migrated rows, then empty | 0.30 s, 0.21 s, 0.21 s (limit 1 s) |
| Acceptance form_check + conformity + migration + rules on my server | 56 passed |

Committed: 043583d (test_concurrency.py). Full backend suite 206 passed.

## 13:30 conformity sweep (stopped on request)

Reference-page sweep on the dated URLs: 152 calls across contacts, companies, deals, tickets, products, line items, quotes, notes/calls/emails/meetings/tasks, pipelines, properties, associations, lists, owners, 401 envelopes. Fixes: be02ef7 (association batch codes, label create, export by id, import cancel, list endpoints) and the commit after it (property create required fields and 409, query cap, 207 trace ids). Server suite 234 passed.
Not enforced on purpose: the documented 10,000-result search cap and batch size limits, because the durability check pages the whole migrated volume.
